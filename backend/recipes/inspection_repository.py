"""In-memory inspection history; one immutable result per run/vial pair."""

from contextlib import contextmanager
from dataclasses import replace
from threading import RLock

from .inspection_models import VialInspection
from .models import _validate_text


class InspectionRepository:
    def __init__(self) -> None:
        self._inspections: dict[str, VialInspection] = {}
        self._by_vial: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        """Serialize operations and roll back changes on failure.

        When combining with RecipeRepository, acquire its transaction first.
        This coordination is in-process only, not durable database storage.
        """
        with self._lock:
            inspections, by_vial = self._inspections.copy(), self._by_vial.copy()
            try:
                yield self
            except BaseException:
                self._inspections, self._by_vial = inspections, by_vial
                raise

    def save_inspection(self, inspection: VialInspection) -> VialInspection:
        """Save once; identical retries return existing data, conflicts raise."""
        if not isinstance(inspection, VialInspection):
            raise TypeError("inspection must be a VialInspection")
        replace(inspection)  # Revalidate at storage boundary.
        key = (inspection.observation.run_id, inspection.observation.vial_id)
        with self._lock:
            existing = self._inspections.get(inspection.inspection_id)
            if existing is not None:
                if existing != inspection:
                    raise ValueError("Inspection ID already contains a different result")
                return existing
            if key in self._by_vial:
                raise ValueError("A result already exists for this run/vial pair")
            # Prepare both indexes before changing either.
            inspections = {**self._inspections, inspection.inspection_id: inspection}
            by_vial = {**self._by_vial, key: inspection.inspection_id}
            self._inspections, self._by_vial = inspections, by_vial
            return inspection

    def get_inspection(self, inspection_id: str) -> VialInspection | None:
        _validate_text("inspection_id", inspection_id)
        with self._lock:
            return self._inspections.get(inspection_id)

    def get_for_vial(self, run_id: str, vial_id: str) -> VialInspection | None:
        _validate_text("run_id", run_id)
        _validate_text("vial_id", vial_id)
        with self._lock:
            identifier = self._by_vial.get((run_id, vial_id))
            return self._inspections.get(identifier)

    def list_inspections_for_recipe(self, recipe_id: int) -> tuple[VialInspection, ...]:
        if isinstance(recipe_id, bool) or not isinstance(recipe_id, int):
            raise TypeError("recipe_id must be an integer")
        if recipe_id <= 0:
            raise ValueError("recipe_id must be positive")
        with self._lock:
            return tuple(item for item in self._inspections.values() if item.recipe_id == recipe_id)
