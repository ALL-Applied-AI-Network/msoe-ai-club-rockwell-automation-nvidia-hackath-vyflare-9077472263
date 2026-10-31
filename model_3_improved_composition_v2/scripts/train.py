"""Train the final checkpoint on the vials marked final_checkpoint=train in the split manifest.

Usage: python scripts/train.py   ->  artifacts/checkpoint.json
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model3.fit import fit_checkpoint  # noqa: E402
from model3.preprocess import load_config  # noqa: E402

cfg = load_config()
frames = pd.read_csv(ROOT / "artifacts" / "frame_features.csv")
split = pd.read_csv(ROOT / "artifacts" / "split_manifest.csv")
train_ids = set(split.loc[split.final_checkpoint == "train", "vial_uid"])
ckpt = fit_checkpoint(frames[frames.vial_uid.isin(train_ids)], cfg,
                      "video 5, training-eligible vials (2nd and 3rd of each recipe batch), 4 finished frames each")
out = ROOT / cfg["checkpoint"]
out.write_text(json.dumps(ckpt, indent=2))
print(json.dumps({k: ckpt[k] for k in ("coef", "intercept", "sha256_of_weights", "training_rows")}, indent=2))
print(f"-> {out}")
