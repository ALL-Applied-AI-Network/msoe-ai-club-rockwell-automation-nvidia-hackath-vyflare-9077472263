"""Recipe-evidence integration. Nominal settings never become invented timing data."""
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from .inspection_api import inspection_to_dict
from .models import Dispense, VialObservation
from .trial_api import register_trial_routes

_ROOT = Path(__file__).resolve().parents[2]


def load_reference_catalog():
    root = _ROOT / "backend/model4_assets"
    payload = (root / "recipes.json").read_bytes()
    manifest = json.loads((root / "manifest.json").read_text())
    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest["sha256"]["recipes.json"]:
        raise ValueError("Reference recipe catalog failed integrity check")
    return json.loads(payload), digest


def create_workflow_blueprint(service, store, catalog, catalog_sha, trial_engine):
    bp = Blueprint("recipe_workflow_api", __name__, url_prefix="/api/recipe-workflow")
    register_trial_routes(bp, trial_engine, store)
    records = {}  # Explicit in-memory fixtures; production uses SQLiteStore.evidence.
    reference_ids = {int(key) for key in catalog["recipes"]}
    manifest = json.loads((_ROOT / "evidence/recorded-inspection.json").read_text())
    videos = {v["id"]: v for v in manifest["videos"] if v["id"] in {"video-1", "video-2"}}

    def transaction():
        return store.transaction() if store else nullcontext()

    def evidence_records():
        return store.evidence if store else records

    def coverage():
        patterns = service.recipes.list_recipes("INTENDED")
        complete = {r.id for r in patterns if r.final_color is not None}
        return {"nominal_reference_count": len(reference_ids),
                "comparable_reference_count": len(reference_ids & complete),
                "missing_reference_ids": sorted(reference_ids - complete),
                "reference_pattern_ids": sorted(complete),
                "required_fields": ["per-dispense duration", "per-dispense color", "final color"],
                "note": "Nominal milliliters and tank order do not establish observed timing or final appearance."}

    def revision(vial):
        patterns = service.recipes.list_recipes("INTENDED")
        value = {"method": "reviewed-video-evidence/1.0", "catalog_sha256": catalog_sha,
                 "patterns": [asdict(r) for r in patterns], "matching_config": asdict(service.matcher.config),
                 "source_observation": vial}
        return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def source(video_id, vial_id):
        video = videos.get(video_id)
        return next((v for v in video["vials"] if v["id"] == vial_id), None) if video else None

    def assessment(identifier, metadata):
        item = service.inspections.get_inspection(identifier)
        if item is None:
            raise RuntimeError("Stored evidence has no inspection")
        result = inspection_to_dict(item)
        status = "MATCHED" if item.verification_status == "PASS" else "UNMATCHED_CANDIDATE" if item.verification_status == "FAIL" else "INSUFFICIENT_EVIDENCE"
        vial = source(metadata.get("video_id"), metadata.get("vial_id"))
        stale = bool(vial and metadata.get("revision") != revision(vial))
        return {**result, "assessment_status": status, "evidence": metadata,
                "requires_reassessment": stale, "coverage": coverage(),
                "persistence": store.persistence if store else "in_memory",
                "automatic_release": False}

    @bp.get("/status")
    def status():
        with transaction():
            return jsonify(coverage=coverage(), persistence=store.persistence if store else "in_memory",
                           saved_assessment_count=len(evidence_records()),
                           catalog_sha256=catalog_sha, method="weighted-recipe/1.0",
                           automatic_video_detection=False, automatic_release=False)

    @bp.get("/videos/<video_id>/assessments")
    def video_assessments(video_id):
        if video_id not in videos:
            return jsonify(error="Unknown reviewed video"), 404
        with transaction():
            latest = {}
            for identifier, record in evidence_records().items():
                if record.get("video_id") == video_id:
                    latest[record["vial_id"]] = (identifier, record)
            return jsonify(assessments=[assessment(i, m) for i, m in latest.values()])

    @bp.post("/recorded/<video_id>/<vial_id>")
    def inspect_recorded(video_id, vial_id):
        if request.get_json(silent=True) != {}:
            return jsonify(error="Send an empty JSON object; reviewed observations are loaded server-side"), 400
        vial = source(video_id, vial_id)
        if not vial:
            return jsonify(error="Unknown reviewed vial"), 404
        with transaction():
            version = revision(vial)
            # Reference/evidence revisions create new immutable assessments.
            # Replaying the same evidence under the same references is idempotent.
            run_id = f"recorded:{video_id}:{version}"
            observation = VialObservation(run_id, vial_id, (), vial["appearance"], False)
            item = service.inspect(observation)
            metadata = {"kind": "sampled_visual_review", "video_id": video_id, "vial_id": vial_id,
                        "vial_label": vial["label"], "revision": version, "timing_basis": "encoded_video_seconds",
                        "source_observation": vial,
                        "limitations": ["Observed pulses retain start/stop sampling brackets; exact ingredient-dispense durations are not established.",
                                        "Visible pulse count is not a verified material/tank dispense sequence.",
                                        "This assessment does not run Model 2 or infer a recipe from Model 4 estimates."]}
            evidence_records().setdefault(item.inspection_id, metadata)
            return jsonify(assessment=assessment(item.inspection_id, metadata))

    @bp.post("/observations")
    def inspect_observation():
        # Trusted future camera/model producers share the same guarded service.
        # This endpoint is intentionally not exposed through the frontend proxy.
        import os
        if not os.getenv("INFERENCE_TOKEN", ""):
            return jsonify(error="Observation ingestion requires INFERENCE_TOKEN configuration"), 503
        body = request.get_json(silent=True)
        try:
            if not isinstance(body, dict) or set(body) != {"observation", "source"}:
                raise ValueError("Provide observation and source")
            raw, provenance = body["observation"], body["source"]
            if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 1024:
                raise ValueError("source must identify the reviewed measurement or producing adapter")
            if not isinstance(raw, dict) or set(raw) != {"run_id", "vial_id", "dispenses", "final_color", "filling_complete"}:
                raise ValueError("Invalid observation fields")
            if any(not isinstance(raw[k], str) or not 1 <= len(raw[k].strip()) <= 128 for k in ("run_id", "vial_id")):
                raise ValueError("Observation identities must contain 1–128 characters")
            if not isinstance(raw["dispenses"], list) or len(raw["dispenses"]) > 100:
                raise ValueError("Provide at most 100 dispenses")
            observation = VialObservation(**{**raw, "dispenses": tuple(Dispense(**d) for d in raw["dispenses"])})
            with transaction():
                item = service.inspect(observation)
                metadata = {"kind": "supplied_observation", "source": provenance.strip()}
                old = evidence_records().get(item.inspection_id)
                if old is not None and old != metadata:
                    raise ValueError("Existing observation has different provenance")
                evidence_records()[item.inspection_id] = metadata
                return jsonify(assessment=assessment(item.inspection_id, metadata))
        except (TypeError, ValueError) as exc:
            return jsonify(error=str(exc)), 400

    return bp
