"""Error/anomaly detector built on top of the Model 4 physics baseline.

Idea: fit the absorbance -> mix-ratio regression on vials that look normal,
then flag any vial whose prediction residual is unusually large. This is a
learned anomaly score rather than the dataset's hardcoded
expected-color-vs-observed-color rule, so it should generalize better
(e.g. to new recipes where "expected color" isn't a simple lookup).

Validated against the two labels the dataset already carries:
- color_match == False  (rule-based color mismatch, 7 of 30 vials)
- carryover_suspected    (first-after-change AND mismatched, 5 of 30 vials)
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
df = df[df["is_labeled"] == True].copy()  # noqa: E712
df[["r100", "r200", "r400"]] = df[["t100_ml", "t200_ml", "t400_ml"]].div(df["total_ml"], axis=0)

rgb = df[["obs_r", "obs_g", "obs_b"]].to_numpy(float)
absorb = -np.log10(np.clip(rgb / 255.0, 1e-3, 1.0))
X = absorb
Y = df[["r200", "r400"]].to_numpy(float)

recipes = df["recipe_id"].to_numpy()
clean = ~df["carryover_suspected"].astype(bool).to_numpy()  # train only on non-carryover vials

residual = np.full(len(df), np.nan)
for r in np.unique(recipes):
    te = recipes == r
    tr = (~te) & clean
    if tr.sum() < 2 or te.sum() == 0:
        continue
    model = RidgeCV(alphas=np.logspace(-3, 3, 13)).fit(X[tr], Y[tr])
    pred = np.clip(model.predict(X[te]), 0, 1)
    residual[te] = np.abs(pred - Y[te]).mean(axis=1)

df["residual"] = residual
valid = ~df["residual"].isna()

# Threshold: mean + 1 std of residuals on vials that are NOT already flagged by the rule,
# i.e. calibrate the anomaly cutoff on vials we trust are normal.
normal_mask = valid & (~df["carryover_suspected"].astype(bool)) & df["color_match"]
thresh = df.loc[normal_mask, "residual"].mean() + df.loc[normal_mask, "residual"].std()
df["flagged_by_model"] = valid & (df["residual"] > thresh)

print(f"Anomaly threshold (mean+1std of clean residuals): {thresh:.3f}\n")

cols = ["vial_uid", "recipe_id", "residual", "flagged_by_model", "color_match", "carryover_suspected", "first_after_recipe_change"]
report = df.loc[valid, cols].sort_values("residual", ascending=False)
print(report.to_string(index=False))

# Agreement with the two existing rule-based labels
for label_col in ["carryover_suspected", "color_match"]:
    y_true = (~df[label_col].astype(bool)) if label_col == "color_match" else df[label_col].astype(bool)
    y_true = y_true[valid]
    y_pred = df.loc[valid, "flagged_by_model"]
    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"\nvs {label_col}: TP={tp} FP={fp} FN={fn} TN={tn}  precision={precision:.2f} recall={recall:.2f}")

report.to_csv(OUT / "model4_anomaly_report.csv", index=False)
