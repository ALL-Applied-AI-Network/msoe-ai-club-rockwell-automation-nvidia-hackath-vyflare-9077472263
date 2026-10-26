"""Colour physics: expected colour from a recipe, carryover, and distances.

All absorbance vectors are in (R, G, B) order. Absorbance adds linearly with
dye concentration (Beer-Lambert), so a recipe's colour is a weighted sum of
the two dyes; clear T-100 only dilutes.
"""
import numpy as np
from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab

from .bundle import Bundle
from .schemas import Recipe


def expected_absorbance(recipe: Recipe, bundle: Bundle) -> np.ndarray:
    total = recipe.total_ml
    if total <= 0:
        raise ValueError(f"recipe {recipe.id} has no volume")
    return (recipe.t200_ml / total) * bundle.dye("t200") + (
        recipe.t400_ml / total
    ) * bundle.dye("t400")


def first_vial_absorbance(prev: Recipe, nxt: Recipe, bundle: Bundle) -> np.ndarray:
    """First vial after a recipe change: residue of `prev` mixed into `nxt`."""
    vr = float(bundle.params["residue_ml"])
    v = nxt.total_ml
    return (vr * expected_absorbance(prev, bundle) + v * expected_absorbance(nxt, bundle)) / (vr + v)


def absorbance_to_lab(absorbance: np.ndarray, bundle: Bundle) -> np.ndarray:
    """Colour the liquid would show in front of the reference white background."""
    white = np.asarray(bundle.params["reference_white_rgb"], dtype=float) / 255.0
    rgb = np.clip(white * np.power(10.0, -np.asarray(absorbance, dtype=float)), 0, 1)
    return rgb2lab(rgb.reshape(1, 1, 3)).reshape(3)


def lab_to_hex(lab: np.ndarray) -> str:
    rgb = lab2rgb(np.asarray(lab, dtype=float).reshape(1, 1, 3)).reshape(3)
    r, g, b = (int(round(c * 255)) for c in np.clip(rgb, 0, 1))
    return f"#{r:02x}{g:02x}{b:02x}"


def delta_e(lab1: np.ndarray, lab2: np.ndarray) -> float:
    return float(deltaE_ciede2000(np.asarray(lab1, float), np.asarray(lab2, float)))


def level(de: float, bundle: Bundle) -> str:
    t = bundle.thresholds
    if de >= t["flag_delta_e"]:
        return "flag"
    if de >= t["watch_delta_e"]:
        return "watch"
    return "pass"
