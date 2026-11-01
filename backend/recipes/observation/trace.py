"""Label-free connected-stream experiment; fixed-station association is inherited.

Uncertainty is preserved rather than merged away when visible flow returns.
Neither recipe identity nor expected episode count is an input.
"""
from dataclasses import dataclass
import math

import numpy as np

from .station import Config as StationConfig,Observer as StationObserver


@dataclass(frozen=True)
class Config(StationConfig):
    motion_threshold: float = 2.0
    delta_cut: int = 15
    flow_on_fraction: float = .50
    flow_off_fraction: float = .25
    band_width: int = 3
    uncertainty_budget_seconds: float = 2.0

    def __post_init__(self):
        super().__post_init__()
        if self.band_width not in (1,3,5):
            raise ValueError("Only predeclared band widths are allowed")
        if not math.isfinite(self.uncertainty_budget_seconds) or self.uncertainty_budget_seconds<=0:
            raise ValueError("Invalid uncertainty budget")


def connected_support(mask):
    """Longest supported path; center step <=1, at most one unsupported bin.

Two DP states retain the maximum supported-bin count per center with zero or
one internal gap. Unsupported bins cannot start paths and contribute no count.
"""
    mask = np.asarray(mask,dtype=bool)
    if mask.ndim!=2 or not mask.shape[0] or not mask.shape[1]:
        raise ValueError("Expected nonempty vertical-bin by band-center mask")
    previous = np.full((mask.shape[1],2),-1000,dtype=int)
    best = 0
    for supported in mask:
        padded = np.pad(previous,((1,1),(0,0)),constant_values=-1000)
        neighbors = np.maximum.reduce([padded[:-2],padded[1:-1],padded[2:]])
        current = np.full_like(previous,-1000)
        current[supported,0] = np.maximum(1,neighbors[supported,0]+1)
        current[supported,1] = neighbors[supported,1]+1
        current[~supported,1] = neighbors[~supported,0]
        previous = current
        best = max(best,int(current.max()))
    return best/mask.shape[0]


def stream_score(current,baseline,config):
    current,baseline = np.asarray(current,dtype=float),np.asarray(baseline,dtype=float)
    if current.shape!=(20,22,3) or baseline.shape!=current.shape or not np.isfinite(current).all() or not np.isfinite(baseline).all():
        raise ValueError("Expected finite fixed-camera contrast bins of shape 20x22x3")
    delta = current-baseline
    width = config.band_width
    local = np.stack([delta[:,i:i+width].mean(axis=1) for i in range(23-width)],axis=1)
    return connected_support(np.linalg.norm(local,axis=2)>config.delta_cut)


class Observer(StationObserver):
    def __init__(self,video,config=None):
        super().__init__(video,config or Config())
        self.trace_baseline = None
        self.last_absence = None
        self.last_flow = None
        self.last_evidence_state = None
        self.uncertain = None

    def _new_visit(self):
        self.trace_baseline = np.asarray(self.stationary_pending[0]["trace_contrast_bins"],dtype=float).copy()
        self.last_absence = self.last_flow = self.last_evidence_state = self.uncertain = None
        super()._new_visit()

    def _close_uncertainty(self,next_state,decision_time):
        if self.uncertain is None:
            return
        span = dict(self.uncertain)
        span.update(next_state=next_state,resolved_at_seconds=decision_time)
        if decision_time-span["start_seconds"]>self.config.uncertainty_budget_seconds:
            span["budget_expired"] = True
            self.current["flags"].append("FLOW_UNCERTAINTY_BUDGET_EXHAUSTED")
        same_holder_confirmed = any(abs(e["started_seconds"]-span["start_seconds"])<1e-9 and
            abs(e["resolved_seconds"]-decision_time)<1e-9 for e in self.current["recovery_events"])
        can_replay = (same_holder_confirmed and span["identity_pending_only"] and
            span["raw_consistent_with_previous"] and not span["budget_expired"] and
            ((span["previous_state"]=="FLOW" and self.active_flow is not None) or
             (span["previous_state"]=="ABSENT" and self.active_flow is None)))
        if can_replay:
            # The images were available: only their association was pending.
            # Same-holder confirmation plus the retained unambiguous image
            # evidence resolves that delay without inventing missing evidence.
            for evidence in self.current["frame_evidence"]:
                if span["start_seconds"]<=evidence["seconds"]<=span["last_seconds"]:
                    evidence["initial_state"] = evidence["state"]
                    evidence["state"] = span["previous_state"]
                    evidence["reclassified_at_seconds"] = decision_time
            if span["previous_state"]=="FLOW":self.last_flow=span["last_seconds"]
            else:self.last_absence=span["last_seconds"]
            span["resolution"] = "RETAINED_UNAMBIGUOUS_IMAGES_AFTER_CONFIRMED_HOLDER_REASSOCIATION"
        # A resumed signal does not prove that no stop/restart occurred.
        ambiguous = not can_replay and ((span["previous_state"]=="FLOW" and next_state=="FLOW")
                     or (span["previous_state"]=="ABSENT" and next_state=="ABSENT" and span["frames"]>=2)
                     or next_state is None)
        span["sequence_ambiguity_unresolved"] = ambiguous
        if ambiguous:
            self.current["flags"].append("UNRESOLVED_FLOW_VISIBILITY")
        self.current.setdefault("uncertainty_spans",[]).append(span)
        self.uncertain = None

    def _stationary_frame(self,frame):
        c,t = self.current,frame["seconds"]
        c["buffered_frame_ids"].append(frame["frame_id"])
        c["last_stationary_seconds"] = t
        score = stream_score(frame["trace_contrast_bins"],self.trace_baseline,self.config)
        state = "FLOW" if score>=self.config.flow_on_fraction else "ABSENT" if score<self.config.flow_off_fraction else "UNCERTAIN"
        raw_state = state
        known_faults = {"INPUT_GAP_IDENTITY_OR_FLOW_UNCERTAIN","FRAME_UNAVAILABLE_DURING_VISIT",
            "PREARRIVAL_EVIDENCE_UNCERTAIN","HOLDER_PRESENCE_LOST_WITHOUT_CONFIRMED_DEPARTURE","UNRESOLVED_MOTION_SPIKE"}
        faults = known_faults.intersection(c["flags"])
        if faults:
            state = "UNCERTAIN"
        c.setdefault("frame_evidence",[]).append({"frame_id":frame["frame_id"],"seconds":t,"score":score,"state":state})
        if state=="UNCERTAIN":
            self.flow_pending = [];self.off_pending = []
            if self.uncertain is None:
                self.uncertain = {"start_seconds":t,"last_seconds":t,"frames":0,"previous_state":self.last_evidence_state,
                    "budget_expired":False,"identity_pending_only":True,"raw_consistent_with_previous":True}
            self.uncertain["identity_pending_only"] &= faults=={"UNRESOLVED_MOTION_SPIKE"}
            self.uncertain["raw_consistent_with_previous"] &= raw_state==self.uncertain["previous_state"]
            self.uncertain["last_seconds"] = t
            self.uncertain["frames"] += 1
            if t-self.uncertain["start_seconds"]>=self.config.uncertainty_budget_seconds:
                self.uncertain["budget_expired"] = True
                c["flags"].append("FLOW_UNCERTAINTY_BUDGET_EXHAUSTED")
            return
        self._close_uncertainty(state,t)
        self.last_evidence_state = state
        if state=="FLOW":
            self.off_pending = []
            self.last_flow = t
            if self.active_flow is None:
                self.flow_pending.append({**frame,"onset_lower":self.last_absence})
                if len(self.flow_pending)>=self.config.confirm_frames:
                    first = self.flow_pending[0]
                    lower = first["onset_lower"]
                    if lower is None:
                        c["flags"].append("FLOW_ONSET_NOT_OBSERVED")
                        lower = first.get("previous_seconds",first["seconds"])
                    self.active_flow = {"start_interval_seconds":[lower,first["seconds"]],
                        "start_evidence":[first["frame_id"]],"last_positive_seconds":t}
                    self.flow_pending = []
            else:
                self.active_flow["last_positive_seconds"] = t
        else:
            self.flow_pending = []
            self.last_absence = t
            if self.active_flow is not None:
                self.off_pending.append({**frame,"cessation_lower":self.last_flow})
                if len(self.off_pending)>=self.config.confirm_frames:
                    first = self.off_pending[0]
                    c["episodes"].append({"order":len(c["episodes"])+1,
                        "start_interval_seconds":self.active_flow["start_interval_seconds"],
                        "end_interval_seconds":[first["cessation_lower"],first["seconds"]],
                        "evidence_frame_ids":self.active_flow["start_evidence"]+[first["frame_id"]],"end_confirmed":True})
                    self.active_flow = None;self.off_pending = []

    def _finish(self,reason,departure=None,decision_seconds=None):
        if self.current:
            self._close_uncertainty(None,decision_seconds if decision_seconds is not None else self.previous["seconds"])
        super()._finish(reason,departure,decision_seconds)


def observe(frames,video,config=None):
    observer = Observer(video,config)
    for frame in frames:
        if frame["video"]==video:
            observer.step(frame)
    return observer.finish_source()
