"""Historical inspection snapshots, independent of current recipe collection."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .models import Recipe, RecipeCollection, VialObservation, _validate_text
from .recipe_matcher import MatchResult


@dataclass(frozen=True)
class VialInspection:
    inspection_id: str
    observation: VialObservation
    recipe_id: int | None
    recipe_collection: RecipeCollection | None
    verification_status: Literal["PASS", "FAIL", "INSUFFICIENT_DATA"]
    intended_comparison: MatchResult
    unmatched_comparison: MatchResult | None
    created_new_recipe: bool
    inspected_at: datetime
    recipe_snapshot: Recipe | None = None

    def __post_init__(self) -> None:
        _validate_text("inspection_id", self.inspection_id)
        if not isinstance(self.observation, VialObservation):
            raise TypeError("observation must be a VialObservation")
        if not isinstance(self.intended_comparison, MatchResult):
            raise TypeError("intended_comparison must be a MatchResult")
        if self.intended_comparison.compared_collection != "INTENDED":
            raise ValueError("intended_comparison must search INTENDED")
        if self.unmatched_comparison is not None:
            if not isinstance(self.unmatched_comparison, MatchResult):
                raise TypeError("unmatched_comparison must be a MatchResult or None")
            if self.unmatched_comparison.compared_collection != "UNMATCHED":
                raise ValueError("unmatched_comparison must search UNMATCHED")
        if not isinstance(self.created_new_recipe, bool):
            raise TypeError("created_new_recipe must be a boolean")
        if not isinstance(self.inspected_at, datetime) or self.inspected_at.utcoffset() is None:
            raise ValueError("inspected_at must be a timezone-aware datetime")
        intended = self.intended_comparison
        unmatched = self.unmatched_comparison
        if self.verification_status == "PASS":
            valid = (intended.status == "MATCH" and unmatched is None
                     and self.recipe_collection == "INTENDED"
                     and self.recipe_id == intended.candidate_recipe_id
                     and not self.created_new_recipe)
        elif self.verification_status == "FAIL":
            valid = (intended.status == "NO_MATCH" and unmatched is not None
                     and self.recipe_collection == "UNMATCHED"
                     and ((self.created_new_recipe and unmatched.status == "NO_MATCH")
                          or (not self.created_new_recipe and unmatched.status == "MATCH"
                              and self.recipe_id == unmatched.candidate_recipe_id)))
        elif self.verification_status == "INSUFFICIENT_DATA":
            valid = (self.recipe_id is None and self.recipe_collection is None
                     and self.recipe_snapshot is None and not self.created_new_recipe
                     and ((intended.status == "INSUFFICIENT_DATA" and unmatched is None)
                          or (intended.status == "NO_MATCH" and unmatched is not None
                              and unmatched.status == "INSUFFICIENT_DATA")))
        else:
            raise ValueError("Unknown verification_status")
        if not valid:
            raise ValueError("Inspection classification must agree with comparison results")
        if self.recipe_collection is not None:
            if not isinstance(self.recipe_snapshot, Recipe):
                raise ValueError("A linked inspection requires a recipe snapshot")
            if (self.recipe_snapshot.id != self.recipe_id
                    or self.recipe_snapshot.collection != self.recipe_collection):
                raise ValueError("Recipe snapshot must agree with the historical recipe link")
