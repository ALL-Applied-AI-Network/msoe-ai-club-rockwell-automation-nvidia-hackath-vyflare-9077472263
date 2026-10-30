import os
import threading
import time
import warnings
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from models import RemoteInferenceError, SafetyBlocked, load_models
from recipes.api import create_recipe_blueprint
from recipes.recipe_repository import RecipeRepository
from recipes.inspection_api import create_inspection_blueprint
from recipes.inspection_repository import InspectionRepository
from recipes.vial_inspection_service import VialInspectionService
from recipes.tracker_api import create_tracker_blueprint
from recipes.tracker_manager import TrackerManager

MAX_IMAGE_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def create_app(model_registry=None, config=None, *, recipe_repository=None, inspection_repository=None,
               tracker_clock=time.monotonic):
    load_dotenv(Path(__file__).with_name(".env"))
    os.environ.setdefault("TORCH_HOME", str(Path(__file__).with_name(".model-cache")))
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        MODEL_MODE=os.getenv("MODEL_MODE", "real"),
        RECIPE_MANAGEMENT_ACTOR=os.getenv("RECIPE_MANAGEMENT_ACTOR", ""),
        TRACKER_SCHEDULER_ENABLED=None,
        CORS_ORIGINS=[x.strip() for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if x.strip()],
    )
    if config:
        app.config.update(config)
    CORS(app, origins=app.config["CORS_ORIGINS"], methods=["GET", "POST", "OPTIONS"],
         allow_headers=["Content-Type", "Authorization"], supports_credentials=False)
    registry = model_registry if model_registry is not None else load_models(app.config["MODEL_MODE"])
    gate = threading.Lock()  # One inference total, including across both GPU models.
    app.extensions["inference_gate"] = gate
    repository = recipe_repository if recipe_repository is not None else RecipeRepository()
    if not isinstance(repository, RecipeRepository):
        raise TypeError("recipe_repository must be a RecipeRepository")
    app.extensions["recipe_repository"] = repository
    app.register_blueprint(create_recipe_blueprint(repository))
    inspections = inspection_repository if inspection_repository is not None else InspectionRepository()
    if not isinstance(inspections, InspectionRepository):
        raise TypeError("inspection_repository must be an InspectionRepository")
    app.extensions["inspection_repository"] = inspections
    app.extensions["vial_inspection_service"] = VialInspectionService(repository, inspections)
    app.register_blueprint(create_inspection_blueprint(repository, inspections))
    scheduler_enabled = app.config["TRACKER_SCHEDULER_ENABLED"]
    if scheduler_enabled is None:
        scheduler_enabled = not app.testing
    trackers = TrackerManager(app.extensions["vial_inspection_service"],
                              scheduler_enabled=scheduler_enabled, clock=tracker_clock)
    app.extensions["tracker_manager"] = trackers
    app.register_blueprint(create_tracker_blueprint(trackers))

    def error(message, code):
        return jsonify(error=message, frame_id=request.form.get("frame_id")), code

    @app.before_request
    def check_origin():
        token = os.getenv("INFERENCE_TOKEN", "")
        protected = request.path == "/predict" or request.blueprint in ("recipe_api", "inspection_api", "tracker_api")
        if token and protected and request.method != "OPTIONS":
            import hmac
            if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
                return jsonify(error="Inference credentials required"), 401
        # CORS alone does not prevent a foreign page from submitting a POST.
        origin = request.headers.get("Origin")
        if origin is not None and origin not in app.config["CORS_ORIGINS"]:
            return jsonify(error="Origin is not allowed"), 403

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.get("/health")
    def health():
        return jsonify(status="ready", mode=app.config["MODEL_MODE"], models=list(registry),
                       busy=gate.locked())

    @app.post("/predict")
    def predict():
        frame_id = request.form.get("frame_id", "").strip()
        name = request.form.get("model", "measurements")
        include_resnet = request.form.get("include_resnet", "false")
        prompt = request.form.get("prompt", "Describe the visible scene briefly.").strip()
        if not frame_id or len(frame_id) > 128:
            return error("frame_id is required and must be at most 128 characters", 400)
        if name not in registry:
            return error("Unknown or disabled model", 400)
        if include_resnet not in {"true", "false"}:
            return error("include_resnet must be true or false", 400)
        paired = include_resnet == "true" and name != "resnet18"
        if paired and "resnet18" not in registry:
            return error("ResNet-18 is required for paired inference but is disabled", 400)
        if not prompt or len(prompt) > 2000:
            return error("prompt must contain 1–2000 characters", 400)
        upload = request.files.get("image")
        if upload is None:
            return error("image file is required", 400)
        if not gate.acquire(blocking=False):
            response, code = error("Inference busy; skip this frame", 429)
            response.headers["Retry-After"] = "1"
            return response, code
        try:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(upload.read())) as source:
                        if source.format not in {"JPEG", "PNG"}:
                            return error("Only JPEG and PNG images are supported", 415)
                        # Framework imports can change Pillow's global limit to None.
                        if source.width * source.height > MAX_IMAGE_PIXELS:
                            return error("Image exceeds 16 million pixels", 413)
                        source.load()
                        image = ImageOps.exif_transpose(source).convert("RGB")
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                return error("Image exceeds pixel limit", 413)
            except (UnidentifiedImageError, OSError, ValueError):
                return error("Invalid or corrupt image", 400)
            # Bound the visual workload; the ResNet adapter applies its own final transform.
            if name not in {"measurements", "resnet18"}:
                image.thumbnail((1280, 1280))
            started = time.perf_counter()
            result = registry[name].predict(image, prompt)
            if paired:
                # Sequential execution under the same gate bounds GPU workload.
                # Cosmos runs first so rejected input does not return partial results.
                results = {name: result, "resnet18": registry["resnet18"].predict(image, prompt)}
                return jsonify(frame_id=frame_id, model=name, mode=app.config["MODEL_MODE"],
                               result=result, results=results,
                               inference_ms=round((time.perf_counter()-started)*1000, 1))
            return jsonify(frame_id=frame_id, model=name, mode=app.config["MODEL_MODE"],
                           result=result, inference_ms=round((time.perf_counter()-started)*1000, 1))
        except SafetyBlocked as exc:
            return error(str(exc), 422)
        except (ValueError, TypeError) as exc:
            return error(str(exc), 422)
        except RemoteInferenceError as exc:
            response, code = error(str(exc), exc.status)
            if code == 429:
                response.headers["Retry-After"] = "1"
            return response, code
        except Exception:
            app.logger.exception("Inference failed for %s", name)
            return error("Model inference failed; see backend log", 500)
        finally:
            gate.release()

    return app


if __name__ == "__main__":
    from waitress import serve
    application = create_app()
    port = int(os.getenv("PORT", "8000"))
    print(f"API: http://127.0.0.1:{port} | mode={application.config['MODEL_MODE']}", flush=True)
    # One process: no reloader or multiple workers duplicating model weights.
    try:
        serve(application, host=os.getenv("HOST", "127.0.0.1"), port=port, threads=4,
              max_request_body_size=5 * 1024 * 1024)
    finally:
        application.extensions["tracker_manager"].shutdown()
