"""Station-scoped tracker commands; GETs never advance the workflow."""

from dataclasses import asdict
import os

from flask import Blueprint, abort, jsonify, request

from .inspection_api import inspection_to_dict
from .tracker_manager import TrackerManager
from .vial_tracker import TrackerEvent


def _body(required, optional=()):
    data = request.get_json()
    if not isinstance(data, dict) or set(data) - set(required) - set(optional) or set(required) - set(data):
        abort(400, description="JSON fields must include " + ", ".join(required)
              + ("; optional: " + ", ".join(optional) if optional else ""))
    return data


def create_tracker_blueprint(manager: TrackerManager):
    blueprint = Blueprint("tracker_api", __name__, url_prefix="/api/stations")

    @blueprint.before_request
    def require_write_token():
        # Configured-token verification is shared with the app's request hook.
        # Unlike reads, ingestion/configuration must never be anonymous writes.
        if request.method == "POST" and not os.getenv("INFERENCE_TOKEN", ""):
            abort(503, description="Tracker writes require INFERENCE_TOKEN configuration")

    @blueprint.errorhandler(KeyError)
    def missing_station(exc):
        return jsonify(error="Station not found"), 404

    @blueprint.errorhandler(RuntimeError)
    def conflict(exc):
        return jsonify(error=str(exc)), 409

    @blueprint.errorhandler(ValueError)
    @blueprint.errorhandler(TypeError)
    @blueprint.errorhandler(OverflowError)
    def invalid_input(exc):
        return jsonify(error=str(exc)), 400

    def response(station_id, tracker, status=200):
        snapshot = tracker.snapshot()
        data = asdict(snapshot)
        data["inspection"] = inspection_to_dict(snapshot.inspection) if snapshot.inspection else None
        if data["observation"] is not None:
            data["observation"]["dispense_count"] = len(snapshot.observation.dispenses)
        return jsonify(station_id=station_id, tracker=data, config=asdict(tracker.config),
                       scheduler=manager.scheduler_status(station_id)), status

    @blueprint.get("/<station_id>/tracker")
    def status(station_id):
        return response(station_id, manager.get(station_id))

    @blueprint.get("/<station_id>/tracker/config")
    def get_config(station_id):
        return jsonify(station_id=station_id, config=asdict(manager.get(station_id).config))

    @blueprint.post("/<station_id>/tracker/config")
    def configure(station_id):
        data = _body((), ("update_interval_ms", "finalization_grace_ms"))
        if not data:
            abort(400, description="Provide at least one tracker setting")
        return response(station_id, manager.configure(station_id, data))

    @blueprint.post("/<station_id>/tracker/start")
    def start(station_id):
        data = _body(("run_id", "vial_id", "captured_at"), ("inspection_id",))
        return response(station_id, manager.start_filling(station_id, **data))

    @blueprint.post("/<station_id>/tracker/events")
    def submit_event(station_id):
        data = _body(("event_id", "run_id", "vial_id", "kind", "captured_at"),
                     ("dispense_id", "color", "source"))
        return response(station_id, manager.submit(station_id, TrackerEvent(**data)), 202)

    @blueprint.post("/<station_id>/tracker/finish")
    def finish(station_id):
        data = _body(("event_id", "run_id", "vial_id", "captured_at"), ("final_color",))
        event = TrackerEvent(data["event_id"], data["run_id"], data["vial_id"],
                             "FILLING_COMPLETED", data["captured_at"], color=data.get("final_color"))
        return response(station_id, manager.submit(station_id, event), 202)

    return blueprint
