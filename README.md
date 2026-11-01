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
$env:MODEL_MODE = "real"
$env:ENABLED_MODELS = "measurements,model4"
pnpm run dev:integrated
```

Open http://localhost:5173/inspect. The original `/analyze` and `/experiments`
workflows remain available. No `.env` is needed: the commands above enable real
CPU measurements and Model 4 on port 8000, Express uses port 8787, and Vite uses
port 5173. Without the environment settings, Python defaults to measurements only.

Without PowerShell activation, start two terminals:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe backend/app.py
# Terminal 2
pnpm run dev
```

On macOS/Linux use `.venv/bin/python` and `source .venv/bin/activate`, then run
`MODEL_MODE=real ENABLED_MODELS=measurements,model4 pnpm run dev:integrated`.
Set `INFERENCE_URL` on Express when Python runs elsewhere (default:
`http://127.0.0.1:8000`). Keep the gateway private or use its optional shared
`INFERENCE_TOKEN`, configured identically on Node and Python.

## Available workflows

- **Solution overview (`/overview`):** actual installed evidence counts, full
  reference-bank size, current model configuration, and workflow links. Simulated
  six-case totals are excluded. Saved recipe-assessment counts come from the connected service; Model 4 image-comparison results remain unsaved.
- **Recipe library (`/recipes`):** all 52 integrity-checked nominal references,
  including 41, 50, 60 and 99, plus a separate unmatched-candidate collection read
  from the Python observation service. Candidates, assessments, reference patterns
  and collection history use local SQLite storage by default. The library shows
  timing/color-reference coverage separately from nominal dosing settings; automatic
  video/model observation extraction remains pending. No automatic
  promotion or recipe discovery is performed by the Model 4 comparison panel.
- **Inspection workspace (`/inspect`):** Recorded mode reviews videos 1–2 with
  sampled visual annotations for 22 fill sequences, native playback, and extraction
  of three post-fill frames. Original videos must be installed in
  `cosmos-original-dataset/videos`; an uploaded video can also be reviewed locally.
  Recipe evidence is assessed separately from the reference selected for Model 4 comparison.
  Missing timing/color references remain Insufficient Evidence; selection alone does not identify a recipe.
  Video sequence IDs do not establish batch position.
- **Model 4 comparison:** enable `ENABLED_MODELS=measurements,model4` with
  `MODEL_MODE=real` in Python before startup. Supply reliable vial/batch IDs and
  batch position, a comparison recipe, and three registered 640×480 images.
  The UI shows estimated proportions and differences from the selected reference,
  flags the first vial separately, and requires review. It does not identify a
  recipe, establish delivered volume, or automatically release a vial.
- **Live mode:** camera selection, preview, and disconnect controls. Browser camera
  access requires localhost or HTTPS and permission. Automated tracking, fill-end
  detection, and live frame capture are pending integration. Model 2 is pending;
  Model 3 is not connected; Cosmos retains its existing prompt-analysis workflow.
- **Analyze an image:** real upload through React -> Express -> Python. The CPU
  method measures average RGB in a user-selected region. It requires no weights
  or GPU, does not segment liquid, and abstains from defect and volume judgments.
  Mouse/touch rectangle drawing and numeric coordinates update each other; new
  image uploads reset the selection. The selected area is sent to real analysis.
- **Recorded experiments:** 30 saved anomaly results, thumbnail images, and Cosmos
  clip observations joined by vial ID. These come from different data pipelines;
  they are saved evidence, not new inference or a jointly validated model.
- **Original inspection pages:** six simulated review cases, still labeled as such.
- **Optional ResNet/Cosmos:** selected methods appear when enabled in Python health.
  An unavailable method returns an error, not fake results.

Uploaded images, manual guides and Model 4 comparison results are not persisted by this console. Recipe assessments and candidate records are persisted by the Python service. A remote Cosmos runtime can
retain its own inference artifacts; inspect its runtime policy before using it.

The optional Advanced Review panel contains recorded-video geometry tools for manual vial boxes and sloped dashed surface
guides at explicit timestamps. Reuse a saved box, mark the surface in another
frame, save, and optionally interpolate between keyframes. Guides are scoped to
the reviewed vial and hidden outside saved time ranges, with coordinates mapped
to the visible video content even when it is letterboxed. They are not object
detection, liquid segmentation, camera registration, or volume calibration. They
do not crop/resize or draw into Model 4 input images. Guides live only in the
current recorded-video page and reset on video/mode changes or navigation.

## Recipe assessment integration

The preset-video workflow uses the existing reviewed annotations, not new model
inference or automatic video detection. At a reviewed final sample, or using
Assess Selected Vial / Assess All Reviewed Vials, Node requests a server-side
assessment. Source observations and outcomes are saved and restored on reload.

Current compatibility audit: the packaged 52-recipe bank supplies nominal tank
amounts/order but no comparable per-dispense timing/color reference patterns.
The 22 reviewed fills retain sampling brackets and observed appearance; they do
not establish exact ingredient-dispense measurements. These remain partial
observations. All 22 therefore produce Insufficient Evidence with no learned
candidate. No milliliter-to-duration conversion, invented tank identity, or
midpoint-as-measurement is used. Model 4 mixture estimates are not recipe IDs.

The service requires coverage of the nominal reference bank before declaring
NO_MATCH. A complete existing reference can still match when others are missing.
With sufficient observations and complete reference coverage, intended patterns
are searched first, then unmatched patterns are reused or created. New candidate
IDs start above the nominal bank's highest ID. Candidates never automatically
become accepted references. Matching tolerances remain engineering defaults.

Default storage: `backend/.data/recipes.sqlite3`, ignored by Git and Docker build
contexts. Set `RECIPE_DB_PATH` to an absolute path on a durable mounted directory
in deployment. Preserve that directory and its SQLite journal files across
restarts/redeployments. Tests use isolated storage; no training fixtures are
inserted into the real bank. Repositories and source-evidence metadata commit
atomically; repeated evidence/reference versions reuse the same inspection.
Reference-pattern or matching-config changes create a new assessment version,
retaining history and marking older results as needing reassessment.

Python endpoints (Node proxies only the reviewed-video operations):

- `GET /api/recipe-workflow/status`: coverage, storage kind and saved-assessment count.
- `GET /api/recipe-workflow/videos/<video_id>/assessments`: latest saved result per vial.
- `POST /api/recipe-workflow/recorded/<video_id>/<vial_id>` with `{}`: assess the
  whitelisted server-side review; browser-supplied observations are rejected.
- `POST /api/recipe-workflow/observations`: trusted future producers supply a
  validated `observation` and a `source` description. Requires a configured
  `INFERENCE_TOKEN` and matching bearer credentials. This route is not exposed
  through the frontend bridge. This provides an integration contract; the
  camera/Model 2 observation producer is still pending.

The ingestion observation contains `run_id`, `vial_id`, `dispenses` (ordered
`color`, positive finite `duration_seconds`, optional `source`), `final_color`
and `filling_complete`. Partial evidence must not be fabricated into complete
dispenses. Node and Python share the optional inference token for reviewed
operations; Node rejects foreign-origin writes. Model inference remains on its
separate existing endpoints.

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
code, plus frozen Model 4 inference through the proxy, normal/first-vial review,
recipe references, recorded evidence, thumbnails and SPA routes. Set `PYTHON` to the Python
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

## Recorded Tracking-Gated Recipe Workflow (Current)

The experimental recorded workflow now processes installed Videos 1 and 2 from original pixels, qualifies tracking identity and direct final-color visibility, then compares timing/color and creates/reuses provisional observed patterns when the existing checks permit. Inspection Workspace displays tracking eligibility with each recipe outcome. Geometry and observer measurements come from one decode pass; overlays do not enter analysis images. Numeric liquid level remains excluded.

This current native workflow is distinct from the older reviewed-annotation/snapshot interfaces described above. Historical packaged snapshots lack the tracking proof and stay held; they cannot authorize recipe creation. Live recipe inspection remains deferred, and other model integrations are unchanged.

Producer 3 uses isolated demo engine 1.4. Preserve older pinned demo files and select a new separate `RECIPE_DEMO_DB_PATH` (for example, `recipe-demo-v1-4.sqlite3`) before enabling it. No automatic history migration or normal-bank changes occur. See [the detailed contract](backend/recipes/recorded_workflow_integration.md).
