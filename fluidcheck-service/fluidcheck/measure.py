"""Turn an empty-vial frame and a full-vial frame into numbers.

Colour is measured as absorbance against the SAME pixels before the fill, so
the background behind the transparent vial and the room lighting cancel out.

Replace the fixed `vial_roi` with the team's segmentation model later: only
`liquid_mask()` needs to change.
"""
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from .bundle import Bundle
from .color import absorbance_to_lab


@dataclass
class Measurement:
    absorbance: np.ndarray          # (R, G, B)
    lab: np.ndarray
    volume_ml: Optional[float]
    liquid_pixels: int
    glare_fraction: float


def decode_image(data: bytes) -> np.ndarray:
    """Bytes of a JPEG/PNG -> BGR image (OpenCV's channel order)."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a readable image")
    return img


def _crop(img: np.ndarray, roi: list[int]) -> np.ndarray:
    x, y, w, h = roi
    if y + h > img.shape[0] or x + w > img.shape[1]:
        raise ValueError(f"vial_roi {roi} is outside the {img.shape[1]}x{img.shape[0]} image")
    return img[y:y + h, x:x + w]


def liquid_mask(absorbance_px: np.ndarray, keep: np.ndarray, bundle: Bundle) -> np.ndarray:
    """Pixels that contain liquid. Swap in an ONNX segmentation model here."""
    threshold = bundle.config.get("liquid_absorbance_min", 0.03)
    return keep & (absorbance_px.mean(axis=2) > threshold)


def measure(empty_bgr: np.ndarray, full_bgr: np.ndarray, bundle: Bundle) -> Measurement:
    if empty_bgr.shape != full_bgr.shape:
        raise ValueError("empty and full frames must be the same size")
    cfg = bundle.config
    roi = cfg["vial_roi"]
    empty = _crop(empty_bgr, roi).astype(float)[..., ::-1] + 1.0   # BGR -> RGB
    full = _crop(full_bgr, roi).astype(float)[..., ::-1] + 1.0

    keep = full.max(axis=2) < cfg.get("glare_cutoff", 245) + 1.0
    glare_fraction = float(1.0 - keep.mean())
    absorbance_px = -np.log10(full / empty)

    mask = liquid_mask(absorbance_px, keep, bundle)
    n_liquid = int(mask.sum())
    if n_liquid >= cfg.get("min_liquid_pixels", 200):
        absorbance = np.median(absorbance_px[mask], axis=0)
    else:
        # Clear or nearly clear liquid: no pixels stand out, so use the whole region.
        absorbance = np.median(absorbance_px[keep], axis=0) if keep.any() else np.zeros(3)
    absorbance = np.clip(absorbance, 0, None)

    return Measurement(
        absorbance=absorbance,
        lab=absorbance_to_lab(absorbance, bundle),
        volume_ml=_volume(mask, cfg),
        liquid_pixels=n_liquid,
        glare_fraction=glare_fraction,
    )


def _volume(mask: np.ndarray, cfg: dict) -> Optional[float]:
    """Crude fill level: highest row that is mostly liquid, measured from the
    bottom of the region. Assumes the region's bottom edge is the vial floor."""
    ml_per_px = cfg.get("ml_per_px")
    if not ml_per_px:
        return None
    rows = np.where(mask.mean(axis=1) > 0.5)[0]
    if rows.size == 0:
        return None
    height_px = mask.shape[0] - rows.min()
    return round(float(height_px * ml_per_px), 1)
