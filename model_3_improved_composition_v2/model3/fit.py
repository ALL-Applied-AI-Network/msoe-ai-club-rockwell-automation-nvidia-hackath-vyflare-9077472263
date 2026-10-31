"""Training: linear least squares from absorbance (A_R, A_G, A_B) to the t200 and t400 fractions.

t100 = 1 - t200 - t400, then the inference adapter projects onto the valid-mix simplex. There are no
tuned hyperparameters. Training rows are finished frames (4 per vial) of training-eligible vials only.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json

import numpy as np
import pandas as pd

FEATURES = ["A_R", "A_G", "A_B"]


def fit_linear(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    Xb = np.c_[X, np.ones(len(X))]
    sol, *_ = np.linalg.lstsq(Xb, Y, rcond=None)
    return sol[:-1].T, sol[-1]          # W: (outputs, features), b: (outputs,)


def fit_checkpoint(frames: pd.DataFrame, cfg: dict, description: str) -> dict:
    X = frames[FEATURES].to_numpy(float)
    W, b = fit_linear(X, frames[["r200", "r400"]].to_numpy(float))
    weights = {"coef": np.round(W, 6).tolist(), "intercept": np.round(b, 6).tolist()}
    return {
        "model_id": cfg["model_id"],
        "model_version": cfg["model_version"],
        "features": FEATURES,
        "targets": ["t200", "t400"],
        "derived": "t100 = 1 - t200 - t400, then Euclidean projection onto the unit simplex",
        **weights,
        "sha256_of_weights": hashlib.sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest(),
        "training_feature_min": np.round(X.min(0), 4).tolist(),
        "training_feature_max": np.round(X.max(0), 4).tolist(),
        "trained_on": description,
        "training_vials": sorted(frames.vial_uid.unique().tolist()),
        "training_rows": int(len(frames)),
        "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
