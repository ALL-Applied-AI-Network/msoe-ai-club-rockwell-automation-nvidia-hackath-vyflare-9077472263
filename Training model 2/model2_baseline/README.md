# Model 2 baseline: frozen ResNet18 recipe classifier

**Recommendation: needs further work. Do not count this model's scores as verification evidence yet.**
At the fixed 0.90 threshold (cross-validation, crop model) it confidently accepted:

- 32% of good vials whose recipe was withheld from training,
- 4 of 16 bad first vials,
- 1 of 2 bad later vials.

Attribution and occlusion indicate a recording-context shortcut for the field recipes.
Scores are uncalibrated recipe-resemblance values. They are not probabilities of
correctness and say nothing about whether a vial is good.

Current version: `model2-baseline-v2` (2026-10-31), using the operator answers below.
v1 results are in Git history (commit `777e6a1`).

## Operator decisions applied in v2

| Item | Decision | Evidence check |
|---|---|---|
| Photo/clip suffix `k` | Batch position k | Every first-vial photo shows carryover matching its station frame |
| Field order | 41 → 99/41-flush → 60 → 99/60-flush → 50 → 99/50-flush | Concatenated video is frame-identical to the six recordings in this order |
| Recipe-60 recording | Correct; sidecar `rec #99` is a sync error | 36–45 s blue-then-green pours of about 70 mL (recipe 99 is a clear ~7 s pour) |
| `99/50-flush/99-2.jpg` | Vial 27 (position 2) | Photo is deep orange; station frames of vial 27 are pale yellow. Recorded, not resolved |
| Timing, recipes 5–14 | `video5_vial_recipes.csv` | 0 of 90 post-flow frames show a stream (vs 9 with `Recipes_5_to_14` end_s); no movement |
| Field end of flow | Measured from video when the stream continues past workbook `end_s` | v01, v09, v10, v21–v25 moved 0.2–4.1 s later (`outputs/flow_boundaries.csv`) |
| Labels | Workbook `336b6c09…0a05` (vials 23–25 and 27–30 good, 26 bad) | Only column S rows 24–31 changed |

**Open: `field_v27`.** The workbook labels vial 27 good, but the operator described its
photo as a bad vial. Excel row 27 holds vial 26, which is labeled bad. Until this is
resolved, vial 27 is excluded from training and from labeled metrics (`label_conflict`).

## Reproduce

Python 3.14.5, CPU. A gitignored `.venv` created with `--system-site-packages` supplies
torch 2.14.1+cpu, torchvision 0.29.1+cpu, numpy 2.5.4, scikit-learn 1.9.1 and Pillow 13.0.0.
`opencv-python-headless==5.0.0.93` is installed in the venv only. ResNet18 `IMAGENET1K_V1`
weights are `resnet18-f37072fd.pth` (SHA-256 `f37072fd47e8…07ec`).

Run from this folder, in order:

```
..\..\.venv\Scripts\python.exe measure_flow_end.py  # no-flow boundary per vial
..\..\.venv\Scripts\python.exe build_manifest.py    # vial + media manifests, folds
..\..\.venv\Scripts\python.exe extract_frames.py    # early post-flow frames -> artifacts/ (gitignored)
..\..\.venv\Scripts\python.exe frame_qc.py          # stream/movement validity
..\..\.venv\Scripts\python.exe run_baseline.py      # features, heads, all predictions (~5 min CPU; delete artifacts/features.npz after re-extracting)
..\..\.venv\Scripts\python.exe evaluate.py          # outputs/metrics.json
..\..\.venv\Scripts\python.exe analysis.py          # Grad-CAM, occlusion, head weights
```

Inputs: `Training model 2/recipes.xlsx`, `video5_vial_recipes.csv`, `vial_fill_video_5.mp4`
and `data/` (hashes in `outputs/media_manifest.csv`). Source files are only read.
Seed: `20261031`.

## Fixed before evaluation (`common.CONFIG`)

| Item | Choice |
|---|---|
| Frames | Early post-flow (not settled): first frame at or after the no-flow boundary + 0.05, 0.15 and 0.25 encoded-video seconds |
| Frame validity | Rejected if a stream is visible in Model 4's stream ROI (centre contrast ≥ 20 or column contrast ≥ 30). All 180 v2 frames pass; visual review found no movement or occlusion |
| Input | Burned-in timestamp masked (rows ≥ 435); crop x 250–390, y 40–430 (whole vial height); letterbox to 224 with ImageNet-mean padding |
| Comparison input | Full frame with timestamp masked (shortcut analysis only) |
| Augmentation | Training frames only: 8 copies with crop-window translation ≤ 4% and pixel noise σ = 1%. No hue, saturation, brightness, scale or flip changes |
| Model | Frozen ResNet18 (backbone hash unchanged) giving 512-d features; StandardScaler and multinomial logistic regression (C = 1) fit on the training fold only; vials weighted equally and classes balanced |
| Per-vial score | Mean softmax over the vial's three frames; accepted when the top score is ≥ 0.90, otherwise unknown/uncertain |
| Checkpoint selection | None (no tuning or early stopping) |

## Data and splits

60 workbook vials, keyed like Model 4 (`v5_eNN`, `field_vNN`), with 180 valid frames.

| Group | Vials |
|---|---|
| Training-eligible good vials | 41: 20 from Video 5 (recipes 5–14, positions 2–3); field 41 (v02–05), 60 (v12–15), 50 (v23–25), 99 (v07–10, v18–20, v28–30) |
| Bad first vials | 16: `v5_e01, e04, …, e28`; `field_v01, v06, v11, v16, v21, v26` |
| Bad later vials | 2: `field_v17` (99), `field_v22` (50) |
| Label conflict | `field_v27` |
| Not used | 5–14 per-vial clips (same frames as Video 5); 640×480 stills (capture time unknown) |
| Phone photos | 30, one per field vial; evaluation only |

Folds: fold *p* holds out batch position *p* in every batch, keeping all frames and
augmentations of a vial together. Recipes 5–14 train on one good vial per recipe in folds
2–3. Every evaluated good recipe is present in its fold's training set.

## Results (crop model, per independent vial, threshold 0.90)

**A. Good known recipes, cross-validation** (41 vials, 123 frames; cross-validation, not an independent test):
top-1 accuracy 0.805, macro F1 0.716, coverage 0.659 (27 vials), accepted-prediction accuracy 0.963 (26/27).
The one confident error is `v5_e15`: recipe 9 → 8 at 0.952. Mean top score is 0.851 against
0.805 accuracy, so the scores are overconfident and uncalibrated.

| Recipe | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 41 | 50 | 60 | 99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Correct / vials | 2/2 | 2/2 | 2/2 | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 | 4/4 | 2/3 | 3/4 | 10/10 |
| Accepted and correct | 0 | 1 | 1 | 0 | 0 | 1 | 2 | 2 | 0 | 0 | 4 | 2 | 3 | 10 |

Errors (true → predicted): 8→9, 8→14, 9→10, 9→8, 14→8, 14→7, 50→60, 60→50. Recipes 5 and 8
were never confused with each other; with two vials each, that does not show they can be told apart.

**B. Good unfamiliar recipes** (each recipe withheld; 5 and 8 withheld together; 41 vials):
**13 false acceptances (0.317)**.

| Withheld | Falsely accepted |
|---|---|
| 60 | all 4, as 50 (0.95–0.99) |
| 99 | 3 of 10, as 60 or 50: clear water accepted as green recipes |
| 7 | 2 of 2, as 14 and 11 |
| 9 | 2 of 2, as 5 and 8 |
| 41 | 1 of 4, as 12 |
| 50 | 1 of 3, as 60 |
| 5+8, 6, 10–14 | none |

**C. Bad vials** (fold predictions; bad vials are never trained on)

| Set | Vials | Accepted at 0.90 | Accepted as intended recipe |
|---|---|---|---|
| Bad first vials | 16 | 4 (0.25): `v5_e19` (11), `v5_e22` (as 9, intended 12), `v5_e25` (13), `field_v11` (as 99, intended 60) | 2 |
| Bad later vials | 2 | 1: `field_v17` (99, 0.998); `field_v22` abstained | 1 |

**D. Recording generalization (recipe 99, three recordings):** each recording held out in turn,
10/10 correct, coverage 0.5, 1.0 and 1.0. Recipes 5–14 (one Video 5 recording) and 41, 50 and 60
(one field recording each) cannot be tested across recordings, so for them recipe and
recording are fully confounded.

**Phone photos** (whole photo, letterboxed, scored by the final head; each vial's station
frames trained that head, so this is a camera-transfer check, not held-out data): good vials
21 photos, 6 top-1 matches, 9 accepted (3 correct); bad first 6 photos, 3 accepted; bad later
2 photos, 1 accepted. Phone photos are not a usable input.

Per-vial context (intended recipe, preceding recipe, batch position, recording, scores) is
in `outputs/predictions_per_vial.csv`. Counts per context cell are 1–4 vials, too few for rates.

## What the model uses (`outputs/analysis/`)

Occlusion on the 41 held-out good vials (same fold heads, regions masked at test time):

| Mask | Top-1 correct | Accepted (correct) |
|---|---|---|
| None (crop) | 33 | 27 (26) |
| Liquid column below holder | 18 | 4 (3) |
| Tube, label and nozzle above holder | 19 | 16 (14) |
| Holder band | 29 | 15 (15) |
| Full frame, no mask | 34 | 25 (25) |
| Full frame with the vial masked (background only) | 12 | 8 (5) |

- Liquid matters: masking the liquid column removes almost all acceptances.
- **Shortcut:** the region above the holder, which holds no liquid at these fills, is nearly as influential for top-1. Grad-CAM for field vials (`field_v07, v11, v12, v14, v25`) peaks at the top of the tube and nozzle, including clear water accepted as 60 and green carryover accepted as 99. With one recording per field recipe, recording-specific scenery there can identify the recipe.
- The full frame identifies 12 of 41 recipes with the vial hidden, so it stays a comparison only.
- Heads fit training frames at 100% in every fold. Class weight vectors are nearly orthogonal (max cosine 0.19). The weights do not reveal composition.

## Proposed next experiment (not run; needs approval)

Pre-register a crop that starts at the holder band (y ≥ 200), which removes labels, nozzle
and background, and evaluate it **only on new recordings**. The current folds have already
been seen, so they can no longer give a clean comparison. Recording several recipes per
field recording, and repeating recipes across recordings, would break the recording–recipe
confound.

## Artifacts (`outputs/model/`)

`model2_head_crop.json`: ordered classes `5…14, 41, 50, 60, 99`, scaler, coefficients,
preprocessing `station-crop-v1`, threshold, backbone hash and `calibrated: false`.
`model2_head_fullframe_comparison.json` is for the shortcut comparison only.
