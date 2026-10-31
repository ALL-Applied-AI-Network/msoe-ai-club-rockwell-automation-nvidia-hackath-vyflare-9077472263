# Model 2 baseline: frozen ResNet18 recipe classifier

**Recommendation: needs further work. Do not use this model's scores as verification evidence yet.**
At the fixed 0.90 threshold it confidently accepted 30% of withheld good unfamiliar
recipes, 3 of 12 bad first vials and the one evaluable bad later vial. Scores are
uncalibrated recipe-resemblance values. They are not probabilities of correctness and
say nothing about whether a vial is good.

## Reproduce

Python 3.14.5, CPU. A gitignored `.venv` created with `--system-site-packages` supplies
torch 2.14.1+cpu, torchvision 0.29.1+cpu, numpy 2.5.4, scikit-learn 1.9.1 and Pillow 13.0.0.
`opencv-python-headless==5.0.0.93` was installed into the venv only. ResNet18
`IMAGENET1K_V1` weights: `resnet18-f37072fd.pth`, SHA-256 `f37072fd47e8…07ec`.

Run from this folder, in order:

```
..\..\.venv\Scripts\python.exe build_manifest.py   # vial + media manifests, folds
..\..\.venv\Scripts\python.exe extract_frames.py   # early post-flow frames -> artifacts/ (gitignored)
..\..\.venv\Scripts\python.exe frame_qc.py         # stream/movement validity
..\..\.venv\Scripts\python.exe run_baseline.py     # features, heads, all predictions (~4 min CPU)
..\..\.venv\Scripts\python.exe evaluate.py         # outputs/metrics.json
..\..\.venv\Scripts\python.exe analysis.py         # Grad-CAM, occlusion, head weights
```

Inputs: `Training model 2/recipes.xlsx` (SHA-256 `1160090945b6…121a`), `vial_fill_video_5.mp4`
(`6f87cec1…05b9`) and `data/` (per-file hashes in `outputs/media_manifest.csv`). Source
files are only read. Seed: `20261031`.

## Fixed before evaluation (`common.CONFIG`)

| Item | Choice |
|---|---|
| Frames | Early post-flow (not settled): first frame at or after `end_s` + 0.05, 0.15 and 0.25 encoded-video seconds |
| Frame validity | Rejected if a stream is visible in Model 4's stream ROI (centre contrast ≥ 20 or column contrast ≥ 30); checked against enlarged visual review. No movement or occlusion seen |
| Input | Burned-in timestamp masked (rows ≥ 435); crop x 250–390, y 40–430 (whole vial height, so fill level is visible; no neighbouring vial); letterbox to 224 with ImageNet-mean padding |
| Comparison input | Full frame with timestamp masked (used only for the shortcut analysis) |
| Augmentation | Training frames only: 8 copies with crop-window translation ≤ 4% and pixel noise σ = 1%. No hue, saturation, brightness, scale or flip changes, because colour and fill height define the recipe |
| Model | Frozen ResNet18 (backbone hash identical before and after) giving 512-d features; StandardScaler and multinomial logistic regression (C = 1) fit on the training fold only; vials weighted equally and classes balanced |
| Per-vial score | Mean softmax over the vial's valid frames; accepted when the top score is ≥ 0.90, otherwise unknown/uncertain |
| Checkpoint selection | None. There is no tuning or early stopping; every head uses the same fixed settings |

## Data and exclusions (`outputs/vials_manifest.csv`, `frames_manifest.csv`, `media_manifest.csv`)

60 workbook vials. Vial keys match the Model 4 checkpoint (`v5_eNN`, `field_vNN`).
Previous recipe is taken from workbook order, supported by sidecar recording times and
the flush folder names; it is `unknown` for the first row of each sheet.

| Group | Vials |
|---|---|
| Training-eligible (good, not first, supported, unquarantined) with frames | 30: `v5` positions 2–3 for recipes 5–14; `field_v02–05` (41); `field_v07–09`, `v18–20` (99) |
| Eligible but no valid frame (stream in all three) | `field_v10` |
| Quarantined: recipe-60 recording sidecar says `rec #99` | `field_v11–15` |
| Bad first vials (evaluation only) | `v5_e01, e04, …, e28`; `field_v06`, `v16`. `field_v01` and `v21` have no valid frame |
| Bad later vials (evaluation only) | `field_v17`; `field_v22` has no valid frame |
| Unknown quality (predictions only) | `field_v26–30`; `field_v23–25` have no valid frame |
| Not used | 5–14 per-vial clips (cut with the outdated window); 640×480 stills (vial mapping unconfirmed; same vials as training) |
| Phone photos (separate test, never trained on) | 29 photos; `99/50-flush/99-2.jpg` quarantined |

For `field_v01` and `v21–25` a stream is still visible in every post-flow frame, so the
workbook `end_s` there falls before the actual end of flow.

Folds: fold *p* holds out batch position *p* in every batch. Recipes 5–14 therefore train
on one good vial per recipe in folds 2 and 3. All frames and augmentations of a vial stay
in its fold. Every evaluated good recipe is present in its fold's training set.

## Results (crop model, per independent vial, threshold 0.90)

**A. Good known recipes, cross-validation** (30 vials, 82 frames; this is cross-validation, not an independent test):
top-1 accuracy 0.733, macro F1 0.642, coverage 0.60 (18 vials), accepted-prediction accuracy 0.889 (16/18).
Two good vials were confidently mislabelled: `v5_e12` (recipe 8 → 14, 0.916) and `v5_e15` (9 → 8, 0.916).

| Recipe | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 41 | 99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Correct / vials | 1/2 | 2/2 | 2/2 | 0/2 | 0/2 | 1/2 | 2/2 | 2/2 | 2/2 | 0/2 | 4/4 | 6/6 |
| Accepted and correct | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 4 | 6 |

Confusion (true → predicted): 5→10, 8→9, 8→14, 9→8, 9→10, 10→5, 14→7, 14→8. Recipes 5 and 8,
which share proportions but differ in volume, were never confused with each other in
cross-validation; with two vials each, that is not evidence that they can be told apart.
The full-frame comparison reached 0.833 top-1, but see the shortcut finding below.

**B. Good unfamiliar recipes** (each recipe withheld; 5 and 8 withheld together; 30 vials):
9 false acceptances (0.30). Withheld 7 → accepted as 14 and 11; withheld 41 → accepted as 12 and 13;
withheld 99 → `field_v20` accepted as 14. Groups 10–13 produced no false acceptances.

**C. Bad vials** (fold predictions; bad vials are never trained on)

| Set | Vials | Accepted at 0.90 | Accepted as intended recipe |
|---|---|---|---|
| Bad first vials | 12 | 3 (0.25): `v5_e19` (11, 0.991), `v5_e22` (as 9, intended 12, 0.990), `field_v16` (99, 0.933) | 2 |
| Bad later vials | 1 | 1: `field_v17` (99, 0.9996) | 1 |

`field_v16` holds visibly dark green liquid (carryover from recipe 60) yet scored 0.93 as
water. Naming the intended recipe is not defect detection.

**D. Recording generalization:** recipe 99 trained on one recording and tested on the
other: 3/3 and 3/3 correct and accepted. Recipes 5–14 (Video 5) and 41 have only one
recording each, so recording independence cannot be tested for them.

**Unknown quality** (no metrics): `field_v26–30` (99 after 50) were all accepted as 99
(0.95–1.00). `field_v26` keeps its first-vial contamination flag regardless.

**Phone photos** (whole photo, letterboxed; a mismatched input, never trained on): 19 photos
from recipes in training (camera transfer) gave 9 top-1 matches with the folder recipe and
4 acceptances (3 correct). 10 photos of recipes 50 and 60 (camera transfer and unfamiliar
recipe) gave 2 false acceptances (`50-1` as 41, `50-4` as 11). Photo-level quality is unknown
because filename-to-vial mapping is unconfirmed.

Context breakdown by intended recipe, preceding recipe, transition, batch position and
recording is in `outputs/predictions_per_vial.csv`. Counts per cell are 1–2 vials, which
is too few for rates.

## What the model uses (`outputs/analysis/`)

Occlusion on the 30 held-out good vials (same fold heads, regions masked at test time):

| Mask | Top-1 correct | Accepted (correct) |
|---|---|---|
| None (crop) | 22 | 18 (16) |
| Liquid column below holder | 8 | 2 (2) |
| Tube, label and nozzle above holder | 17 | 12 (9) |
| Holder band | 20 | 9 (9) |
| Full frame, no mask | 25 | 15 (15) |
| Full frame with the vial masked (background only) | 11 | 8 (6) |

- The crop model depends mainly on the liquid column and the band where the fill level sits, which is consistent with colour and fill height.
- The region above the holder (labels, which vary by vial, and the nozzle) also contributes. Grad-CAM shows weight on labels for `v5_e19`, `v5_e22` and `field_v03`, and on the nozzle area for `field_v16` and `v17`.
- **The full frame carries a context shortcut.** With the vial hidden it still names 11 of 30 recipes (chance is about 1/12), probably from neighbouring vials of the same batch. Its higher accuracy is therefore not credible, and the crop stays primary.
- **Suspected recording confound.** Field recordings contain only 41 (orange) and 99 among the training classes, so any non-orange field vial may default to 99. The dark-green `field_v16` accepted as 99 fits this pattern. The recipe 99 recording holdout cannot rule it out, because both of its recordings are field recordings.
- Heads fit training frames at 100% in every fold. That is expected with 512 features and 1–6 vials per class, and it means the scores are overconfident. Class-weight vectors are nearly orthogonal (largest cosine 0.15, between 11 and 7). The weights reveal nothing about ingredient composition.

## Artifacts (`outputs/model/`)

`model2_head_crop.json` is the deployable head: ordered classes `5…14, 41, 99`, scaler,
coefficients, preprocessing `station-crop-v1`, threshold and backbone hash, with
`calibrated: false`. `model2_head_fullframe_comparison.json` is the shortcut comparison only.
No `.pth` is needed because the backbone is unmodified torchvision weights.

## Limitations

- Two good vials per recipe for 5–14, from a single recording.
- No settled-liquid frames (early post-flow only); field `end_s` is too early for some vials.
- No calibration data.
- Recipes 50 and 60 are unsupported or quarantined.
- Phone photos cannot be tied to vials.
- Bad and unfamiliar mixtures receive high scores.

Correct model outputs still must not clear first-vial or other review flags.
