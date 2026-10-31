"""Model 3 inference adapter: finished-vial composition (t100 / t200 / t400 volume fractions).

Usage:
    from model3.inference import Model3Composition
    m = Model3Composition()                     # config.json + artifacts/checkpoint.json
    out = m.predict_vial(empty_frame, [finished_frame_1, finished_frame_2],
                         run_id="RUN-1", vial_id="VIAL-43", frame_id="f-1287", captured_at=52.1)

Inputs are RGB uint8 arrays (or image paths) from the calibrated 640x480 station view:
  - empty_frame: the same vial, empty, after it arrived and before the first dispense
  - finished_frames: 1+ frames of the completed vial (the median absorbance is used)

The result follows the proposed integration contract. status is PREDICTED or UNABLE_TO_ESTIMATE; when
unable, ratios is null (never zeros). captured_at is returned exactly as given; inference completion time
is reported separately under diagnostics. This adapter creates no tracker events and no pass/fail verdicts.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np

from .preprocess import PACKAGE_ROOT, absorbance_features, load_config, load_rgb, project_to_simplex

LIMITATIONS = (
    "Ratios estimate the commanded recipe proportions from colour; they are not measured composition "
    "and not millilitres.",
    "Recipes with equal proportions but different totals (e.g. recipes 5 and 8) are indistinguishable.",
    "Trained on one recording session (video 5, 20 clean vials, 10 recipes); validated on one further "
    "session (Oct 28 field data) only.",
    "Requires an empty-vial reference frame of the same vial from the same calibrated camera pose.",
    "The first 1-2 vials after a recipe change can contain residue of the previous recipe; this model "
    "reports their colour, it does not decide whether they are contaminated.",
)

UNABLE_FLAGS = {"NO_FINISHED_FRAMES", "FRAME_SIZE_MISMATCH", "EMPTY_FULL_SIZE_MISMATCH",
                "NO_LIQUID_DETECTED", "TOO_DARK"}


class Model3Composition:
    def __init__(self, config_path=None, checkpoint=None, black_floor_srgb: float | None = None):
        self.cfg = load_config(config_path)
        if black_floor_srgb is not None:
            self.cfg["quality"]["black_floor_srgb"] = float(black_floor_srgb)
        if checkpoint is None or isinstance(checkpoint, (str, Path)):
            checkpoint = json.loads(Path(checkpoint or PACKAGE_ROOT / self.cfg["checkpoint"]).read_text())
        self.ckpt = checkpoint
        self.W = np.array(checkpoint["coef"], float)          # rows: t200, t400; cols: A_R, A_G, A_B
        self.b = np.array(checkpoint["intercept"], float)
        self.A_min = np.array(checkpoint["training_feature_min"], float)
        self.A_max = np.array(checkpoint["training_feature_max"], float)

    # ------------------------------------------------------------------ public
    def predict_vial(self, empty_frame, finished_frames, *, run_id, vial_id, frame_id, captured_at) -> dict:
        empty = load_rgb(empty_frame) if isinstance(empty_frame, (str, Path)) else np.asarray(empty_frame)
        frames = [load_rgb(f) if isinstance(f, (str, Path)) else np.asarray(f) for f in finished_frames]
        flags = []
        feats = []
        W, H = self.cfg["camera"]["frame_size_wh"]
        if not frames:
            flags.append("NO_FINISHED_FRAMES")
        if empty.shape[:2] != (H, W) or any(f.shape[:2] != (H, W) for f in frames):
            flags.append("FRAME_SIZE_MISMATCH")
        elif any(f.shape != empty.shape for f in frames):
            flags.append("EMPTY_FULL_SIZE_MISMATCH")
        if not flags:
            feats = [absorbance_features(empty, f, self.cfg) for f in frames]
        return self.predict_from_features(feats, flags, run_id=run_id, vial_id=vial_id,
                                          frame_id=frame_id, captured_at=captured_at)

    def predict_from_features(self, feats: list[dict], flags: list | None = None, *, run_id=None,
                              vial_id=None, frame_id=None, captured_at=None) -> dict:
        """Shared by inference and evaluation, so both apply identical aggregation and quality rules."""
        q = self.cfg["quality"]
        flags = list(flags or [])
        A = cov = None
        sat = ""
        if feats:
            As = np.array([f["A"] for f in feats])
            A = np.median(As, 0)
            cov = float(np.median([f["liquid_coverage"] for f in feats]))
            # saturation on the median finished colour across frames
            med_rgb = np.median([f["full_median_rgb"] for f in feats], 0)
            from .preprocess import saturation_level
            lvl = saturation_level(q["black_floor_srgb"], q["saturation_headroom_linear"])
            sat = "".join(c for c, v in zip("RGB", med_rgb) if v < lvl)
            if cov < q["min_liquid_coverage"]:
                flags.append("NO_LIQUID_DETECTED")
            if len(sat) >= q["too_dark_min_saturated_channels"]:
                flags.append("TOO_DARK")
            elif len(sat) == 1:
                flags.append(f"CHANNEL_SATURATED_{sat}")
            if len(feats) > 1 and np.ptp(As, 0).max() > q["max_frame_spread_absorbance"]:
                flags.append("FRAME_DISAGREEMENT")
            m = q["training_range_margin_absorbance"]
            if np.any(A < self.A_min - m) or np.any(A > self.A_max + m):
                flags.append("OUTSIDE_TRAINING_RANGE")

        ratios, raw = None, None
        status = "UNABLE_TO_ESTIMATE" if (not feats or UNABLE_FLAGS & set(flags)) else "PREDICTED"
        if A is not None:
            o, b = self.W @ A + self.b
            raw = np.array([1 - o - b, o, b])
            proj = project_to_simplex(raw)
            if np.abs(raw - proj).max() > q["max_raw_simplex_violation"]:
                flags.append("RAW_OUTSIDE_SIMPLEX")
            if status == "PREDICTED":
                ratios = {k: round(float(v), 4) for k, v in zip(self.cfg["output_order"], proj)}

        return {
            "task": self.cfg["task"],
            "model_id": self.cfg["model_id"],
            "model_version": self.cfg["model_version"],
            "run_id": run_id,
            "vial_id": vial_id,
            "frame_id": frame_id,
            "captured_at": captured_at,
            "status": status,
            "ratios": ratios,
            "quality_flags": flags,
            "limitations": list(LIMITATIONS),
            "diagnostics": {
                "absorbance_rgb": None if A is None else [round(float(x), 4) for x in A],
                "liquid_coverage": None if cov is None else round(cov, 3),
                "saturated_channels": sat,
                "frames_used": len(feats),
                "raw_unprojected": None if raw is None else [round(float(x), 4) for x in raw],
                "checkpoint_sha256": self.ckpt.get("sha256_of_weights"),
                "inference_completed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            },
        }
