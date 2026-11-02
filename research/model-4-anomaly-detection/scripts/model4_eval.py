"""Reproduce + extend the training-model report's Figure 3 result:
leave-one-recipe-out absorbance regression, carryover vials excluded from
both train and eval (anomaly cases), single-dye line vs a joint ridge model.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, RidgeCV

DATA = Path(__file__).resolve().parents[1] / "data" / "csi_vial_ai_dataset_v1"
OUT = Path(__file__).resolve().parents[1] / "outputs"
OUT.mkdir(exist_ok=True)

df = pd.read_csv(DATA / "vials.csv")
df = df[df["is_labeled"] == True].copy()  # noqa: E712
df[["r100", "r200", "r400"]] = df[["t100_ml", "t200_ml", "t400_ml"]].div(df["total_ml"], axis=0)
df = df[~df["carryover_suspected"].astype(bool)].copy()  # exclude from train AND eval, per the report

rgb = df[["obs_r", "obs_g", "obs_b"]].to_numpy(float)
absorb = -np.log10(np.clip(rgb / 255.0, 1e-3, 1.0))
df["A_red"], df["A_green"], df["A_blue"] = absorb[:, 0], absorb[:, 1], absorb[:, 2]

recipes = df["recipe_id"].to_numpy()
uniq_recipes = np.unique(recipes)


def loro_eval(X, y):
    """Leave-one-recipe-out MAE, model vs guess-training-mean baseline."""
    pred = np.full(len(y), np.nan)
    base = np.full(len(y), np.nan)
    for r in uniq_recipes:
        te = recipes == r
        tr = ~te
        if te.sum() == 0 or tr.sum() < 2:
            continue
        Xtr, Xte = X[tr], X[te]
        ytr = y[tr]
        model = LinearRegression().fit(Xtr, ytr) if Xtr.shape[1] == 1 else RidgeCV(
            alphas=np.logspace(-3, 3, 13)
        ).fit(Xtr, ytr)
        pred[te] = np.clip(model.predict(Xte), 0, 1)
        base[te] = ytr.mean()
    valid = ~np.isnan(pred)
    return (
        float(np.abs(pred[valid] - y[valid]).mean()),
        float(np.abs(base[valid] - y[valid]).mean()),
        int(valid.sum()),
    )


results = {}

# Single-dye line, matching the report's Figure 3.
# Orange dye absorbs BLUE light -> predict r200 from A_blue.
# Blue dye absorbs RED light -> predict r400 from A_red.
mae, base, n = loro_eval(df[["A_red"]].to_numpy(), df["r400"].to_numpy())
results["blue_single_feature_A_red_vs_r400"] = {"mae": mae, "baseline": base, "n": n}

mae, base, n = loro_eval(df[["A_blue"]].to_numpy(), df["r200"].to_numpy())
results["orange_single_feature_A_blue_vs_r200"] = {"mae": mae, "baseline": base, "n": n}

# Joint 3-channel ridge, both targets (mean MAE across r200/r400)
X3 = absorb
for name, col in [("r200", "r200"), ("r400", "r400")]:
    mae, base, n = loro_eval(X3, df[col].to_numpy())
    results[f"ridge_3ch_vs_{col}"] = {"mae": mae, "baseline": base, "n": n}

print(json.dumps(results, indent=2))
(OUT / "model4_eval_results.json").write_text(json.dumps(results, indent=2))
print(f"\nn vials after excluding carryover-suspected: {len(df)} (of 30)")
print(f"recipes: {len(uniq_recipes)}")
