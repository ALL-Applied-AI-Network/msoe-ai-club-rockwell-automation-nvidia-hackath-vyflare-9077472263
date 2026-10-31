# Cosmos/Amy companion implementation - October 30, 2026

> Historical implementation record, superseded for integration October 31.
> See the [correction report](model4-integration-correction.md) and
> [current reference-branch guide](model4-backend-integration-guide.md).
> This record documents the earlier custom gateway, not compatibility with the
> reference branch's native `RemoteCosmosModel` contract.

## Scope and decision

The latest user instruction separates ownership: teammates work on Amy's models;
this work makes Cosmos usable alongside them. The changes are on the Cosmos
branch only. Earlier Amy process-prototype files remain isolated/unmerged and
were not committed or pushed to Amy's branch. No Amy notebook, checkpoint,
backend decision logic or active service was changed by this companion work.

Cosmos remains an appearance observer. It must not substitute its color sequence
for source identity, event timing, dose, mixture proportions or total volume.
No weights were updated. The active worker still serves the original Version 1
adapter, not the experimental synthetic continuation.

## Implemented

- `scripts/cosmos_companion.py`: versioned appearance envelope, context validation,
  upload/worker hash agreement, explicit unmeasured quantities, and a read-only
  attachment to the existing Model 4 response contract.
- `scripts/serve_cosmos_companion.py`: lightweight Flask/Waitress gateway. It
  calls the existing worker with adapter mode and neutral filenames. It never
  sends caller IDs, expected recipes, or tank assignments into the model prompt.
- `scripts/request_cosmos_observation.py`: standard-library client and optional
  saved-Model-4-result attachment; fresh output paths required.
- An editable context example, isolated gateway requirements, contract/ownership
  guide, and 13 new contract/API tests.

The wrapper retains the whole Amy response unchanged. Cross-vial, cross-batch,
optional run mismatches, unverified binding and invalid Cosmos schemas are
rejected for combination. Existing Amy review and challenger flags are not
cleared by a plausible Cosmos color. The wrapper issues no combined verdict,
confidence percentage, recipe creation or history mutation.

## Validation readings

| Check | Result |
|---|---|
| Local Cosmos test suite | 40 passed, no skips, including existing tester tests |
| Live worker | Existing Version 1, unchanged adapter path/source snapshot |
| Live gateway | Ready on private-network port 7866 |
| Real inference input | Original reviewed video5-vial-04 clip, 23.0667 s |
| Output | observed_color_sequence = [green], schema valid, advisory_only |
| Worker processing time | 3.1883 s for that one inference; not exclusive GPU time |
| Media hash | Returned worker hash matched uploaded bytes |
| Provenance window | 138.25-161.3167 s on caller-declared video-5 timebase |
| Gateway process snapshot | PID 1125645; 37,040 KiB RSS (about 36.2 MiB) |
| Additional GPU model/training | No additional model load; zero training updates |
| Live Amy service handoff | Deferred by user; backend URL unavailable |

The test timestamp was 2026-10-31 04:52:35 UTC, corresponding to October 30 at
11:52:35 PM America/Chicago. Source worker request ID:
`09559e40a4de4174a9e5a7f84a9e1dbf`. The full saved response is private under
`outputs/cosmos-companion-v1/live-observation.json`.

Vial association and recording offset were provided from the existing reviewed
clip metadata. The gateway did not infer or independently verify that identity.
This one successful request demonstrates transport/provenance behavior, not
new color accuracy or factory inspection performance.

## Compatibility evidence

Inspected the latest remote Amy branch and Model 4 integration branch. Amy's
notebook branch is at `97fb0ba26a06d716bcd3dd0be0042729f0b506f0`. The concrete
Model 4 envelope is documented in backend/MODEL4_API.md at integration commit
`956d5d24d19f80b99f85d4841e678d20d533e0fb`. Its nested result and review are
preserved, not converted into a replacement mixture model.

No source/weights from the earlier local Amy prototype are included in this
Cosmos commit. The new test cases use explicitly fake Model 4 envelopes to
exercise preservation and mismatch handling; a real joint backend request has
not been performed. The teammate-reported flow recalls and level coverage are
not claimed as measurements of this implementation.

## Limits and next joint test

The serving model still has its previously documented accuracy and photo-format
limitations. Video answers have clip-level order but no measured transition
times. Thirty-two samples can miss brief changes. The companion cannot establish
chemical identity, calibration, source order, registered geometry or physical
vial tracking. Valid structured output is not ground truth.

When the team is ready, use shared tracking IDs and original captures to call
both running services. Confirm that the combined record preserves Amy's estimates
and review, rejects an intentionally wrong vial ID, and does not create recipes
or release decisions. Then evaluate real inspection performance with independently
verified labels. The user explicitly asked to postpone the live joint test until
the Amy backend can be accessed.

Run/access instructions and the precise payload contract are in
`reports/cosmos-amy-companion-guide.md`. Gateway code is on
`codex/cosmos3-nano-finetune`; it is not an Amy model recreation.
