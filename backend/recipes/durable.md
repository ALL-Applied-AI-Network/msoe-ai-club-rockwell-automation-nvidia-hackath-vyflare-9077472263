# Durable Recipe Storage

`SQLiteStore(path)` provides recipe and inspection repositories backed by a shared
SQLite transaction. Both repository snapshots and associated evidence metadata
commit together. Failed writes roll back the complete transaction. Separate
connections serialize writes to avoid duplicate candidate creation.

The store preserves recipe collection history and historical inspection snapshots
across reopening. Its append-only assessment interface also preserves the first
saved result on retries and rejects conflicting evidence under the same ID.
Stored domain values use explicit JSON types rather than executable serialization.

Durable repositories reserve IDs below 100 for nominal references by default.
Applications can raise `recipes.minimum_new_recipe_id` to reserve a larger catalog.
`VialInspectionService(required_reference_ids=...)` prevents missing reference
coverage from being treated as proof of an unknown recipe. A complete existing
reference can still match when other references are missing.

The application factory now uses this store by default for normal application
recipes/inspections at `RECIPE_DB_PATH` or `backend/.data/recipes.sqlite3`.
Injected repositories and tests without an explicit database can remain in
memory. The recorded experimental bank uses its own separate `RECIPE_DEMO_DB_PATH`;
it is not merged into this normal store.
Keep database files and their SQLite journal files outside version control and
container build contexts. Close each store when its application shuts down.

Validation: restart/replay, candidate reuse, historical approval records, atomic
rollback, concurrent connections, missing references and immutable assessments are
covered in `backend/tests/test_durable_store.py`.
