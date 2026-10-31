"""Shared paths, fixed configuration and workbook access for the Model 2 baseline."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TM2 = HERE.parent
REPO = TM2.parent
DATA = TM2 / "data"
WORKBOOK = TM2 / "recipes.xlsx"
VIDEO5 = TM2 / "vial_fill_video_5.mp4"
FIELD_CONCAT = DATA / "41-50-60-99.mp4"
OUT = HERE / "outputs"            # committed: manifests, predictions, metrics
ART = HERE / "artifacts"          # gitignored: extracted frames, features

sys.path.insert(0, str(TM2 / "label_updates"))
import build_label_updates as labels  # noqa: E402  (reuse the audited workbook reader)

# Field recordings in concatenation order, verified frame-for-frame against
# 41-50-60-99.mp4 (start frame and start pts in the concatenated timeline).
FIELD_RECORDINGS = [
    # folder json,                              recipe per folder, concat start frame, start s
    ("41/41-video.json", 41, 0, 0.0),
    ("99/41-flush/99-video-41-flush.json", 99, 7370, 298.667),
    ("60/60-video.json", 60, 12668, 513.334),
    ("99/60-flush/99-video-60-flush.json", 99, 21049, 853.001),
    ("50/50-video.json", 50, 26388, 1069.335),
    ("99/50-flush/99-video-50-flush.json", 99, 35107, 1422.635),
]

# Decisions fixed before any evaluation (see README).
CONFIG = {
    "config_version": "model2-baseline-v6",
    "seed": 20261031,
    "post_flow_offsets_s": [0.05, 0.15, 0.25],
    "frame_label": "early post-flow (not settled)",
    "backbone": "torchvision resnet18 IMAGENET1K_V1, frozen, global-average-pool 512-d",
    "backbone_sha256": "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec",
    "head": "multinomial logistic regression (linear), StandardScaler fit on training fold only",
    "head_C": 1.0,
    "head_max_iter": 5000,
    "augment_copies": 8,
    "augment": "translation <=4% of crop each axis, gaussian pixel noise sigma=0.01; no hue/saturation/brightness/scale/flip",
    "input_size": 224,
    "aggregation": "mean of per-frame softmax over valid frames of one vial",
    "accept_threshold": 0.90,
    # Operator confirmed 2026-10-31: recipe-60 recording is correct (sidecar "rec #99" is a
    # sync error) and 99/50-flush/99-2.jpg is batch position 2. Nothing is quarantined.
    "quarantine_media": [],
    "quarantine_recordings": [],
    # A recipe is supported only when it has training-eligible vials with valid frames.
    "unsupported_recipes": [],
    # Vials held out of training and labeled metrics until the operator resolves a conflict.
    # field_v27 resolved 2026-10-31: workbook f98b3a74 labels it bad, matching its photo.
    "label_conflicts": {},
    # Recipes with identical nominal proportions are withheld together.
    "proportion_groups": [[5, 8]],
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def workbook_vials():
    """Vial records from the two labeled sheets, keyed like the Model 4 checkpoint."""
    out = []
    for sheet, rows in labels.read_sheets(WORKBOOK).items():
        header = {name.strip().lower(): i for i, name in rows[0][1].items()}
        timing = {r: (v.get(header["start_s"]), v.get(header["end_s"])) for r, v in rows[1:]}
        for r in labels.records(sheet, rows):
            start, end = timing[r["row"]]
            r["start_s"] = float(start) if start is not None else None
            r["end_s"] = float(end)
            r["vial_key"] = f"{labels.SHEETS[sheet]}{r['vial_id']:02d}"
            out.append(r)
    return out


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
