"""Opt-in, separate-bank API using checksummed automatic-observer snapshots."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from flask import Blueprint,current_app,jsonify,request

from .demo_store import DemoBank,ENGINE_VERSION,digest,validate_observation

ASSETS=Path(__file__).resolve().parents[1]/"recipe_demo_assets"


class RecordedDemoService:
    def __init__(self,catalog_sha,trial_engine,path,normal_paths,assets=ASSETS):
        assets=Path(assets)
        manifest=json.loads((assets/"manifest.json").read_text())
        payload=(assets/"recorded_observations.json").read_bytes()
        actual=hashlib.sha256(payload).hexdigest()
        if manifest["version"]!=1 or manifest["nominal_catalog_sha256"]!=catalog_sha:
            raise ValueError("Demo assets do not match the nominal catalog")
        if actual!=manifest["sha256"]["recorded_observations.json"]:
            raise ValueError("Demo asset integrity check failed")
        self.bundle=json.loads(payload)
        # Hash the already validated reference contents, not a research path.
        reference_bytes=(json.dumps(trial_engine.bundle,indent=2,allow_nan=False)+"\n").encode()
        reference_sha=hashlib.sha256(reference_bytes).hexdigest()
        if manifest["reference_bundle_sha256"]!=reference_sha or self.bundle["reference_bundle_sha256"]!=reference_sha:
            raise ValueError("Demo reference revision differs from the reviewed comparison bundle")
        if (self.bundle["version"]!=1 or self.bundle["nominal_catalog_sha256"]!=catalog_sha
                or self.bundle["input_mode"]!="PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOTS"
                or self.bundle["operational_qualification_claim"] is not False):
            raise ValueError("Unsupported demo observation mode")
        observations=self.bundle["observations"]
        self.observations={}
        for o in observations:
            validate_observation(o)
            if o["operational_eligibility"]!="NOT_VALIDATED" or o["source_kind"]!="PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOT":
                raise ValueError("Demo must retain the automatic observation qualification scope")
            key=(o["video_id"],o["vial_id"])
            if key in self.observations:raise ValueError("Duplicate demo source identity")
            self.observations[key]=deepcopy(o)
        counts={v:sum(k[0]==v for k in self.observations) for v in {k[0] for k in self.observations}}
        if len(observations)!=manifest["observation_count"] or counts!=manifest["video_counts"]:
            raise ValueError("Invalid demo observation coverage")
        if len({o["source_lineage"]["video_sha256"]+":"+o["observation_id"] for o in observations})!=len(observations):
            raise ValueError("Duplicate demo producer identity")
        self.coverage=trial_engine.coverage()
        self.rules=deepcopy(trial_engine.rules)
        self.revision=digest({"payload_sha256":actual,"manifest":manifest,"engine_version":ENGINE_VERSION})
        self.bank=DemoBank(path,trial_engine.profiles,self.rules,trial_engine.catalog_ids,
            normal_paths=normal_paths,bundle_revision=self.revision,allow_development_writes=True)

    def source(self,video_id,vial_id):return deepcopy(self.observations.get((video_id,vial_id)))

    def video(self,video_id):
        if video_id not in {k[0] for k in self.observations}:return None
        return [deepcopy(o) for k,o in self.observations.items() if k[0]==video_id]


def create_demo_blueprint(service, producer=None):
    bp=Blueprint("recipe_demo_api",__name__,url_prefix="/api/recipe-workflow/demo")

    @bp.before_request
    def demo_gate():
        if request.method=="OPTIONS":return None
        if service is None and request.endpoint not in ("recipe_demo_api.status", "recipe_demo_api.producer_status"):
            return jsonify(error="Recipe demonstration is disabled; configure a separate store explicitly"),503
        if request.method=="POST" and not os.getenv("INFERENCE_TOKEN", ""):
            return jsonify(error="Demo writes require INFERENCE_TOKEN configuration"),503

    def empty_body():
        if request.get_json(silent=True)!={}:return jsonify(error="Send exactly {}; packaged automatic observations are loaded server-side"),400

    @bp.get('/producer/status')
    def producer_status():
        from .recorded_producer import NativeDecoder, PRODUCER_VERSION
        from .recorded_eligibility import VERSION as TRACKING_POLICY
        return jsonify(enabled=producer is not None, **NativeDecoder.capability(),
            input_mode='FRESH_RECORDED_VIDEO_OBSERVATION', supported_videos=['video-1','video-2'],
            producer_version=PRODUCER_VERSION,tracking_policy_version=TRACKING_POLICY,tracking_gate_enabled=True,
            coverage=service.coverage if service else None,
            operational_qualification_claim=False, normal_recipe_bank_writes=False)

    @bp.get('/producer/videos/<video_id>')
    def producer_video(video_id):
        if producer is None:return jsonify(error='Recorded producer is disabled'),503
        try:return jsonify(**producer.get(video_id))
        except KeyError:return jsonify(error='Unknown recorded video'),404

    @bp.post('/producer/videos/<video_id>')
    def process_video(video_id):
        invalid=empty_body()
        if invalid:return invalid
        if producer is None:return jsonify(error='Recorded producer is disabled'),503
        try:return jsonify(**producer.start(video_id)),202
        except (KeyError,FileNotFoundError):return jsonify(error='Unknown or unavailable source recording'),404
        except ValueError as exc:return jsonify(error=str(exc)),503
        except RuntimeError as exc:return jsonify(error=str(exc)),409

    @bp.get("/status")
    def status():
        return jsonify(enabled=service is not None,scope=DemoBank.scope,engine_version=ENGINE_VERSION,
            input_mode="PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOTS",automatic_video_detection=False,
            operational_qualification_claim=False,normal_recipe_bank_writes=False,
            demo_writes_ready=service is not None and bool(os.getenv("INFERENCE_TOKEN", "")),
            persistence="isolated_demo_sqlite" if service else "disabled",
            counts=service.bank.counts() if service else None,coverage=service.coverage if service else None,
            revision=service.revision if service else None,
            video_counts={v:len(service.video(v)) for v in ("video-1","video-2")} if service else {},
            limitations=service.bundle["limitations"] if service else ["Demonstration mode is opt-in and requires a separate database."])

    @bp.post("/recorded/<video_id>/<vial_id>")
    def assess_recorded(video_id,vial_id):
        invalid=empty_body()
        if invalid:return invalid
        observation=service.source(video_id,vial_id)
        if observation is None:return jsonify(error="Unknown packaged automatic observation"),404
        try:return jsonify(**service.bank.assess(observation))
        except ValueError as exc:return jsonify(error=str(exc)),409

    @bp.post("/videos/<video_id>/assessments")
    def assess_video(video_id):
        invalid=empty_body()
        if invalid:return invalid
        observations=service.video(video_id)
        if observations is None:return jsonify(error="Unknown packaged demonstration video"),404
        try:
            result=service.bank.assess_many(observations)
            return jsonify(video_id=video_id,**result)
        except ValueError as exc:return jsonify(error=str(exc)),409

    @bp.get("/videos/<video_id>/assessments")
    def video_assessments(video_id):
        if service.video(video_id) is None:return jsonify(error="Unknown packaged demonstration video"),404
        results=[r for r in service.bank.assessments() if r["observation"]["video_id"]==video_id]
        return jsonify(video_id=video_id,assessments=results)

    @bp.get("/recorded/<video_id>/<vial_id>")
    def get_recorded(video_id,vial_id):
        observation=service.source(video_id,vial_id)
        if observation is None:return jsonify(error="Unknown packaged automatic observation"),404
        found=next((r for r in service.bank.assessments() if r["observation_id"]==observation["observation_id"]),None)
        if found is None:return jsonify(error="No saved demo assessment for this fill"),404
        return jsonify(assessment=found)

    @bp.get("/patterns")
    def patterns():
        with service.bank.lock:
            return jsonify(groups=service.bank.pending_patterns(),recipes=service.bank.patterns(),required_fill_count=2,scope=DemoBank.scope,
                normal_recipe_bank_writes=False)

    @bp.get("/patterns/<group_id>/history")
    def pattern_history(group_id):
        group=next((g for g in service.bank.pending_patterns() if g["group_id"]==group_id),None)
        if group is None:return jsonify(error="Unknown observed-pattern group"),404
        return jsonify(group=group,members=[{**m,"history":service.bank.membership_history(m["observation_key"])} for m in group["members"]])

    @bp.get("/recipes")
    def recipes():return jsonify(recipes=service.bank.patterns(),scope=DemoBank.scope,normal_recipe_bank_writes=False)

    @bp.get("/recipes/<int:recipe_id>")
    def recipe(recipe_id):
        found=next((p for p in service.bank.patterns() if p["recipe_id"]==recipe_id),None)
        if found is None:return jsonify(error="Unknown discovered demonstration recipe"),404
        return jsonify(recipe=found)

    @bp.errorhandler(Exception)
    def demo_error(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc,HTTPException):return jsonify(error=exc.description),exc.code
        current_app.logger.exception("Recipe demonstration failed")
        return jsonify(error="Recipe demonstration failed; no incomplete transaction was committed"),500

    return bp
