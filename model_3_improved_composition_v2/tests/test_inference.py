"""Smoke tests for the Model 3 inference adapter (synthetic frames; no dataset needed).

Run from composition_v2/:  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model3.inference import Model3Composition  # noqa: E402
from model3.preprocess import linear_light, load_config  # noqa: E402

CONTRACT_KEYS = {"task", "model_id", "model_version", "run_id", "vial_id", "frame_id", "captured_at",
                 "status", "ratios", "quality_flags", "limitations", "diagnostics"}


def to_srgb(lin):
    lin = np.clip(lin, 0, 1)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(np.round(c * 255), 0, 255).astype(np.uint8)


def frames(absorbance_rgb, background=(90, 92, 80)):
    """Empty frame with a flat background; full frame = background attenuated by A inside the ROI."""
    rng = np.random.default_rng(0)
    empty = np.clip(np.full((480, 640, 3), background, float) + rng.normal(0, 1.5, (480, 640, 3)), 0, 255)
    empty = empty.astype(np.uint8)
    x0, y0, x1, y1 = load_config()["preprocessing"]["liquid_roi_xyxy"]
    full = empty.copy()
    lin = linear_light(empty[y0:y1, x0:x1]) * 10 ** (-np.asarray(absorbance_rgb))
    full[y0:y1, x0:x1] = to_srgb(lin)
    return empty, full


class TestModel3Composition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = Model3Composition()

    def call(self, empty, finished, **kw):
        return self.m.predict_vial(empty, finished, run_id="RUN-1", vial_id="VIAL-43", frame_id="f-1287",
                                   captured_at=52.125, **kw)

    def test_predicted_valid_composition(self):
        empty, full = frames([0.10, 0.70, 1.30])          # orange-like (recipe 41 in the field data)
        out = self.call(empty, [full, full])
        self.assertEqual(set(out), CONTRACT_KEYS)
        self.assertEqual(out["status"], "PREDICTED")
        r = out["ratios"]
        self.assertEqual(list(r), ["t100", "t200", "t400"])
        self.assertTrue(all(0 <= v <= 1 for v in r.values()))
        self.assertAlmostEqual(sum(r.values()), 1.0, places=3)
        self.assertGreater(r["t200"], r["t400"])          # orange dye dominates
        self.assertEqual(out["captured_at"], 52.125)      # preserved exactly
        self.assertEqual((out["run_id"], out["vial_id"], out["frame_id"]), ("RUN-1", "VIAL-43", "f-1287"))
        self.assertIn("inference_completed_at", out["diagnostics"])

    def test_too_dark_is_rejected_not_guessed(self):
        empty, full = frames([3.0, 3.0, 3.0])             # liquid near black on every channel
        out = self.call(empty, [full])
        self.assertEqual(out["status"], "UNABLE_TO_ESTIMATE")
        self.assertIsNone(out["ratios"])
        self.assertIn("TOO_DARK", out["quality_flags"])

    def test_no_liquid(self):
        empty, _ = frames([0, 0, 0])
        out = self.call(empty, [empty.copy()])
        self.assertEqual(out["status"], "UNABLE_TO_ESTIMATE")
        self.assertIn("NO_LIQUID_DETECTED", out["quality_flags"])

    def test_wrong_frame_size(self):
        empty, full = frames([0.1, 0.7, 1.3])
        out = self.call(empty[:240, :320], [full[:240, :320]])
        self.assertEqual(out["status"], "UNABLE_TO_ESTIMATE")
        self.assertIn("FRAME_SIZE_MISMATCH", out["quality_flags"])
        self.assertIsNone(out["ratios"])

    def test_no_finished_frames(self):
        empty, _ = frames([0, 0, 0])
        out = self.call(empty, [])
        self.assertEqual(out["status"], "UNABLE_TO_ESTIMATE")
        self.assertIn("NO_FINISHED_FRAMES", out["quality_flags"])

    def test_single_saturated_channel_still_predicts_with_flag(self):
        empty, full = frames([0.10, 0.70, 2.5])           # blue channel driven to the floor
        out = self.call(empty, [full])
        self.assertEqual(out["status"], "PREDICTED")
        self.assertIn("CHANNEL_SATURATED_B", out["quality_flags"])

    def test_evaluation_parity(self):
        """The adapter reproduces the stored evaluation output for a real field vial, if artifacts exist."""
        import pandas as pd
        ev = ROOT / "artifacts" / "eval" / "vial_predictions.csv"
        ff = ROOT / "artifacts" / "frame_features.csv"
        if not (ev.exists() and ff.exists()):
            self.skipTest("evaluation artifacts not built")
        row = pd.read_csv(ev).query("scheme == 'cross_session' and method == 'model3_absorbance' "
                                    "and vial_uid == 'field:41-video:v3'").iloc[0]
        g = pd.read_csv(ff).query("vial_uid == 'field:41-video:v3'")
        feats = [dict(A=r[["A_R", "A_G", "A_B"]].to_numpy(float), liquid_coverage=r.liquid_coverage,
                      full_median_rgb=r[["full_R", "full_G", "full_B"]].to_numpy(float)) for _, r in g.iterrows()]
        out = Model3Composition(black_floor_srgb=15.0).predict_from_features(feats)
        self.assertAlmostEqual(out["ratios"]["t200"], row.pred_r200, places=3)


if __name__ == "__main__":
    unittest.main()
