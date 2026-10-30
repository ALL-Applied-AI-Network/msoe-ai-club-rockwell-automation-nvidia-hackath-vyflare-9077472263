"""Read-only recipe HTTP routes backed by the application's shared repository."""

import re

from flask import Blueprint, jsonify, request

from .models import Recipe
from .recipe_repository import RecipeRepository


def recipe_to_dict(recipe: Recipe) -> dict:
    """Stable API representation, including derived metadata."""
    return {
        "id": recipe.id,
        "collection": recipe.collection,
        "dispense_count": recipe.dispense_count,
        "dispenses": [
            {"color": dispense.color, "duration_seconds": dispense.duration_seconds,
             "source": dispense.source}
            for dispense in recipe.dispenses
        ],
        "final_color": recipe.final_color,
    }


def create_recipe_blueprint(repository: RecipeRepository) -> Blueprint:
    blueprint = Blueprint("recipe_api", __name__, url_prefix="/api/recipes")

    @blueprint.get("")
    def list_recipes():
        if set(request.args) - {"collection"} or len(request.args.getlist("collection")) > 1:
            return jsonify(error="Only one optional collection parameter is supported"), 400
        collection = request.args.get("collection", "INTENDED")
        if collection not in ("INTENDED", "UNMATCHED"):
            return jsonify(error="collection must be INTENDED or UNMATCHED"), 400
        recipes = repository.list_recipes(collection)
        return jsonify(collection=collection, recipes=[recipe_to_dict(recipe) for recipe in recipes])

    @blueprint.get("/<recipe_id>")
    def get_recipe(recipe_id: str):
        if not re.fullmatch(r"[1-9][0-9]*", recipe_id):
            return jsonify(error="recipe_id must be a positive integer without leading zeros"), 400
        try:
            identifier = int(recipe_id)
        except ValueError:
            return jsonify(error="recipe_id is too long"), 400
        recipe = repository.get_recipe(identifier)
        if recipe is None:
            return jsonify(error="Recipe not found"), 404
        return jsonify(recipe=recipe_to_dict(recipe))

    return blueprint
