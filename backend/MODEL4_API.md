# Model 4 API

`POST /predict/model4` runs the frozen kernel-ridge mixture checkpoint on three
registered post-fill frames. It returns expected recipe proportions, estimated
proportions, and their signed and absolute differences. Optional observed-pour
frames produce a separate experimental stream-color comparison.

The checkpoint remains the default. First-vial contamination review cannot be
cleared by either model or by changing the expected recipe. Model 4 does not
create learned recipes, write inspection history, or issue manufacturing passes.

## Start

From `backend/`, use Python 3.12+ and the integration dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-integration.lock.txt
MODEL_MODE=real ENABLED_MODELS=measurements,model4 .venv/bin/python app.py
```

The API binds to loopback on port 8000 by default. The backend Dockerfile also
enables `measurements,model4`. Model 4 requires NumPy and Pillow; no Torch,
sklearn, GPU, model download or remote worker is needed. The existing Cosmos
and ResNet routes retain their existing runtime requirements.

`GET /health` lists enabled models. `GET /model4` reports the packaged model
hashes and camera contract. `GET /model4/recipes` lists the 52 nominal recipe
definitions exported from `recipes.xlsx`, `Recipe_Bank`. This quantity catalog
is separate from the existing duration/color pattern repositories.

If `INFERENCE_TOKEN` is configured, all three new endpoints require
`Authorization: Bearer <token>`. Existing origin checks and the shared inference
gate apply. Disabling `model4` makes its endpoints return 503.

## Checkpoint request

```bash
curl http://127.0.0.1:8000/predict/model4 \
  -F frame_id=fill-42 \
  -F vial_id=vial-42 \
  -F batch_id=batch-7 \
  -F batch_position=2 \
  -F camera_profile=vial-fill-640x480 \
  -F recipe_id=41 \
  -F images=@post-05.png \
  -F images=@post-15.png \
  -F images=@post-25.png
```

Supply three JPEG or PNG images of the **same vial**, approximately 0.05, 0.15
and 0.25 encoded-video seconds after the upper reviewed no-flow end bracket.
They must use the calibrated 640×480 camera view. Width and height alone do not
establish registration; the camera geometry must also match the saved liquid
patch. The backend does not resize Model 4 inputs or capture the frames itself.

Required metadata:

| Field | Meaning |
|---|---|
| `frame_id` | Request/capture identifier, 1–128 characters |
| `vial_id` | Caller-supplied vial identity, 1–128 characters |
| `batch_id` | Caller-supplied batch identity, 1–128 characters |
| `batch_position` | Positive integer; 1 always flags expected transition contamination |
| `camera_profile` | `vial-fill-640x480` |
| `images` | Exactly three post-fill JPEG/PNG files |

Supply exactly one expected-recipe input:

- `recipe_id`: ID from the packaged quantity catalog, including 41, 50, 60, 99.
- `expected_ml`: JSON containing exactly `T100`, `T200`, `T400`, with finite
  nonnegative nominal amounts and a positive total. For example,
  `{"T100":50,"T200":20,"T400":0}`. These are instructions, not measured doses.

Batch position must come from reliable batch tracking. The endpoint does not
infer vial identity, batch position or actual contamination fractions from
these images. The first-vial flag follows the user-confirmed process rule.

## Optional stream-color comparison

Include an `events` JSON list for 1–3 consecutive **observed chronological**
pours. For each event, upload its before-flow and during-flow images:

```text
events=[{"event_number":1,"duration_s":7.5},
        {"event_number":2,"duration_s":8.0}]
event_1_before=@before-1.png
event_1_during=@during-1.png
event_2_before=@before-2.png
event_2_during=@during-2.png
```

The curl syntax is `-F 'events=[...]' -F event_1_before=@before-1.png`, etc.
Before frames use roughly 0.1 seconds before the lower onset bracket; during
frames use the midpoint of observed start/stop. Event segmentation remains an
upstream responsibility. Do not supply recipe-assigned tank names or intended
event counts as visual evidence.

`duration_s` is the observed duration in encoded video seconds. Use JSON `null`
when it is unknown. The stream challenger uses duration availability as a
missing-data flag; it does not convert durations to milliliters. If an event
began before recording and its before image is missing, set
`"before_missing":true` and omit that before file. The missing stream change
is explicitly imputed using the saved training medians. Its duration should
also be null if its onset is unknown.

Omitting `events` returns a checkpoint estimate with
`stream_color_comparison.available=false`. Supplying incomplete or inconsistent
event evidence returns an error. Comparisons are never fabricated.

## Response

The top level echoes `frame_id`, `vial_id`, `batch_id` and `batch_position`, with
`model`, `mode`, `inference_ms` and `result`.

Within `result`:

| Key | Contents |
|---|---|
| `expected` | Nominal amounts, total and unit-sum proportions, with source/basis |
| `checkpoint` | Estimated proportions and percentages, signed/absolute differences in percentage points, average T200/T400 difference and extrapolation flag |
| `stream_color_comparison` | Separate experimental estimate and differences when observations are provided; `promoted=false` |
| `review` | Required review, independent first-vial flag, conservative retained discrepancy, `automatic_release=false` |
| `model_metadata` | Checkpoint/challenger IDs, hashes and camera contract |

For example, an expected T200 fraction of 0.25 and an estimate of 0.30 produces
a signed difference of **+5 percentage points** and an absolute difference of
**5 percentage points**. The average dye difference averages T200 and T400;
T100 is also reported separately. These differences are against recipe settings,
not measured physical composition or a percentage of incorrectly classified vials.

When the challenger is available, the retained review discrepancy is the
maximum of the two average dye differences. A challenger closer to the recipe
cannot erase the checkpoint's discrepancy. No defect/release threshold is
calibrated. Batch position 1 remains `expected_transition_contamination` even
when either estimate exactly matches the target; later vials return `needs_review`.

`MODEL_MODE=mock` returns `mock=true`, expected metadata and review state, but
no estimated proportions. It never returns fabricated inference values.

## Limits and compatibility

Model 4 requests have a 12 MiB body limit and at most 24 multipart parts. The
original single-image `/predict` route retains its 5 MiB Flask limit. Unsupported
formats return 415, invalid request data 400, geometry/model-input errors 422,
busy inference 429, and disabled Model 4 503. Unexpected model failures withhold
estimates and return 500. The shared inference gate is released after failures.

Use the dedicated route; `/predict` with `model=model4` returns a routing error.
The existing recipe, tracker and pattern-inspection APIs are unchanged. Model 4
results are returned to the caller and are not fed into recipe learning or the
existing pass/fail matcher.

The trained labels are recipe settings, and the camera/time coverage is limited.
Neither model establishes actual delivered composition or independently verified
defect detection. Preserve the source images and event observations for review.

## Verify

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/model4_request.py --fixture transition
```

The example client posts included, unchanged decoded RGB fixture pixels to an
already-running localhost API and includes the stream comparison. It also
supports `--fixture normal`, `--url` and the `INFERENCE_TOKEN` environment
variable. Test oracles come from frozen standalone-model inference, not from
the newly implemented backend predictor.

Asset SHA-256 hashes are checked at startup. The original checkpoint backup
and archive are external retained originals; this branch packages byte-identical
JSON weights for deployment and keeps challenger weights in a separate file.
