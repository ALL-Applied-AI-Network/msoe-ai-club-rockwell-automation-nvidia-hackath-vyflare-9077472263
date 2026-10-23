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

from models import SafetyBlocked, load_models

Image.MAX_IMAGE_PIXELS = 16_000_000


def create_app(model_registry=None, config=None):
    load_dotenv(Path(__file__).with_name(".env"))
    os.environ.setdefault("TORCH_HOME", str(Path(__file__).with_name(".model-cache")))
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        MODEL_MODE=os.getenv("MODEL_MODE", "mock"),
        CORS_ORIGINS=[x.strip() for x in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",") if x.strip()],
    )
    if config:
        app.config.update(config)
    CORS(app, origins=app.config["CORS_ORIGINS"], methods=["GET", "POST", "OPTIONS"],
         allow_headers=["Content-Type"], supports_credentials=False)
    registry = model_registry if model_registry is not None else load_models(app.config["MODEL_MODE"])
    gate = threading.Lock()  # One inference total, including across both GPU models.
    app.extensions["inference_gate"] = gate

    def error(message, code):
        return jsonify(error=message, frame_id=request.form.get("frame_id")), code

    @app.before_request
    def check_origin():
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
        name = request.form.get("model", "resnet18")
        prompt = request.form.get("prompt", "Describe the visible scene briefly.").strip()
        if not frame_id or len(frame_id) > 128:
            return error("frame_id is required and must be at most 128 characters", 400)
        if name not in registry:
            return error("Unknown or disabled model", 400)
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
                        if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                            return error("Image exceeds 16 million pixels", 413)
                        source.load()
                        image = ImageOps.exif_transpose(source).convert("RGB")
            except (Image.DecompressionBombError, Image.DecompressionBombWarning):
                return error("Image exceeds pixel limit", 413)
            except (UnidentifiedImageError, OSError, ValueError):
                return error("Invalid or corrupt image", 400)
            # Bound the visual workload; the ResNet adapter applies its own final transform.
            image.thumbnail((1280, 1280))
            started = time.perf_counter()
            result = registry[name].predict(image, prompt)
            return jsonify(frame_id=frame_id, model=name, mode=app.config["MODEL_MODE"],
                           result=result, inference_ms=round((time.perf_counter()-started)*1000, 1))
        except SafetyBlocked as exc:
            return error(str(exc), 422)
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
    serve(application, host="127.0.0.1", port=port, threads=4,
          max_request_body_size=5 * 1024 * 1024)
