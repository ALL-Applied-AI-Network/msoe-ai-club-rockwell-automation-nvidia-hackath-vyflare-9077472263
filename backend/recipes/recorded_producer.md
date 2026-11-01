# Fresh Recorded-Video Observation

The local experimental path now decodes installed Videos 1 and 2 anew, runs the fixed-station observer, measures final appearance at reference cadence, and passes complete interval observations into the separate demonstration bank. The browser accepts no measurements or source paths. The matcher and its 1-second timing allowance are unchanged. Boundary cases stay unresolved; conflicting colors remain flagged.

This is fixed-camera fill-visit association, not a general vial detector or liquid-surface tracker. No Cosmos, Model 2, or Model 4 call is made by this producer. No chemical identification or unattended reliability claim is made.

## Configuration

Use the existing opt-in demonstration configuration described in [demo_api.md](demo_api.md): `RECIPE_DEMO_ENABLED=true`, an explicitly separate `RECIPE_DEMO_DB_PATH`, and `INFERENCE_TOKEN` configured in both Python and the Node proxy environment. Keep the normal and demonstration databases separate. These changes do not modify the existing `.env`, enable the feature on a running server, or deploy it.

Fresh acquisition currently requires **macOS, AVFoundation, and `swiftc`**. The decoder is compiled in a temporary work directory. It rejects rotated or resized views, recordings longer than 30 minutes, and more than 7,200 event frames. Decode subprocesses have timeouts. Linux/Render needs a decoder adapter and color/timestamp equivalence checks before this path can run there. The status endpoint explicitly reports an unavailable decoder on unsupported hosts.

The supported recordings are the files `vial_fill_video_1.mp4` and `vial_fill_video_2.mp4` under `cosmos-original-dataset/videos/`. `RECORDED_VIDEO_ROOT` is an application configuration override for controlled deployments/tests, not a request parameter. Opening a local browser video remains playback/manual review only. Live mode remains a camera preview.

## API and UI

Python routes, all using the existing token/origin gate:

- `GET /api/recipe-workflow/demo/producer/status`: capability, scope, supported sources, comparison-reference coverage.
- `POST /api/recipe-workflow/demo/producer/videos/video-1` (or `video-2`), body exactly `{}`: start a fresh job; returns HTTP 202.
- `GET /api/recipe-workflow/demo/producer/videos/video-1`: progress, error, saved automatic assessments, incomplete held visits.
- `GET /api/recipe-workflow/demo/recipes`: discovered patterns in the shared experimental bank.

The Node proxy exposes `/api/recorded-observer/status`, `/videos/:videoId`, and `/recipes`, forwarding the private token server-side. It preserves upstream error codes and rejects arbitrary video IDs, measurements, file paths, and cross-origin writes.

On Inspection Workspace, select an installed recording and choose **Process Recording**. No manual timing/color qualification is requested. The job continues independently of playback; the UI polls progress, shows saved outcomes and hold reasons, and offers **View Fill** seeking. Reprocess Recording reads the actual media again; unchanged evidence reuses assessments. Playback alone does not start processing. The reviewed timeline and Model 4's selected-recipe comparison remain separately identified.

Recipes includes **Discovered Recipes · Experimental Bank**, showing IDs, linked fill counts, founder duration intervals, and measured RGB. The earlier review-service candidates are separately labeled; they are not the experimental store. The nominal recipe catalog is unchanged.

## Integrity and Lifecycle

Event images preserve the development decoder's 4 fps JPEG acquisition. Color uses fresh native PNGs at three requested offsets 0.05, 0.15 and 0.25 seconds into the observer-derived appearance window, checking actual times, cadence, temporal stability and spatial sensitivity. Actual source hashes are checked before and after processing. No reviewed labels, saved predictions, manual event boundaries or expected recipe IDs are loaded by the producer.

The observer/configuration/decoder revision is included in source lineage. Fresh observations have a different source kind and identity namespace from packaged snapshots. Reprocessing the same evidence adds no duplicate occurrences. Decoder/configuration changes need an explicit producer revision and reassessment policy; changed evidence with an existing identity is rejected, not overwritten.

One worker per application process runs one recording at a time. Duplicate starts of the active recording share that job; another recording returns 409. New observations are assessed in one bank transaction only after acquisition completes. Failures preserve previous assessments and do not commit a partial run. Incomplete event intervals stay held and do not create recipes. Temporary images/compiler products are removed on completion or failure.

Job progress and incomplete held-visit details are process-local. Assessment and recipe records persist in the demonstration SQLite database; after restart they appear as saved results. A recording interrupted by shutdown must be processed again. This is a single-process development integration, not a distributed job queue.

## Verification

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

`GET /api/recipe-workflow/demo/patterns` returns pending/confirmed groups and the discovered recipe list in one consistent snapshot. `GET /api/recipe-workflow/demo/patterns/<group_id>/history` returns member histories. The Node proxy exposes `/api/recorded-observer/patterns`. Inspection Workspace shows pending/confirmed status and membership history. Recipes shows pending groups without IDs alongside discovered recipes with their counts and retained review flags.

The engine version is 1.3. Older pinned demo stores must be preserved and a new separately configured demo filename selected before enabling 1.3. They are rejected before the new membership tables are created; no automatic migration or old-result rewriting occurs. Producer 2's timing/acquisition logic remains unchanged. Actual `.env`, normal recipe storage and public deployment are not changed by this integration.

Fresh processing of Videos 1 and 2 creates observed Recipe 102 from Video 1 Vial 13 and Video 2 Vial 3 in an empty bank processed in that order. Pending groups for Video 1 Vials 9 and 19 remain at one qualifying fill each. Effective links increase from 6 to 8 of 22; the 14 remaining fills remain unassigned to an observed/reference pattern. The majority goal is still unmet. IDs depend on existing bank contents and processing order. Replay/restart/concurrency/rollback checks cover the membership transaction and history; unseen-source reliability remains unvalidated.

## Producer 3 — Tracking-Gated Recipe Actions

The current producer is `fixed-station-native/3`. It computes geometry during the same decode as the original observer, directly checks the three original final-color images, and binds this evidence to the observation before bank assessment. It publishes the same-pass geometry for display; the frontend no longer starts a duplicate automatic geometry job. Engine 1.4 blocks unsupported tracking on all recipe action paths and holds legacy packaged snapshots. Numeric liquid level remains excluded. See [recorded_workflow_integration.md](recorded_workflow_integration.md) for the current contract and separate-store requirement.
