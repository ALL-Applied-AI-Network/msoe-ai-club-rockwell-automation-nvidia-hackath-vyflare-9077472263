"""Step 7: package the crop head for the backend and build a parity fixture.

Writes backend/model2_assets/{head.json, manifest.json} and
backend/tests/fixtures/model2/{frames.npz, oracle.json}. The oracle comes from the
training preprocessing (run_baseline.station_input) and backbone, so the backend
adapter is tested against training behavior, not against itself.
"""
import hashlib
import json
import shutil

import cv2
import numpy as np

from common import ART, CONFIG, OUT, REPO, write_json
from frame_qc import CENTER_LIMIT, PROFILE_LIMIT
from run_baseline import Backbone, station_input

ASSETS = REPO / "backend" / "model2_assets"
FIXTURES = REPO / "backend" / "tests" / "fixtures" / "model2"
# good 41 accepted; bad first 60 accepted as 99; bad first 8 abstains (final model).
FIXTURE_VIALS = ["field_v04", "field_v11", "v5_e10"]
TAGS = ["post005", "post015", "post025"]


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / "model" / "model2_head_crop.json", ASSETS / "head.json")
    head = json.loads((ASSETS / "head.json").read_text())
    metrics = json.loads((OUT / "metrics.json").read_text())["crop"]
    write_json(ASSETS / "manifest.json", {
        "model_id": "model2-baseline-v2-crop",
        "sha256": {"head.json": hashlib.sha256((ASSETS / "head.json").read_bytes()).hexdigest()},
        "source": "Training model 2/model2_baseline (config model2-baseline-v2)",
        "camera_profile": "vial-fill-640x480",
        "frames_required": "three early post-flow frames: +0.05, +0.15, +0.25 s after the no-flow boundary",
        "stream_rule": {"rows": [90, 145], "center_limit": CENTER_LIMIT, "profile_limit": PROFILE_LIMIT},
        # Set to true only after a validation run shows acceptable false acceptance.
        "approved_for_supporting_evidence": False,
        "validation": {
            "report": "Training model 2/model2_baseline/README.md",
            "good_known_cv_accepted_accuracy": metrics["A_good_known_recipe_cv"]["accepted_prediction_accuracy"],
            "unfamiliar_false_acceptance_rate": metrics["B_unfamiliar_good_recipes"]["false_acceptance_rate"],
            "bad_first_false_acceptance_rate": metrics["C_bad_first_vials"]["false_acceptance_rate"],
            "bad_later_false_acceptance_rate": metrics["C_bad_later_vials"]["false_acceptance_rate"],
            "known_issue": "recording-context shortcut on field recipes (see report)",
        },
    })

    backbone = Backbone()
    mean, scale = np.array(head["scaler_mean"]), np.array(head["scaler_scale"])
    coef, intercept = np.array(head["coef"]), np.array(head["intercept"])
    frames, oracle = {}, {}
    for key in FIXTURE_VIALS:
        rgbs = [cv2.cvtColor(cv2.imread(str(ART / "frames" / f"{key}_{t}.png")), cv2.COLOR_BGR2RGB) for t in TAGS]
        feats = backbone([station_input(rgb, "crop") for rgb in rgbs])
        logits = ((feats - mean) / scale) @ coef.T + intercept
        probs = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs /= probs.sum(axis=1, keepdims=True)
        for i, rgb in enumerate(rgbs):
            frames[f"{key}_{i}"] = rgb
        oracle[key] = {"frame_probabilities": probs.tolist(), "mean_probabilities": probs.mean(axis=0).tolist()}
    np.savez_compressed(FIXTURES / "frames.npz", **frames)
    write_json(FIXTURES / "oracle.json", {"classes": head["classes"], "config_version": CONFIG["config_version"],
                                          "vials": oracle})
    for key, o in oracle.items():
        p = np.array(o["mean_probabilities"])
        print(key, head["classes"][int(p.argmax())], round(float(p.max()), 4))


if __name__ == "__main__":
    main()
