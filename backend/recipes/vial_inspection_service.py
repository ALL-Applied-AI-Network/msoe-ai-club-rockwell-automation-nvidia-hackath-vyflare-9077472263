"""Inspect snapshots without camera capture, model inference, or HTTP handling."""

from datetime import datetime, timezone
from uuid import uuid4

from .inspection_models import VialInspection
from .inspection_repository import InspectionRepository
from .models import VialObservation, _validate_text
from .recipe_matcher import RecipeMatcher
from .recipe_repository import RecipeRepository


class VialInspectionService:
    """Intended-first verification with unmatched pattern reuse and learning.

    Share the same repositories across service instances. Recipe transactions
    serialize matching/creation with collection moves; inspection transactions
    preserve both records together on failure. Always lock recipes first.
    """

    def __init__(self, recipes: RecipeRepository, inspections: InspectionRepository,
                 matcher: RecipeMatcher | None = None) -> None:
        if not isinstance(recipes, RecipeRepository):
            raise TypeError("recipes must be a RecipeRepository")
        if not isinstance(inspections, InspectionRepository):
            raise TypeError("inspections must be an InspectionRepository")
        if matcher is not None and not isinstance(matcher, RecipeMatcher):
            raise TypeError("matcher must be a RecipeMatcher")
        self.recipes = recipes
        self.inspections = inspections
        self.matcher = matcher if matcher is not None else RecipeMatcher()

    def inspect(self, observation: VialObservation,
                inspection_id: str | None = None) -> VialInspection:
        """Return one result per run/vial, with a caller ID or generated UUID.

        An identical retry returns the stored result even after recipe/config
        changes. Conflicting IDs or changed observations raise ValueError;
        historical inspections are never silently overwritten or reclassified.
        """
        if not isinstance(observation, VialObservation):
            raise TypeError("observation must be a VialObservation")
        if inspection_id is not None:
            _validate_text("inspection_id", inspection_id)
        with self.recipes.transaction(), self.inspections.transaction():
            existing = self.inspections.get_for_vial(observation.run_id, observation.vial_id)
            if existing is not None:
                if (existing.observation != observation
                        or (inspection_id is not None and inspection_id != existing.inspection_id)):
                    raise ValueError("Run/vial already has a different inspection; history cannot be overwritten")
                return existing
            identifier = inspection_id if inspection_id is not None else str(uuid4())
            if self.inspections.get_inspection(identifier) is not None:
                raise ValueError("Inspection ID already belongs to another vial")

            intended = self.matcher.find_best_match(
                observation, self.recipes.list_recipes("INTENDED"), "INTENDED")
            unmatched = None
            linked = None
            created = False
            status = "INSUFFICIENT_DATA"
            if intended.status == "MATCH":
                linked = self.recipes.get_recipe(intended.candidate_recipe_id)
                status = "PASS"
            elif intended.status == "NO_MATCH":
                unmatched = self.matcher.find_best_match(
                    observation, self.recipes.list_recipes("UNMATCHED"), "UNMATCHED")
                if unmatched.status == "MATCH":
                    linked = self.recipes.get_recipe(unmatched.candidate_recipe_id)
                    status = "FAIL"
                elif unmatched.status == "NO_MATCH":
                    linked = self.recipes.create_unmatched_recipe(
                        observation.dispenses, observation.final_color)
                    created = True
                    status = "FAIL"
            inspection = VialInspection(
                inspection_id=identifier, observation=observation,
                recipe_id=linked.id if linked else None,
                recipe_collection=linked.collection if linked else None,
                verification_status=status, intended_comparison=intended,
                unmatched_comparison=unmatched, created_new_recipe=created,
                inspected_at=datetime.now(timezone.utc), recipe_snapshot=linked,
            )
            return self.inspections.save_inspection(inspection)
