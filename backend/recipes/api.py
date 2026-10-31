"""Recipe HTTP routes backed by the application's shared repository."""

import hmac
import os
import re

from flask import Blueprint, abort, current_app, jsonify, request

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


def _recipe_id(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]*", value):
        abort(400, description="recipe_id must be a positive integer without leading zeros")
    try:
        return int(value)
    except ValueError:
        abort(400, description="recipe_id is too long")


def _management_actor() -> str:
    """Shared-token service principal; never trust actor fields from a client.

    Replace this boundary with verified per-user identity/permissions when that
    authentication system is introduced. The current token authorizes its holder
    to perform both management actions as the configured service actor.
    """
    token = os.getenv("INFERENCE_TOKEN", "")
    actor = current_app.config.get("RECIPE_MANAGEMENT_ACTOR")
    if not token or not isinstance(actor, str) or not actor.strip():
        abort(503, description="Recipe management requires INFERENCE_TOKEN and RECIPE_MANAGEMENT_ACTOR configuration")
    if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
        abort(401, description="Recipe management credentials required")
    return actor.strip()


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
        recipe = repository.get_recipe(_recipe_id(recipe_id))
        if recipe is None:
            return jsonify(error="Recipe not found"), 404
        return jsonify(recipe=recipe_to_dict(recipe))

    @blueprint.get("/<recipe_id>/history")
    def get_history(recipe_id: str):
        identifier = _recipe_id(recipe_id)
        try:
            changes = repository.list_collection_changes(identifier)
        except KeyError:
            return jsonify(error="Recipe not found"), 404
        return jsonify(recipe_id=identifier, history=[{
            "change_id": change.change_id,
            "recipe_id": change.recipe_id,
            "previous_collection": change.previous_collection,
            "new_collection": change.new_collection,
            "changed_by": change.changed_by,
            "changed_at": change.changed_at.isoformat(),
            "reason": change.reason,
        } for change in changes])

    def change_collection(recipe_id: str, destination: str):
        actor = _management_actor()
        identifier = _recipe_id(recipe_id)
        body = request.get_json()
        if not isinstance(body, dict) or set(body) != {"reason"}:
            return jsonify(error="Provide a JSON object containing only reason"), 400
        reason = body["reason"]
        if not isinstance(reason, str) or not reason.strip():
            return jsonify(error="reason must be a nonblank string"), 400
        operation = repository.promote_to_intended if destination == "INTENDED" else repository.demote_to_unmatched
        try:
            recipe = operation(identifier, actor, reason.strip())
        except KeyError:
            return jsonify(error="Recipe not found"), 404
        except (ValueError, TypeError) as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(recipe=recipe_to_dict(recipe))

    @blueprint.post("/<recipe_id>/promote")
    def promote_recipe(recipe_id: str):
        return change_collection(recipe_id, "INTENDED")

    @blueprint.post("/<recipe_id>/demote")
    def demote_recipe(recipe_id: str):
        return change_collection(recipe_id, "UNMATCHED")

    return blueprint
