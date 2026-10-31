# Model 2 API

Model 2 reports which supported recipe a completed vial visually resembles, or
abstains. It is supporting evidence only. It does not judge visual quality, does not
estimate composition, never clears another model's flag and never releases a vial.

**Status: not approved as supporting evidence.** `model2_assets/manifest.json` sets
`approved_for_supporting_evidence: false`. The reason is the validation in
`Training model 2/model2_baseline/README.md`: at 0.90 it falsely accepted 32% of good
unfamiliar recipes and 6 of 19 bad vials, and it shows a recording-context shortcut.
While unapproved, matches are reported but never counted as evidence.

## Start

Install the integration lock plus `requirements-models.txt` (torch, torchvision and
opencv-python-headless). Then:

```bash
MODEL_MODE=real ENABLED_MODELS=measurements,model4,model2 .venv/bin/python app.py
```

The backbone is torchvision's ImageNet ResNet18 (`resnet18-f37072fd.pth`). It is read
from `MODEL2_BACKBONE_WEIGHTS`, or from the torch hub cache (downloaded once if absent).
Its full SHA-256 must match the trained hash, or startup fails. `head.json` is checked
against `manifest.json` at load.

## Routes

| Route | Purpose |
|---|---|
| `GET /model2` | Model ID, head hash, preprocessing and config versions, supported recipe IDs, threshold, `calibrated: false`, approval status and validation summary |
| `POST /predict/model2` | Model 2 only |
| `POST /predict/vial-evidence` | Model 4 and Model 2 on the same three frames, reported side by side (both models must be enabled) |

All routes use the existing `INFERENCE_TOKEN`, origin checks and the shared one-inference gate (429 when busy).

## Request (both POST routes)

`multipart/form-data`, no other fields:

| Field | Meaning |
|---|---|
| `frame_id`, `vial_id`, `batch_id` | Caller identity, 1–128 characters; echoed so results join Model 4 by vial, batch and position |
| `batch_position` | Positive integer; 1 always carries `expected_transition_contamination` |
| `camera_profile` | `vial-fill-640x480` (the registered station view shared with Model 4) |
| `recipe_id` | **Intended** recipe from the machine or operator. It is used only for the comparison and is never a classifier input |
| `images` × 3 | JPEG/PNG 640×480 station frames, not resized: the first frames at or after the no-flow boundary + 0.05, 0.15 and 0.25 s |

Workbook visual-quality labels are dataset labels. They are not inputs and are not
available for production vials.

```bash
curl http://127.0.0.1:8000/predict/vial-evidence \
  -F frame_id=fill-11 -F vial_id=field_v11 -F batch_id=2026-10-0004 \
  -F batch_position=1 -F camera_profile=vial-fill-640x480 -F recipe_id=60 \
  -F images=@post-05.png -F images=@post-15.png -F images=@post-25.png
```

## Model 2 result

| Key | Contents |
|---|---|
| `observation` | `predicted_recipe_id`, `top_score`, second choice, per-frame tops, all class scores, `score_calibrated: false`, `status` |
| `status` | `accepted_observation` when the mean softmax is ≥ 0.90 and input checks pass; otherwise `unknown_uncertain` |
| `input_quality` | Frames in which a liquid stream is visible (the training frame rule). Any such frame forces abstention |
| `verification` | `relation`, `flags`, `counts_as_supporting_evidence`, `review_required: true`, `automatic_release: false`, `can_clear_other_flags: false` |
| `model_metadata` | As `GET /model2` |

`relation` values:

| Relation | Meaning |
|---|---|
| `matches_intended_recipe` | Supporting evidence only if approved; otherwise recorded but not counted |
| `recipe_disagreement` | Observation kept; adds a `recipe_disagreement` flag |
| `abstained` / `abstained_input_rejected` | No evidence; Model 4 and other checks continue |
| `intended_recipe_unsupported` | The intended recipe is outside the 14 supported IDs; a known-class resemblance cannot verify it |
| `no_inference` | Mock mode |

Scores are uncalibrated recipe-resemblance values, not probabilities of correctness and
not a quality signal. A bad vial can score above 0.90 as its intended recipe.

## Vial-evidence result

`model4` is Model 4's result byte-for-byte as `/predict/model4` returns it. `model2` is the
result above. `combined_review` keeps both:

- `required: true` and `automatic_release: false`
- `flags`: the union of the first-vial flag, Model 2 flags and `model4_needs_review`
- `model4_review`: copied unchanged, including the retained dye difference

Scores and composition differences are never averaged, voted or combined into a
confidence. Real example (bad first vial of recipe 60; Model 2 accepted it as 99):

```json
{"vial_id": "field_v11", "batch_position": 1, "intended_recipe_id": 60,
 "combined_review": {"required": true, "automatic_release": false,
   "flags": ["expected_transition_contamination", "recipe_disagreement"],
   "model2_relation": "recipe_disagreement", "model2_counts_as_supporting_evidence": false,
   "model4_review": {"status": "expected_transition_contamination",
     "retained_mean_dye_difference_percentage_points": 23.48, "automatic_release": false}},
 "model2": {"observation": {"predicted_recipe_id": 99, "top_score": 0.9258, "status": "accepted_observation",
   "score_calibrated": false}}}
```

Both models look at the same vial appearance and can be wrong in the same direction. Here
Model 4 also estimates about 90% T100. Agreement between them is not independent confirmation.

## Errors

| Status | Cause |
|---|---|
| 400 | Missing, unknown or duplicate fields; not three images; `recipe_id` unknown to Model 4 (vial evidence) |
| 401 | Missing token |
| 413 / 415 | Image too large; not JPEG/PNG or not multipart |
| 422 | Wrong `camera_profile` or frame size |
| 429 | Gate busy |
| 503 | Model disabled |

## Tests

`tests/test_model2_api.py`. Real-inference tests need the cached ResNet18 weights and
compare backend scores with an oracle computed by the training pipeline
(`export_backend_assets.py`) to 5 decimal places.
