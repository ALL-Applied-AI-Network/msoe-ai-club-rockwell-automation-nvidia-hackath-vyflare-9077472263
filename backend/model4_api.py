"""Multipart API for one registered vial, without recipe learning or release."""
import json
import re
import time
import warnings
from io import BytesIO

from flask import Blueprint, abort, current_app, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError

from model4 import CAMERA_PROFILE


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("JSON numbers must be finite")
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        raise ValueError("Invalid JSON object or event list") from None


def decode(upload):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(upload.read())) as source:
                if source.format not in {"JPEG", "PNG"}:
                    abort(415, description="Only JPEG and PNG images are supported")
                if source.width * source.height > 16_000_000:
                    abort(413, description="Image exceeds 16 million pixels")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        abort(413, description="Image exceeds pixel limit")
    except (UnidentifiedImageError, OSError, ValueError):
        abort(400, description="Invalid or corrupt image")
    if image.size != (640, 480):
        abort(422, description="Model 4 requires registered 640x480 frames; images are not resized")
    return image


def create_model4_blueprint(model, gate):
    bp = Blueprint("model4_api", __name__)

    def require_model():
        if model is None:
            abort(503, description="Model 4 is disabled; enable model4 in ENABLED_MODELS")

    @bp.get("/model4")
    def metadata():
        require_model()
        return jsonify(model.describe())

    @bp.get("/model4/recipes")
    def recipes():
        require_model()
        return jsonify(source="recipes.xlsx/Recipe_Bank snapshot", basis="recipe_settings_not_measured_delivery",
                       recipes=[model.expected_recipe(recipe_id=int(key)) for key in sorted(model.catalog["recipes"], key=int)])

    @bp.post("/predict/model4")
    def predict_vial():
        require_model()
        if request.mimetype != "multipart/form-data":
            abort(415, description="Use multipart/form-data")
        allowed = {"frame_id", "vial_id", "batch_id", "batch_position", "camera_profile", "recipe_id", "expected_ml", "events"}
        if set(request.form) - allowed or any(len(request.form.getlist(k)) != 1 for k in request.form):
            abort(400, description="Unknown or duplicate request fields")
        identity = {}
        for key in ("frame_id", "vial_id", "batch_id"):
            value = request.form.get(key, "").strip()
            if not value or len(value) > 128:
                abort(400, description=f"{key} is required and must contain 1–128 characters")
            identity[key] = value
        position = request.form.get("batch_position", "")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", position):
            abort(400, description="batch_position must be a positive integer")
        if request.form.get("camera_profile") != CAMERA_PROFILE:
            abort(422, description=f"camera_profile must be {CAMERA_PROFILE}; registered camera geometry is required")
        rid = request.form.get("recipe_id", "").strip()
        amounts = request.form.get("expected_ml", "").strip()
        if bool(rid) == bool(amounts):
            abort(400, description="Supply exactly one of recipe_id or expected_ml")
        try:
            if rid and not re.fullmatch(r"[1-9][0-9]{0,8}", rid):
                raise ValueError("recipe_id must be a positive integer")
            expected = model.expected_recipe(recipe_id=int(rid) if rid else None,
                                             expected_ml=strict_json(amounts) if amounts else None)
            events_spec = strict_json(request.form["events"]) if "events" in request.form else None
            if "events" in request.form:
                if not isinstance(events_spec, list) or not 1 <= len(events_spec) <= 3:
                    raise ValueError("events must be an ordered list of 1–3 observed pours")
                for index, event in enumerate(events_spec, 1):
                    if not isinstance(event, dict) or set(event) - {"event_number", "duration_s", "before_missing"}:
                        raise ValueError("Event fields are event_number, duration_s and optional before_missing")
                    if (type(event.get("event_number")) is not int or event["event_number"] != index
                            or "duration_s" not in event or type(event.get("before_missing", False)) is not bool):
                        raise ValueError("Events must be consecutive chronological numbers with observed duration_s or null")
        except (ValueError, TypeError) as exc:
            abort(400, description=str(exc))
        uploads = request.files.getlist("images")
        if len(uploads) != 3:
            abort(400, description="Exactly three post-fill files named images are required")
        expected_files = {"images"}
        if events_spec is not None:
            for index, spec in enumerate(events_spec, 1):
                expected_files.add(f"event_{index}_during")
                if not spec.get("before_missing", False):
                    expected_files.add(f"event_{index}_before")
        if set(request.files) != expected_files or any(len(request.files.getlist(k)) != 1 for k in expected_files - {"images"}):
            abort(400, description="Supply exactly the before/during files described by events, with no unused uploads")
        if not gate.acquire(blocking=False):
            response = jsonify(error="Inference busy; retry this vial", frame_id=identity["frame_id"])
            response.headers["Retry-After"] = "1"
            return response, 429
        try:
            images = [decode(upload) for upload in uploads]
            events = None
            if events_spec is not None:
                events = [{"duration_s": spec["duration_s"],
                           "before": None if spec.get("before_missing", False) else decode(request.files[f"event_{i}_before"]),
                           "during": decode(request.files[f"event_{i}_during"])} for i, spec in enumerate(events_spec, 1)]
            started = time.perf_counter()
            result = model.predict_vial(images, expected=expected, batch_position=int(position), events=events)
            return jsonify(**identity, batch_position=int(position), model="model4", mode="mock" if model.mock else "real",
                           result=result, inference_ms=round((time.perf_counter() - started) * 1000, 1))
        except (ValueError, TypeError) as exc:
            abort(422, description=str(exc))
        except Exception as exc:
            # HTTP upload errors retain their JSON status; runtime errors withhold estimates.
            from werkzeug.exceptions import HTTPException
            if isinstance(exc, HTTPException):
                raise
            current_app.logger.exception("Model 4 inference failed")
            return jsonify(error="Model 4 inference failed; see backend log", frame_id=identity["frame_id"]), 500
        finally:
            gate.release()

    return bp
