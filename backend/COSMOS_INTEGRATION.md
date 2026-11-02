# Recorded-Frame Cosmos Integration

This console uses the current `codex/cosmos3-nano-finetune` interface, verified at commit `8d66f7ef043aa3c4b6f1e37bc63988e7c579a6e0` on 2026-11-01. The upstream guide is `reports/model4-backend-integration-guide.md` on that branch. No branch merge or retraining is required.

## Worker Selection

Use the resident **Version 1 LoRA worker on DGX port 7865**, route **`/backend/predict`**. It implements the existing backend's `RemoteCosmosModel` request/response contract. Do not confuse it with the native Framework model on port 8001, or the retired companion gateway on 7866.

The inspected worker reports the `pilot-v1/adapter-step-020` adapter and base snapshot `e59a53c25979a090fa8706c9acc0c254a6e89b92`. The adapter file SHA checked through SSH matches the guide: `9dae56b981de7e7de200e39580e57cbcba81d3efdcf940f2e025e80a41a3a5f4`. This checks the documented artifact on disk and reported runtime identity, not a hash recomputed from resident GPU tensors. The synthetic continuation remains unpromoted.

From the backend machine, keep a private tunnel open:

```sh
ssh -N -L 127.0.0.1:8002:127.0.0.1:7865 yt-vyflare71b7@172.30.102.122
```

Configure the Python gateway process (preserve any other enabled models you need):

```dotenv
MODEL_MODE=real
ENABLED_MODELS=measurements,model4,cosmos_full
COSMOS_FULL_URL=http://127.0.0.1:8002/backend/predict
COSMOS_FULL_REMOTE_MODEL=cosmos
COSMOS_EXPECTED_IMPLEMENTATION=cosmos3-nano-vial-lora
```

Restart the gateway after configuring it. From the repository root, the Python entry point is `.venv/bin/python backend/app.py`. The regular console uses `pnpm dev`; its Node gateway defaults to `INFERENCE_URL=http://127.0.0.1:8000`.

The optional expected-implementation setting rejects a wrong worker rather than silently using the native model. It does not pin adapter weights. Native Framework use remains possible with its own explicit URL and this expectation unset. The example environment now documents the LoRA endpoint; actual environment files were not edited.

## Inspection Workspace Test

1. Open Recorded mode and seek/pause at the evidence you want.
2. Under **Ask Cosmos About a Frame**, select **Capture Current Frame for Cosmos**.
3. Inspect the clean captured image and its source/time. Video overlays are not included.
4. Enter a prompt and select **Ask Cosmos**. GPU access and a real configured route are required.
5. Read the observation and expand **Cosmos Evidence and Execution** to inspect the applied prompt, frame ID, capture hash, actual worker identity, execution and limitations.

Only the captured still is sent. The worker identity’s `frames:32` field is video configuration, not the frame count of this still-image request. Playing a recording does not automatically call Cosmos. Fine-tuned photo behavior is experimental because this adapter trained on videos. This feature is not full-video sequence reasoning or automatic continuous inspection. The branch's existing port-7865 video tester remains separate; automatic video-Cosmos orchestration is future work.

The browser capture position is not a validated presentation timestamp. The captured PNG hash identifies the uploaded snapshot. The backend/remote client may resize/re-encode before worker inference, so the worker input hash can legitimately differ. Both are identified separately. Recording source changes remount the panel and cancel pending requests; editing prompt/model clears the previous observation. Moving playback alone does not change the captured evidence.

## Separation From Recipe Decisions

Cosmos is supporting appearance text only. Its prose never becomes dispense timing, measured volume, chemical identity, recipe identity, a pending-group vote or a bank mutation. Recipe matching/discovery retains all its current timing, color, tracking and lineage gates. Model 4 retains a separate explicit three-frame comparison API; its manual form is no longer mounted on Inspection Workspace. The current automatic log does not call Cosmos or Model 4.

Successful HTTP results must match the submitted frame and route. Mock observations are rejected; errors and GPU busy responses stay visible, with no fallback to saved Video 5 descriptions. Cancellation aborts the client request; a running GPU request may finish remotely.

The LoRA worker explicitly reports **no Framework content screening**. This is surfaced in the UI; the native worker's screening claims are not attached to this model.

## Verification Performed

The real browser → Node → Python → SSH → LoRA worker path was tested with Video 1 at browser time 28.00 seconds. The worker returned real Linux/aarch64/NVIDIA GB10 execution and:

> The vial contains a blue liquid. The vial is partially obstructed by a black object.

Gateway inference time was approximately 3.83 seconds. This establishes transport, correct worker selection, prompt/provenance forwarding and rendering, not inspection accuracy. Both temporary recipe-store contents stayed unchanged. The normal application bank was not opened by this isolated preview.

At the Cosmos integration checkpoint, validation passed 358 backend tests and 40 frontend/server tests, plus TypeScript and production build. These are historical counts; see the root README for the current recorded-workflow validation and Model 2 parity issue. Evidence is under the project-level `outputs/cosmos-recorded-integration-2026-11-01/`.
