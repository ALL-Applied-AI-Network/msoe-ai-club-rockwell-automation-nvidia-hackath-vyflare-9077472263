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
from recipes.geometry_api import GeometryService, create_geometry_blueprint
from recipes.tracker_api import create_tracker_blueprint
from recipes.tracker_manager import TrackerManager
from model4_api import create_model4_blueprint
from model2_api import create_model2_blueprint
from recipes.durable import SQLiteStore
from recipes.workflow_api import create_workflow_blueprint, load_reference_catalog
from recipes.reviewed_trial import ReviewedTrialEngine
from recipes.demo_api import RecordedDemoService, create_demo_blueprint
from recipes.demo_store import validate_demo_location
from recipes.recorded_producer import RecordedVideoProducer

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
        MODEL4_MAX_CONTENT_LENGTH=12 * 1024 * 1024,
        RECIPE_MANAGEMENT_ACTOR=os.getenv("RECIPE_MANAGEMENT_ACTOR", ""),
        TRACKER_SCHEDULER_ENABLED=None,
        RECIPE_DB_PATH=None,
        RECIPE_DEMO_ENABLED=os.getenv("RECIPE_DEMO_ENABLED", "false").strip().lower() == "true",
        RECIPE_DEMO_DB_PATH=os.getenv("RECIPE_DEMO_DB_PATH", ""),
        CORS_ORIGINS=[x.strip() for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if x.strip()],
    )
    if config:
        app.config.update(config)
    normal_db_path = app.config["RECIPE_DB_PATH"] or os.getenv("RECIPE_DB_PATH") or str(Path(__file__).with_name(".data") / "recipes.sqlite3")
    normal_paths = [normal_db_path, Path(__file__).with_name(".data") / "recipes.sqlite3"]
    if type(app.config["RECIPE_DEMO_ENABLED"]) is not bool:
        raise ValueError("RECIPE_DEMO_ENABLED must be a boolean application setting")
    if app.config["RECIPE_DEMO_ENABLED"]:
        validate_demo_location(app.config["RECIPE_DEMO_DB_PATH"], normal_paths)
    CORS(app, origins=app.config["CORS_ORIGINS"], methods=["GET", "POST", "OPTIONS"],
         allow_headers=["Content-Type", "Authorization"], supports_credentials=False)
    registry = model_registry if model_registry is not None else load_models(app.config["MODEL_MODE"])
    gate = threading.Lock()  # One inference total, including across both GPU models.
    app.extensions["inference_gate"] = gate
    app.register_blueprint(create_model4_blueprint(registry.get("model4"), gate))
    app.register_blueprint(create_model2_blueprint(registry.get("model2"), registry.get("model4"), gate))
    catalog, catalog_sha = load_reference_catalog()
    store = None
    if recipe_repository is None and inspection_repository is None and (not app.testing or app.config["RECIPE_DB_PATH"]):
        db_path = normal_db_path
        store = SQLiteStore(db_path)
        store.recipes.minimum_new_recipe_id = max(int(k) for k in catalog["recipes"]) + 1
    app.extensions["recipe_store"] = store
    repository = recipe_repository if recipe_repository is not None else store.recipes if store else RecipeRepository()
    if not isinstance(repository, RecipeRepository):
        raise TypeError("recipe_repository must be a RecipeRepository")
    app.extensions["recipe_repository"] = repository
    app.register_blueprint(create_recipe_blueprint(repository))
    inspections = inspection_repository if inspection_repository is not None else store.inspections if store else InspectionRepository()
    if not isinstance(inspections, InspectionRepository):
        raise TypeError("inspection_repository must be an InspectionRepository")
    app.extensions["inspection_repository"] = inspections
    app.extensions["vial_inspection_service"] = VialInspectionService(repository, inspections,
        required_reference_ids={int(k) for k in catalog["recipes"]} if store or not app.testing else None)
    app.register_blueprint(create_inspection_blueprint(repository, inspections))
    trial_engine = ReviewedTrialEngine(catalog, catalog_sha)
    app.extensions["recipe_trial_engine"] = trial_engine
    app.register_blueprint(create_workflow_blueprint(app.extensions["vial_inspection_service"], store, catalog, catalog_sha, trial_engine))
    demo_service = None
    if app.config["RECIPE_DEMO_ENABLED"]:
        try:
            demo_service = RecordedDemoService(catalog_sha, trial_engine, app.config["RECIPE_DEMO_DB_PATH"], normal_paths,
                **({"assets": app.config["RECIPE_DEMO_ASSETS"]} if app.config.get("RECIPE_DEMO_ASSETS") else {}))
        except Exception:
            if store:
                store.close()
            raise
    app.extensions["recipe_demo_service"] = demo_service
    geometry = GeometryService(app.config.get("RECORDED_VIDEO_ROOT", Path(__file__).resolve().parents[1] / "cosmos-original-dataset" / "videos"),
        app.config.get("GEOMETRY_CACHE_ROOT", Path(__file__).resolve().parent / ".data" / "geometry"), demo_service.bank if demo_service else None)
    app.extensions["geometry_service"] = geometry
    app.register_blueprint(create_geometry_blueprint(geometry))
    producer = RecordedVideoProducer(demo_service.bank,
        app.config.get('RECORDED_VIDEO_ROOT', Path(__file__).resolve().parents[1] / 'cosmos-original-dataset' / 'videos'),
        geometry_service=geometry, upload_root=app.config.get("RECORDING_UPLOAD_ROOT") or os.getenv("RECORDING_UPLOAD_ROOT") or Path(app.config["RECIPE_DEMO_DB_PATH"]).expanduser().resolve().parent / "recordings") if demo_service else None
    if producer:geometry.source_resolver=producer.source
    app.extensions['recorded_video_producer'] = producer
    app.register_blueprint(create_demo_blueprint(demo_service, producer))
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
        if request.path == "/api/recipe-workflow/demo/producer/recordings":
            request.max_content_length = 128 * 1024 * 1024
        if request.path in ("/predict/model4", "/predict/model2", "/predict/vial-evidence"):
            request.max_content_length = app.config["MODEL4_MAX_CONTENT_LENGTH"]
            request.max_form_parts = 24
        token = os.getenv("INFERENCE_TOKEN", "")
        protected = request.path == "/predict" or request.blueprint in ("recipe_api", "inspection_api", "tracker_api", "model4_api", "model2_api", "recipe_workflow_api", "recipe_demo_api", "geometry_api")
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

    @app.after_request
    def recipe_storage_header(response):
        if request.blueprint == "recipe_demo_api":
            response.headers["X-Recipe-Storage"] = "isolated_demo_sqlite" if demo_service else "disabled"
        if request.blueprint in ("recipe_api", "inspection_api", "recipe_workflow_api"):
            response.headers["X-Recipe-Storage"] = store.persistence if store else "in_memory"
        return response

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
        if name == "model4":
            return error("Use POST /predict/model4 with three registered post-fill frames", 400)
        if name == "model2":
            return error("Use POST /predict/model2 with three early post-flow frames and an intended recipe", 400)
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
              max_request_body_size=12 * 1024 * 1024)
    finally:
        if application.extensions["recipe_demo_service"]:
            application.extensions['recorded_video_producer'].close()
        application.extensions["geometry_service"].close()
        if application.extensions["recipe_demo_service"]:
            application.extensions["recipe_demo_service"].bank.close()
        application.extensions["tracker_manager"].shutdown()
        if application.extensions["recipe_store"]:
            application.extensions["recipe_store"].close()
