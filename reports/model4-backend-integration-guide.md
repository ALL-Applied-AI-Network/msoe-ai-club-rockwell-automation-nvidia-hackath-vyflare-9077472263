# Cosmos worker for the recipe-detection backend

Integration target: [model4/recipe-detection-backend-integration](https://github.com/ALL-Applied-AI-Network/msoe-ai-club-rockwell-automation-nvidia-hackath-vyflare-9077472263/tree/model4/recipe-detection-backend-integration), commit `956d5d24d19f80b99f85d4841e678d20d533e0fb`.
This is the sole integration reference for this branch.

## Connect the existing backend

The reference branch's `backend/models.py` already has `RemoteCosmosModel`.
It posts one image and its prompt to a configurable worker URL. No reference
backend source modification is required to select our worker.

From the machine running that backend, establish a tunnel to the Spark:

```bash
ssh -N -L 8002:127.0.0.1:7865 yt-vyflare71b7@172.30.102.122
```

In the backend's environment, select the experimental LoRA worker:

```text
COSMOS_FULL_URL=http://127.0.0.1:8002/backend/predict
COSMOS_FULL_REMOTE_MODEL=cosmos
MODEL_MODE=real
ENABLED_MODELS=measurements,model4,cosmos_full
```

Preserve any other required enabled models in your existing configuration.
If the backend runs on the Spark itself, use port 7865 directly. If it runs in a
container, its loopback address is the container's own network: arrange the tunnel
or reachable host address accordingly. Restart the backend after configuration.
The frontend continues using its normal backend API with model `cosmos_full`;
the worker multipart field is `cosmos` (or the accepted alias `cosmos_lite`).

The native Cosmos Framework worker on port 8001 remains separate and unchanged.
Selecting this LoRA worker is an explicit experimental configuration choice.
Unlike that native worker, this extracted reasoner does not provide Framework
guardrail screening; the response reports that screening is not provided.

## Worker contract

`POST /backend/predict` on the existing port 7865 accepts multipart fields:

| Field | Required content |
|---|---|
| `frame_id` | Caller identifier, 1–128 characters |
| `model` | `cosmos` or `cosmos_lite` |
| `prompt` | Caller prompt, 1–2,000 characters; forwarded to inference |
| `image` | JPEG or PNG; request at most 5 MiB; image at most 16 megapixels |

Responses echo `frame_id` and `model`, set `mode=real`, and include
`inference_ms` plus `result.text` and `result.execution`. Execution metadata is
read from the actual runtime: Linux, aarch64 and NVIDIA GB10. The worker also
returns model provenance, input hash, applied prompt and task limitations.
The prompt can request a JSON answer, but this route returns raw generated text;
it does not force every answer into the legacy color-list schema.

The image route and existing video/photo `/predict` route share a nonblocking
inference gate. Busy requests return 429 with `Retry-After: 1`; skip or retry
frames rather than accumulating a real-time backlog. Invalid inputs return
400/413/415, unavailable execution metadata 503, and inference failures 500.
No safety approval is fabricated. Only one model remains resident.

## Responsibilities and limits

Model 4 retains its own mixture estimates, measurement outputs and review policy.
Cosmos supplies supporting appearance text. This interface does not establish
which tank dispensed, measured doses, total volume, contamination or chemical
identity, and it does not create recipe match percentages or authorize release.
Single-frame inspection also cannot recover a full dispensing history. Photo
behavior remains exploratory because the active Version 1 adapter trained on
videos.

Use the direct worker on port 7865. The obsolete port 7866 gateway, its client,
configuration, tests and deployment guides have been removed from this branch.
Earlier revisions remain recoverable through Git history. An older deployment
outside this checkout may still exist; it is not the integration endpoint.

## Verification boundary

Automated tests cover field validation, real-response shape, prompt forwarding,
image cleanup, error handling, execution metadata and concurrency. A separate
check uses the actual `RemoteCosmosModel` class from the pinned branch.
Live worker results and remaining deployment work are recorded in the
[correction report](model4-integration-correction.md). The full team's Model 4
backend and frontend handoff still requires their running service; its URL was
not available for this task. Successful protocol tests are not accuracy evidence.

To repeat the actual reference-client check from the repository root, fetch the
reference branch first, then use a Python environment with Flask and Pillow:

```bash
python -m pip install -r requirements-worker.txt
python scripts/check_model4_reference_client.py --output outputs/contract-check-new.json
python scripts/check_model4_reference_client.py --url http://127.0.0.1:8002/backend/predict --image /path/to/vial.png --output outputs/live-check-new.json
```

Use a new output path for each run. The first command uses a fixture runtime;
the second performs real inference. The script records the fetched reference
commit so checks against future branch revisions are distinguishable.
