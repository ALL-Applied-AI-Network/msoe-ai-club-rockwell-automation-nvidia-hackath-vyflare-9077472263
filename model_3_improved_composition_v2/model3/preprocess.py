"""Shared preprocessing for training, evaluation and inference (one implementation, no copies).

Everything works on RGB uint8 arrays (H, W, 3). Callers using OpenCV must convert BGR -> RGB first;
load_rgb() does this for files.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or PACKAGE_ROOT / "config.json").read_text())


def load_rgb(path: str | Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))


def linear_light(u8: np.ndarray) -> np.ndarray:
    c = np.asarray(u8, dtype=float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb_from_linear(lin: float) -> float:
    c = 12.92 * lin if lin <= 0.0031308 else 1.055 * lin ** (1 / 2.4) - 0.055
    return float(c * 255)


def saturation_level(black_floor_srgb: float, headroom: float) -> float:
    """sRGB level below which a channel is saturated: within `headroom` x the floor's linear light."""
    return srgb_from_linear(headroom * float(linear_light(np.array([black_floor_srgb]))[0]))


def absorbance_features(empty_rgb: np.ndarray, full_rgb: np.ndarray, cfg: dict) -> dict:
    """Per-channel absorbance of the liquid in one finished frame relative to the empty-vial frame."""
    p, q = cfg["preprocessing"], cfg["quality"]
    x0, y0, x1, y1 = p["liquid_roi_xyxy"]
    e, f = empty_rgb[y0:y1, x0:x1], full_rgb[y0:y1, x0:x1]
    a = -np.log10((linear_light(f) + 1e-3) / (linear_light(e) + 1e-3))
    liquid = a.mean(2) > p["liquid_pixel_min_mean_absorbance"]
    coverage = float(liquid.mean())
    sel = liquid if liquid.sum() > 0 else np.ones(liquid.shape, bool)
    A = np.median(a[sel], 0)
    full_med = np.median(f[sel], 0)
    sat = full_med < saturation_level(q["black_floor_srgb"], q["saturation_headroom_linear"])
    return dict(A=A, liquid_coverage=coverage, full_median_rgb=full_med,
                saturated_channels="".join(c for c, s in zip("RGB", sat) if s))


def colour_stats(full_rgb: np.ndarray, crop_xyxy=(272, 270, 352, 415)) -> np.ndarray:
    """The original notebook's colour baseline: RGB mean and std over its vial crop."""
    x0, y0, x1, y1 = crop_xyxy
    c = full_rgb[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    return np.r_[c.mean(0), c.std(0)]


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection onto {x >= 0, sum x = 1}."""
    v = np.asarray(v, float)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, len(v) + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0)
