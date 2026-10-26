"""Verdict, cause ranking and explanation for one vial; risk for a queue."""
import math
from typing import Optional

import numpy as np

from .bundle import Bundle
from .color import (
    absorbance_to_lab,
    delta_e,
    expected_absorbance,
    first_vial_absorbance,
    lab_to_hex,
    level,
)
from .measure import Measurement
from .schemas import (
    Cause,
    ColorReading,
    DeltaE,
    QueueRiskResponse,
    Recipe,
    TransitionRisk,
    VialResult,
)


def _reading(lab: np.ndarray, volume_ml: Optional[float] = None) -> ColorReading:
    return ColorReading(
        lab=[round(float(v), 2) for v in lab], hex=lab_to_hex(lab), volume_ml=volume_ml
    )


def _same_mix(a: Recipe, b: Recipe) -> bool:
    return (a.t100_ml, a.t200_ml, a.t300_ml, a.t400_ml) == (b.t100_ml, b.t200_ml, b.t300_ml, b.t400_ml)


def diagnose(
    m: Measurement,
    recipe: Recipe,
    bundle: Bundle,
    prev: Optional[Recipe] = None,
    batch_position: Optional[int] = None,
    tank_flags: Optional[list[str]] = None,
    vial_id: Optional[str] = None,
) -> VialResult:
    tank_flags = tank_flags or []
    t = bundle.thresholds

    exp_lab = absorbance_to_lab(expected_absorbance(recipe, bundle), bundle)
    de_exp = delta_e(m.lab, exp_lab)

    carry_lab, de_carry = None, None
    if prev is not None and not _same_mix(prev, recipe):
        carry_lab = absorbance_to_lab(first_vial_absorbance(prev, recipe, bundle), bundle)
        de_carry = delta_e(m.lab, carry_lab)

    nearest_id, de_other = None, None
    for other in bundle.known_recipes:
        if other.id == recipe.id or _same_mix(other, recipe):
            continue
        d = delta_e(m.lab, absorbance_to_lab(expected_absorbance(other, bundle), bundle))
        if de_other is None or d < de_other:
            nearest_id, de_other = other.id, d

    vol_err = None
    if bundle.config.get("volume_calibrated") and m.volume_ml is not None:
        vol_err = m.volume_ml - recipe.total_ml

    # --- verdict -------------------------------------------------------------
    verdict = level(de_exp, bundle)
    if vol_err is not None and abs(vol_err) > t["volume_tolerance_ml"]:
        verdict = "flag"
    if tank_flags and verdict == "pass":
        verdict = "watch"

    # --- cause ranking (simple rules; replace with the team's scorer) ---------
    causes: list[Cause] = []
    if verdict == "pass":
        causes.append(Cause(cause="none", score=1.0, evidence=f"within {t['watch_delta_e']} ΔE of expected"))
    else:
        raw: dict[str, tuple[float, str]] = {}
        if de_carry is not None and batch_position in (1, 2) and de_carry < de_exp:
            weight = 1.0 if batch_position == 1 else 0.5
            raw["carryover"] = (
                weight * math.exp(-de_carry / 5),
                f"vial {batch_position} after recipe {prev.id}; "
                f"{de_carry:.1f} ΔE from the carryover prediction vs {de_exp:.1f} from clean",
            )
        if de_other is not None and de_other < de_exp:
            raw["wrong_recipe"] = (
                0.8 * math.exp(-de_other / 5),
                f"closest to recipe {nearest_id} ({de_other:.1f} ΔE)",
            )
        if vol_err is not None and abs(vol_err) > t["volume_tolerance_ml"]:
            raw["volume"] = (0.9, f"estimated {m.volume_ml} mL vs {recipe.total_ml:g} mL in the recipe")
        if tank_flags:
            raw["tank_state"] = (0.8, "tank camera: " + ", ".join(tank_flags))
        meas_weight = 0.4 if (m.glare_fraction > 0.3 or m.liquid_pixels == 0) else 0.1
        raw["measurement"] = (meas_weight, f"glare on {m.glare_fraction:.0%} of the vial region")

        total = sum(w for w, _ in raw.values())
        for name, (w, ev) in sorted(raw.items(), key=lambda kv: -kv[1][0]):
            score = round(w / total, 2)
            if score >= 0.02:
                causes.append(Cause(cause=name, score=score, evidence=ev))

    return VialResult(
        vial_id=vial_id,
        recipe_id=recipe.id,
        prev_recipe_id=prev.id if prev else None,
        batch_position=batch_position,
        verdict=verdict,
        measured=_reading(m.lab, m.volume_ml),
        expected=_reading(exp_lab, recipe.total_ml),
        carryover_prediction=_reading(carry_lab) if carry_lab is not None else None,
        delta_e=DeltaE(
            vs_expected=round(de_exp, 2),
            vs_carryover=round(de_carry, 2) if de_carry is not None else None,
            nearest_other_recipe=round(de_other, 2) if de_other is not None else None,
            nearest_other_recipe_id=nearest_id,
        ),
        tank_flags=tank_flags,
        causes=causes,
        explanation=_explain(verdict, causes, recipe, prev, de_exp),
        explanation_source="template",
        model_version=bundle.version,
    )


def _explain(verdict: str, causes: list[Cause], recipe: Recipe, prev: Optional[Recipe], de_exp: float) -> str:
    """Template explanation. Replace with a Cosmos Reason call; keep this as the fallback."""
    if verdict == "pass":
        return f"Vial matches recipe {recipe.id} ({de_exp:.1f} ΔE from expected)."
    top = causes[0].cause if causes else "measurement"
    opening = f"Vial is {de_exp:.1f} ΔE away from the expected colour for recipe {recipe.id}."
    reasons = {
        "carryover": f" It follows recipe {prev.id if prev else '?'} and matches the predicted mix with "
        "leftover liquid from the shared mixing path. Later vials of this batch should come out clean.",
        "wrong_recipe": " Its colour is closer to another recipe; check the queue and the vial's identity.",
        "volume": " The fill level does not match the recipe volume; check for a short dose or a spill.",
        "tank_state": " The tank camera reports a problem; check tank contents and levels.",
        "measurement": " No clear process cause; check the image for glare, labels or a misplaced vial.",
    }
    return opening + reasons.get(top, "")


# --- queue (pre-fill) risk ----------------------------------------------------

def recipe_warnings(r: Recipe) -> list[str]:
    """Operating limits from the station brief."""
    w = []
    if r.total_ml > 80:
        w.append(f"total {r.total_ml:g} mL exceeds the 80 mL vial limit")
    if r.t200_ml > 50:
        w.append(f"T-200 {r.t200_ml:g} mL exceeds 50 mL (can fault the system)")
    if r.t300_ml > 0:
        w.append("T-300 must not be used")
    for name, ml in (("T-100", r.t100_ml), ("T-200", r.t200_ml), ("T-400", r.t400_ml)):
        if 0 < ml < 10:
            w.append(f"{name} {ml:g} mL is below the 10 mL practical minimum")
    return w


def queue_risk(queue: list[Recipe], bundle: Bundle, last_run: Optional[Recipe] = None) -> QueueRiskResponse:
    seq = ([last_run] if last_run else []) + list(queue)
    transitions = []
    for prev, nxt in zip(seq, seq[1:]):
        if _same_mix(prev, nxt):
            continue
        clean = absorbance_to_lab(expected_absorbance(nxt, bundle), bundle)
        first = absorbance_to_lab(first_vial_absorbance(prev, nxt, bundle), bundle)
        de = delta_e(first, clean)
        risk = level(de, bundle)
        advice = {
            "pass": "No visible carryover expected.",
            "watch": f"First vial of {nxt.id} may be slightly off-colour from {prev.id} residue.",
            "flag": f"First vial of {nxt.id} will likely be off-colour from {prev.id} residue. "
            "Consider a purge vial or a different order (plant manager decision).",
        }[risk]
        transitions.append(
            TransitionRisk(
                from_recipe_id=prev.id,
                to_recipe_id=nxt.id,
                predicted_first_vial_delta_e=round(de, 2),
                risk=risk,
                advice=advice,
            )
        )
    warnings = {r.id: recipe_warnings(r) for r in queue if recipe_warnings(r)}
    return QueueRiskResponse(transitions=transitions, recipe_warnings=warnings, model_version=bundle.version)
