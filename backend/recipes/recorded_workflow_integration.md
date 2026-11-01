# Recorded Tracking Eligibility in the Recipe Workflow

## Reviewed Rules and Scope

Recorded-only processing now applies the qualification rules before recipe actions. Numeric surface height is excluded. A missing surface line does not mean empty/no-flow/unknown recipe, and strict every-frame continuity is not an eligibility switch.

A fill needs one supported identity spanning the required timing/final-color evidence. A short body-detection loss or transient exposure hold can be accepted after supported re-confirmation; unresolved/expired recovery, identity changes, timestamp gaps, changed geometry or missing directly visible final-color evidence hold the observation. Recovering body identity does not invent a missing dispense onset/end or repair unsupported color measurements. The existing timing, source-phase, reference/color-quality and repeated-pattern checks remain mandatory.

This is developmental eligibility for the fixed recorded station, not operational or chemical identity qualification. Live inspection remains deferred.

## Same-Pass Producer and Evidence

`fixed-station-native/3` computes the original dispense observer and geometry tracker from the same freshly decoded event frames. The timing allowance, observer/refinement thresholds, RGB measurement regions and nominal references are unchanged. A versioned report binds the original observation, source recording SHA, tracker/policy implementations, frame timestamps/hashes and direct final-color sample provenance. Surface coordinates do not enter this report or matcher.

Three original lossless final-color frames are checked directly. Their dimensions, source timestamps, evidence IDs and hashes must agree with the measurement provenance. The observed vial must cover the entire fixed RGB region and placement offsets, and its geometry must agree with nearby confirmed identity anchors. A latent tracking candidate does not substitute a drawn/interpolated box for missing sample evidence.

`recorded_eligibility.evaluate()` recomputes `SUPPORTED`, `SUPPORTED_WITH_RECOVERY` or `HELD` from report evidence; it does not trust a caller-supplied supported boolean. Detection-loss events must account for missing samples, source clock and the bounded recovery. Per-frame unconfirmed states remain in the audit.

The producer publishes its same-pass geometry for frontend playback before the bank transaction. This replaces the frontend's separate automatic geometry job. A publisher/source/pixel-processing failure causes no recipe transaction; the separately cached geometry is read-only evidence. The standalone Track Entire Recording action remains read-only.

## Bank Enforcement

Engine **`recorded-pattern-demo/1.4`** requires the tracking check for fresh recorded observations. Held tracking reasons enter the existing quality gate before reference reuse, discovered reuse, ordinary discovery or repeated-color-conflict voting. Matching still exposes the original timing/color candidate information. Two qualified, distinct color-conflicting fills remain necessary for that discovery exception; replay cannot add another vote.

An ID shared by distinct source fills is held before batch writes, with an additional persisted cross-transaction check. The bank retains unresolved assessments for audit; it does not create an identity or count a pending vote for a held observation. Existing source-fill deduplication and append-only memberships remain.

Historical packaged snapshots have no new tracking proof. Their API routes retain observations and comparisons as `HELD` with `TRACKING_EVIDENCE_MISSING`; they cannot create/reuse patterns or vote through an alternate legacy route. Current discovery requires fresh recorded processing. Explicit synthetic test fixtures are not production ingestion paths.

`assessment.recorded_tracking` stores eligibility, hold reasons, selected track ID, recovery/unconfirmed spans, evidence hash and the fact that numeric surface is unused. Original measurements and flags are retained. Exact retries return the original assessment; changed evidence under the same observation ID is rejected rather than overwriting history.

## Versioned Stores and Frontend

The old engine-1.3 store is preserved and rejected by engine 1.4. Select a **new, separate** `RECIPE_DEMO_DB_PATH` such as `recipe-demo-v1-4.sqlite3` when enabling this revision. No old results are silently migrated, requalified or rewritten. The normal recipe bank and actual environment configuration are unchanged. The example environment file documents the new filename.

Inspection Workspace shows tracking-supported/recovered/held status alongside recipe outcomes. Held evidence is excluded from effective link counts. Refreshing/completing producer processing refreshes geometry automatically. Numeric level is explicitly excluded. Other model workflows remain unchanged.

## Verification

Fresh processing of both complete recordings evaluated 22 fills. Tracking eligibility supported 21; Video 1 Vial 7 was held because its three direct final-color frames lack supported vial geometry despite recovered event-frame identity. This does not label the liquid wrong or empty. The existing timing uncertainty for that fill remains.

The final isolated bank retains 8 effective links, 3 discovered patterns and 2 pending groups; 14 fills remain unresolved, including the tracking-held fill. The repeated-color-conflict pattern 102 retains possible Recipe 7 and its review flag. No normal-bank or live-camera actions were performed.

Tests cover malformed/missing/bound/stale evidence, expiry/cadence, direct sample visibility, conflicting IDs, all recipe action paths, pending vote suppression, supported-recovery confirmation, immutable restart/replay, legacy route closure and prior-store preservation. The original packaged decision oracle is retained as historical evidence; current tests apply the new explicit hold without rewriting source measurements.
