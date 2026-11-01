"""Independent synthetic state/fault tests; no manual observation labels loaded."""
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from recipes.observation.trace import Config,Observer,observe,connected_support,stream_score
from recipes.observation.features import frame_features


def frame(t,present=True,moving=False,flow=False,signature=0):
    contrast = np.zeros((20,22,3))
    if flow:contrast[:,8:11]=[50,-50,0]
    return {"video":1,"frame_id":f"synthetic-{t}","seconds":t,
        "trace_contrast_bins":contrast,
        "holder_dark_fraction":1.0 if present else 0.0,"station_motion":5.0 if moving else 0.0,
        "holder_signature":[signature]*64,"stream_contrast_signature":([50,-50,0] if flow else [0,0,0])*20,
        **{f"row_fraction_chroma_{cut}":float(flow) for cut in (10,15,20,25)}}


def sequence():
    # Fifteen seconds between starts: quiet time must not split this visit.
    return [frame(i/4,present=.25 <= i/4 <20,moving=i/4 in (20,20.25),
                  flow=1 <= i/4 <2 or 16 <= i/4 <17) for i in range(89)]


class ObservationTests(unittest.TestCase):
    def test_two_flows_and_causal_completion(self):
        result = observe(sequence(),1)
        self.assertEqual(len(result["observations"]),1)
        c = result["observations"][0]
        self.assertEqual(len(c["episodes"]),2)
        self.assertEqual(c["flags"],[])
        self.assertEqual(c["decision_seconds"],20.25)
        self.assertEqual(c["departure_interval_seconds"],[19.75,20])
        self.assertEqual(c["recipe_bank_writes"],0)
        self.assertFalse(c["automatic_recipe_creation"])

    def test_long_pause_never_completes_fill(self):
        o = Observer(1)
        for f in sequence():
            if f["seconds"] >15:
                break
            o.step(f)
        self.assertEqual(o.closed,[])
        self.assertIsNotNone(o.current)

    def test_eof_during_flow_is_held(self):
        r = observe([f for f in sequence() if f["seconds"]<=1.5],1)["observations"][0]
        self.assertIn("FLOW_END_NOT_OBSERVED",r["flags"])
        self.assertIn("VISIT_END_NOT_OBSERVED",r["flags"])
        self.assertEqual(r["observation_state"],"UNASSIGNED")

    def test_trailing_unfilled_context_is_not_completed_fill(self):
        rows = [frame(i/4,present=i>0) for i in range(20)]
        c = observe(rows,1)["observations"][0]
        self.assertEqual(c["episodes"],[])
        self.assertIn("NO_SUSTAINED_FLOW_OBSERVED",c["flags"])

    def test_left_censored_arrival_kept_as_hold(self):
        rows = sequence()[1:]
        c = observe(rows,1)["observations"][0]
        self.assertIn("ARRIVAL_LEFT_CENSORED",c["flags"])

    def test_single_frame_droplet_is_not_extra_flow(self):
        rows = [frame(5,flow=True) if f["seconds"]==5 else f for f in sequence()]
        self.assertEqual(len(observe(rows,1)["observations"][0]["episodes"]),2)

    def test_transient_motion_recovers_without_losing_evidence(self):
        rows = [dict(f,station_motion=5) if f["seconds"]==10 else f for f in sequence()]
        c = observe(rows,1)["observations"][0]
        self.assertNotIn("UNRESOLVED_MOTION_SPIKE",c["flags"])
        self.assertNotIn("UNRESOLVED_FLOW_VISIBILITY",c["flags"])
        self.assertEqual(len(c["recovery_events"]),1)
        self.assertIn("synthetic-10.0",c["buffered_frame_ids"])
        self.assertEqual(len(c["buffered_frame_ids"]),len(set(c["buffered_frame_ids"])))

    def test_changed_holder_does_not_falsely_recover(self):
        rows = [dict(f,station_motion=5) if f["seconds"]==10 else
                dict(f,holder_signature=[100]*64) if f["seconds"]>10 else f for f in sequence()]
        c = observe(rows,1)["observations"][0]
        self.assertIn("UNRESOLVED_MOTION_SPIKE",c["flags"])
        self.assertEqual(c["recovery_events"],[])

    def test_input_gap_is_not_silently_qualified(self):
        c = observe([f for f in sequence() if f["seconds"]!=10],1)["observations"][0]
        self.assertIn("INPUT_GAP_IDENTITY_OR_FLOW_UNCERTAIN",c["flags"])

    def test_prearrival_gap_is_not_silently_trusted(self):
        c = observe([f for f in sequence() if f["seconds"]!=.25],1)["observations"][0]
        self.assertIn("PREARRIVAL_EVIDENCE_UNCERTAIN",c["flags"])

    def test_unavailable_frame_holds_visit_and_continues(self):
        rows = [{"video":1,"seconds":10,"frame_id":"bad","frame_error":"OSError"} if f["seconds"]==10 else f for f in sequence()]
        r = observe(rows,1)
        self.assertIn("FRAME_UNAVAILABLE_DURING_VISIT",r["observations"][0]["flags"])
        self.assertTrue(r["health_events"])

    def test_recovery_timeout_does_not_fragment_stationary_vial(self):
        r = observe(sequence(),1,Config(maximum_visit_seconds=2))
        self.assertEqual(len(r["observations"]),1)
        self.assertEqual(r["observations"][0]["end_reason"],"RECOVERY_BUDGET_EXHAUSTED")

    def test_incremental_chunk_replay_is_identical(self):
        rows = sequence()
        o = Observer(1)
        for chunk in (rows[:9],rows[9:60],rows[60:]):
            for f in chunk:
                o.step(f)
        self.assertEqual(o.finish_source(),observe(rows,1))

    def test_timestamp_and_source_validation(self):
        for bad in (float("nan"),float("inf"),-.25,0):
            o = Observer(1);o.step(frame(0))
            with self.assertRaises(ValueError):o.step(frame(bad))
        with self.assertRaises(ValueError):Observer(1).step(dict(frame(0),video=2))

    def test_invalid_configuration_rejected(self):
        for kwargs in ({"maximum_visit_seconds":0},{"flow_off_fraction":.8},{"confirm_frames":2.5},
                       {"presence_fraction":float("nan")},{"signature_recovery_distance":-1}):
            with self.assertRaises(ValueError):Config(**kwargs)

    def test_unsupported_image_geometry_rejected(self):
        with self.assertRaises(ValueError):frame_features(np.zeros((480,639,3),dtype=np.uint8))

    def test_stream_pixels_produce_real_contrast_features(self):
        pixels = np.full((480,640,3),128,dtype=np.uint8)
        pixels[100:140,303:314] = [20,150,20]
        features,_ = frame_features(pixels)
        self.assertEqual(features["row_fraction_chroma_20"],1)
        self.assertGreater(features["stream_delta_median"],100)


class TraceTests(unittest.TestCase):
    def test_retained_flow_images_can_recover_after_same_holder_confirmation(self):
        rows = [dict(f,station_motion=5) if f["seconds"]==1.5 else f for f in sequence()]
        c = observe(rows,1)["observations"][0]
        self.assertNotIn("UNRESOLVED_FLOW_VISIBILITY",c["flags"])
        self.assertEqual(c["episodes"][0]["end_interval_seconds"],[1.75,2])
        self.assertTrue(any(s.get("resolution") for s in c["uncertainty_spans"]))

    def test_holder_recovery_cannot_erase_genuinely_weak_stream_evidence(self):
        rows = sequence()
        for f in rows:
            if f["seconds"]==1.5:f["station_motion"]=5
            if f["seconds"] in (1.5,1.75):f["trace_contrast_bins"][6:]=0
            if f["seconds"]==2:f["trace_contrast_bins"][:,8:11]=[50,-50,0]
        c = observe(rows,1)["observations"][0]
        self.assertIn("UNRESOLVED_FLOW_VISIBILITY",c["flags"])
        self.assertFalse(any(s.get("resolution") for s in c["uncertainty_spans"]))

    def test_horizontal_drift_can_follow_connected_stream(self):
        mask = np.zeros((20,22),dtype=bool)
        for i in range(20):mask[i,2+i//2]=True
        self.assertEqual(connected_support(mask),1)

    def test_disconnected_streaks_cannot_be_added_together(self):
        mask = np.zeros((20,22),dtype=bool)
        mask[:10,0]=True;mask[10:,21]=True
        self.assertEqual(connected_support(mask),.5)

    def test_only_one_internal_gap_is_allowed(self):
        mask = np.ones((20,1),dtype=bool);mask[[6,13],0]=False
        self.assertEqual(connected_support(mask),.6)

    def test_hanging_drop_with_short_vertical_support_is_not_flow(self):
        matrix = np.zeros((20,22,3));matrix[:2,8:11]=[50,-50,0]
        self.assertLess(stream_score(matrix,np.zeros_like(matrix),Config()),.25)

    def test_uncertainty_widens_cessation_interval(self):
        rows = sequence()
        for f in rows:
            if f["seconds"]==2:
                f["trace_contrast_bins"][:6,8:11]=[50,-50,0]
        c = observe(rows,1)["observations"][0]
        self.assertEqual(c["episodes"][0]["end_interval_seconds"],[1.75,2.25])

    def test_returned_flow_does_not_erase_ambiguous_interruption(self):
        rows = sequence()
        for f in rows:
            if f["seconds"] in (1.25,1.5):
                f["trace_contrast_bins"][6:]=0
        c = observe(rows,1)["observations"][0]
        self.assertIn("UNRESOLVED_FLOW_VISIBILITY",c["flags"])
        self.assertEqual(c["observation_state"],"UNASSIGNED")

    def test_uncertainty_budget_is_bounded(self):
        rows = sequence()
        for f in rows:
            if 5<=f["seconds"]<8:f["trace_contrast_bins"][:6,8:11]=[50,-50,0]
        c = observe(rows,1)["observations"][0]
        self.assertIn("FLOW_UNCERTAINTY_BUDGET_EXHAUSTED",c["flags"])

    def test_returning_signal_cannot_bypass_budget_between_samples(self):
        times=[0,.25,.5,.75,1,1.25,1.5,1.75,1.95,2.2,2.45,2.7]
        rows=[frame(t,present=t>0,moving=t>=2.45) for t in times]
        for f in rows:
            if .5<=f["seconds"]<2.2:f["trace_contrast_bins"][:6,8:11]=[50,-50,0]
        # First uncertain=.5; return=2.2, still within the 2s budget.
        within=observe(rows,1)["observations"][0]
        self.assertNotIn("FLOW_UNCERTAINTY_BUDGET_EXHAUSTED",within["flags"])
        later_times=[0,.25,.5,.75,1,1.25,1.5,1.75,2.0,2.3,2.55,2.8,3.05]
        shifted=[frame(t,present=t>0,moving=t>=2.8) for t in later_times]
        for f in shifted:
            if .5<=f["seconds"]<2.55:f["trace_contrast_bins"][:6,8:11]=[50,-50,0]
        # Last uncertainty=2.3 (<2.5 deadline); return=2.55 crosses it.
        beyond=observe(shifted,1)["observations"][0]
        self.assertIn("FLOW_UNCERTAINTY_BUDGET_EXHAUSTED",beyond["flags"])
        self.assertNotIn("INPUT_GAP_IDENTITY_OR_FLOW_UNCERTAIN",beyond["flags"])

    def test_all_nine_configs_preserve_two_flows_in_state_fixture(self):
        for width in (1,3,5):
            for cut in (10,15,20):
                c = observe(sequence(),1,Config(band_width=width,delta_cut=cut))["observations"][0]
                self.assertEqual(len(c["episodes"]),2)
                self.assertFalse(c["flags"])


if __name__ == "__main__":
    unittest.main()
