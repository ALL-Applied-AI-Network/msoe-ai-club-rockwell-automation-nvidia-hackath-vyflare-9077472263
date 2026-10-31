# Cosmos alongside Amy's models

> Historical guide, superseded October 31, 2026. The integration target is now
> `model4/recipe-detection-backend-integration`. Follow the
> [current guide](model4-backend-integration-guide.md), not this deployment path.
> The optional gateway source now uses `model4` / `model4_response` and
> `--model4-result`; the old Amy names below describe the earlier revision.

This work is on `codex/cosmos3-nano-finetune`. It does not merge, replace or
retrain Amy's models. Earlier process-verification prototype work remains in an
isolated, unmerged local worktree; nothing from that worktree was pushed to Amy's
branch or imported into this Cosmos integration.

## Responsibilities

| Component | Responsibility | Cosmos integration behavior |
|---|---|---|
| Amy Model 3 / Model 4 | Their existing mixture/composition estimates | Keep separate and unchanged; do not substitute a Cosmos color name for proportions |
| Flow-event producer | Count pours and establish start/end times | Cosmos does not fabricate these from its whole-clip color answer |
| Controller/source producer | Identify which tank actually activated | Expected recipe order is never sent to Cosmos as observed identity |
| Dose calibration | Estimate actual delivery from validated measurements | No dose or mL estimate from this Cosmos adapter |
| Independent level check | Final level/total-volume evidence | Do not reuse a Cosmos color label as a volume measurement |
| Tracker/backend | Assign vial/batch IDs and associate captures | Supply verified binding metadata; Cosmos does not assign physical identity |
| Cosmos Version 1 | Supporting visible-color sequence and review evidence | Return appearance, limitations, raw text and inference provenance |
| Amy/backend verification policy | Interpret measurements and decide review | Existing Amy results and review flags preserved; no combined verdict here |

The current service continues using Version 1. The experimental synthetic-trained
adapter was not promoted because its real final-color development score regressed.
No additional weight updates were made for this integration.

## Services and workflow

- Existing tester: `http://172.30.102.122:7865/`.
- New companion health: `http://172.30.102.122:7866/health`.
- Observation: `POST /v1/cosmos/observe`.
- Optional read-only evidence attachment: `POST /v1/cosmos/combine-model4`.

Both Spark services require the existing network/VPN route. The companion is a
small CPU gateway; it calls the existing worker and loads no second GPU model.
No public tunnel, authentication system or production deployment is implied.

1. The station/tracker associates a capture with a vial, batch and recording.
2. The backend sends that media plus caller context to Cosmos. It separately
   runs Amy's measurement/model pipeline on the appropriate original captures.
3. Cosmos returns an appearance-evidence envelope. It does not receive intended
   recipes or tank assignments in its model prompt.
4. The backend may attach the returned envelope to the existing Model 4 response
   after verifying identical vial/batch IDs. Neither response is overwritten.
5. Amy's/backend's own validation policy remains responsible for decisions.

Send original registered frames to Model 4. Its existing contract requires three
640x480 post-fill frames from the same vial and calibrated camera geometry. Do
not substitute Cosmos processor-resized images or interpret file dimensions as
proof of registration. Cosmos and Model 4 may need different temporal captures.

## Request an observation

The multipart request has `media` and `context`. Context is a JSON object:

```json
{
  "run_id": "line-run-42",
  "vial_id": "vial-42",
  "batch_id": "batch-7",
  "camera_id": "vial-fill-camera",
  "timebase_id": "recording-42-elapsed-seconds",
  "stage": "filling",
  "clip_start_s": 12.5,
  "binding_verified": false
}
```

Use the IDs assigned by the tracking/backend owner. `binding_verified` is an
explicit caller assertion, not a model result; mark it true only after verifying
the media/vial association. An optional `event_id` may link a separately measured
pour. It does not cause Cosmos to measure an event. Accepted caller stages are
`filling`, `post_fill`, `cap_seal`; non-filling stages and photos are flagged as
outside the original filling-video training target or exploratory mode.

The model never receives this context. Additional context keys, including recipe
targets, are rejected. Clip start is a nonnegative offset on the named timebase.
The returned window end uses the worker-reported encoded clip duration, not a
predicted dispense end. Individual color changes have no measured timestamps.

```powershell
python scripts/request_cosmos_observation.py --url http://172.30.102.122:7866 --context configs/cosmos-companion-context.example.json --media C:/path/to/vial-clip.mp4 --output outputs/companion-test-01.json
```

Edit a private copy of the example context to use actual IDs and timing. Its
default binding is false, deliberately. Use a fresh output filename on each run.
The client uses the standard library and does not need GPU or ML packages.

## Returned evidence contract

`schema_version` is `cosmos-vial-observation/1.0`. The response includes:

- `context`: caller IDs, stage and binding assertion, preserved independently.
- `appearance`: ordered observed-color list, final visible color, and null color
  transition timestamps. Valid JSON is not proof of correct visual interpretation.
- `evidence_window`: whole-clip or single-image scope on the declared timebase.
- `provenance`: worker request ID, media hash, model identity, exact prompt/hash,
  input sampling summary and worker processing time. Worker identity currently
  contains the base snapshot and adapter path, not a signed weight attestation.
- `raw_output` and `output_schema_valid` for review.
- `measurements`: tank, flow events, dose, mixture fractions and total volume are
  explicitly null. No confidence percentage, release or learned recipe is created.
- `status`: `advisory_only`, `unbound`, or `unusable_output`.

Scalar color strings are not silently converted into valid lists. Missing or
invalid worker responses are withheld. Media hashes are checked against the
actual uploaded bytes. Busy worker status propagates as HTTP 429; a response
contract/hash failure gives 502. Oversized uploads give 413. Existing worker
format/decoding limits still apply, including 32 sampled video frames.

## Attach the existing Model 4 result

The reference is the response documented in
`backend/MODEL4_API.md` on `model4/recipe-detection-backend-integration`, inspected
at commit `956d5d24d19f80b99f85d4841e678d20d533e0fb`.
It has `vial_id`, `batch_id`, and a nested `result` with estimates and review.
This is a concrete existing interface, not a replacement of Amy's notebooks.

The combine endpoint accepts `{"cosmos": <observation>, "amy": <Model 4 response>}`.
Alternatively the client accepts a saved response:

```powershell
python scripts/request_cosmos_observation.py --url http://172.30.102.122:7866 --context C:/path/to/verified-context.json --media C:/path/to/vial-clip.mp4 --amy-result C:/path/to/amy-model4-result.json --output outputs/joint-evidence-01.json
```

Both results must describe the same actual vial and batch. Do not relabel old
fixtures to make IDs match. If Amy supplies `run_id`, it must also match. Unbound
or schema-invalid Cosmos evidence cannot be combined. The wrapper deep-copies
the entire Amy result, including expected values, estimates, challenger and
required/first-vial review flags. `combined_verdict` remains null, and
`recipe_learning_performed` is false. It does not call inspection/history or
unmatched-recipe-learning endpoints.

Do not auto-populate the legacy recipe matcher's dispense durations/tank order
from Cosmos. Those quantities have independent measurement owners. A different
Amy API contract needs an explicit adapter after its actual fields are agreed.

## Lifecycle and testing

Gateway PID/log on Spark: `companion-v1.pid`, `companion-v1.log` under
`/home/yt-vyflare71b7/workspace/vial-finetune-20261029/`. Scripts are isolated in
`scripts/companion-v1/`. The process survives SSH disconnect but is not configured
to restart after reboot. Do not start a second copy on an occupied port.

```bash
python scripts/serve_cosmos_companion.py --worker-url http://127.0.0.1:7865 --host 127.0.0.1 --port 7866
```

Install `requirements-companion.txt` in a separate environment when needed;
the existing Spark environment already supplies the dependencies. Never replace
the GPU worker environment just to run the gateway.

All 40 Cosmos-side tests passed in the isolated local environment. A live Spark
observation succeeded using the existing reviewed vial-04 clip. The actual Amy
backend URL was unavailable; the user explicitly deferred a live joint test.
Once available, test same-vial media on both services, attach outputs, verify
review retention and deliberately try a mismatched vial ID. These integration
tests do not replace independently labeled factory evaluation.
