"""Atomic SQLite snapshots of the prototype's recipe/inspection repositories.

A shared transaction refreshes both repositories, then commits them and evidence
metadata together. BEGIN IMMEDIATE also serializes separate app processes. No
pickle or executable payloads are used; only known domain types are decoded.
"""
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from functools import wraps
import json
from pathlib import Path
import sqlite3
from threading import RLock

from .models import Dispense, Recipe, VialObservation
from .matching_config import MatchingConfig
from .recipe_matcher import FieldDifference, MatchResult
from .inspection_models import VialInspection
from .recipe_repository import RecipeRepository, RecipeCollectionChange
from .inspection_repository import InspectionRepository

_TYPES = {c.__name__: c for c in (Dispense, Recipe, VialObservation, MatchingConfig,
          FieldDifference, MatchResult, VialInspection, RecipeCollectionChange)}


def _encode(value):
    if is_dataclass(value):
        return {"type": type(value).__name__, "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, tuple):
        return {"type": "tuple", "values": [_encode(v) for v in value]}
    if isinstance(value, dict):
        return {"type": "dict", "values": [[k, _encode(v)] for k, v in value.items()]}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    return value


def _decode(value):
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    kind = value["type"]
    if kind == "datetime":
        return datetime.fromisoformat(value["value"])
    if kind == "tuple":
        return tuple(_decode(v) for v in value["values"])
    if kind == "dict":
        return {k: _decode(v) for k, v in value["values"]}
    if kind not in _TYPES:
        raise ValueError("Unsupported stored recipe type")
    return _TYPES[kind](**{k: _decode(v) for k, v in value["fields"].items()})


class SQLiteStore:
    def __init__(self, path):
        self.persistence = "in_memory" if str(path) == ":memory:" else "sqlite"
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=15, check_same_thread=False, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS recipe_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS recipe_trial_assessments (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id TEXT NOT NULL UNIQUE, revision TEXT NOT NULL,
            video_id TEXT NOT NULL, vial_id TEXT NOT NULL, payload TEXT NOT NULL)""")
        self.lock = RLock()
        self.depth = 0
        self.evidence = {}
        self.recipes = DurableRecipeRepository(self)
        self.inspections = DurableInspectionRepository(self)
        with self.transaction():
            pass

    def _dump(self):
        return json.dumps({"version": 1, "recipes": _encode(self.recipes._recipes),
                           "changes": _encode(self.recipes._changes),
                           "inspections": _encode(self.inspections._inspections),
                           "evidence": self.evidence}, allow_nan=False, separators=(",", ":"))

    def _load(self, payload):
        state = json.loads(payload) if payload else None
        if state and state.get("version") != 1:
            raise ValueError("Unsupported recipe database version")
        self.recipes._recipes = _decode(state["recipes"]) if state else {}
        self.recipes._changes = _decode(state["changes"]) if state else {}
        self.inspections._inspections = _decode(state["inspections"]) if state else {}
        self.inspections._by_vial = {(i.observation.run_id, i.observation.vial_id): key
                                    for key, i in self.inspections._inspections.items()}
        self.evidence = state["evidence"] if state else {}

    @contextmanager
    def transaction(self):
        with self.lock:
            if self.depth:
                # Domain transactions provide nested rollback; the outermost
                # store transaction owns refresh/commit of the shared snapshot.
                self.depth += 1
                try:
                    yield self
                finally:
                    self.depth -= 1
                return
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute("SELECT payload FROM recipe_state WHERE id=1").fetchone()
            original = row[0] if row else None
            try:
                self._load(original)
                self.depth = 1
                yield self
                payload = self._dump()
                if payload != original:
                    self.connection.execute("INSERT INTO recipe_state(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (payload,))
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                self._load(original)
                raise
            finally:
                self.depth = 0

    def save_trial_assessment(self, video_id, vial_id, result):
        """Append a version; exact retries return the original saved timestamp."""
        with self.transaction():
            payload = json.dumps(result, sort_keys=True, allow_nan=False)
            self.connection.execute("""INSERT INTO recipe_trial_assessments
                (assessment_id, revision, video_id, vial_id, payload) VALUES(?,?,?,?,?)
                ON CONFLICT(assessment_id) DO NOTHING""",
                (result["assessment_id"], result["revision"], video_id, vial_id, payload))
            row = self.connection.execute("SELECT video_id, vial_id, payload FROM recipe_trial_assessments WHERE assessment_id=?",
                                          (result["assessment_id"],)).fetchone()
            saved = json.loads(row[2])
            if (row[0], row[1]) != (video_id, vial_id) or {k: v for k, v in saved.items() if k != "generated_at"} != {
                    k: v for k, v in result.items() if k != "generated_at"}:
                raise ValueError("Trial revision conflicts with an immutable saved result")
            return saved

    def list_trial_assessments(self, video_id):
        with self.transaction():
            rows = self.connection.execute("SELECT payload FROM recipe_trial_assessments WHERE video_id=? ORDER BY sequence DESC",
                                           (video_id,)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def trial_assessment_count(self):
        with self.transaction():
            return self.connection.execute("SELECT COUNT(*) FROM recipe_trial_assessments").fetchone()[0]

    def close(self):
        with self.lock:
            self.connection.close()


def _durable(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.store.transaction():
            return method(self, *args, **kwargs)
    return call


class DurableRecipeRepository(RecipeRepository):
    def __init__(self, store):
        super().__init__()
        self.store = store
        # Catalog IDs 1..99 are reserved for documented nominal references.
        self.minimum_new_recipe_id = 100

    @contextmanager
    def transaction(self):
        with self.store.transaction(), super().transaction():
            yield self

    create_unmatched_recipe = _durable(RecipeRepository.create_unmatched_recipe)
    add_recipe = _durable(RecipeRepository.add_recipe)
    get_recipe = _durable(RecipeRepository.get_recipe)
    list_recipes = _durable(RecipeRepository.list_recipes)
    update_recipe = _durable(RecipeRepository.update_recipe)
    promote_to_intended = _durable(RecipeRepository.promote_to_intended)
    demote_to_unmatched = _durable(RecipeRepository.demote_to_unmatched)
    list_collection_changes = _durable(RecipeRepository.list_collection_changes)


class DurableInspectionRepository(InspectionRepository):
    def __init__(self, store):
        super().__init__()
        self.store = store

    @contextmanager
    def transaction(self):
        with self.store.transaction(), super().transaction():
            yield self

    save_inspection = _durable(InspectionRepository.save_inspection)
    get_inspection = _durable(InspectionRepository.get_inspection)
    get_for_vial = _durable(InspectionRepository.get_for_vial)
    list_inspections_for_recipe = _durable(InspectionRepository.list_inspections_for_recipe)
