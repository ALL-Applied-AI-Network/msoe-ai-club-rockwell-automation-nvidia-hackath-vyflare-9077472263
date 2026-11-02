# Fresh Recorded-Video Observation

## Current Contract — Producer 4 / Engine 1.4

The recorded producer decodes original pixels for installed Videos 1–5 and
content-addressed opened station recordings. It detects fill visits/dispenses,
performs bounded timing refinement, measures final RGB and checks same-pass
tracking plus direct final-color visibility before any recipe action. It does
not load reviewed labels, expected recipe IDs or saved predictions as observation
inputs. No Cosmos, Model 2 or Model 4 call is required by this producer.

First playback ensures an analysis job. The **Inspection Log** replaces the manual
comparison form, reviewed timeline and separate processing panel. Pause freezes
log arrivals while analysis continues; resume and seeks reveal only appropriate
source-time events. Later confirming fills append later membership updates rather
than rewriting early events with knowledge from the future. See
[automatic_recordings.md](automatic_recordings.md) for the maintained API,
registration, playback, persistence and upload contract.

## Configuration and Supported Sources

Enable `RECIPE_DEMO_ENABLED=true`, configure an explicitly separate
`RECIPE_DEMO_DB_PATH` for engine 1.4, and configure the same private `INFERENCE_TOKEN`
on Python and Node. Keep the normal and demo databases separate. Preserve old
incompatible demo files; there is no automatic migration.

Fresh acquisition requires **macOS, AVFoundation and `swiftc`**, unrotated original
640 × 480 station geometry and at most 30 minutes of footage. Linux/Render needs
a validated decoder adapter. Installed sources are
`cosmos-original-dataset/videos/vial_fill_video_1.mp4` through `_5.mp4`.
`RECORDED_VIDEO_ROOT` is an application configuration override, not a request or
default-launcher environment parameter. New MP4/MOV/WebM media is registered by
SHA256; filenames cannot select server paths. Local uploads are bounded to
128 MiB each and a 512 MiB registration storage budget.

The one-second timing allowance, color safeguards and tracking eligibility checks
remain in force. Boundary/ambiguity cases stay unresolved; conflicting colors
retain their review flag. Numeric liquid height is excluded. Two distinct
qualifying color-conflicting fills can establish an unverified observed pattern
under the agreed exception. Missing reference evidence alone cannot prove novelty.
This is not chemical identification or qualification for unattended use.

## Integrity and Lifecycle

The source SHA is checked at queuing, processing start and completion. Observation
lineage binds decoder/configuration/producer revisions and source evidence.
Unchanged evidence reuses saved assessments without new occurrences; conflicting
evidence under the same identity is rejected. Engine 1.4 enforces tracking on all
recipe actions, including pending-group votes. Historical packaged snapshots
without tracking proof remain held.

One worker runs one recording at a time. Automatic `ensure` supports up to four
active/queued recordings and reuses existing jobs/results. The explicit legacy
start route remains for controlled reprocessing and returns 409 if another
recording is active. Jobs are process-local; shutdown-interrupted work needs to
be restarted. Acquisition/qualification/log-preparation failures do not commit
partial recipe runs. Assessments and memberships commit together in SQLite.

Persistent source-bound event journals retain incomplete-visit details, causal
membership updates and analyzed-through time. They are scoped to the bank path
and checked against immutable bank rows, preventing results from a different or
reset bank from appearing as that bank's recipe IDs. If a historical bank lacks
a valid journal, fallback uses original baseline decisions rather than later
membership projections. See the automatic guide for storage directories.

Recipes displays the experimental discovered patterns and pending groups
separately from nominal references and normal-service candidates. IDs depend on
bank contents and processing order. Live camera preview/tracking is separate;
automatic live recipe processing remains deferred.

## Validation and Development History

Current validation (2026-11-01): 51 frontend/gateway tests, TypeScript checks and
production build pass; 392/393 backend tests pass with the existing Model 2 strict
score-parity issue retained. Fresh native runs of Videos 1, 3 and 4, content-ID
processing and restart/replay checks exercised the current integration. These do
not establish accuracy on all installed or unseen recordings.

The following sections preserve the **earlier development checkpoints**, including
their original counts, versions and scripts. They do not describe the current UI,
current assignment counts or a requirement to downgrade an engine-1.4 bank.

## Historical Initial-Producer Verification

Run from the repository root:

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests
pnpm run check
.venv/bin/python backend/scripts/smoke_recorded_producer.py --output /tmp/recorded-producer-results
```

The smoke script uses actual source recordings and a temporary bank, never the normal application database. Run in an environment allowed to access macOS video decoding services. Source videos are not included in the saved reports.

Fresh processing of both recordings reproduced all 22 prior offline decisions: two discovered patterns (100 and 101 in an empty demo bank), one reuse of 100, one reference-pattern link to Recipe 8, and 18 unresolved fills. All 22 are observed automatically, but only four receive an ID link under the agreed rules. This integration does not improve that assignment rate. IDs depend on existing bank contents and processing order; 100/101 are test outcomes, not guaranteed identifiers.

## Reference-Color Guard (Engine 1.1)

Recorded discovery now applies the existing temporal/spatial stability limits to each reference color before comparison. Missing, malformed, nonfinite or unstable reference colors are withheld, while their timing profiles and recipe IDs remain in the candidate set. Other qualified colors for the same ID remain usable. If an applicable timing candidate has no qualified reference color, the fill stays unresolved: neither reuse nor a new ID is permitted from that missing evidence. Excluded profile IDs/reasons and missing-qualified-color recipe IDs are retained under `color.reference_color_qualification`.

The frozen historical reviewed-trial helper, format, assets and results are preserved. This guard applies to packaged and fresh observations assessed through the recorded demonstration/discovery bank.

The recorded engine version is now `recorded-pattern-demo/1.1`. Its pinned configuration deliberately does not reinterpret a bank created by 1.0. Before enabling the updated service with existing demo data, preserve that database and explicitly configure a **new, separate demo database filename**, then replay the source observations. This does not migrate or overwrite old records; IDs in a new bank depend on processing order. The normal recipe bank and actual runtime environment configuration are unchanged by this code update.

## Contained Timing Refinement (Producer 2 / Engine 1.2)

Fresh recorded processing now includes an optional bounded native-cadence pass before appearance measurement. It uses existing automatic boundary hypotheses, the frozen arrival contrast reference and connected-trace settings. It does not use labels, recipe identities, or an expected matching result. Each review retains 0.75 seconds of lead-in and at most two seconds of look-ahead. Overlapping windows share acquisition; limits are 30 unique seconds per visit and 300 per recording, with decoder time/frame limits.

A fill receives refined timing only when **all** episode starts/ends have a confirmed native transition, every proposed bracket is contained in its original bracket, and chronological ordering/positive durations remain valid. The whole fill falls back to its original intervals if any boundary is incomplete, unresolved or outside its original bracket. No partial update or intersection selected to obtain a recipe match is allowed. Existing observation holds are never cleared. Missing/failed native acquisition falls back with an explicit reason. Possible short low-trace gaps are not silently bridged. This is a conservative connected-trace refinement, not a parcel or physical-flow qualification model.

The original appearance window is retained. Contained end brackets ensure that its samples remain after the refined upper end; original color values, sampling checks and color-conflict holds are preserved. Every fresh observation includes `timing_refinement` with original intervals, accepted/fallback status, boundary evidence, actual native timestamps/hashes, resource use and rule version. Ordinary frontend progress polling displays the added **Refining Dispense Timing** stage and existing assessment components display the resulting outcomes.

Producer source identities now use `fixed-station-native/2`. Recorded engine 1.2 pins this change and requires a new separately configured demo database if the existing bank was created by 1.0/1.1. Old stores and actual environment settings are not overwritten. Both earlier and new records retain their respective provenance in their own versioned banks.

A fresh paired test of Videos 1 and 2 yielded six reference/discovered-pattern ID links out of 22 fills, compared with four using their original coarse intervals. Video 1 Vial 3 and Video 2 Vial 1 gained tentative reference-pattern links to Recipe 7. Four fills qualified for contained refinement; 18 retained baseline intervals. The majority-assignment objective remains unmet, and nominal identity remains unconfirmed. Segmented-flow cases retain their existing holds.

To reproduce the paired comparison after the fresh smoke run:

```sh
.venv/bin/python backend/scripts/compare_timing_refinement.py --run /tmp/recorded-producer-results
```

## Persistent Pending Patterns and Membership History (Engine 1.3)

The user-approved color-conflict exception now persists pending groups and append-only memberships in the isolated demo SQLite bank. Two distinct, qualifying fill events can establish a Discovered–Unverified observed pattern while the original timing candidate and color-conflict flag remain. No nominal/chemical identity is confirmed. Existing boundary, ambiguity, phase, visibility, missing-reference-color and sampling-quality holds remain blockers.

Grouping uses the existing one-second timing allowance, mutual full containment and the 24.10 RGB-distance band against every member. Founders do not drift or average. Partial/multiple group overlaps stay unresolved. Original source video hash plus frozen arrival timestamp prevents replays or producer-name aliases from supplying a second vote. Stable original-capture lineage remains required for re-encoded/overlapping clips outside the installed sources.

A pending group has no recipe ID. The second qualifying occurrence creates the observed-pattern ID and appends membership revisions for both the earlier and current fill in one transaction. Later qualified occurrences append reuse revisions. Original baseline assessment JSON is never overwritten. Confirmed group profiles are evaluated in this supplemental observed-pattern layer, preserving the original reference comparison rather than introducing a new nominal identity. Before ordinary no-reference discovery, a unique qualified confirmed-group match is reused; ambiguous matches or missing source lineage cannot create a duplicate pattern.

`assessment.recipe_id`, `action`, `timing` and `color` retain their baseline meanings. `assessment.pattern_membership` supplies the current effective pattern ID/status, revision ID, qualifying count, prior candidate IDs, retained review flags and membership history. Consumers should use the membership recipe ID when present for effective observed-pattern counts, while displaying the original conflict. `DemoBank.baseline_assessments()` exposes immutable baseline snapshots; `assessments()` exposes the current projected view. `counts().linked_occurrences` counts persisted links once per canonical membership.

`GET /api/recipe-workflow/demo/patterns` returns pending/confirmed groups and the discovered recipe list in one consistent snapshot. `GET /api/recipe-workflow/demo/patterns/<group_id>/history` returns member histories. The Node proxy exposes `/api/recorded-observer/patterns`. Inspection Workspace now shows evidence-timed pending/confirmed updates in the log; full group history remains available through the API. Recipes shows pending groups without IDs alongside discovered recipes with their counts and retained review flags.

The engine version is 1.3. Older pinned demo stores must be preserved and a new separately configured demo filename selected before enabling 1.3. They are rejected before the new membership tables are created; no automatic migration or old-result rewriting occurs. Producer 2's timing/acquisition logic remains unchanged. Actual `.env`, normal recipe storage and public deployment are not changed by this integration.

Fresh processing of Videos 1 and 2 creates observed Recipe 102 from Video 1 Vial 13 and Video 2 Vial 3 in an empty bank processed in that order. Pending groups for Video 1 Vials 9 and 19 remain at one qualifying fill each. Effective links increase from 6 to 8 of 22; the 14 remaining fills remain unassigned to an observed/reference pattern. The majority goal is still unmet. IDs depend on existing bank contents and processing order. Replay/restart/concurrency/rollback checks cover the membership transaction and history; unseen-source reliability remains unvalidated.

## Producer 3 — Tracking-Gated Recipe Actions

Producer `fixed-station-native/3` introduced this tracking gate; current producer 4 retains it. It computes geometry during the same decode as the original observer, directly checks the three original final-color images, and binds this evidence to the observation before bank assessment. It publishes the same-pass geometry for display; the frontend no longer starts a duplicate automatic geometry job. Engine 1.4 blocks unsupported tracking on all recipe action paths and holds legacy packaged snapshots. Numeric liquid level remains excluded. See [recorded_workflow_integration.md](recorded_workflow_integration.md) for the current contract and separate-store requirement.
