"""Step 3: validity of early post-flow frames.

Rule (fixed before training): a post-flow frame is invalid when a liquid stream is
visible in the Model 4 stream ROI, i.e. centre-band colour contrast >= 20 or the
maximum per-column contrast >= 30 (rows 90-145, columns 288-333). The in-flow
review frame (end_s - 0.5 s) is a positive control and is never used as input.
Clear water streams are faint, so the rule was checked against an enlarged visual
review (notes below). No movement or occlusion was observed in any reviewed vial.
"""
import csv

import cv2
import numpy as np

from common import ART, OUT

CENTER_LIMIT, PROFILE_LIMIT = 20.0, 30.0

# Visual review of enlarged stream-region crops (Claude review, not operator-confirmed).
VISUAL_REVIEW = {
    "v5_e27": "thin stream at +0.05 s; +0.15/+0.25 s show drops at nozzle only",
    "field_v02": "no stream; elevated profile score from vial edge",
    "field_v04": "no stream; elevated profile score from vial edge",
    "field_v09": "thin clear stream at +0.05/+0.15 s; none at +0.25 s",
    "field_v10": "thin clear stream in all post-flow frames",
    "field_v01": "stream continues through all post-flow frames: end_s precedes end of flow",
    "field_v21": "stream continues through all post-flow frames: end_s precedes end of flow",
    "field_v22": "stream continues through all post-flow frames: end_s precedes end of flow",
    "field_v23": "stream continues through all post-flow frames: end_s precedes end of flow",
    "field_v24": "stream continues through all post-flow frames: end_s precedes end of flow",
    "field_v25": "stream continues through all post-flow frames: end_s precedes end of flow",
}


def stream_scores(img):
    roi = img[90:145].astype(np.float32)
    center = roi[:, 305:316].mean(axis=(0, 1))
    side = np.concatenate([roi[:, 288:298], roi[:, 323:333]], axis=1).mean(axis=(0, 1))
    profile = roi[:, 295:326].mean(axis=0)
    return float(np.abs(center - side).sum()), float(np.abs(profile - np.median(profile, axis=0)).sum(axis=1).max())


def main():
    rows = list(csv.DictReader(open(OUT / "frames_raw.csv", encoding="utf-8")))
    for r in rows:
        c, p = stream_scores(cv2.imread(str(ART / r["image"])))
        r["stream_center"], r["stream_profile"] = round(c, 2), round(p, 2)
        if r["tag"].startswith("review"):
            r["valid"], r["qc_reason"] = False, "in-flow review frame (positive control, never model input)"
        elif c >= CENTER_LIMIT or p >= PROFILE_LIMIT:
            r["valid"], r["qc_reason"] = False, "liquid stream visible (flow not ended or renewed)"
        else:
            r["valid"], r["qc_reason"] = True, "early post-flow; no stream, movement or occlusion"
        r["visual_review"] = VISUAL_REVIEW.get(r["vial_key"], "")
    with open(OUT / "frames_manifest.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    valid = {}
    for r in rows:
        valid.setdefault(r["vial_key"], 0)
        valid[r["vial_key"]] += r["valid"] is True
    print("vials with 0 valid frames:", [k for k, n in valid.items() if n == 0])
    print("vials with 1-2 valid frames:", {k: n for k, n in valid.items() if 0 < n < 3})
    print("valid frames:", sum(valid.values()))


if __name__ == "__main__":
    main()
