"""Synthetic frames: a grey station with a vial region that absorbs like a recipe."""
from pathlib import Path

import numpy as np

from fluidcheck import load_bundle

BUNDLE_DIR = Path(__file__).resolve().parent.parent / "model_bundle"


def bundle():
    return load_bundle(BUNDLE_DIR)


def make_frames(absorbance_rgb, fill_rows: int, roi=(280, 150, 80, 220), size=(480, 640), grey=200):
    """Empty and full BGR frames. The bottom `fill_rows` of the region hold liquid."""
    empty = np.full((*size, 3), grey, np.uint8)
    full = empty.copy().astype(float)
    x, y, w, h = roi
    t_rgb = np.power(10.0, -np.asarray(absorbance_rgb, float))
    t_bgr = t_rgb[::-1]
    full[y + h - fill_rows:y + h, x:x + w] *= t_bgr
    return empty, np.clip(np.round(full), 0, 255).astype(np.uint8)
