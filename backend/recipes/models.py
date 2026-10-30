"""Validated recipe definitions, independent of inference and storage."""

from dataclasses import dataclass
import math
from typing import Literal


RecipeCollection = Literal["INTENDED", "UNMATCHED"]


def _validate_text(name: str, value: str | None, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string" + (" or None" if optional else ""))
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


@dataclass(frozen=True)
class Dispense:
    """One completed dispense; color vocabulary and matching are defined separately."""

    color: str
    duration_seconds: float
    source: str | None = None

    def __post_init__(self) -> None:
        _validate_text("color", self.color)
        _validate_text("source", self.source, optional=True)
        duration = self.duration_seconds
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise TypeError("duration_seconds must be a number")
        try:
            valid = duration > 0 and math.isfinite(duration)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("duration_seconds must be positive and finite")


@dataclass(frozen=True)
class Recipe:
    """One reference pattern. Identifier uniqueness is enforced by storage.

    A list of dispenses is accepted and copied to an immutable tuple. Tuple
    position defines order; source/material identity is optional. To change a
    recipe, construct a replacement and persist it through the repository.
    """

    id: int
    collection: RecipeCollection
    dispenses: tuple[Dispense, ...]
    final_color: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or not isinstance(self.id, int):
            raise TypeError("id must be an integer")
        if self.id <= 0:
            raise ValueError("id must be positive")
        if self.collection not in ("INTENDED", "UNMATCHED"):
            raise ValueError("collection must be INTENDED or UNMATCHED")
        if not isinstance(self.dispenses, (list, tuple)):
            raise TypeError("dispenses must be an ordered list or tuple")
        if not self.dispenses:
            raise ValueError("a completed recipe must contain at least one dispense")
        if any(not isinstance(dispense, Dispense) for dispense in self.dispenses):
            raise TypeError("each dispense must be a Dispense object")
        _validate_text("final_color", self.final_color, optional=True)
        object.__setattr__(self, "dispenses", tuple(self.dispenses))

    @property
    def dispense_count(self) -> int:
        """Number of dispenses, always consistent with the ordered sequence."""
        return len(self.dispenses)


@dataclass(frozen=True)
class VialObservation:
    """Snapshot supplied by the tracker; missing final data is not a new recipe.

    Partial snapshots may have no dispenses or final color. Individual Dispense
    objects must contain valid measurements; a tracker must not fabricate them
    for unavailable duration/color evidence. Mark filling_complete only after
    all required dispense measurements have been finalized.
    """

    run_id: str
    vial_id: str
    dispenses: tuple[Dispense, ...]
    final_color: str | None = None
    filling_complete: bool = False

    def __post_init__(self) -> None:
        _validate_text("run_id", self.run_id)
        _validate_text("vial_id", self.vial_id)
        _validate_text("final_color", self.final_color, optional=True)
        if not isinstance(self.filling_complete, bool):
            raise TypeError("filling_complete must be a boolean")
        if not isinstance(self.dispenses, (list, tuple)):
            raise TypeError("dispenses must be an ordered list or tuple")
        if any(not isinstance(dispense, Dispense) for dispense in self.dispenses):
            raise TypeError("each dispense must be a Dispense object")
        object.__setattr__(self, "dispenses", tuple(self.dispenses))
