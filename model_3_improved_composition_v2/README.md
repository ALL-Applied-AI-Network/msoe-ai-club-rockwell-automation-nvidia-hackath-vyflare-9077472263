# Model 3 v2: finished-vial mixture composition

Estimates the **volume fractions** of the three ingredients in a finished vial (t100 clear, t200 orange,
t400 blue; they sum to 1) from the colour of the liquid. It does **not** estimate millilitres, recipe
identity, dispense events, or whether a vial passes. See [REPORT.md](REPORT.md) for the assessment,
data audit, evaluation and integration notes. The original notebook (`../training model 3.ipynb`) is
unchanged.

## How it works
1. For each vial, an **empty frame** (the vial before its first dispense) and **finished frames** (the
   completed vial, before it moves on) from the fixed 640x480 station camera.
2. Inside the liquid ROI `x 295-335, y 275-412`: convert sRGB to linear light and compute per-channel
   absorbance `A = -log10(full / empty)`. The empty frame cancels lighting, glass and background.
3. Median absorbance over liquid pixels, then over the finished frames: 3 numbers per vial.
4. Linear map `A -> (t200, t400)`, `t100 = 1 - t200 - t400`, Euclidean projection onto the valid-mix simplex.
5. Quality rules return `UNABLE_TO_ESTIMATE` (ratios `null`) for wrong frame size, no liquid, or a liquid
   too dark to measure (2+ channels at the camera's black floor).

## Commands (run from this folder)
```bash
python -m pip install -r requirements.txt

# 1. dataset from the original videos (reads only; writes artifacts/frame_features.csv, segments.csv)
python scripts/build_dataset.py \
  --video5 path/to/vial_fill/videos/vial_fill_video_5.mp4 \
  --labels5 ../video5_vial_recipes.csv \
  --field-root path/to/newData/field-data/field-data --recipes-xlsx path/to/newData/recipes.xlsx
python scripts/make_splits.py          # artifacts/split_manifest.csv
python scripts/train.py                # artifacts/checkpoint.json (video 5 only)
python scripts/evaluate.py             # artifacts/eval/*  (all splits, baselines, report)
python -m unittest discover -s tests -v

# inference on one vial
python scripts/predict.py --empty empty.png --finished f1.png f2.png \
  --run-id RUN-1 --vial-id VIAL-43 --frame-id f-1287 --captured-at 52.1 --black-floor 15
```
The videos and field data are not in
Git (`*.mp4` is ignored); see "Artifacts".

## Python interface
```python
from model3.inference import Model3Composition
m = Model3Composition(black_floor_srgb=15)          # set per camera (see config.json)
out = m.predict_vial(empty_rgb, [finished_rgb_1, finished_rgb_2],
                     run_id="RUN-1", vial_id="VIAL-43", frame_id="f-1287", captured_at=52.1)
```
Returns the proposed integration contract:
```json
{"task": "mixture_composition", "model_id": "model3-absorbance-linear", "model_version": "2.0.0",
 "run_id": "RUN-1", "vial_id": "VIAL-43", "frame_id": "f-1287", "captured_at": 52.1,
 "status": "PREDICTED", "ratios": {"t100": 0.71, "t200": 0.27, "t400": 0.02},
 "quality_flags": ["CHANNEL_SATURATED_B"], "limitations": ["..."],
 "diagnostics": {"absorbance_rgb": [...], "liquid_coverage": 0.99, "saturated_channels": "B",
                 "frames_used": 2, "raw_unprojected": [...], "checkpoint_sha256": "...",
                 "inference_completed_at": "2026-10-30T23:10:02+00:00"}}
```
`captured_at` is returned exactly as supplied; inference time is only in `diagnostics`. `diagnostics`
is an addition to the proposed contract and can be dropped by the caller.

| status | ratios | when |
|---|---|---|
| `PREDICTED` | t100/t200/t400 in [0,1], sum 1 | otherwise |
| `UNABLE_TO_ESTIMATE` | `null` | `NO_FINISHED_FRAMES`, `FRAME_SIZE_MISMATCH`, `EMPTY_FULL_SIZE_MISMATCH`, `NO_LIQUID_DETECTED`, `TOO_DARK` |

Informational flags (do not change status): `CHANNEL_SATURATED_<R|G|B>`, `FRAME_DISAGREEMENT`,
`OUTSIDE_TRAINING_RANGE`, `RAW_OUTSIDE_SIMPLEX`. In the evaluation these were not associated with larger
errors, so they are not confidence scores. No confidence score is produced.

## Model card
| | |
|---|---|
| Task / units | Volume fractions of the commanded recipe; output order t100, t200, t400 |
| Inputs | Empty frame + 1..n finished frames, RGB, 640x480, calibrated station pose |
| Checkpoint | `artifacts/checkpoint.json`: 2x3 coefficients + 2 intercepts, SHA-256 of weights inside |
| Training data | Video 5 (Sep 23), 20 vials = 2nd and 3rd vial of each of 10 recipes, 4 finished frames each |
| Not used for training | First vials after a recipe change (residue); all field data (held out) |
| Hyperparameters | None (ordinary least squares) |
| Config | `config.json`: ROI, thresholds, segmentation, black floor (per camera) |
| Device | CPU, NumPy; ~ms per vial. Tested here on Linux x86_64 only. DGX Spark not tested |

Headline results (vial level, steady vials, percentage points of fraction, details in REPORT.md):
unseen vials of known recipes 5.9 pp; unseen recipes 6.4 pp; new session/camera 11.2 pp
(colour baseline 9.3 pp, mean baseline 32.8 pp on the same vials).

## Artifacts
In Git (small CSV/JSON): `artifacts/checkpoint.json`, `split_manifest.csv`, `frame_features.csv`,
`segments.csv`, `eval/`. Not in Git: videos and field data. Video 5 is on the backend branch at
`cosmos-original-dataset/videos/`; the Oct 28 field data (`field-data.zip`, 484 MB, and `recipes.xlsx`)
is on the team Drive folder `new-data`. A shared download location with hashes is still needed.
