# Recorded Tracker Qualification and Eligibility Rules

## Scope and Decision

This work covers recorded Videos 1 and 2 only. Live inspection is deferred per the user's instruction and is not a prerequisite for recorded workflow integration.

Version 2 repairs the three demonstrated identity-fragmentation cases. On the same 5,130 source-linked samples, all 22 fill windows have one emitted track ID, compared with 19 in version 1. No track ID is shared between adjacent fill windows. This is developmental validation on the same two recordings, not independent proof of general identity accuracy or unattended reliability.

Surface detection is only partially supported. It can provide display candidates, but the reviewed results do not qualify numeric liquid level as a recipe-matching or recipe-creation feature. Recipe decisions, matching tolerances, nominal references and pending/discovered memberships remain unchanged.

## Root Cause and Bounded Recovery

Video 1 Vials 7/16 and Video 2 Vial 1 remain visibly stationary during short detector failures. Liquid appearance changes weaken the sustained glass/body edges. Sampled weaker-edge contrasts fall to approximately 3.5–3.83 against a threshold of 4. Version 1 immediately deleted the slot on a missing detection, causing a new ID upon return.

Version 2 preserves a latent candidate for at most **two seconds**, including re-confirmation. It does not emit stale boxes, IDs or surface lines during missing detections. Reassociation requires:

- A previously confirmed ID, supported original camera geometry and uninterrupted source timestamps (maximum input gap 0.4 seconds).
- Continued holder visibility and agreement with the pre-loss holder-side appearance (mean distance at most 4). Central changing-liquid/label pixels are excluded.
- No sustained holder motion, and returning horizontal geometry within 0.04 normalized units of the pre-loss box.
- Two consecutive supported returning detections before the original ID is emitted again.

One isolated exposure/motion spike retains the prior conservative recovery policy. Consecutive motion crossing the detected/missing boundary breaks identity. Changed holder appearance, changed geometry, absent holder, input gaps and expired recovery budgets reset the candidate. A single returning detection cannot restart the budget. This time budget is a tracker recovery limit, **not a change to the approved one-second recipe timing allowance**.

Frame `identity_events` retain pending, reassociated and reset events. Observation summaries preserve `bounded_detection_recoveries` and `identity_reset_events`. Strict `identity_continuous` remains false when any sampled frame is unconfirmed; recovery does not rewrite gaps into uninterrupted observation. `affects_recipe_decision` remains false.

## Surface Review

A source-only, stratified review contains 82 frames: pre-flow, mid-flow, final samples and selected version-1 surface emissions. Developmental labels were frozen before comparing positions with the predictions. They include approximate vertical bands, ambiguity categories, source recording hashes and exact decoded-frame hashes. They are assistant-reviewed, not independent or human-verified ground truth.

| Source Review Category | Findings |
| --- | --- |
| 42 empty/obscured examples | All 42 withheld a line. |
| 36 approximately visible boundaries | 10 emitted lines within review bands, 4 outside, 22 emitted no line. |
| 4 ambiguous foam/occlusion examples | All 4 emitted candidates that cannot be qualified as exact surfaces. |

These are selected-frame counts, not population accuracy/recall estimates. Two missed final surfaces are visibly above the holder but inside the conservative fixed label-band exclusion. Other misses include low contrast and turbulent boundaries. Colored-liquid boundaries and the upper foam surface need not coincide. The qualification does not silently widen review bands or remove failed/ambiguous examples.

The surface detector itself was not retuned against these labels. Its current candidate lines must not establish physical volume, ingredient amounts, empty-vial status or a new recipe identity.

## Reviewed Automatic Eligibility Rules — Implemented

These rules were reviewed and are now enforced by the recorded workflow; see `recorded_workflow_integration.md`. They do not introduce per-fill human approval.

| Condition | Recorded-Workflow Treatment |
| --- | --- |
| One confirmed association supports the required evidence; original timing/color/source checks pass | Compare with reference and discovered patterns using the existing matcher. |
| Non-critical detector loss resolves within the bounded recovery checks | Preserve the ID and recovery audit; allow comparison only when required timing/final-color evidence is directly supported. |
| Recovery remains pending | Continue bounded automatic observation; do not vote for a new pattern yet. |
| Loss expires, holder/geometry changes, capture gap occurs, or identity remains unresolved | Retain an unresolved outcome; do not merge fills or count the observation toward new-pattern creation. |
| Timing onset/end or final-color samples lack direct support | Preserve the existing timing/phase/color hold. A recovered ID cannot repair unobserved measurements. |
| Surface is hidden, missing, noisy or ambiguous | Exclude numeric level; do not infer empty/no-flow/unknown recipe merely from the missing line. Timing/color comparison may proceed when its own required evidence is sufficient. |
| No pattern matches after all existing evidence checks | Follow the already-approved provisional discovery/reuse policy, preserving review flags and the two-distinct-fill requirement for the repeated color-conflict exception. |

Do not map `identity_continuous == false` directly to recipe failure. That strict display/evidence diagnostic is false for all 22 windows because it includes temporary confirmation/exposure holds. Recorded eligibility inspects the actual identity events, their resolution and the critical measurement windows. It also retains the existing source-lineage deduplication, reference-coverage, timing-boundary and color-quality safeguards. Review the rates of recovery, unresolved identity and missing measurements without automatically loosening thresholds.

## Reproduction and Regression Tests

From the repository, decode/read source recordings and run qualification without a recipe bank:

```sh
PYTHONPATH=backend .venv/bin/python backend/scripts/qualify_geometry_tracking.py \
  --decode --frames /absolute/path/to/source-frames \
  --output /absolute/path/to/qualification-results
```

Fresh decoding retains the existing macOS dependency. Already decoded frame evidence can be re-evaluated without decoding. Surface labels are read only after pixel tracking; labels never affect detection.

`backend/tests/fixtures/geometry_qualification/manifest.json` pins real dropout/departure regression clips to recording/frame hashes. Tests cover genuine departure, missing detections, expired budgets, capture gaps, changed appearance/geometry, sustained motion, unconfirmed identity and non-extending budgets. The full backend suite passed 342 tests after this change.

## Original Next Step (Completed)

Review the proposed eligibility table, then integrate qualified recorded identity/visibility evidence with comparison, pending groups, discovery and reuse. Keep numeric surface height excluded until its coverage/foam/placement cases are resolved. No frontend, live-camera or recipe-policy changes are part of this qualification work.

## Integration Review Outcome

The eligibility table has now been implemented for recorded processing. Direct final-color visibility is checked on the actual original sample images; body-edge loss during the fill can recover, but cannot substitute for unsupported final-color sample geometry. Numeric level remains excluded. See [recorded_workflow_integration.md](recorded_workflow_integration.md) for the same-pass producer, bank guard, legacy route behavior, versioned store and verification results.
