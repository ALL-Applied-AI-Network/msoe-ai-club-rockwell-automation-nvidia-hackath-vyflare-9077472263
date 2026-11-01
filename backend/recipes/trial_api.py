"""Backend-only reviewed-data trial routes; never wired to video playback."""
from copy import deepcopy
from threading import RLock

from flask import jsonify, request


def register_trial_routes(bp, engine, store):
    memory = {}
    lock = RLock()
    videos = {key[0] for key in engine.observations}

    @bp.get("/trial/status")
    def trial_status():
        return jsonify(experimental=True, coverage=engine.coverage(), rules=engine.rules,
                       saved_assessment_count=store.trial_assessment_count() if store else len(memory),
                       persistence=store.persistence if store else "in_memory", automatic_recipe_creation=False,
                       automatic_video_detection=False, limitations=engine.bundle["limitations"])

    @bp.post("/trial/recorded/<video_id>/<vial_id>")
    def assess_trial_recorded(video_id, vial_id):
        if request.get_json(silent=True) != {}:
            return jsonify(error="Send an empty JSON object; reviewed trial observations are loaded server-side"), 400
        if (video_id, vial_id) not in engine.observations:
            return jsonify(error="Unknown reviewed trial fill"), 404
        result = engine.assess(video_id, vial_id)
        if store:
            result = store.save_trial_assessment(video_id, vial_id, result)
        else:
            with lock:
                key = result["assessment_id"]
                if key not in memory:
                    memory[key] = (video_id, deepcopy(result))
                result = deepcopy(memory[key][1])
        return jsonify(assessment=result)

    @bp.get("/trial/videos/<video_id>/assessments")
    def trial_video_assessments(video_id):
        if video_id not in videos:
            return jsonify(error="Unknown reviewed trial video"), 404
        if store:
            results = store.list_trial_assessments(video_id)
        else:
            with lock:
                results = [deepcopy(value) for video, value in reversed(list(memory.values())) if video == video_id]
        return jsonify(assessments=results, includes_history=True)
