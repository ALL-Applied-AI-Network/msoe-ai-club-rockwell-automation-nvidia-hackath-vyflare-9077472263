# Reviewed Recipe Trial

This backend-only experiment compares the 22 reviewed fills in Videos 1 and 2
against 44 eligible observed reference profiles covering 14 of the 52 nominal
recipes. It runs interval timing and final-liquid RGB comparisons, not Model 2,
Model 4, Cosmos, video decoding or automatic vial detection. Existing assessment
routes and the frontend continue to use their existing workflow.

## API

All paths start with `/api/recipe-workflow` on the Python backend. These routes
inherit the existing origin checks and `INFERENCE_TOKEN` authentication when
configured. They are not added to the Express/browser proxy.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/trial/status` | Experimental rules, reference coverage, limitations and separate saved trial count. |
| POST | `/trial/recorded/<video_id>/<vial_id>` | Assess packaged reviewed evidence and save/reuse its immutable version. Body must be exactly `{}`. |
| GET | `/trial/videos/<video_id>/assessments` | All saved trial versions for that video, newest insertion first; `includes_history` is true. |

For example, `POST /api/recipe-workflow/trial/recorded/video-1/V1-V11` with an
empty JSON object assesses Video 1, Vial 11. Unknown source identities return
404; caller-supplied measurements or recipe IDs return 400. Assessment results
are under the `assessment` key. The bundled `assessment_response.schema.json`
defines that result shape. Runtime validation implements the restricted schema
keyword subset used in that file, not a general JSON Schema evaluator.

## Comparison Rules

Reference episode intervals expand by exactly 1.0 second at each end; query
intervals retain their reviewed uncertainty. Compare equal observed episode
counts in chronological order against actual individual reference profiles.
Never combine per-position ranges from different fills. A unique candidate needs
one possible recipe ID and a single containing reference profile. Otherwise
report Ambiguous, Boundary Uncertain or No Compatible Reference. Observed flow
episodes are not verified ingredient dispenses, and missing episodes can still
produce misleading candidates; the trial cannot confirm completeness or identity.

Final color uses Euclidean distance from the query RGB to the nearest observed
RGB for each possible timing recipe ID. The provisional inclusive limits are
24.10 color distance, 2.24 temporal variation and 2.45 region sensitivity, in native
RGB-distance units. Temporal variation is the maximum pairwise distance among
three sampled frame medians; region sensitivity is the maximum change from the
nominal median under the reviewed +/-2 and +/-4 pixel cardinal shifts. These
measurements are frozen from the prior pixel-level offline experiment.

Missing or failed query sampling reliability takes precedence. Recorded fills
must retain three actual decoded timestamps strictly after reviewed flow end and
before movement. Known qualitative failures, such as glare, also make color
Unreliable even if numeric checks pass. A missing reference color is Unreliable.
With no candidate/reference comparison, usable measurements are Not Evaluated.

Consistent/Conflicting are explicitly **experimental numerical diagnostics**.
Passing the checks does not independently establish camera registration,
comparable lighting, lack of occlusion or fully settled appearance. Sampling
and phase limitations remain in every response. A conflict produces a review
flag without pruning, replacing or confirming timing candidates; Unreliable
color provides no support or contradiction. Per-candidate band results retained
under Unreliable are diagnostics only.

Every present overall result is Insufficient Evidence with a null confirmed
recipe ID and automatic creation disabled. No-compatible-reference results are
not novelty decisions: 38 catalog recipes lack comparable observed profiles.
The engine has no recipe repository and cannot add recipes. Integration of the
other expected models, automatic observation and discovered-pattern creation/reuse
remain future work.

## Evidence and Versions

`backend/recipe_trial_assets/` contains a checksummed bundle, response schema and
manifest tied to the nominal catalog digest. The bundle retains original reviewed
observations, reference profiles, RGB measurements, actual query frame times,
195 source image hashes, source artifact hashes and exclusions embodied in the
44-profile reference selection. It does not package the videos or decoded images.
No research-directory paths are needed at runtime.

Response provenance hashes cover normalized observations, measurements,
reference profiles, rules, schema, engine version and original evidence lineage.
They are not identical to every original research-file hash; original hashes
remain in the packaged bundle. Change the engine version when comparison
semantics change. Evidence/reference/rule changes produce new assessment IDs;
timestamps are excluded from revision identity.

Trial results occupy the separate `recipe_trial_assessments` SQLite table in the
existing recipe database. An additive `CREATE TABLE IF NOT EXISTS` runs when a
store opens. Existing `recipe_state` records remain intact. Exact retries return
the original stored result and timestamp; changed revisions append new records.
Inserts and retries share the store's serialized transaction, including across
processes. The API exposes no update/delete operation for these versions.
Injected testing repositories without a SQLite store use isolated memory instead.

To reproduce the frozen assets from the reviewed research artifacts:

```sh
.venv/bin/python backend/scripts/package_recipe_trial.py --research-root /absolute/path/to/outputs
```

This is an explicit developer packaging operation, not a runtime ingestion API.
It reads the named research inputs and updates the bundle, manifest, schema and
offline expected-response test fixture. Research inputs are not edited. The
original coarse `evidence/recorded-inspection.json` and nominal catalog are not
changed. Backend Docker packaging already copies the complete backend directory,
including these assets.

## Tests

From the backend directory:

```sh
../.venv/bin/python -m unittest discover -s tests -p 'test_reviewed_trial.py'
../.venv/bin/python -m unittest discover -s tests
```

The trial tests compare all 22 actual API responses with the saved offline
examples. Additional cases cover interval edges, ambiguity, chronological order,
reference-profile separation, sampling reliability, exact color limits, source
integrity, authentication/origin checks, idempotency, revision history, restart
persistence, concurrent connections and rollback. Temporary test databases are
used; the existing application database is not populated by testing.
