"""In-memory recipe storage. Contents and change history are lost on restart."""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from .models import Dispense, Recipe, RecipeCollection


@dataclass(frozen=True)
class RecipeCollectionChange:
    """One explicit user-requested collection change."""

    change_id: str
    recipe_id: int
    previous_collection: RecipeCollection
    new_collection: RecipeCollection
    changed_by: str
    changed_at: datetime
    reason: str


class RecipeRepository:
    """Manage intended and unmatched recipes in one process.

    Collections are logical partitions of a single ID map, ensuring each recipe
    belongs to exactly one collection. IDs are supplied by the caller and must
    be unique within this repository. Returned recipes and history are immutable.

    Methods are thread-safe. Use transaction() to serialize matching/creation
    with collection moves and roll back on failure. Acquire recipe transactions
    before inspection transactions. Coordination is in-process only; database
    transactions and authentication remain outside this implementation.
    """

    def __init__(self) -> None:
        self._recipes: dict[int, Recipe] = {}
        self._changes: dict[int, tuple[RecipeCollectionChange, ...]] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        """Hold the shared lock across workflow operations; restore on failure."""
        with self._lock:
            recipes, changes = self._recipes.copy(), self._changes.copy()
            try:
                yield self
            except BaseException:
                self._recipes, self._changes = recipes, changes
                raise

    def create_unmatched_recipe(self, dispenses: tuple[Dispense, ...], final_color: str) -> Recipe:
        """Allocate an ID unique across both collections and store a pattern.

        The inspection service must establish NO_MATCH against both collections
        before calling. IDs are local to this in-memory repository instance.
        """
        if final_color is None:
            raise ValueError("A learned recipe requires final_color")
        with self._lock:
            identifier = max(self._recipes, default=0) + 1
            return self.add_recipe(Recipe(identifier, "UNMATCHED", dispenses, final_color))

    def add_recipe(self, recipe: Recipe) -> Recipe:
        """Store a recipe; raise ValueError if its ID already exists."""
        self._validate_recipe(recipe)
        with self._lock:
            if recipe.id in self._recipes:
                raise ValueError(f"Recipe {recipe.id} already exists")
            self._recipes[recipe.id] = recipe
            return recipe

    def get_recipe(self, recipe_id: int) -> Recipe | None:
        """Return a recipe from either collection, or None when absent."""
        self._validate_id(recipe_id)
        with self._lock:
            return self._recipes.get(recipe_id)

    def list_recipes(self, collection: RecipeCollection) -> tuple[Recipe, ...]:
        """Return an immutable snapshot of one collection, ordered by ID."""
        self._validate_collection(collection)
        with self._lock:
            return tuple(self._recipes[key] for key in sorted(self._recipes)
                         if self._recipes[key].collection == collection)

    def update_recipe(self, recipe: Recipe) -> Recipe:
        """Replace existing metadata; use explicit methods to change collection."""
        self._validate_recipe(recipe)
        with self._lock:
            current = self._require_recipe(recipe.id)
            if recipe.collection != current.collection:
                raise ValueError("Use promote_to_intended or demote_to_unmatched to change collection")
            self._recipes[recipe.id] = recipe
            return recipe

    def promote_to_intended(self, recipe_id: int, changed_by: str, reason: str) -> Recipe:
        """Approve an unmatched recipe, preserving its ID and measurements."""
        return self._move_recipe(recipe_id, "INTENDED", changed_by, reason)

    def demote_to_unmatched(self, recipe_id: int, changed_by: str, reason: str) -> Recipe:
        """Remove a recipe from the intended set without deleting its identity."""
        return self._move_recipe(recipe_id, "UNMATCHED", changed_by, reason)

    def list_collection_changes(self, recipe_id: int) -> tuple[RecipeCollectionChange, ...]:
        """Return change history in operation order; raise KeyError if absent."""
        self._validate_id(recipe_id)
        with self._lock:
            self._require_recipe(recipe_id)
            return self._changes.get(recipe_id, ())

    def _move_recipe(self, recipe_id: int, destination: RecipeCollection,
                     changed_by: str, reason: str) -> Recipe:
        self._validate_id(recipe_id)
        for name, value in (("changed_by", changed_by), ("reason", reason)):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        with self._lock:
            current = self._require_recipe(recipe_id)
            if current.collection == destination:
                return current  # Repeated requests do not duplicate history.
            updated = replace(current, collection=destination)
            change = RecipeCollectionChange(
                change_id=str(uuid4()), recipe_id=recipe_id,
                previous_collection=current.collection, new_collection=destination,
                changed_by=changed_by, changed_at=datetime.now(timezone.utc), reason=reason,
            )
            # Prepare both new maps before publishing either. Readers hold the
            # same lock, so collection and history become visible together.
            recipes = {**self._recipes, recipe_id: updated}
            changes = {**self._changes,
                       recipe_id: self._changes.get(recipe_id, ()) + (change,)}
            self._recipes, self._changes = recipes, changes
            return updated

    def _require_recipe(self, recipe_id: int) -> Recipe:
        try:
            return self._recipes[recipe_id]
        except KeyError:
            raise KeyError(f"Recipe {recipe_id} not found") from None

    @staticmethod
    def _validate_id(recipe_id: int) -> None:
        if isinstance(recipe_id, bool) or not isinstance(recipe_id, int):
            raise TypeError("recipe_id must be an integer")
        if recipe_id <= 0:
            raise ValueError("recipe_id must be positive")

    @staticmethod
    def _validate_collection(collection: RecipeCollection) -> None:
        if collection not in ("INTENDED", "UNMATCHED"):
            raise ValueError("collection must be INTENDED or UNMATCHED")

    @staticmethod
    def _validate_recipe(recipe: Recipe) -> None:
        if not isinstance(recipe, Recipe):
            raise TypeError("recipe must be a Recipe object")
        # Revalidate at the storage boundary; normal frozen models are already valid.
        replace(recipe)
