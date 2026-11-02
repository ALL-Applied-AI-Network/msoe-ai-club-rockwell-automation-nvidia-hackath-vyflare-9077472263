# Integrated Vyflare Workspace

**Team Vyflare — Fluid Mixing Station.** Start with the
[executive summary](docs/EXECUTIVE_SUMMARY.md): problem, data cleaning, findings
and compute usage.

## Repository Layout

```text
backend/        Python API: image measurements, Model 4, recorded recipe observer, Cosmos routing
client/         React + Vite inspection console
server/         Express gateway (serves the console, proxies the Python API)
shared/         TypeScript domain types shared by client and server
scripts/        Integration smoke test
evidence/       Recorded inspection manifest used by the console
cosmos-original-dataset/  Station videos 1–5 and video-5 labels (default recording source)
research/       Models 1–4 experiments and the Cosmos baseline — see research/README.md
docs/           Executive summary, architecture diagram, integration index, technical reports
```

Vyflare combines recorded vial inspection, experimental recipe-pattern discovery,
image analysis and separate model APIs. The workspace incorporates the earlier
`ui-development`, `full-stack-attempt` and `vial-mix-anomaly-detection` work.

## Current Recorded Inspection Workflow

Open `/inspect`, select an installed recording (Videos 1–5) or **Open a Recording**,
then play it. First playback starts an idempotent background analysis job. The
producer reads original pixels to associate vial visits, detect dispenses, measure
final appearance and qualify tracking/visibility before recipe actions.

The **Inspection Log** shows timestamped flow observations, timing/color evidence,
recipe candidates, discovered patterns and unresolved/review reasons. Pausing
freezes log arrivals while backend analysis continues. Resuming admits entries
at or before playback time; seeking updates visible history without revealing
future confirmations. Analysis can lag playback and reports its progress.

The manual Model 4 comparison form, reviewed timeline and separate Process
Recording panel have been removed from this page. Saved reviewed annotations are
not inputs to automatic observation. New recordings use the same observer and
checks; they do not train or tune a model. Replaying identical footage reuses its
results without adding recipe votes.

Supported fresh processing currently requires **macOS, AVFoundation and `swiftc`**,
the original unrotated **640 × 480 station view**, and recordings of at most 30
minutes. This is not arbitrary-camera or unattended qualification. Local uploads
accept MP4/MOV/WebM up to 128 MiB, with a 512 MiB registration storage budget.

See [automatic recorded inspection](backend/recipes/automatic_recordings.md),
[tracking eligibility](backend/recipes/recorded_workflow_integration.md) and the
[corrected data-pipeline diagram](docs/architecture/README.md).

## Local Startup

Requirements: Node 24.19+ (24.x), pnpm 11.25+, Python 3.12+. Install from the
repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-integration.lock.txt
pnpm install --frozen-lockfile
source .venv/bin/activate
export MODEL_MODE=real
export ENABLED_MODELS=measurements,model4
```

To enable automatic recorded recipe processing, configure the following in the
same shell before starting both services:

```sh
export RECIPE_DEMO_ENABLED=true
export RECIPE_DEMO_DB_PATH="$PWD/backend/.data/recipe-demo-v1-4.sqlite3"
# Supply a private server-to-server token locally; use the same value on Node/Python.
export INFERENCE_TOKEN='replace-with-your-private-local-token'
pnpm run dev:integrated
```

Open http://localhost:5173/inspect. Python defaults to port 8000, Express to 8787,
and Vite to 5173. `INFERENCE_URL` selects a different private Python gateway.
Without demo configuration the separate recorded recipe service is disabled;
CPU image measurements remain available. Automatic observation does not require
Model 4, Model 2 or Cosmos.

On Windows use `.venv\Scripts\python.exe` and PowerShell environment variables
(`$env:NAME = "value"`) for the image/model APIs. Fresh recorded decoding is not
yet supported on Windows or Linux. `RECORDED_VIDEO_ROOT` and `GEOMETRY_CACHE_ROOT`
are application configuration overrides; they are not environment-variable
settings read by the default launcher. Installed sources default to
`cosmos-original-dataset/videos/vial_fill_video_1.mp4` through `_5.mp4`.

## Recipe Banks and Persistence

- **Nominal references:** 52 integrity-checked recipe settings, including 41, 50,
  60 and 99. Nominal amounts/order do not establish measured composition or
  complete comparable timing/color coverage.
- **Recorded experimental bank:** an explicitly separate SQLite file selected by
  `RECIPE_DEMO_DB_PATH`. Producer `fixed-station-native/4` uses demo engine 1.4.
  Eligible fills reuse reference/discovered patterns or establish provisional
  patterns; pending repeat, boundary, ambiguity and missing/poor evidence cases
  retain their holds. Two qualifying distinct color-conflicting fills can create
  a Discovered–Unverified pattern while retaining the review flag. Missing an
  applicable qualified reference is not by itself proof of a new recipe.
- **Normal workflow bank:** defaults to `backend/.data/recipes.sqlite3`, or
  `RECIPE_DB_PATH`. Its reviewed/tracker APIs remain distinct from recorded demo
  processing. The automatic recorded producer does not write this bank.

Preserve older incompatible pinned demo banks and select a new 1.4 filename;
there is no automatic history migration. Recipe IDs depend on bank contents and
processing order. Discovered IDs describe unverified timing/appearance patterns,
not chemical identification or automatic promotion to verified recipes.

`RECORDING_UPLOAD_ROOT` selects registered media/log storage; its default is a
`recordings` directory beside the demo database. Source-bound journals preserve
playback events across restarts and are checked against the selected bank.
Interrupted jobs need to be restarted; the single-process queue is not durable.
Normal/demo databases, recording storage and geometry caches must remain outside
Git and have persistent storage if deployed. Image-analysis uploads and separate
Model 4 results are not saved by the console; registered recordings are persisted.

## Other Available Workflows

- **Overview (`/overview`):** installed evidence, reference-bank size, saved
  assessments, current configuration and workflow links. Model 4 results remain
  unsaved; historical simulated cases are separate.
- **Recipes (`/recipes`):** nominal references, normal unmatched candidates and
  separate experimental pending/discovered patterns. Provisional patterns are not
  verified recipes.
- **Analyze an Image (`/analyze`):** React → Express → Python analysis. CPU
  measurements average RGB within a drawn/numeric region; they do not segment
  liquid or establish physical volume or defects.
- **Recorded Experiments (`/experiments`):** saved anomaly results and Cosmos
  observations for 30 vials, not fresh inference or jointly validated accuracy.
- **Live Mode:** camera preview and experimental pixel tracking. Actual station
  camera validation, automatic live fill completion, final-color sampling and
  live recipe processing remain deferred. Uncertain/hidden surfaces stay unmarked;
  numeric liquid height is excluded from recipe decisions.
- **Cosmos:** optional prompted still-frame analysis on the DGX Spark LoRA worker;
  it does not decide recipe matches or mutate the bank. See
  [Cosmos integration](backend/COSMOS_INTEGRATION.md) and [DGX setup](backend/dgx/README.md).
- **Model 4:** optional API for kernel-ridge mixture estimates from three
  registered post-fill frames and a chosen recipe/context. It does not identify
  an unknown recipe or release a vial. See [API guide](backend/MODEL4_API.md).
- **Model 2:** imported experimental v4 classifier API, excluded from automatic
  recipe decisions and not approved as supporting evidence. See
  [integration status](backend/MODEL2_INTEGRATION.md) and [API](backend/MODEL2_API.md).
  Model 3's workflow role is not integrated.

The old six-case demo pages remain explicitly simulated. Manual geometry-guide
components and comparison components remain in source but are not mounted in the
current inspection page. Drawn overlays never enter analysis pixels.

## Verification

```sh
pnpm run check
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'
pnpm run test:integration
```

Model 2 tests additionally need its separate dependencies and pinned backbone;
see its integration guide. The HTTP smoke test needs a production build and uses
temporary ports 18000/18787; set `PYTHON` if the executable differs from `.venv`.

Recorded implementation validation (2026-11-01): 51 frontend/gateway tests,
TypeScript checks and production build pass. Backend: 392/393 pass; the existing
Model 2 strict macOS ARM64 score-parity failure is retained without relaxed
assertions. Fresh pixel-based runs of Videos 1, 3 and 4, arbitrary content-ID
processing of Video 3, paused/resumed/seeking logs and restart/replay checks were
validated against an isolated bank. These are development checks, not accuracy
or unattended-reliability estimates.

## Deployment and Remaining Limits

The root Dockerfile builds the Node console; `backend/Dockerfile` is the separate
CPU Python service. DGX Cosmos uses its own worker. Node hosting alone does not
provide Python inference, database persistence or native video acquisition.
Linux/Render requires a validated decoder adapter before fresh recording analysis
can run there. Public media uploads are denied by the current loopback-only
upload route; remote support requires authenticated deployment configuration.

The checked-in `render.yaml` still names `ui-development`; the team has separately
reported configuring the Render dashboard to deploy `main`. Verify dashboard
settings rather than assuming the YAML reflects the deployed branch. Deployment
and Render backend connections are separate work; this commit does not deploy.

Earlier anomaly recall/precision and Cosmos color-review figures describe their
original experiments, not the current automatic workflow. No calibrated volume,
chemical identity, verified carryover cause, production reliability or measured
scrap savings is established. Numeric surface height, live recipe automation and
further model qualification remain outside the completed recorded integration.
