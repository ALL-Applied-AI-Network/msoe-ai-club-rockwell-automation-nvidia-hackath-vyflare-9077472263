"""Read-only inspection endpoints and explicit JSON representations."""

from dataclasses import asdict
from datetime import timezone

from flask import Blueprint, jsonify

from .api import _recipe_id, recipe_to_dict
from .inspection_models import VialInspection
from .inspection_repository import InspectionRepository
from .recipe_matcher import MatchResult
from .recipe_repository import RecipeRepository


def comparison_to_dict(comparison: MatchResult | None) -> dict | None:
    if comparison is None:
        return None
    # asdict recursively converts Dispense objects used in extra/missing-field
    # differences as well as the configuration snapshot.
    data = asdict(comparison)
    data["feature_scores"] = dict(comparison.feature_scores)
    data["differences"] = list(data["differences"])
    data["reasons"] = list(comparison.reasons)
    return data


def inspection_to_dict(inspection: VialInspection) -> dict:
    observation = asdict(inspection.observation)
    observation["dispense_count"] = len(inspection.observation.dispenses)
    return {
        "inspection_id": inspection.inspection_id,
        "observation": observation,
        "recipe_id": inspection.recipe_id,
        "recipe_collection": inspection.recipe_collection,
        "verification_status": inspection.verification_status,
        "intended_comparison": comparison_to_dict(inspection.intended_comparison),
        "unmatched_comparison": comparison_to_dict(inspection.unmatched_comparison),
        "created_new_recipe": inspection.created_new_recipe,
        "inspected_at": inspection.inspected_at.astimezone(timezone.utc).isoformat(),
        "recipe_snapshot": recipe_to_dict(inspection.recipe_snapshot) if inspection.recipe_snapshot else None,
    }


def create_inspection_blueprint(recipes: RecipeRepository,
                                inspections: InspectionRepository) -> Blueprint:
    blueprint = Blueprint("inspection_api", __name__, url_prefix="/api")

    @blueprint.get("/inspections/<inspection_id>")
    def get_inspection(inspection_id: str):
        if not inspection_id.strip():
            return jsonify(error="inspection_id must not be blank"), 400
        inspection = inspections.get_inspection(inspection_id)
        if inspection is None:
            return jsonify(error="Inspection not found"), 404
        return jsonify(inspection=inspection_to_dict(inspection))

    @blueprint.get("/recipes/<recipe_id>/inspections")
    def list_recipe_inspections(recipe_id: str):
        identifier = _recipe_id(recipe_id)
        if recipes.get_recipe(identifier) is None:
            return jsonify(error="Recipe not found"), 404
        occurrences = inspections.list_inspections_for_recipe(identifier)
        return jsonify(recipe_id=identifier, count=len(occurrences),
                       inspections=[inspection_to_dict(item) for item in occurrences])

    return blueprint
