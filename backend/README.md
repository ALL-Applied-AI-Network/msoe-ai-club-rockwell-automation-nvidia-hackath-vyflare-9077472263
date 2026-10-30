# VyFlare inference backend

For the deployed worker and step-by-step laptop startup, see
[DGX startup instructions](dgx/README.md). The current DGX Framework release
disables image content classification; the API reports that limitation
explicitly rather than claiming an image safety pass.

## Cosmos Lite / Full switch

The included frontend requests **ResNet-18 plus the selected Cosmos model**
for each photo by sending `include_resnet=true`. The backend runs them
sequentially under one inference gate and returns both outputs in
`results.resnet18` and `results.cosmos_lite` or `results.cosmos_full`.
The existing `result` field continues to contain the selected Cosmos output.
If either model fails, the request returns an error without partial results.
Requests without `include_resnet=true` retain single-model behavior; the
DGX worker receives single-model requests and needs only Cosmos enabled.

For real paired inference use `MODEL_MODE=real` and enable both ResNet and
the chosen Cosmos route. On Windows, `ENABLED_MODELS=resnet18,cosmos_full`
can use local CPU ResNet and the DGX worker. Enabling `cosmos_lite` still
requires the existing local Linux/CUDA runtime; mock mode does not run models.

The frontend selects the destination per request using the existing multipart
`model` field. There is no global switch shared between clients:

| Value | Execution |
| --- | --- |
| `resnet18` | Local ResNet-18 (unchanged) |
| `cosmos_lite` | Local existing Cosmos3-Nano adapter |
| `cosmos_full` | HTTP request to the DGX worker |
| `cosmos` | Legacy local Cosmos alias; also the DGX worker selector |

For a dropdown, send `body.append('model', 'cosmos_lite')` or
`body.append('model', 'cosmos_full')` with the image, frame ID, and prompt.
The response echoes the frontend selector and original frame ID. `/health`
lists enabled selectors; it reports gateway initialization, not DGX readiness.
Mock mode mocks both routes and does not contact the DGX.

### Local gateway

In `backend/.env`:

```dotenv
MODEL_MODE=real
ENABLED_MODELS=resnet18,cosmos_lite,cosmos_full
COSMOS_CHECKPOINT=Cosmos3-Nano
COSMOS_FULL_URL=http://127.0.0.1:8001/predict
COSMOS_FULL_REMOTE_MODEL=cosmos
COSMOS_FULL_TIMEOUT_SECONDS=120
```

The Lite label uses the existing Cosmos3-Nano implementation; it does not add
a new smaller checkpoint or a Windows-compatible runtime. This adapter still
requires its Linux/CUDA Framework environment. To run only ResNet and remote
Full on Windows, use `ENABLED_MODELS=resnet18,cosmos_full`. To test all dropdown
choices without model dependencies, use `MODEL_MODE=mock`.

### DGX worker

Place this backend folder on the DGX and use the validated Cosmos Framework
environment. In the DGX copy's `.env`, configure:

```dotenv
PORT=8001
MODEL_MODE=real
ENABLED_MODELS=cosmos
COSMOS_CHECKPOINT=/absolute/path/to/your/full/cosmos/checkpoint
COSMOS_MAX_NEW_TOKENS=256
```

Run `python app.py` there. The checkpoint must support the existing
Cosmos Framework reasoner interface in `Cosmos3Model`; a different Cosmos
architecture requires a corresponding adapter. `ENABLED_MODELS=cosmos` runs
locally on the worker and prevents recursive forwarding. Full weights load
only on the DGX; Lite weights load only on the gateway.

On Windows, keep this SSH tunnel running in a separate terminal:

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 8001:127.0.0.1:8001 yt-vyflare71b7@172.30.102.122
```

The worker stays bound to loopback. Use the tunnel instead of exposing the
unauthenticated API on the network. Check worker initialization through
`http://127.0.0.1:8001/health`; it must report `mode: real` and `cosmos`.
Start the local gateway with `python app.py` and select either route in the
included test client. No worker was installed or started automatically.

Remote safety rejections return 422, busy workers return 429 with Retry-After,
connection failures return 503, timeouts return 504, and invalid responses or
other worker failures return 502. Full never falls back to Lite or mock.
Mock responses from a worker are rejected. A gateway timeout releases its
gate but does not cancel inference already running on the DGX.

Full results must also include runtime-reported Linux/aarch64/NVIDIA GB10
execution metadata. Results from other hardware or older workers without
metadata are rejected with 502. Returned Cosmos results include the worker
hostname and GPU so the execution destination is visible. This metadata is
a configuration check, not hardware attestation: use the SSH tunnel to
`yt-vyflare71b7@172.30.102.122` to establish the destination. Deploy the updated
`models.py` with the worker before using Full. Local Cosmos weights are never
loaded by the `cosmos_full` adapter, and it has no local fallback.

Flask API for ResNet-18 classification and Cosmos3-Nano image reasoning. This folder is designed to live at `backend/` in the team repository. `frontend/` is a small API test client, not the final product UI.

## What is implemented

- Browser/test client at port **3000**, Flask/Waitress API at **8000**, both bound to loopback.
- Explicit CORS origins for localhost and 127.0.0.1 on port 3000. CORS controls browser access; it does not assign or reserve ports and is not authentication.
- `POST /predict`: multipart image, frame ID, model selector, optional Cosmos prompt.
- Models load once before the server starts. One inference at a time across both models prevents simultaneous GPU workloads. Extra requests receive 429; the client skips frames instead of queuing them.
- Mock mode clearly marks all results as transport tests. It never claims to run models or safety classifiers.
- Real ResNet-18: pretrained ImageNet baseline, or a custom state dictionary with ordered class labels.
- Real Cosmos3-Nano: persistent Cosmos Framework reasoner pipeline, prompt/output checks through its text guardrail (Qwen3Guard), and explicit uploaded-image screening and face processing through its visual guardrail (Cosmos-Guardrail1).

**Validation boundary:** API tests run with mock adapters. Real Cosmos execution, guardrail behavior, memory use, and latency must be validated in the target Linux/NVIDIA environment. The Cosmos adapter uses Framework Python interfaces inspected on October 23, 2026; they are not a versioned stable SDK. Pin the validated Framework commit before the demo. A single image cannot establish motion or temporal event history.

## This development machine

MacBook Pro, M4 Pro, 24 GB unified memory: run ResNet on CPU first, or try `RESNET_DEVICE=mps` after verifying the CPU baseline. The prepared local `.env` enables real ResNet only. Cosmos3-Nano is implemented for a compatible Linux/NVIDIA device and is not runnable through this CUDA adapter on the Mac. To test both routes without Cosmos weights, use `MODEL_MODE=mock` and `ENABLED_MODELS=resnet18,cosmos`.

The local Cosmos setup below also applies to the DGX worker. Use the routing
configuration above for the two-machine topology.

## 1. Start without model downloads

From this folder, on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python app.py
```

On Windows PowerShell, use `py -m venv .venv`, `.venv\Scripts\Activate.ps1`, and `Copy-Item .env.example .env`. This supports mock/ResNet use; the Cosmos instructions below target Linux/CUDA.

In a second terminal, from the same folder:

```bash
python3 -m http.server 3000 --bind 127.0.0.1 --directory frontend
```

Open http://localhost:3000, click **Check API**, then upload a JPEG/PNG or start the camera. Health should show `mode: mock`. Camera access is requested only after you click Start.

## 2. Enable ResNet-18

In the API virtual environment:

```bash
python -m pip install -r requirements-models.txt
```

For CUDA, install the matched torch/torchvision pair recommended by the [PyTorch installation selector](https://pytorch.org/get-started/locally/) for your driver first. The file above is suitable for the initial CPU baseline; it is not a CUDA platform lockfile.

Edit `.env`:

```dotenv
MODEL_MODE=real
ENABLED_MODELS=resnet18
RESNET_DEVICE=cpu
```

Restart the API. The first start downloads torchvision's pretrained weights. Subsequent starts reuse its cache. `cuda:0` can be used on a compatible NVIDIA system; `mps` can be tried on a supported Mac.

ImageNet labels are general object categories, **not vial defects or your custom project classes**. No defect detection accuracy is implied. To use a trained classifier, set:

```dotenv
RESNET_CHECKPOINT=/absolute/path/resnet18.pt
RESNET_LABELS=/absolute/path/labels.json
```

`labels.json` is a JSON array in the exact training class order. The checkpoint must be a ResNet-18 state dictionary (or a dictionary containing `state_dict`) with matching classifier dimensions. Strict loading deliberately rejects incompatible weights. Update the validation transform in `models.py` to match training; the default is torchvision's ImageNet transform. Softmax scores are not calibrated probabilities.

## 3. Enable Cosmos3-Nano and safety checks

For this frame-based API, Cosmos uses **reasoner mode (image + prompt → text)**. Video generation, action generation, and multi-frame event reasoning are separate future endpoints.

NVIDIA lists workstation/datacenter GPUs such as RTX PRO 6000, H100, or B200 for Nano. Hardware suitability depends on the loaded towers, precision, context, and guardrails; do not assume it fits on an ordinary laptop just because it is named Nano. The full checkpoint is roughly 35 GB on Hugging Face, plus dependencies and safety models. This Mac can develop/test the API, but the supplied Cosmos runtime requires Linux/CUDA.

1. Follow [Cosmos Framework setup](https://github.com/NVIDIA/cosmos-framework/blob/main/docs/setup.md) on the actual demo device. Use its locked Python/PyTorch/CUDA environment. Do not install `requirements-models.txt` over that environment.
2. Obtain access to the required model repositories, including [Cosmos3-Nano](https://huggingface.co/nvidia/Cosmos3-Nano), [Cosmos-Guardrail1](https://huggingface.co/nvidia/Cosmos-Guardrail1), and [Qwen3Guard-Gen-0.6B](https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B). Authenticate through the model tooling; never put an access token in browser code or Git.
3. In the activated Framework environment, install this API's small dependencies with `python -m pip install -r /absolute/path/to/backend/requirements.txt`.
4. From this backend folder, set `.env` as below, then run `python app.py` with the Framework environment's Python.

```dotenv
MODEL_MODE=real
ENABLED_MODELS=resnet18,cosmos
RESNET_DEVICE=cpu
COSMOS_CHECKPOINT=Cosmos3-Nano
COSMOS_MAX_NEW_TOKENS=256
```

Keeping ResNet on CPU initially leaves GPU memory available for Cosmos. The model/guardrail pipeline loads before port 8000 begins accepting requests; initial setup can take a long time. Guardrails stay enabled, with CPU offloading between calls. No fallback to mock or unscreened text occurs on failure.

The adapter screens the prompt, screens the image as a single-frame array, applies the visual runner's postprocessing, and generates text using the persistent pipeline. It only returns a successful result after text screening. Framework-generated safety errors may arrive as generic HTTP 500 errors, while explicit adapter safety rejections return 422. Both withhold output. Test allowed and rejected samples on your installed Framework version before relying on the integration. These content safety models do not validate industrial defect judgments or machine safety.

Temporary input/output files are created for the Framework's file-based sample interface and removed after each request. Framework logs may contain prompts and rejection details. No image archive is maintained by Flask.

## API contract

`GET /health` reports mode, enabled models, and busy status. It is available only after model initialization succeeds.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict \
  -F image=@frame.jpg -F frame_id=42 -F model=resnet18
curl -X POST http://127.0.0.1:8000/predict \
  -F image=@frame.jpg -F frame_id=43 -F model=cosmos \
  -F 'prompt=Describe the visible scene briefly.'
```

A successful response contains `frame_id` (string), `model`, `mode`, `result`, and `inference_ms`. ResNet returns `result.predictions`; Cosmos returns `result.text` and safety-check status. Mock results always include `result.mock: true`.

Error codes: 400 invalid fields/image; 403 disallowed browser origin; 413 body/pixel limit; 415 unsupported image format; 422 explicit safety rejection; 429 busy; 500 inference/runtime failure. Body limit: 5 MiB. Pixel limit: 16 million. Images are bounded to 1280×1280 before model preprocessing.

A browser request should use `FormData` without a manual `Content-Type` header:

```javascript
const body = new FormData();
body.append('image', jpegBlob, 'frame.jpg');
body.append('frame_id', String(frameId));
body.append('model', 'resnet18'); // or cosmos
const response = await fetch('http://127.0.0.1:8000/predict', {method: 'POST', body});
const payload = await response.json();
if (!response.ok) throw new Error(payload.error);
```

## Scheduling and ports

- Keep one outstanding request in the frontend. The test client targets 2 FPS for ResNet and one request per 5 seconds for Cosmos, skipping captures while busy. Neither interval is a throughput guarantee.
- Changing model or stopping camera invalidates late results using a session counter and echoed frame IDs. Stopping capture does not cancel GPU inference already running.
- Both models share one inference gate. A slow Cosmos request pauses ResNet work too; a production scheduler or separate model workers would be needed for uninterrupted ResNet updates.
- If port 8000 is occupied, set `PORT=8001` and change the test client's API URL. If port 3000 changes, update `CORS_ORIGINS` as well. Do not kill an unknown process just to free a port.
- Use one API process, with no debug reloader. Multiple workers would duplicate model memory and each have its own gate.
- This is a local demo. Do not expose these unauthenticated endpoints on a shared/public interface.

## Verification

```bash
python -m unittest discover -s tests -v
```

API tests cover model routing, CORS, validation, backpressure, and error/guardrail rejection recovery. The browser camera flow requires manual permission and testing on the target browser. Before demo day, pre-download all weights, start both models, verify `/health` shows real mode, test both routes and rejected content, and record actual latency/memory on the target hardware.

## References

- [Flask deployment](https://flask.palletsprojects.com/en/stable/deploying/)
- [Flask-CORS configuration](https://flask-cors.readthedocs.io/en/latest/configuration.html)
- [torchvision ResNet-18](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.resnet18.html)
- [Cosmos model matrix](https://docs.nvidia.com/cosmos/latest/cosmos3/model_matrix.html)
- [Cosmos Framework inference and guardrails](https://github.com/NVIDIA/cosmos-framework/blob/main/docs/inference.md)


## Read-only recipe endpoints

The Python API now exposes `GET /api/recipes` (intended recipes by default),
`GET /api/recipes?collection=UNMATCHED`, and `GET /api/recipes/<id>`.
Lists return `{"collection": "INTENDED", "recipes": [...]}`; detail returns
`{"recipe": {...}}`. Metadata includes ID, collection, derived dispense count,
ordered dispenses, and final color. Invalid parameters return 400; unknown IDs
return 404. If `INFERENCE_TOKEN` is set, include its Bearer authorization header.

One repository is shared across requests through
`app.extensions["recipe_repository"]`; it starts empty and resets on restart.
Applications/tests can inject it with `create_app(..., recipe_repository=repo)`.
These routes are separate from the Express console's existing demo recipe data.
See [recipe design and API contract](recipes/recipe_design.md) for details.


## Recipe promotion, demotion, and history

- `POST /api/recipes/<id>/promote` approves an unmatched recipe as intended.
- `POST /api/recipes/<id>/demote` moves an intended recipe to unmatched.
- `GET /api/recipes/<id>/history` returns collection-change history.

POST requests require JSON containing only `{"reason": "Explanation"}` and return
`{"recipe": {...}}`. Configure both `INFERENCE_TOKEN` and
`RECIPE_MANAGEMENT_ACTOR` on the server, then send `Authorization: Bearer <token>`.
Without that configuration, writes are disabled (503); invalid credentials return
401. The configured actor identifies the calling service, not an individual user.
Every holder of this shared token has management access. Per-user approval roles
remain a future authentication integration. Never send `changed_by` from the UI.

History returns `{"recipe_id": 1, "history": [...]}` with actor, reason, UTC time,
old/new collections, and unique change ID. Moves preserve recipe IDs and metadata;
repeating a move to the current collection does not duplicate history. Historical
vial inspections are unchanged. Missing recipes return 404; invalid IDs/bodies
return 400; non-JSON requests return 415. History follows the existing read-token
policy. All storage remains in memory; no frontend actions are connected yet.
