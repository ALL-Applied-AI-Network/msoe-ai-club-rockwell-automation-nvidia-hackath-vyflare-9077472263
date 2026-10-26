"""Write a model bundle from the team's notebook results.

Use from a notebook after fitting:

    import sys; sys.path.append("path/to/fluidcheck-service/scripts")
    from export_bundle import export_bundle
    export_bundle("path/to/fluidcheck-service/model_bundle",
                  version="0.2.0",
                  dyes={"t200": orange_rgb_absorbance, "t400": blue_rgb_absorbance},
                  residue_ml=fitted_vr,
                  vial_roi=[x, y, w, h],
                  fitted_on="video 5, recipes 5-14 (3rd vials)")

Then restart the API. Running this file directly writes the placeholder bundle.
"""
import json
from datetime import date
from pathlib import Path

VIDEO5_RECIPES = [
    {"id": "5", "t100_ml": 10, "t200_ml": 10, "t400_ml": 10},
    {"id": "6", "t100_ml": 30, "t200_ml": 10, "t400_ml": 0},
    {"id": "7", "t100_ml": 20, "t200_ml": 0, "t400_ml": 50},
    {"id": "8", "t100_ml": 20, "t200_ml": 20, "t400_ml": 20},
    {"id": "9", "t100_ml": 10, "t200_ml": 35, "t400_ml": 35},
    {"id": "10", "t100_ml": 45, "t200_ml": 15, "t400_ml": 15},
    {"id": "11", "t100_ml": 10, "t200_ml": 10, "t400_ml": 50},
    {"id": "12", "t100_ml": 10, "t200_ml": 50, "t400_ml": 10},
    {"id": "13", "t100_ml": 0, "t200_ml": 50, "t400_ml": 20},
    {"id": "14", "t100_ml": 60, "t200_ml": 0, "t400_ml": 10},
]


def _list(v):
    return [round(float(x), 5) for x in v]


def export_bundle(
    out_dir,
    version: str,
    dyes: dict,
    residue_ml: float,
    vial_roi: list,
    fitted_on: str,
    reference_white_rgb=(230, 230, 230),
    thresholds=None,
    known_recipes=None,
    ml_per_px=None,
    volume_calibrated=False,
    notes="",
):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "created": date.today().isoformat(),
        "fitted_on": fitted_on,
        "notes": notes,
    }
    config = {
        "vial_roi": [int(v) for v in vial_roi],
        "glare_cutoff": 245,
        "liquid_absorbance_min": 0.03,
        "min_liquid_pixels": 200,
        "ml_per_px": ml_per_px,
        "volume_calibrated": volume_calibrated,
    }
    params = {
        "dyes": {k: _list(v) for k, v in dyes.items()},
        "residue_ml": float(residue_ml),
        "reference_white_rgb": [int(c) for c in reference_white_rgb],
        "thresholds": thresholds or {"watch_delta_e": 3.0, "flag_delta_e": 5.0, "volume_tolerance_ml": 5.0},
        "known_recipes": known_recipes if known_recipes is not None else VIDEO5_RECIPES,
    }
    for name, data in (("manifest.json", manifest), ("config.json", config), ("params.json", params)):
        (out / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    # Placeholder values so the API runs before the real fit exists.
    target = Path(__file__).resolve().parent.parent / "model_bundle"
    export_bundle(
        target,
        version="0.0.1-placeholder",
        dyes={"t200": [0.04, 0.45, 1.2], "t400": [1.3, 0.5, 0.08]},
        residue_ml=10,
        vial_roi=[280, 150, 80, 220],
        fitted_on="placeholder values, not fitted",
        ml_per_px=0.4,
        notes="Replace with the notebook fit before trusting any verdict.",
    )
    print(f"wrote placeholder bundle to {target}")
