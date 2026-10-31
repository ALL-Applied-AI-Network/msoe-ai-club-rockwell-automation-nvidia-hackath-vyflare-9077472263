# Cosmos integration correction — October 31, 2026

## Decision and cause

The user corrected the integration target to
[model4/recipe-detection-backend-integration](https://github.com/ALL-Applied-AI-Network/msoe-ai-club-rockwell-automation-nvidia-hackath-vyflare-9077472263/tree/model4/recipe-detection-backend-integration).
The reviewed commit is `956d5d24d19f80b99f85d4841e678d20d533e0fb`.
Work remains on `codex/cosmos3-nano-finetune`.

The earlier companion gateway packaged appearance evidence in a custom schema.
That was useful for attaching caller-provided vial and batch metadata, but it
did not implement the requested branch's native Cosmos worker contract. Naming
it a companion integration overstated its readiness for that backend. The
correction targets the real `RemoteCosmosModel` client in `backend/models.py`.

## Changes

| Before | Current implementation | Reason |
|---|---|---|
| Custom observation gateway on 7866 | `/backend/predict` on resident worker 7865 | Accept the reference client's actual request format |
| Gateway-specific context and media fields | `image`, `frame_id`, `model`, `prompt` multipart fields | Match the reference backend without copying its measurement models |
| Fixed appearance question | Forward the caller's prompt into inference | Preserve the backend's requested inspection task |
| Custom evidence envelope | Echoed IDs, `mode=real`, text and actual execution metadata | Satisfy the client's real-worker validation |
| Ambiguous integration reference | Pinned reference branch and commit, updated guides | Make ownership and implementation target explicit |
| Separate inference request paths | One shared nonblocking inference gate | Prevent overlapping inference on the same resident model |

`scripts/model4_worker_contract.py` registers the route. Changes to
`serve_spark_adapter.py` collect runtime metadata and support explicit prompt
overrides while keeping the browser tester's original prompts. Input validation,
image cleanup, busy responses and inference errors are covered by tests.
The subsequent branch cleanup removed the obsolete gateway, client, context
configuration and associated tests and guides. Only the direct reference-client
integration remains. The consolidated PDF describing the retired gateway was
also removed; prior revisions remain available through Git history. Other
training reports remain because they describe the actual Cosmos experiments.

## Model and hardware impact

There was **no training, weight update or accuracy improvement** in this change.
The worker still loads Version 1, adapter SHA-256
`9dae56b981de7e7de200e39580e57cbcba81d3efdcf940f2e025e80a41a3a5f4`,
with source base snapshot `e59a53c25979a090fa8706c9acc0c254a6e89b92`.
The synthetic continuation remains experimental and unpromoted because its real
final-color development result regressed. Previous validation scores do not
measure this new single-frame prompt interface.

Only our idle tester was restarted: old PID 828715, replacement PID 1135162.
The restart verified its PID ownership, active adapter and exact adapter hash,
and saved the previous command in `tester-before-model4-worker.json` on the
Spark. Updated scripts are in `scripts/model4-worker-v1` under the experiment
directory. The native Cosmos Framework worker on 8001 was left untouched and
its health remained ready. No second copy of our LoRA model was loaded by this
interface, and no optimizer steps were run.

This worker does not provide the native Framework worker's guardrail screening.
Its response explicitly records that absence. It is a configurable experimental
alternative, not a claim of feature parity with the native worker.

## Validation

Before cleanup, all **45 local tests passed**, including five new worker-contract tests. The
tests cover request validation, prompt preservation, expected response fields,
verified hardware requirements, shared concurrency exclusion, cleanup and
failure recovery. Tests initially encountered Windows sandbox temporary-file
permissions; rerunning with approved filesystem access passed. The logged
fixture inference exception is intentional coverage of the 500 response.

`scripts/check_model4_reference_client.py` loads the actual reference branch's
`RemoteCosmosModel` from Git without initializing its other models. The local
transport check passed using a fixture runtime; its hardware values are test
fixtures, not evidence of live GPU execution. Evidence was saved separately in
`outputs/model4-backend-contract/client-contract-test.json`.

The **live reference-client check passed** against
`http://172.30.102.122:7865/backend/predict`. It used a 640×480 end frame from
the existing `vial-04.mp4` development clip. The real worker returned Linux /
aarch64 / NVIDIA GB10 execution metadata, the unchanged Version 1 identity and
the exact caller prompt. Its answer was: “The visible liquid in the vial is
black.” Visual inspection shows a very dark liquid region with greenish edges;
this one answer is not a scored accuracy result or proof that still-frame
inspection matches the reviewed whole-video label. Evidence is saved in
`outputs/model4-backend-contract/client-live-test.json` and `frame.png`.

The original `/predict` video route also passed a live regression smoke check:
the same complete development clip returned valid JSON with
`observed_color_sequence=["green"]` in 3.23 seconds. Evidence is saved in
`outputs/model4-backend-contract/legacy-video-smoke.json`. The difference between
the single frame's black answer and the video's green answer reinforces the
need to validate capture framing and context before comparing model results.

The direct client accepted the response, establishing protocol compatibility
with the pinned implementation. The check does not exercise the frontend or
the reference backend's complete Model 4 route.

## Branch cleanup verification

The cleanup removed three obsolete gateway/client modules, their example context,
13 gateway-specific tests, two retired guides and the consolidated PDF describing
that integration. Worker HTTP dependencies are now `requirements-worker.txt`.
The remaining **32 tests passed**, including all five direct-worker contract
tests. The actual reference branch client check passed again after cleanup,
with evidence in `outputs/model4-backend-contract/client-cleanup-check.json`.
The earlier count of 45 includes the 13 deliberately removed gateway tests.

The reference was freshly fetched and remains at commit `956d5d2`. Both paths
derive from Cosmos3-Nano, but the reference defaults to the native Framework
worker while this branch serves an extracted reasoner with our Version 1 LoRA.
Request/response compatibility is confirmed; identical weights, guardrails and
prediction behavior are not claimed. No model retraining was performed during
cleanup. Retained text and PDF reports were checked for retired integration
references. Git history remains intact for auditability.

## Application verification remaining

The team's complete Model 4 backend/frontend handoff remains untested because
its running URL was unavailable and the user deferred that check. Direct worker
compatibility does not establish a combined application deployment or factory
accuracy. No Model 4 implementation, calibration or decision policy was copied,
retrained or replaced. Separate unmerged prototype worktrees are outside the
tracked branch contents and were not imported into this integration.

Cosmos still supplies appearance observations rather than measured ingredient
identity, delivery amount, full event history or a release decision. The next
application check is to configure the reference backend to this worker, submit
the same capture through its frontend, and verify IDs, errors and review behavior
with the team's running service. See the [configuration guide](model4-backend-integration-guide.md).
