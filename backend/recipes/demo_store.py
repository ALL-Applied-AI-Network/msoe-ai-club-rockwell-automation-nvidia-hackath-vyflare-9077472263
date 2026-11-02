"""Separate, explicitly enabled SQLite bank for experimental observed patterns."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock

from .reviewed_trial import compare_timing
from .reference_color import qualified_color as compare_color
from . import pattern_membership
from .recorded_eligibility import evaluate as evaluate_recorded_geometry, SOURCE_KIND

ENGINE_VERSION = "recorded-pattern-demo/1.4"


def validate_demo_location(path, normal_paths):
    if not path or str(path).strip() in {"", ":memory:"}:
        raise ValueError("RECIPE_DEMO_DB_PATH must explicitly name a separate demo SQLite file")
    target = Path(path).expanduser().resolve()
    for normal in normal_paths:
        if not normal or str(normal) == ":memory:":
            continue
        reserved = Path(normal).expanduser().resolve()
        if target == reserved or (target.exists() and reserved.exists() and target.samefile(reserved)):
            raise ValueError("Demo and normal recipe databases must be different files")
    return target


def encoded(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def validate_observation(observation):
    o=deepcopy(observation)
    if not isinstance(o.get("observation_id"),str) or not o["observation_id"].strip():raise ValueError("Missing observation identity")
    episodes=o.get("source_episode_intervals")
    if not episodes or len(episodes)!=len(o.get("duration_bounds_seconds",[])):raise ValueError("Missing episode intervals")
    bounds=[];previous_end=None
    for e in episodes:
        start,end=e["start"],e["end"]
        if end is None or any(not isinstance(pair,list) or len(pair)!=2 for pair in (start,end)):raise ValueError("Incomplete episode")
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in start+end):raise ValueError("Invalid event time")
        if not 0<=start[0]<=start[1]<end[0]<=end[1]:raise ValueError("Unusable event interval")
        if previous_end is not None and start[0]<previous_end:raise ValueError("Episode order/overlap invalid")
        bounds.append([end[0]-start[1],end[1]-start[0]]);previous_end=end[1]
    if bounds!=o["duration_bounds_seconds"]:raise ValueError("Duration bounds differ from original event intervals")
    if not isinstance(o.get("hold_reasons"),list) or any(not isinstance(x,str) for x in o["hold_reasons"]):raise ValueError("Missing quality reasons")
    lineage=o.get("source_lineage")
    if not isinstance(lineage,dict) or not isinstance(lineage.get("video_sha256"),str) or len(lineage["video_sha256"])!=64:raise ValueError("Missing source lineage")
    raw=o.get("raw_rgb")
    if raw is not None:
        rgb=raw.get("nominal")
        if not isinstance(rgb,list) or len(rgb)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=255 for x in rgb):raise ValueError("Invalid RGB")
        if any(type(raw.get(k)) not in (int,float) or not math.isfinite(raw[k]) or raw[k]<0 for k in ("temporal_distance","region_distance")):raise ValueError("Invalid RGB reliability metrics")
    encoded(o)
    return o


def recorded_tracking_check(observation):
    # Packaged historical snapshots cannot act as an alternate write path around
    # the fresh pixel-evidence gate. They remain assessable/readable as held.
    if observation.get('source_kind')=='PACKAGED_AUTOMATIC_OBSERVER_SNAPSHOT':
        return evaluate_recorded_geometry({'source_kind':SOURCE_KIND})
    return evaluate_recorded_geometry(observation)


class DemoBank:
    scope="ISOLATED_BACKEND_DEMONSTRATION_NOT_OPERATIONAL_QUALIFICATION"
    encode = staticmethod(encoded)

    def __init__(self,path,references,rules,nominal_ids,*,normal_paths,bundle_revision,allow_development_writes=False):
        if allow_development_writes is not True:raise ValueError("Explicit isolated development-write opt-in required")
        path=validate_demo_location(path, normal_paths)
        path.parent.mkdir(parents=True,exist_ok=True)
        self.references=deepcopy(references);self.rules=deepcopy(rules);self.nominal_ids=set(nominal_ids)
        self.lock=RLock()
        self.depth=0
        self.connection=sqlite3.connect(str(path),timeout=10,isolation_level=None,check_same_thread=False)
        if self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('recipe_state','recipe_trial_assessments')").fetchone():
            self.connection.close()
            raise ValueError("Demo storage cannot contain normal recipe-bank tables")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS demo_meta (name TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS demo_patterns (recipe_id INTEGER PRIMARY KEY,founder TEXT NOT NULL UNIQUE,profile TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS demo_assessments (observation_key TEXT PRIMARY KEY,evidence_hash TEXT NOT NULL,result TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS demo_occurrences (observation_key TEXT PRIMARY KEY REFERENCES demo_assessments(observation_key),recipe_id INTEGER NOT NULL)")
        config_hash=digest({"engine_version":ENGINE_VERSION,"bundle_revision":bundle_revision,"scope":self.scope,"references":references,"rules":rules,"nominal_ids":sorted(nominal_ids)})
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row=self.connection.execute("SELECT value FROM demo_meta WHERE name='configuration'").fetchone()
            if row and row[0]!=config_hash:raise ValueError("Demo bank/reference/rule revision differs; use a separate demo bank")
            for statement in pattern_membership.SCHEMA:self.connection.execute(statement)
            self.connection.execute("INSERT OR IGNORE INTO demo_meta VALUES ('configuration',?)",(config_hash,))
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK");self.connection.close();raise

    def close(self):
        with self.lock:self.connection.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.depth:
                yield
                return
            self.connection.execute("BEGIN IMMEDIATE")
            self.depth=1
            try:
                yield
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise
            finally:self.depth=0

    def patterns(self):
        with self.lock:
            rows=self.connection.execute("SELECT p.recipe_id,p.founder,p.profile,(SELECT COUNT(*) FROM demo_occurrences o WHERE o.recipe_id=p.recipe_id) FROM demo_patterns p ORDER BY p.recipe_id").fetchall()
        return [{"recipe_id":i,"status":"DISCOVERED_UNVERIFIED","founding_observation_key":founder,"profile":json.loads(profile),
            "occurrence_count":count,
            "confirmed_nominal_recipe_id":None,"scope":self.scope}
            for i,founder,profile,count in rows]

    def baseline_assessments(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.connection.execute("SELECT result FROM demo_assessments ORDER BY rowid")]

    def assessments(self):
        with self.lock:return [pattern_membership.project(self,r) for r in self.baseline_assessments()]

    def pending_patterns(self):
        with self.lock:return pattern_membership.groups(self)

    def membership_history(self,key):
        with self.lock:return pattern_membership.history(self,key)

    def counts(self):
        with self.lock:
            p,a,o=self.connection.execute("SELECT (SELECT COUNT(*) FROM demo_patterns),(SELECT COUNT(*) FROM demo_assessments),(SELECT COUNT(*) FROM demo_occurrences)").fetchone()
        return {"discovered_patterns":p,"saved_assessments":a,"linked_occurrences":o}

    def assess_many(self, observations, *, capture_timeline=False):
        with self.transaction():
            before=self.counts()
            observations=[validate_observation(o) for o in observations]
            tracks={}
            for o in observations:
                check=recorded_tracking_check(o)
                if check and check['track_id']:
                    group=(o['source_lineage']['video_sha256'],o['recorded_geometry'].get('tracker_sha256'),check['track_id'])
                    tracks.setdefault(group,[]).append(o)
            for group in tracks.values():
                fills={pattern_membership.source_key(o) or str(o['source_episode_intervals'][0]['start']) for o in group}
                if len(fills)>1:
                    for o in group:o['recorded_geometry']['batch_identity_conflict']=True
            results=[]; snapshots=[]; seen={}
            for o in observations:
                results.append(self.assess(o))
                if capture_timeline:
                    from .inspection_log import completion_time
                    for prior in results:
                        a=pattern_membership.project(self,prior['assessment'])
                        key=a['observation_id'];signature=digest(a.get('pattern_membership'))
                        if key not in seen or seen[key]!=signature:
                            snapshots.append({'assessment':deepcopy(a),'initial':key not in seen,
                                'at':max(completion_time(o),completion_time(a['observation'])),'sequence':len(snapshots)})
                        seen[key]=signature
            after=self.counts()
            return {**({"playback_snapshots":snapshots} if capture_timeline else {}), "results":[{**r,"assessment":pattern_membership.project(self,r["assessment"])} for r in results],"new_patterns":after["discovered_patterns"]-before["discovered_patterns"],
                "new_assessments":after["saved_assessments"]-before["saved_assessments"],
                "replayed_assessments":sum(r["idempotent_replay"] for r in results)}

    def _save_assessment(self,key,evidence_hash,result):
        self.connection.execute("INSERT INTO demo_assessments VALUES (?,?,?)",(key,evidence_hash,encoded(result)))

    def assess(self,observation):
        o=validate_observation(observation)
        key=o["source_lineage"]["video_sha256"]+":"+o["observation_id"]
        evidence_hash=digest(o)
        with self.transaction():
            existing=self.connection.execute("SELECT evidence_hash,result FROM demo_assessments WHERE observation_key=?",(key,)).fetchone()
            if existing:
                if existing[0]!=evidence_hash:raise ValueError("Observation identity already has different evidence; explicit revision required")
                return {"assessment":pattern_membership.project(self,json.loads(existing[1])),"idempotent_replay":True}
            profiles=self.references+[p for (raw_profile,) in self.connection.execute("SELECT profile FROM demo_patterns ORDER BY recipe_id")
                if (p:=json.loads(raw_profile)).get("discovery_origin")!="REPEATED_COLOR_CONFLICT"]
            timing=compare_timing(o["duration_bounds_seconds"],profiles,self.rules["timing_allowance_seconds"])
            color=compare_color({"raw_rgb":o["raw_rgb"],"phase_note":"Automatic window; isolated development evidence, not operational qualification."},
                timing["possible_recipe_ids"],profiles,self.rules)
            tracking=recorded_tracking_check(o)
            reasons=list(o["hold_reasons"])
            if tracking:
                reasons.extend(tracking["hold_reasons"])
                if tracking['track_id']:
                    physical=pattern_membership.source_key(o) or str(o['source_episode_intervals'][0]['start'])
                    for (raw_prior,) in self.connection.execute('SELECT result FROM demo_assessments WHERE observation_key LIKE ?',(o['source_lineage']['video_sha256']+':%',)):
                        prior=json.loads(raw_prior);old=prior.get('recorded_tracking')
                        if not old or old.get('track_id')!=tracking['track_id']:continue
                        po=prior['observation']
                        same_tracker=po.get('recorded_geometry',{}).get('tracker_sha256')==o.get('recorded_geometry',{}).get('tracker_sha256')
                        old_physical=pattern_membership.source_key(po) or str(po['source_episode_intervals'][0]['start'])
                        if same_tracker and physical!=old_physical:
                            reasons.append('TRACKING_ID_REUSED_ACROSS_FILLS')
                            tracking['hold_reasons']=sorted(set(tracking['hold_reasons']+['TRACKING_ID_REUSED_ACROSS_FILLS']))
                            tracking['status']='HELD'
                            break
            if o.get("available_demo_checks_pass") is not True:reasons.append("AVAILABLE_DEMO_CHECKS_NOT_PASSED")
            raw=o["raw_rgb"];times=o.get("sample_actual_seconds",[]);departure=o.get("departure_interval_seconds")
            window=o.get("candidate_appearance_window_seconds")
            if raw is None or raw["temporal_distance"]>self.rules["temporal_distance_limit"] or raw["region_distance"]>self.rules["placement_distance_limit"]:reasons.append("COLOR_SAMPLING_UNRELIABLE")
            valid_times=(len(times)==3 and all(type(t) in (int,float) and math.isfinite(t) for t in times)
                and all(a<b for a,b in zip(times,times[1:])) and departure and window
                and all(o["source_episode_intervals"][-1]["end"][1]<t<departure[0] and window[0]<t<window[1] for t in times)
                and all(abs((b-a)-.1)<=.034 for a,b in zip(times,times[1:])))
            if not valid_times or o.get("reference_cadence_and_window_check") is not True:reasons.append("POSTFILL_SAMPLE_PHASE_NOT_SUPPORTED")
            repeat_matches,repeat_partial=pattern_membership.confirmed_matches(self,o) if timing['status']=='NO_COMPATIBLE_REFERENCE' else ([],[])
            action="UNRESOLVED";reason="OBSERVATION_CHECK_FAILED";identity=None
            if not reasons:
                if color["status"]=="CONFLICTING":reason="COLOR_CONFLICT"
                elif color["status"]=="UNRELIABLE":reason="REFERENCE_COMPARISON_UNRELIABLE"
                elif timing["status"]=="UNIQUE_TIMING_CANDIDATE" and color["status"]=="CONSISTENT":
                    identity=timing["possible_recipe_ids"][0]
                    action="REUSE_REFERENCE_PATTERN" if identity in self.nominal_ids else "REUSE_DISCOVERED_PATTERN"
                    reason="UNIQUE_CONTAINING_PROFILE_WITH_CONSISTENT_COLOR"
                elif timing["status"]=="NO_COMPATIBLE_REFERENCE" and (repeat_matches or repeat_partial):
                    if len(repeat_matches)!=1 or repeat_partial:reason="OBSERVED_PATTERN_AMBIGUOUS"
                    elif pattern_membership.source_key(o) is None:reason="OBSERVED_PATTERN_SOURCE_LINEAGE_MISSING"
                    else:reason="KNOWN_OBSERVED_PATTERN_REUSE"
                elif timing["status"]=="NO_COMPATIBLE_REFERENCE":
                    current_max=self.connection.execute("SELECT MAX(recipe_id) FROM demo_patterns").fetchone()[0] or 0
                    identity=max(max(self.nominal_ids,default=0),current_max)+1
                    profile={"vial_uid":f"demo-founder-{identity}","recipe_id":identity,
                        "duration_bounds_s":deepcopy(o["duration_bounds_seconds"]),"raw_rgb":deepcopy(raw),
                        "source_observation":deepcopy(o),"scope":self.scope}
                    self.connection.execute("INSERT INTO demo_patterns VALUES (?,?,?)",(identity,key,encoded(profile)))
                    action="CREATE_DISCOVERED_PATTERN";reason="NO_COMPATIBLE_OBSERVED_PROFILE"
                else:reason=timing["status"]
            result={"observation_key":key,"observation_id":o["observation_id"],"action":action,"reason":reason,
                "recipe_id":identity,"recipe_status":"DISCOVERED_UNVERIFIED" if identity is not None and identity not in self.nominal_ids else "REFERENCE_PATTERN_CANDIDATE" if identity else None,
                "confirmed_nominal_recipe_id":None,"hold_reasons":sorted(set(reasons)),"timing":timing,"color":color,
                "observation":o,"validation_scope":self.scope,"original_operational_eligibility":o.get("operational_eligibility"),
                "normal_bank_write":False,"reference_coverage_complete":self.nominal_ids<={p["recipe_id"] for p in self.references}}
            if tracking:result["recorded_tracking"]=tracking
            self._save_assessment(key,evidence_hash,result)
            if identity is not None:self.connection.execute("INSERT INTO demo_occurrences VALUES (?,?)",(key,identity))
            pattern_membership.apply_membership(self,result)
            return {"assessment":pattern_membership.project(self,result),"idempotent_replay":False}
