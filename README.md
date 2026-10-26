# Integrated Vyflare workspace

The console combines `ui-development`, `full-stack-attempt` (which includes Amy's
three notebooks and the Cosmos gateway), and `vial-mix-anomaly-detection`.

## Complete local startup

Requirements: Node 24.19+ (24.x), pnpm 11.25+, Python 3.12+.
From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-integration.lock.txt
pnpm install --frozen-lockfile
.\.venv\Scripts\Activate.ps1
pnpm run dev:integrated
```

Open http://localhost:5173/analyze or http://localhost:5173/experiments.
No `.env` is needed: Python defaults to real CPU measurements on port 8000,
Express to port 8787, and Vite to port 5173. If an old `backend/.env` exists,
set `MODEL_MODE=real` and `ENABLED_MODELS=measurements` for the CPU workflow.

Without PowerShell activation, start two terminals:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe backend/app.py
# Terminal 2
pnpm run dev
```

On macOS/Linux use `.venv/bin/python` and `source .venv/bin/activate`.
Set `INFERENCE_URL` on Express when Python runs elsewhere (default:
`http://127.0.0.1:8000`). Keep the gateway private or use its optional shared
`INFERENCE_TOKEN`, configured identically on Node and Python.

## Available workflows

- **Analyze an image:** real upload through React -> Express -> Python. The CPU
  method measures average RGB in a user-selected region. It requires no weights
  or GPU, does not segment liquid, and abstains from defect and volume judgments.
- **Recorded experiments:** 30 saved anomaly results, thumbnail images, and Cosmos
  clip observations joined by vial ID. These come from different data pipelines;
  they are saved evidence, not new inference or a jointly validated model.
- **Original inspection pages:** six simulated review cases, still labeled as such.
- **Optional ResNet/Cosmos:** selected methods appear when enabled in Python health.
  An unavailable method returns an error, not fake results.

Uploads/results are not persisted by this console. A remote Cosmos runtime can
retain its own inference artifacts; inspect its runtime policy before using it.

## Connect the vial-only recipe classifier

Install torch/torchvision for your platform using `backend/requirements-models.txt`.
Keep weights outside Git. Create a JSON labels file containing this ordered array:

```json
["5","6","7","8","9","10","11","12","13","14"]
```

In `backend/.env`:

```dotenv
MODEL_MODE=real
ENABLED_MODELS=measurements,resnet18
RESNET_DEVICE=cpu
RESNET_CHECKPOINT=/absolute/path/to/vial_resnet18_recipe_model.pth
RESNET_LABELS=/absolute/path/to/recipe-labels.json
```

Restart Python and refresh the connection in Analyze an image. The adapter accepts
Model 1's `model_state_dict` bundle, validates recipe order, and applies its timestamp
mask and image-padding/normalization. Unknown custom preprocessing fails explicitly.
Fusion requires a paired-image adapter and is rejected by this single-image path.
Without custom weights, ResNet returns generic ImageNet demonstration classes.
Recipe scores are not calibrated defect probabilities. Actual checkpoint parity
and GPU inference have not been tested in this integration environment.

For Cosmos, follow [the DGX guide](backend/dgx/README.md), then enable
`measurements,cosmos_full` and set the existing `COSMOS_FULL_URL` tunnel destination.
Gateway health does not guarantee remote GPU readiness. Lite/Full are routes to
Cosmos3-Nano, not differently sized models. Browser cancellation does not stop an
already-running remote inference job.

## Verification

```powershell
pnpm run check
$env:PYTHONPATH = "$PWD\backend"
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p 'test_*.py'
pnpm run test:integration
```

The integration smoke test needs a production build and uses temporary ports 18000
and 18787. It tests a known red image through the actual HTTP proxy into real Python
code, plus recorded evidence, thumbnails and SPA routes. Set `PYTHON` to the Python
executable if your environment differs from `.venv`. CI uses the same workflow.

## Deployment and branch scope

The root Dockerfile now builds the Node console. The CPU Python image is
`backend/Dockerfile`, built with repository root as context. Python binds loopback
locally and supports `HOST=0.0.0.0` inside the container. GPU Cosmos uses its existing
DGX runtime, not this CPU container.

The existing `render.yaml` continues targeting `ui-development`; this integration
does not change the deployed service. A test Render service can target
`integration/usable-console` with the existing Node build/start commands and
`INFERENCE_URL` pointing to its private Python gateway. Recorded evidence works
without Python; image analysis requires a reachable Python service.

The reverted `model_api` FluidCheck service is not activated: it uses unfitted
physical parameters and a different schema. Its branch remains available. The
maintained Flask gateway provides the integrated runtime. Original notebooks and
Cosmos evidence remain in their team folders. Large existing source-branch videos
remain in Git history; this integration adds no new dataset or weight binaries.

## Submission limits

- Resolve the reported camera/video clock discrepancy before further training.
- Model 2's random-frame 100% score is not unseen-vial performance.
- Anomaly reference labels are rule-based/suspected, and threshold calibration
  reuses the evaluated pool: 5/5 suspected detections include five false alarms.
- Cosmos 24/30 color-description acceptance is a team review of one recorded batch.
- No calibrated milliliters, actual composition assay, verified carryover cause,
  production reliability, or measured scrap savings is established.
- Complete independent evaluation, external dataset/weight distribution, and a
  supervised CSI demonstration before making broader claims.
