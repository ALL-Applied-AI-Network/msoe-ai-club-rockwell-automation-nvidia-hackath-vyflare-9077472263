"""Export per-vial data (predictions, residuals, flags, thumb paths) as JSON
for the teammate-facing demo UI."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

DATA = Path(__file__).resolve().parents[1] / "data" / "csi_vial_ai_dataset_v1"
OUT = Path(__file__).resolve().parents[1] / "outputs"
THUMBS_OUT = OUT / "demo_thumbs"
THUMBS_OUT.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(DATA / "vials.csv")
df = df[df["is_labeled"] == True].copy()  # noqa: E712
df[["r100", "r200", "r400"]] = df[["t100_ml", "t200_ml", "t400_ml"]].div(df["total_ml"], axis=0)

rgb = df[["obs_r", "obs_g", "obs_b"]].to_numpy(float)
absorb = -np.log10(np.clip(rgb / 255.0, 1e-3, 1.0))
X = absorb
Y = df[["r200", "r400"]].to_numpy(float)
recipes = df["recipe_id"].to_numpy()
clean = ~df["carryover_suspected"].astype(bool).to_numpy()

pred = np.full_like(Y, np.nan)
residual = np.full(len(df), np.nan)
for r in np.unique(recipes):
    te = recipes == r
    tr = (~te) & clean
    if tr.sum() < 2 or te.sum() == 0:
        continue
    model = RidgeCV(alphas=np.logspace(-3, 3, 13)).fit(X[tr], Y[tr])
    p = np.clip(model.predict(X[te]), 0, 1)
    pred[te] = p
    residual[te] = np.abs(p - Y[te]).mean(axis=1)

df["pred_r200"], df["pred_r400"] = pred[:, 0], pred[:, 1]
df["residual"] = residual
valid = ~df["residual"].isna()
normal_mask = valid & (~df["carryover_suspected"].astype(bool)) & df["color_match"]
thresh = df.loc[normal_mask, "residual"].mean() + df.loc[normal_mask, "residual"].std()
df["flagged_by_model"] = (valid & (df["residual"] > thresh)).astype(bool)

records = []
for _, row in df[valid].sort_values("vial").iterrows():
    vuid = row["vial_uid"]
    src_thumb = DATA / row["thumb_path"]
    dst_thumb = THUMBS_OUT / f"{vuid}.jpg"
    if src_thumb.exists():
        shutil.copyfile(src_thumb, dst_thumb)
    records.append({
        "vial_uid": vuid,
        "vial": int(row["vial"]),
        "recipe_id": int(row["recipe_id"]),
        "t100_ml": row["t100_ml"], "t200_ml": row["t200_ml"], "t400_ml": row["t400_ml"],
        "total_ml": row["total_ml"],
        "r200_actual": round(row["r200"], 3), "r400_actual": round(row["r400"], 3),
        "r200_pred": round(row["pred_r200"], 3), "r400_pred": round(row["pred_r400"], 3),
        "residual": round(float(row["residual"]), 4),
        "flagged": bool(row["flagged_by_model"]),
        "color_match": bool(row["color_match"]),
        "carryover_suspected": bool(row["carryover_suspected"]),
        "first_after_recipe_change": bool(row["first_after_recipe_change"]),
        "obs_color_class": row["obs_color_class"],
        "expected_color_class": row["expected_color_class"],
        "obs_r": int(row["obs_r"]), "obs_g": int(row["obs_g"]), "obs_b": int(row["obs_b"]),
        "thumb": f"thumbs/{vuid}.jpg",
    })

out = {"threshold": round(float(thresh), 4), "vials": records}
(OUT / "demo_data.json").write_text(json.dumps(out, indent=2))
print(f"Exported {len(records)} vials, threshold={thresh:.4f}")
print(f"Flagged: {sum(r['flagged'] for r in records)}")
