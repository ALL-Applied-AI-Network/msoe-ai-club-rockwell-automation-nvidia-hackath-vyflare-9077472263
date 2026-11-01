# Recorded Pattern Demonstration API

This opt-in backend connects packaged automatic-observer snapshots to interval/RGB matching and a separate persistent discovered-pattern bank. It creates/reuses **Discovered—Unverified** entries. The normal recipe bank and existing reviewed trial are unchanged. No frontend or Express routes are connected to these endpoints yet.

It consumes saved automatic observations for Videos 1 and 2. It does **not** decode an uploaded video, run a camera/tracker, Model 4, Cosmos, Model 2, or the proposed higher-cadence revalidator. The snapshots retain their original `NOT_VALIDATED` markers. Available development checks are not operational qualification; an observed reference-pattern link is not a confirmed nominal or chemical identity.

## Configuration

Disabled by default. Set the following server-side values deliberately:

```dotenv
RECIPE_DEMO_ENABLED=true
RECIPE_DEMO_DB_PATH=/absolute/path/to/recipe-demo.sqlite3
INFERENCE_TOKEN=<server-side-token>
```

The demo path is required when enabled and must differ from both the configured normal recipe database and its default location. Symlinks and hard links to the normal bank are rejected; a copied database containing normal recipe tables is rejected. Demo data must not be merged into the normal bank by copying IDs. Local demo IDs start above the nominal catalog's maximum ID, but may overlap IDs used in another isolated/normal bank.

Bump `ENGINE_VERSION` when decision or stored-schema semantics change; do not reuse a bank across incompatible revisions.

Enabling this feature does not enable normal-bank automatic creation. The service validates the checksummed portable observation package and pins it, the comparison rules/references, and engine version to the selected demo bank. Changed revisions require an explicit separate bank or future migration; no silent history rewriting occurs. No demo file is created when the feature is disabled.

All routes use `/api/recipe-workflow/demo` on the Python backend. Existing origin checks apply. When `INFERENCE_TOKEN` is configured, send `Authorization: Bearer <token>` for reads and writes. Writes return 503 if no token is configured, even on localhost. No browser secrets or raw feature submission is required.

## Routes

| Method | Suffix | Behavior |
|---|---|---|
| GET | `/status` | Enabled/write-ready state, isolated counts, source mode, reference coverage, revision and limitations. Safe when disabled; does not assess fills. |
| POST | `/recorded/<video_id>/<vial_id>` | Assess one packaged automatic fill, save its immutable result, and create/reuse a demo pattern when supported. Body must be exactly `{}`. |
| GET | `/recorded/<video_id>/<vial_id>` | Read an already saved assessment; 404 if not assessed. No inference or bank mutation. |
| POST | `/videos/<video_id>/assessments` | Assess that video's snapshots in source order in one atomic transaction. Body must be exactly `{}`. |
| GET | `/videos/<video_id>/assessments` | Read saved results for that video; does not start processing. |
| GET | `/recipes` | List discovered demo patterns, immutable founding profiles and occurrence counts. Does not duplicate the normal nominal-catalog listing. |
| GET | `/recipes/<recipe_id>` | Read one discovered demo entry. |

Valid sources are `video-1`, fills `V1-V01` through `V1-V19`, and `video-2`, fills `V2-V01` through `V2-V03`. These identify reviewed source visits, not scanned vial barcodes or batch positions. Other sources return 404. A disabled feature returns 503 for data routes. Extra POST fields, supplied measurements/recipe IDs, missing JSON and non-object bodies return 400.

An individual POST returns `{assessment, idempotent_replay}`. The stored assessment action is one of:

- `CREATE_DISCOVERED_PATTERN`: create a new unverified observed pattern.
- `REUSE_DISCOVERED_PATTERN`: link another observation to the immutable founder.
- `REUSE_REFERENCE_PATTERN`: link to an observed catalog-reference candidate; nominal identity remains unconfirmed.
- `UNRESOLVED`: retain quality/ambiguity/conflict evidence without creating or assigning a pattern.

The wrapper distinguishes a newly processed observation from replay of its historical outcome. A replay may retain an original `CREATE_DISCOVERED_PATTERN` action in its assessment, but `idempotent_replay: true` means no new creation or occurrence happened in this call.

A batch POST returns `{video_id, results, new_patterns, new_assessments, replayed_assessments}`. All tentative changes roll back if any assessment/storage operation fails. Exact retries return original assessments without adding duplicates. Changing evidence under the same identity returns 409. Unexpected failures return 500 and are logged; they are not classified as unknown recipes. Each call uses a shared transaction/lock, and separate processes serialize matching and allocation with SQLite.

The `X-Recipe-Storage` response header is `isolated_demo_sqlite` when enabled and `disabled` otherwise. Responses expose evidence IDs, hashes and source timestamps, not research-directory paths.

## Preserved Rules and Demonstration Results

The unchanged timing allowance is 1.0 second. A link requires one possible recipe ID and one actual reference profile containing all chronological query intervals; otherwise boundary and ambiguous cases stay unresolved. Final-color limits remain 24.10 distance, 2.24 temporal variation and 2.45 spatial sensitivity. Color conflict preserves timing candidates and causes no ID action. Unreliable observations do not create recipes.

When no observed profile matches and the available demo checks pass, missing nominal reference coverage does not prevent an unverified observed-pattern discovery. Its actual ingredients, tank identity, volume and nominal recipe remain unconfirmed. The implementation preserves interval bounds and final RGB; it does not invent per-dispense colors or midpoint measurements to fit the older weighted service.

With a fresh demo bank, process Video 1 then Video 2 in source order to reproduce the offline demonstration:

- Video 1, Vial 6 creates demo Recipe 100; Vial 12 reuses 100.
- Video 1, Vial 16 creates demo Recipe 101.
- Video 2, Vial 2 links to the observed reference-pattern candidate for Recipe 8.
- The other 18 observations remain unresolved under the agreed rules. The majority-assignment objective is not met.

Founders are immutable, so different ingestion orders can produce different founders/decisions; do not claim these example IDs/outcomes for an already populated or differently ordered bank. The original 52 nominal settings have comparable observed profiles for only 14 IDs. This feature demonstrates the recognition/learning mechanism, not unattended reliability.

## Portable Assets and Checks

`backend/recipe_demo_assets/` contains 22 automatic-observer snapshots and a checksum manifest. Runtime reads only packaged backend assets, reuses the existing validated 44 reference profiles, and does not access research directories or require the original video files. The offline decision oracle is a test fixture, not a runtime decision input.

Repackage explicitly from the existing research artifacts:

```sh
.venv/bin/python backend/scripts/package_recipe_demo.py --research-root /absolute/path/to/outputs
```

This packaging command writes assets/test fixtures only. It does not open a bank, alter observations, or run video/model inference.

From `backend/`, test the feature and then the backend regression suite:

```sh
../.venv/bin/python -m unittest discover -s tests -p 'test_demo_*.py' -v
../.venv/bin/python -m unittest discover -s tests
../.venv/bin/python scripts/smoke_recipe_demo.py
```

The smoke script opens an ephemeral loopback HTTP server with empty inference registry and temporary normal/demo databases, verifies create/reuse/hold and exact replay, then shuts the server down. It does not change the running application, its real database, or runtime configuration.

The next integration is an actual recorded-video observation producer and frontend display after contract review. Automatic vial/liquid tracking, spatial color qualification, remaining model adapters and live operation remain separate work.

## Fresh Recorded Producer

The packaged-snapshot endpoints above remain unchanged. A separate fresh acquisition path and frontend display are now available; see [recorded_producer.md](recorded_producer.md) for configuration, platform support and routes.

Reference-color qualification is enabled in recorded engine 1.1. Color exclusions are returned in `color.reference_color_qualification`; timing evidence remains intact. A bank pinned to engine 1.0 requires a new separately configured database filename before starting 1.1, preserving old results. See [recorded_producer.md](recorded_producer.md#reference-color-guard-engine-11).

Fresh recorded producer 2 now performs bounded contained timing refinement; packaged snapshot observations remain the frozen comparison input. Recorded engine 1.2 requires a fresh separately configured demo filename for older pinned banks. See the contained timing section of [recorded_producer.md](recorded_producer.md#contained-timing-refinement-producer-2--engine-12).

Engine 1.3 adds persistent two-fill pending groups and versioned membership projections. `GET /patterns` returns groups and discovered recipes in one snapshot; `GET /patterns/<group_id>/history` returns the member revision history. Effective membership is additive under `assessment.pattern_membership`; the original baseline decision remains unchanged. Older pinned banks require a preserved archive and a new separate demo filename. See the persistent membership section of [recorded_producer.md](recorded_producer.md#persistent-pending-patterns-and-membership-history-engine-13).

## Engine 1.4 — Recorded Tracking Eligibility

Fresh recorded assessments now require source-bound tracking and direct final-color visibility evidence before any recipe action. Packaged historical snapshots are retained as tracking-held assessments and cannot create/reuse patterns or vote. Use a new, separately configured demo filename for 1.4; older pinned stores remain unchanged. See [recorded_workflow_integration.md](recorded_workflow_integration.md). The actual environment is not modified automatically.
