"""Model 4 physics-first baseline: predict dye mix ratios (r100/r200/r400)
from the observed vial-bottom color, per the training-model report's plan.

Evaluation follows the report: recipe-grouped folds (the dataset's own
`split` column, 2 recipes per fold), carryover-suspected vials excluded
from training, MAE vs a guess-the-training-mean baseline.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

DATA = Path(__file__).resolve().parents[1] / "data" / "csi_vial_ai_dataset_v1"
OUT = Path(__file__).resolve().parents[1] / "outputs"
OUT.mkdir(exist_ok=True)

df = pd.read_csv(DATA / "vials.csv")
df = df[df["is_labeled"] == True].copy()  # noqa: E712  (video 5 only, 30 vials)

targets = ["t100_ml", "t200_ml", "t400_ml"]
df[["r100", "r200", "r400"]] = df[targets].div(df["total_ml"], axis=0)
Y_cols = ["r200", "r400"]  # predict two; r100 = 1 - sum, as in the report's plan

rgb = df[["obs_r", "obs_g", "obs_b"]].to_numpy(float)
feature_sets = {
    "raw_rgb_0_1": rgb / 255.0,
    "absorbance_no_white_ref": -np.log10(np.clip(rgb / 255.0, 1e-3, 1.0)),
    "lab": df[["obs_lab_l", "obs_lab_a", "obs_lab_b"]].to_numpy(float),
}

Y = df[Y_cols].to_numpy(float)
folds = df["split"].to_numpy()
fold_values = sorted(df["split"].unique())
train_mask_for_baseline = ~df["carryover_suspected"].astype(bool)

results = {}
for feat_name, X in feature_sets.items():
    pred = np.full_like(Y, np.nan)
    baseline_pred = np.full_like(Y, np.nan)
    for f in fold_values:
        te = folds == f
        tr = (~te) & train_mask_for_baseline.to_numpy()
        if tr.sum() < 3 or te.sum() == 0:
            continue
        model = RidgeCV(alphas=np.logspace(-3, 3, 13))
        model.fit(X[tr], Y[tr])
        pred[te] = np.clip(model.predict(X[te]), 0, 1)
        baseline_pred[te] = Y[tr].mean(axis=0)

    valid = ~np.isnan(pred).any(axis=1)
    mae_model = np.abs(pred[valid] - Y[valid]).mean(axis=0)
    mae_baseline = np.abs(baseline_pred[valid] - Y[valid]).mean(axis=0)
    results[feat_name] = {
        "n_eval": int(valid.sum()),
        "mae_model_r200_r400": mae_model.tolist(),
        "mae_baseline_r200_r400": mae_baseline.tolist(),
        "mae_model_mean": float(mae_model.mean()),
        "mae_baseline_mean": float(mae_baseline.mean()),
    }

print(json.dumps(results, indent=2))
(OUT / "model4_baseline_results.json").write_text(json.dumps(results, indent=2))

# Anomaly check: how far off are the carryover-suspected vials under the best feature set?
best_feat = min(results, key=lambda k: results[k]["mae_model_mean"])
print(f"\nBest feature set: {best_feat}")
X_best = feature_sets[best_feat]
model = RidgeCV(alphas=np.logspace(-3, 3, 13)).fit(
    X_best[train_mask_for_baseline.to_numpy()], Y[train_mask_for_baseline.to_numpy()]
)
carry_idx = df["carryover_suspected"].astype(bool).to_numpy()
if carry_idx.any():
    pred_carry = np.clip(model.predict(X_best[carry_idx]), 0, 1)
    err_carry = np.abs(pred_carry - Y[carry_idx]).mean(axis=1)
    print("Carryover-suspected vials, per-vial mean abs error (r200,r400):")
    for vuid, e in zip(df.loc[carry_idx, "vial_uid"], err_carry):
        print(f"  {vuid}: {e:.3f}")
