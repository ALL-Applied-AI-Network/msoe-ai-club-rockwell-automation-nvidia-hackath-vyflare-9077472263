"""Request and response shapes shared by the API and the front end.

These models ARE the contract in section 5 of the team plan. Change a field
name here only with the whole team's agreement: the C# client mirrors them.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["pass", "watch", "flag"]
CauseName = Literal[
    "carryover", "wrong_recipe", "volume", "tank_state", "measurement", "none"
]


class Recipe(BaseModel):
    """Millilitres drawn from each tank. Tanks are identified by number, not colour."""

    id: str
    t100_ml: float = Field(0, ge=0, description="T-100, clear diluent")
    t200_ml: float = Field(0, ge=0, description="T-200, orange")
    t300_ml: float = Field(0, ge=0, description="T-300, out of service: must be 0")
    t400_ml: float = Field(0, ge=0, description="T-400, blue")

    @property
    def total_ml(self) -> float:
        return self.t100_ml + self.t200_ml + self.t300_ml + self.t400_ml


class ColorReading(BaseModel):
    lab: list[float] = Field(description="CIELAB [L, a, b]")
    hex: str = Field(description="Approximate display colour, e.g. #3a7bd5")
    volume_ml: Optional[float] = None


class DeltaE(BaseModel):
    """CIEDE2000 colour distances. Under 2 is barely visible; over 5 is clearly different."""

    vs_expected: float
    vs_carryover: Optional[float] = None
    nearest_other_recipe: Optional[float] = None
    nearest_other_recipe_id: Optional[str] = None


class Cause(BaseModel):
    cause: CauseName
    score: float = Field(ge=0, le=1)
    evidence: str


class VialResult(BaseModel):
    vial_id: Optional[str] = None
    recipe_id: str
    prev_recipe_id: Optional[str] = None
    batch_position: Optional[int] = None
    verdict: Verdict
    measured: ColorReading
    expected: ColorReading
    carryover_prediction: Optional[ColorReading] = None
    delta_e: DeltaE
    tank_flags: list[str] = []
    causes: list[Cause]
    explanation: str
    explanation_source: Literal["template", "cosmos"] = "template"
    model_version: str


class QueueRiskRequest(BaseModel):
    queue: list[Recipe] = Field(description="Recipes in the order they will run")
    last_run: Optional[Recipe] = Field(None, description="The recipe that ran just before the queue")


class TransitionRisk(BaseModel):
    from_recipe_id: str
    to_recipe_id: str
    predicted_first_vial_delta_e: float
    risk: Verdict
    advice: str


class QueueRiskResponse(BaseModel):
    transitions: list[TransitionRisk]
    recipe_warnings: dict[str, list[str]] = Field(
        default_factory=dict, description="Operating-limit problems per recipe id"
    )
    model_version: str
