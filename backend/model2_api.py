"""Multipart API for Model 2 and for Model 2 + Model 4 evidence on the same vial."""
import re
import time
import warnings
from io import BytesIO

from flask import Blueprint, abort, current_app, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException

from model2 import CAMERA_PROFILE

FIELDS = {"frame_id", "vial_id", "batch_id", "batch_position", "camera_profile", "recipe_id"}


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
        abort(422, description="Registered 640x480 station frames are required; images are not resized")
    return image


def parse_request():
    """Identity, intended recipe and three early post-flow frames, validated like Model 4."""
    if request.mimetype != "multipart/form-data":
        abort(415, description="Use multipart/form-data")
    if set(request.form) - FIELDS or any(len(request.form.getlist(k)) != 1 for k in request.form):
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
    if not re.fullmatch(r"[1-9][0-9]{0,8}", rid):
        abort(400, description="recipe_id (the intended recipe from the machine or operator) must be a positive integer")
    if set(request.files) != {"images"} or len(request.files.getlist("images")) != 3:
        abort(400, description="Exactly three early post-flow files named images are required")
    return identity, int(position), int(rid), request.files.getlist("images")


def create_model2_blueprint(model, model4, gate):
    bp = Blueprint("model2_api", __name__)

    def require(*models):
        if any(m is None for m in models):
            abort(503, description="Required model is disabled; enable model2 (and model4 for vial evidence) in ENABLED_MODELS")

    def run(identity, work):
        if not gate.acquire(blocking=False):
            response = jsonify(error="Inference busy; retry this vial", frame_id=identity["frame_id"])
            response.headers["Retry-After"] = "1"
            return response, 429
        try:
            return work()
        except (ValueError, TypeError) as exc:
            abort(422, description=str(exc))
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            current_app.logger.exception("Model 2 inference failed")
            return jsonify(error="Inference failed; see backend log", frame_id=identity["frame_id"]), 500
        finally:
            gate.release()

    @bp.get("/model2")
    def metadata():
        require(model)
        return jsonify(model.describe())

    @bp.post("/predict/model2")
    def predict_vial():
        require(model)
        identity, position, rid, uploads = parse_request()

        def work():
            images = [decode(u) for u in uploads]
            started = time.perf_counter()
            result = model.predict_vial(images, intended_recipe_id=rid, batch_position=position)
            return jsonify(**identity, batch_position=position, model="model2", mode="mock" if model.mock else "real",
                           result=result, inference_ms=round((time.perf_counter() - started) * 1000, 1))
        return run(identity, work)

    @bp.post("/predict/vial-evidence")
    def vial_evidence():
        require(model, model4)
        identity, position, rid, uploads = parse_request()
        try:
            expected = model4.expected_recipe(recipe_id=rid)
        except ValueError as exc:
            abort(400, description=str(exc))

        def work():
            images = [decode(u) for u in uploads]
            started = time.perf_counter()
            # Same vial, same frames; each model runs independently and neither sees the other's output.
            m4 = model4.predict_vial(images, expected=expected, batch_position=position)
            m2 = model.predict_vial(images, intended_recipe_id=rid, batch_position=position)
            flags = list(m2["verification"]["flags"])
            review4 = m4["review"]
            if review4.get("expected_transition_contamination") and "expected_transition_contamination" not in flags:
                flags.insert(0, "expected_transition_contamination")
            if review4.get("status") == "needs_review":
                flags.append("model4_needs_review")
            combined = {
                "required": True, "automatic_release": False, "flags": flags,
                "model4_review": review4,
                "model2_relation": m2["verification"]["relation"],
                "model2_counts_as_supporting_evidence": m2["verification"]["counts_as_supporting_evidence"],
                "note": ("Reported side by side. Model 2 cannot clear Model 4 discrepancies or first-vial contamination; "
                         "classifier scores and composition differences are never averaged or voted."),
            }
            return jsonify(**identity, batch_position=position, intended_recipe_id=rid, model4=m4, model2=m2,
                           combined_review=combined, inference_ms=round((time.perf_counter() - started) * 1000, 1))
        return run(identity, work)

    return bp
