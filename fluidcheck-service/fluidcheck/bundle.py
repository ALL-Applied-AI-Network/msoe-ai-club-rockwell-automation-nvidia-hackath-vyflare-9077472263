"""Load the model bundle: the folder of files the team's notebooks produce.

model_bundle/
  manifest.json   version, date, what the parameters were fitted on
  config.json     camera geometry: vial region, glare cutoff, volume scale
  params.json     dye colours, residue volume, thresholds, known recipes

Swapping in a new model = replacing this folder and restarting the API.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .schemas import Recipe

REQUIRED = {
    "manifest.json": ["version"],
    "config.json": ["vial_roi"],
    "params.json": ["dyes", "residue_ml", "reference_white_rgb", "thresholds"],
}


@dataclass
class Bundle:
    path: Path
    manifest: dict
    config: dict
    params: dict
    known_recipes: list[Recipe] = field(default_factory=list)

    @property
    def version(self) -> str:
        return str(self.manifest["version"])

    def dye(self, tank: str) -> np.ndarray:
        """Absorbance (R, G, B) of a vial that is 100% this tank's dye."""
        return np.asarray(self.params["dyes"].get(tank, [0.0, 0.0, 0.0]), dtype=float)

    @property
    def thresholds(self) -> dict:
        defaults = {"watch_delta_e": 3.0, "flag_delta_e": 5.0, "volume_tolerance_ml": 5.0}
        return {**defaults, **self.params["thresholds"]}


def load_bundle(path: str | Path) -> Bundle:
    path = Path(path)
    loaded = {}
    for name, keys in REQUIRED.items():
        file = path / name
        if not file.exists():
            raise FileNotFoundError(f"model bundle is missing {file}")
        data = json.loads(file.read_text(encoding="utf-8"))
        missing = [k for k in keys if k not in data]
        if missing:
            raise ValueError(f"{file} is missing keys: {missing}")
        loaded[name] = data

    params = loaded["params.json"]
    recipes = [Recipe.model_validate(r) for r in params.get("known_recipes", [])]
    return Bundle(
        path=path,
        manifest=loaded["manifest.json"],
        config=loaded["config.json"],
        params=params,
        known_recipes=recipes,
    )
