"""Causal fixed-station event prototype. This module never reads annotation files.

It associates visits through holder motion, not general object/biometric identity.
Recipe matching, recipe creation and camera control are deliberately absent.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Config:
    motion_threshold: float = 4.0
    presence_fraction: float = .20
    chroma_cut: int = 15
    delta_cut: int = 20
    flow_on_fraction: float = .35
    flow_off_fraction: float = .175
    confirm_frames: int = 2
    maximum_input_gap_seconds: float = .40
    maximum_visit_seconds: float = 180.0
    post_flow_guard_seconds: float = .50
    motion_guard_seconds: float = .25
    signature_recovery_distance: float = 4.0

    def __post_init__(self):
        if self.chroma_cut not in (10,15,20,25) or type(self.confirm_frames) is not int or self.confirm_frames < 2:
            raise ValueError("Unsupported prototype configuration")
        if not 0 < self.flow_off_fraction < self.flow_on_fraction < 1:
            raise ValueError("Invalid flow hysteresis")
        if not 0 < self.presence_fraction < 1:
            raise ValueError("Invalid holder-presence fraction")
        if any(not math.isfinite(v) or v <= 0 for v in (self.motion_threshold,self.maximum_input_gap_seconds,
               self.maximum_visit_seconds,self.post_flow_guard_seconds,self.motion_guard_seconds,
               self.signature_recovery_distance,self.delta_cut)):
            raise ValueError("Invalid prototype threshold")


class Observer:
    def __init__(self, video, config=None):
        self.video = video
        self.config = config or Config()
        self.previous = None
        self.current = None
        self.closed = []
        self.stationary_pending = []
        self.motion_pending = []
        self.flow_pending = []
        self.off_pending = []
        self.active_flow = None
        self.counter = 0
        self.stable_signature = None
        self.motion_reference = None
        self.pending_recovery = None
        self.blocked_until_motion = False
        self.arrival_context_uncertain = False
        self.health_events = []

    def _new_visit(self):
        first = self.stationary_pending[0]
        self.counter += 1
        self.current = {"observation_id":f"auto-video-{self.video}-visit-{self.counter:03}","video":self.video,
            "first_stationary_seconds":first["seconds"],
            "arrival_settling_interval_seconds":[first.get("previous_seconds",first["seconds"]),first["seconds"]],
            "initially_present_at_source_start":bool(first.get("source_initial",False)),
            "episodes":[],"flags":[],"buffered_frame_ids":[],"last_stationary_seconds":first["seconds"],
            "recovery_events":[],
            "identity_method":"fixed_station_visit_association_not_general_vial_tracking"}
        self.current["stream_baseline"] = first["stream_contrast_signature"]
        if self.arrival_context_uncertain:
            self.current["flags"].append("PREARRIVAL_EVIDENCE_UNCERTAIN")
        if first[f"row_fraction_chroma_{self.config.chroma_cut}"] >= .5:
            self.current["flags"].append("POSSIBLE_FLOW_ALREADY_PRESENT_AT_ARRIVAL")
        self.active_flow = None
        self.flow_pending = []
        self.off_pending = []
        self.pending_recovery = None
        for frame in self.stationary_pending:
            self._stationary_frame(frame)
        self.stationary_pending = []

    def _stationary_frame(self, frame):
        c = self.current
        c["buffered_frame_ids"].append(frame["frame_id"])
        c["last_stationary_seconds"] = frame["seconds"]
        baseline = c["stream_baseline"]
        signature = frame["stream_contrast_signature"]
        changes = [math.sqrt(sum((signature[i+j]-baseline[i+j])**2 for j in range(3))) for i in range(0,len(baseline),3)]
        color_changes = [(max(signature[i:i+3])-min(signature[i:i+3]))-
                         (max(baseline[i:i+3])-min(baseline[i:i+3])) for i in range(0,len(baseline),3)]
        value = sum(v>self.config.delta_cut or c>self.config.chroma_cut for v,c in zip(changes,color_changes))/len(changes)
        t = frame["seconds"]
        previous = frame.get("previous_seconds",t)
        if self.active_flow is None:
            if value >= self.config.flow_on_fraction:
                self.flow_pending.append(frame)
                if len(self.flow_pending) >= self.config.confirm_frames:
                    first = self.flow_pending[0]
                    self.active_flow = {"start_interval_seconds":[first.get("previous_seconds",first["seconds"]),first["seconds"]],
                        "start_evidence":[first["frame_id"]],"last_positive_seconds":t}
                    self.flow_pending = []
            else:
                self.flow_pending = []
        else:
            if value < self.config.flow_off_fraction:
                self.off_pending.append(frame)
                if len(self.off_pending) >= self.config.confirm_frames:
                    first = self.off_pending[0]
                    episode = {"order":len(c["episodes"])+1,
                        "start_interval_seconds":self.active_flow["start_interval_seconds"],
                        "end_interval_seconds":[first.get("previous_seconds",first["seconds"]),first["seconds"]],
                        "evidence_frame_ids":self.active_flow["start_evidence"]+[first["frame_id"]],
                        "end_confirmed":True}
                    c["episodes"].append(episode)
                    self.active_flow = None
                    self.off_pending = []
            else:
                self.active_flow["last_positive_seconds"] = t
                self.off_pending = []

    def _finish(self, reason, departure=None, decision_seconds=None):
        c = self.current
        if c is None:
            return
        c["end_reason"] = reason
        c["departure_interval_seconds"] = departure
        c["decision_seconds"] = decision_seconds if decision_seconds is not None else self.previous["seconds"]
        if self.active_flow is not None:
            c["flags"].append("FLOW_END_NOT_OBSERVED")
            c["episodes"].append({"order":len(c["episodes"])+1,
                "start_interval_seconds":self.active_flow["start_interval_seconds"],"end_interval_seconds":None,
                "evidence_frame_ids":self.active_flow["start_evidence"],"end_confirmed":False})
        if reason != "DEPARTURE_MOTION":
            c["flags"].append("VISIT_END_NOT_OBSERVED")
        if c["initially_present_at_source_start"]:
            c["flags"].append("ARRIVAL_LEFT_CENSORED")
        c["candidate_appearance_window_seconds"] = None
        complete = c["episodes"] and all(e["end_confirmed"] for e in c["episodes"])
        if complete and departure is not None:
            lo = c["episodes"][-1]["end_interval_seconds"][1] + self.config.post_flow_guard_seconds
            hi = departure[0] - self.config.motion_guard_seconds
            if hi-lo > .35:
                c["candidate_appearance_window_seconds"] = [lo,hi]
            else:
                c["flags"].append("NO_USABLE_POSTFLOW_WINDOW")
        elif not c["episodes"]:
            c["flags"].append("NO_SUSTAINED_FLOW_OBSERVED")
        c["flags"] = sorted(set(c["flags"]))
        c["observation_state"] = "CANDIDATE_REQUIRES_COLOR_REFINEMENT" if not c["flags"] else "UNASSIGNED"
        c["recipe_id"] = None
        c["recipe_bank_writes"] = 0
        c["operational_eligibility"] = "NOT_VALIDATED"
        c["automatic_recipe_creation"] = False
        self.closed.append(deepcopy(c))
        self.current = None
        self.active_flow = None
        self.flow_pending = []
        self.off_pending = []
        self.pending_recovery = None
        self.stable_signature = None

    def step(self, frame):
        f = dict(frame)
        if f.get("video",self.video) != self.video:
            raise ValueError("Do not mix source streams in one observer")
        t = f["seconds"]
        if not math.isfinite(t) or (self.previous is not None and t <= self.previous["seconds"]):
            raise ValueError("Input timestamps must be finite and strictly increasing")
        f["previous_seconds"] = self.previous["seconds"] if self.previous is not None else t
        f["source_initial"] = self.previous is None
        if self.previous is not None and t-self.previous["seconds"] > self.config.maximum_input_gap_seconds:
            self.health_events.append({"seconds":t,"reason":"INPUT_GAP","gap_seconds":t-self.previous["seconds"]})
            self.arrival_context_uncertain = True
            if self.current:
                self.current["flags"].append("INPUT_GAP_IDENTITY_OR_FLOW_UNCERTAIN")
            self.stationary_pending = []
            self.flow_pending = []
        if f.get("frame_error"):
            self.arrival_context_uncertain = True
            self.health_events.append({"seconds":t,"reason":"FRAME_UNAVAILABLE"})
            if self.current:
                self.current["flags"].append("FRAME_UNAVAILABLE_DURING_VISIT")
            self.stationary_pending = []
            self.previous = f
            return
        present = f["holder_dark_fraction"] >= self.config.presence_fraction
        moving = f["station_motion"] is not None and f["station_motion"] >= self.config.motion_threshold
        if self.current and t-self.current["first_stationary_seconds"] > self.config.maximum_visit_seconds:
            self._finish("RECOVERY_BUDGET_EXHAUSTED",decision_seconds=t)
            self.blocked_until_motion = True
        if moving:
            if not self.motion_pending:
                self.motion_reference = self.stable_signature
            self.motion_pending.append(f)
            self.stationary_pending = []
            if len(self.motion_pending) >= self.config.confirm_frames:
                first = self.motion_pending[0]
                self._finish("DEPARTURE_MOTION",[first["previous_seconds"],first["seconds"]],decision_seconds=t)
                self.blocked_until_motion = False
                self.arrival_context_uncertain = False
        else:
            if self.motion_pending and self.current:
                self.current["flags"].append("UNRESOLVED_MOTION_SPIKE")
                self.pending_recovery = {"reference":self.motion_reference,"stable_frames":0,
                    "started_seconds":self.motion_pending[0]["seconds"]}
                # Preserve the image evidence across a single unresolved spike.
                # Identity remains flagged until the appearance check resolves it.
                for pending_frame in self.motion_pending:
                    self._stationary_frame(pending_frame)
            self.motion_pending = []
            if self.current and self.pending_recovery:
                reference = self.pending_recovery["reference"]
                signature = f.get("holder_signature")
                if reference is not None and signature is not None:
                    distance = sum(abs(a-b) for a,b in zip(reference,signature))/len(reference)
                    if distance <= self.config.signature_recovery_distance:
                        self.pending_recovery["stable_frames"] += 1
                    else:
                        self.pending_recovery["stable_frames"] = 0
                    if self.pending_recovery["stable_frames"] >= self.config.confirm_frames:
                        self.current["flags"] = [x for x in self.current["flags"] if x!="UNRESOLVED_MOTION_SPIKE"]
                        self.current["recovery_events"].append({"reason":"TRANSIENT_MOTION_REASSOCIATED_WITH_PRE_SPIKE_HOLDER_APPEARANCE",
                            "started_seconds":self.pending_recovery["started_seconds"],"resolved_seconds":t,"signature_distance":distance})
                        self.pending_recovery = None
            if present and not self.blocked_until_motion:
                if self.current is None:
                    self.stationary_pending.append(f)
                    if len(self.stationary_pending) >= self.config.confirm_frames:
                        self._new_visit()
                else:
                    self._stationary_frame(f)
                self.stable_signature = f.get("holder_signature")
            else:
                self.stationary_pending = []
                if self.current:
                    self.current["flags"].append("HOLDER_PRESENCE_LOST_WITHOUT_CONFIRMED_DEPARTURE")
        self.previous = f

    def finish_source(self):
        self._finish("SOURCE_END")
        return {"video":self.video,"config":asdict(self.config),"observations":deepcopy(self.closed),
            "health_events":deepcopy(self.health_events),"label_files_read":False,
            "limits":["fixed-camera station association, not general object tracking",
                "4fps JPEG event input cannot resolve every original frame or brief event",
                "color must be refined at reference cadence from an independent automatic window",
                "no recipe matching, learning, camera control or operational qualification performed"]}


def observe(frames, video, config=None):
    observer = Observer(video,config)
    for frame in frames:
        if frame["video"] == video:
            observer.step(frame)
    return observer.finish_source()
