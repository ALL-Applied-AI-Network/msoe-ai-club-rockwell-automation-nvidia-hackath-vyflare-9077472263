"""Write the split manifest: one row per vial, one column per evaluation scheme.

Rules (all at vial level; the 4 finished frames of a vial never cross a split):
  training_eligible  batch_position >= 2 in video 5. First vials after a recipe change carry residue of
                     the previous recipe, so their label is not their colour. Field vials are never used
                     for training (the field session is the held-out run).
  vial3fold_v5       test fold = position of the vial in its recipe batch (1, 2, 3), as in the original
                     notebook: unseen vials of known recipes. Same recording, so not evidence of
                     generalisation to other runs.
  loro_v5            test fold = recipe id: unseen compositions, same recording.
  cross_session      train = eligible video 5 vials, test = every field vial (new run, camera, lighting,
                     and new compositions 41/50/60/99). This is also the final checkpoint's training set.

Usage: python scripts/make_splits.py [--features artifacts/frame_features.csv]
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument("--features", default=str(ROOT / "artifacts" / "frame_features.csv"))
a = ap.parse_args()

v = (pd.read_csv(a.features).groupby("vial_uid")
     .agg(session=("session", "first"), run_id=("run_id", "first"), recipe_id=("recipe_id", "first"),
          batch_position=("batch_position", "first"), prev_recipe_id=("prev_recipe_id", "first"),
          r100=("r100", "first"), r200=("r200", "first"), r400=("r400", "first"),
          notes=("notes", "first")).reset_index())
v5 = v.session == "video5"
v["training_eligible"] = v5 & (v.batch_position >= 2)
v["vial3fold_v5"] = v.batch_position.where(v5).astype("Int64")
v["loro_v5"] = v.recipe_id.where(v5).astype("Int64")
v["cross_session"] = "test"
v.loc[v5, "cross_session"] = "train"
v.loc[v5 & ~v.training_eligible, "cross_session"] = "excluded_transition"
v["final_checkpoint"] = v.cross_session.map({"train": "train"}).fillna("not_used")
v = v.sort_values(["session", "run_id", "vial_uid"])
v.to_csv(ROOT / "artifacts" / "split_manifest.csv", index=False)
print(v.groupby(["session", "cross_session"]).size().to_string())
print(f"-> {ROOT / 'artifacts' / 'split_manifest.csv'}")
