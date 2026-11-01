# Model 2 baseline: frozen ResNet18 recipe classifier

**Recommendation: needs further work. Do not count this model's scores as verification evidence yet.**
At the fixed 0.90 threshold (cross-validation, crop model) it confidently accepted:

- 33% of good vials whose recipe was withheld from training,
- 5 of 15 bad first vials,
- 3 of 4 bad later vials.

Attribution and occlusion indicate a recording-context shortcut for the field recipes.
Scores are uncalibrated recipe-resemblance values. They are not probabilities of
correctness and say nothing about whether a vial is good.

Current version: `model2-baseline-v4` (2026-10-31), retrained on workbook `771c86ea…6aea`.
Relative to v3, vial 28 changed good → bad (it left training, now 40 vials) and first
vial 26 changed bad → good (it stays out of training and is reported as a transition
vial). Earlier versions are in Git history: v1 `777e6a1`, v2 `052cb35`, v3 `669b3c2`.
v5 adds the holder-crop test, v6 the below-holder crop and v7 whole-vial label inpainting,
described below. None of them changes the v4 results or the deployed model.

## Operator decisions applied

| Item | Decision | Evidence check |
|---|---|---|
| Photo/clip suffix `k` | Batch position k | Every first-vial photo shows carryover matching its station frame |
| Field order | 41 → 99/41-flush → 60 → 99/60-flush → 50 → 99/50-flush | Concatenated video is frame-identical to the six recordings in this order |
| Recipe-60 recording | Correct; sidecar `rec #99` is a sync error | 36–45 s blue-then-green pours of about 70 mL (recipe 99 is a clear ~7 s pour) |
| `99/50-flush/99-2.jpg` | Vial 27 (position 2), a bad vial | Photo is deep orange; station frames of vial 27 are pale yellow. Workbook now labels vial 27 bad |
| Timing, recipes 5–14 | `video5_vial_recipes.csv` | 0 of 90 post-flow frames show a stream (vs 9 with `Recipes_5_to_14` end_s); no movement |
| Field end of flow | Measured from video when the stream continues past workbook `end_s` | v01, v09, v10, v21–v25 moved 0.2–4.1 s later (`outputs/flow_boundaries.csv`) |
| Labels | Workbook `771c86ea…6aea`: vials 23–26 and 29–30 good, 27 and 28 bad | Only column S changed (rows 24–31) |

Vials 27 and 28 are bad later vials. Following the rule to train only on explicitly good
vials, they are used in bad-vial evaluation, not as training examples. Vial 26 is labeled
good but is a first vial: it keeps its contamination flag, is never trained on, and is
reported separately (`C_first_vial_labeled_good`).

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
..\..\.venv\Scripts\python.exe export_backend_assets.py  # backend/model2_assets + parity fixture
```

The v1 and v2 runs used Pillow 13.0.0; v3 and v4 ran with 12.3.0. Installing `backend/requirements-integration.lock.txt`
afterwards pins Pillow 12.3.0 in the same venv. The backend parity test still matches
the training oracle to 5 decimal places on the exported PNG frames. Backend usage is in
`backend/MODEL2_API.md`.

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
| Training-eligible good vials | 40: 20 from Video 5 (recipes 5–14, positions 2–3); field 41 (v02–05), 60 (v12–15), 50 (v23–25), 99 (v07–10, v18–20, v29–30) |
| Bad first vials | 15: `v5_e01, e04, …, e28`; `field_v01, v06, v11, v16, v21` |
| Bad later vials | 4: `field_v17` (99), `field_v22` (50), `field_v27` (99), `field_v28` (99) |
| First vial labeled good | 1: `field_v26` (99 after 50); contamination flag retained |
| Not used | 5–14 per-vial clips (same frames as Video 5); 640×480 stills (capture time unknown) |
| Phone photos | 30, one per field vial; evaluation only |

Folds: fold *p* holds out batch position *p* in every batch, keeping all frames and
augmentations of a vial together. Recipes 5–14 train on one good vial per recipe in folds
2–3. Every evaluated good recipe is present in its fold's training set.

## Results (crop model, per independent vial, threshold 0.90)

**A. Good known recipes, cross-validation** (40 vials, 120 frames; cross-validation, not an independent test):
top-1 accuracy 0.775, macro F1 0.682, coverage 0.650 (26 vials), accepted-prediction accuracy 0.962 (25/26).
The one confident error is `v5_e15`: recipe 9 → 8 at 0.952. Mean top score is 0.846 against
0.775 accuracy, so the scores are overconfident and uncalibrated.

| Recipe | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 41 | 50 | 60 | 99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Correct / vials | 2/2 | 2/2 | 2/2 | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 | 1/2 | 0/2 | 4/4 | 2/3 | 3/4 | 9/9 |
| Accepted and correct | 0 | 1 | 1 | 0 | 0 | 1 | 2 | 2 | 0 | 0 | 4 | 2 | 3 | 9 |

Errors (true → predicted): 8→9, 8→14, 9→10, 9→8, 13→10, 14→8, 14→7, 50→60, 60→50. Recipes 5
and 8 were never confused with each other; with two vials each, that does not show they can be told apart.

**B. Good unfamiliar recipes** (each recipe withheld; 5 and 8 withheld together; 40 vials):
**13 false acceptances (0.325)**.

| Withheld | Falsely accepted |
|---|---|
| 60 | all 4, as 50 (0.95–0.99) |
| 99 | 3 of 9, as 60 or 50: clear water accepted as green recipes |
| 7 | 2 of 2, as 14 and 11 |
| 9 | 2 of 2, as 5 and 8 |
| 41 | 1 of 4, as 12 |
| 50 | 1 of 3, as 60 |
| 5+8, 6, 10–14 | none |

**C. Bad vials** (fold predictions; bad vials are never trained on)

| Set | Vials | Accepted at 0.90 | Accepted as intended recipe |
|---|---|---|---|
| Bad first vials | 15 | 5 (0.33): `v5_e04` (as 9, intended 6, 0.901), `v5_e19` (11), `v5_e22` (as 9, intended 12), `v5_e25` (13), `field_v11` (as 99, intended 60) | 2 |
| Bad later vials | 4 | 3 (0.75): `field_v17` (99, 0.998), `field_v27` (99, 0.920), `field_v28` (99, 0.998); `field_v22` abstained | 3 |
| First vial labeled good | 1 | 0: `field_v26` abstained (99, 0.854) | 0 |

**D. Recording generalization (recipe 99, three recordings):** each recording held out in turn,
9/9 correct, coverage 0.5, 1.0 and 1.0. Recipes 5–14 (one Video 5 recording) and 41, 50 and 60
(one field recording each) cannot be tested across recordings, so for them recipe and
recording are fully confounded.

**Phone photos** (whole photo, letterboxed, scored by the final head; each vial's station
frames trained that head, so this is a camera-transfer check, not held-out data): good vials
20 photos, 7 top-1 matches, 9 accepted (3 correct); bad first 5 photos, 3 accepted; bad later
4 photos, 1 accepted; first vial labeled good 1 photo, not accepted. Phone photos are not a usable input.

Per-vial context (intended recipe, preceding recipe, batch position, recording, scores) is
in `outputs/predictions_per_vial.csv`. Counts per context cell are 1–4 vials, too few for rates.

## What the model uses (`outputs/analysis/`)

Occlusion on the 40 held-out good vials (same fold heads, regions masked at test time):

| Mask | Top-1 correct | Accepted (correct) |
|---|---|---|
| None (crop) | 31 | 26 (25) |
| Liquid column below holder | 17 | 4 (3) |
| Tube, label and nozzle above holder | 19 | 15 (13) |
| Holder band | 27 | 15 (15) |
| Full frame, no mask | 33 | 25 (25) |
| Full frame with the vial masked (background only) | 11 | 6 (4) |

- Liquid matters: masking the liquid column removes almost all acceptances.
- **Shortcut:** the region above the holder, which holds no liquid at these fills, is nearly as influential for top-1. Grad-CAM for field vials (`field_v07, v11, v12, v14, v25`) peaks at the top of the tube and nozzle, including clear water accepted as 60 and green carryover accepted as 99. With one recording per field recipe, recording-specific scenery there can identify the recipe.
- The full frame identifies 11 of 40 recipes with the vial hidden, so it stays a comparison only.
- Heads fit training frames at 100% in every fold. Class weight vectors are nearly orthogonal (max cosine 0.19). The weights do not reveal composition.

## Holder-crop test (v5, run at operator request)

The v4 full-vial model was saved first (`checkpoints/v4-station-crop/`, tag
`model2-v4-station-crop`) and still serves the backend. v5 adds a second input,
`station-holder-crop-v1`: crop x 250–390, **y 200–430** (holder band and below), as proposed
above. Everything else is identical: same 40 training vials, folds, augmentation, head and
0.90 threshold. Full-vial results reproduce v4 exactly.

**Caveat:** these folds were already used to find the shortcut, so this is a same-data
comparison, not an independent test. It needs confirming on new recordings.

| Test (per vial, CV, 0.90) | Full vial (v4) | Holder and below (v5) |
|---|---|---|
| A. Good known: top-1 accuracy | 0.775 (31/40) | **0.875 (35/40)** |
| A. Macro F1 | 0.682 | **0.849** |
| A. Coverage (answered) | 0.650 (26) | 0.675 (27) |
| A. Accuracy when answered | 0.962 (25/26) | **1.000 (27/27)** |
| B. Unfamiliar good recipes falsely accepted | 13/40 (0.325) | **6/40 (0.150)** |
| C. Bad first vials accepted | 5/15 (0.333) | **3/15 (0.200)** |
| C. Bad later vials accepted | 3/4 (0.75) | **4/4 (1.00)**, worse |
| C. First vial labeled good (v26) accepted | 0/1 | 0/1 |
| D. Recipe 99 held-out recordings | 9/9, coverage 0.5/1/1 | 9/9, coverage 1/1/1 |
| Phone photos accepted (good / bad) | 9 / 4 | 0 / 0 |

Holder per recipe (correct / vials): 5 2/2, 6 2/2, 7 1/2, 8 1/2, 9 1/2, 10 2/2, 11 2/2, 12 2/2,
13 2/2, 14 2/2, 41 4/4, 50 2/3, 60 3/4, 99 9/9. Recipes 8, 9 and 14 improve from 0/2.

Remaining holder failures:

- **Unfamiliar recipes falsely accepted:** 7 → 11 (0.9999), 13 → 12, 14 → 50, 41 → 12 twice, 50 → 60. The 60 ↔ 50 swap and clear water accepted as green (v4 failures) now abstain.
- **Bad first vials accepted:** `v5_e16` (as 9), `v5_e19` (11), `v5_e22` (as 9).
- **Bad later vials accepted:** all four: `field_v17`, `v27`, `v28` as 99 (0.99–1.00) and `field_v22` as 11 (0.91). Three of these are recipe 99 vials whose defect is not visible to the classifier as a different recipe.

What it uses (occlusion on 40 held-out good vials):

| Holder model, mask | Top-1 correct | Accepted (correct) |
|---|---|---|
| None | 35 | 27 (27) |
| Holder band (label residue and high fill line) | 30 | 14 (14) |
| Liquid column below holder | 13 | 1 (0) |

- The liquid column now drives the decision: masking it removes almost every acceptance.
- **A shortcut remains: label stickers.** The bottom of each vial's label (printed `VIAL - NN`) sits inside y 200–225, together with the fill line of 60–80 mL vials. Grad-CAM (`outputs/analysis/gradcam_holder_model.png`) peaks on that label strip for `v5_e15`, `v5_e22`, `field_v11`, `v22`, `v07` and `v12`, including the bad later vial `field_v22` accepted as 11. Labels identify physical vials, not recipes.

**Assessment:** the holder crop is better on good-vial recognition and unfamiliar-recipe
rejection, but it accepts every bad later vial and still sees vial labels. It is not yet
usable as supporting evidence. Next steps: confirm on new recordings with several recipes
per recording, and remove or standardize the vial labels (or the label strip) at capture time.

## Label-removal test (v6)

v5 was saved first (`checkpoints/v5-holder-crop/`, tag `model2-v5-holder-crop`). Physically
removing labels needs new recordings, so this test removes them from the image at
capture-time preprocessing instead. `station-below-holder-crop-v1` crops x 250–390,
**y 265–430**. The holder's bottom edge was measured at y 258–262 in all 120 frames, and a
visual check of all 60 vials found no label below it. Everything else is unchanged.
The same caveat applies: this is a same-data comparison.

| Test (per vial, CV, 0.90) | Full vial (v4) | Holder and below (v5) | Below holder, no labels (v6) |
|---|---|---|---|
| A. Top-1 accuracy (40 good vials) | 0.775 | **0.875** | 0.850 |
| A. Macro F1 | 0.682 | **0.849** | 0.811 |
| A. Coverage | 0.650 | 0.675 | 0.675 |
| A. Accuracy when answered | 0.962 | **1.000** | 0.963 |
| B. Unfamiliar recipes falsely accepted | 13/40 | **6/40** | 19/40 |
| C. Bad first vials accepted | 5/15 | 3/15 | **2/15** |
| C. Bad later vials accepted | 3/4 | 4/4 | **2/4** |
| C. First vial labeled good accepted | 0/1 | 0/1 | 0/1 |
| D. Recipe 99 held-out recordings | 9/9 | 9/9 | 9/9 |
| Phone photos accepted (good / bad) | 9 / 4 | 0 / 0 | 4 / 2 |

Below-holder failures:

- **Confident error on a good vial:** `v5_e11` (8 → 9, 0.93).
- **Bad vials accepted:** `v5_e22` (as 9), `field_v06` (99 after 41, as 41), `field_v17` and `v28` (99).
- **Unfamiliar recipes:** most become look-alike colors: 12 → 13, 6 → 12, 7 → 11, 11 → 7/8, 10 → 8, and clear 99 → pale 14 (4 of 9).

Interpretation:

- **Without labels, the model sees the liquid.** Grad-CAM (`gradcam_below_model.png`) is mostly on the liquid column and base, and fewer bad vials are accepted.
- **It cannot tell when a mixture is new.** With only the liquid colour below the holder, an unfamiliar mixture looks like the nearest known colour and gets a high score. The v5 crop's better unfamiliar rejection therefore partly depended on the label strip and the high fill line in the holder hole, not only on the liquid.
- **Fill height is weaker.** Fills of 60 mL and more fill the whole crop, so their heights cannot be compared; 30–50 mL levels remain visible.
- **One cue remains.** A few maps (`v5_e15`, `v5_e22`, `field_v22`) use the dark background or metal post at the crop's side edges, which differs between Video 5 and the field recordings.

**Assessment:** no crop is usable as supporting evidence yet. Each trades one failure for
another. The real fix is at capture: record without visible labels (remove them, or turn
them to face away from the camera), and keep the full vial so the fill line stays visible.
Then retrain the full-vial or holder crop on those recordings, with several recipes per
recording.

## Whole vial with labels inpainted (v7, flawed approximation)

v6 was saved first (`checkpoints/v6-below-holder-crop/`, tag `model2-v6-below-holder-crop`).
v7 keeps the whole-vial crop (x 250–390, y 40–430) and first removes label marks in software
(`station-crop-delabel-v1`, `remove_labels` in `run_baseline.py`). A black-hat filter
finds dark barcode bars and print on the tube (y 90–240, x 284–356), and OpenCV Telea
inpainting fills them. This is applied identically in training and evaluation.

**Read these results as an approximation.** Visual review of all 60 vials
(`outputs/analysis/label_removal_preview.png`, `label_mask_coverage.json`) shows:

- **Paper remains.** The blank label paper is still visible, often with an inpainting smudge, so a vial-specific patch remains.
- **Some labels are untouched.** Labels facing away from the camera are not detected: 20 of 60 vials have no mask in any frame.
- **Liquid is sometimes masked.** In a few vials (for example `field_v04`, `v24`, `v5_e25`) liquid, bubbles or the meniscus in the holder hole are masked and smoothed.
- **Same data again.** As with v5 and v6, this is a same-data comparison.

| Test (per vial, CV, 0.90) | Full vial (v4) | Holder (v5) | Below holder (v6) | Whole vial, labels inpainted (v7) |
|---|---|---|---|---|
| A. Top-1 accuracy (40 good vials) | 0.775 | **0.875** | 0.850 | 0.800 |
| A. Macro F1 | 0.682 | **0.849** | 0.811 | 0.721 |
| A. Coverage | 0.650 | 0.675 | 0.675 | 0.650 |
| A. Accuracy when answered | 0.962 | **1.000** | 0.963 | **1.000** |
| B. Unfamiliar recipes falsely accepted | 13/40 | **6/40** | 19/40 | 10/40 |
| C. Bad first vials accepted | 5/15 | 3/15 | 2/15 | **1/15** |
| C. Bad later vials accepted | 3/4 | 4/4 | **2/4** | 3/4 |
| C. First vial labeled good accepted | 0/1 | 0/1 | 0/1 | 0/1 |
| D. Recipe 99 held-out recordings | 9/9 | 9/9 | 9/9 | 9/9 |
| Phone photos accepted (good / bad) | 9 / 4 | 0 / 0 | 4 / 2 | 5 / 4 |

v7 details:

- **Per recipe (correct / vials):** 5 1/2, 6 2/2, 7 2/2, 8 0/2, 9 1/2, 10 2/2, 11 2/2, 12 2/2, 13 1/2, 14 0/2, 41 4/4, 50 2/3, 60 4/4, 99 9/9.
- **No confident errors on good vials.** One 5 → 8 confusion (`v5_e03`, 0.47) abstained.
- **Bad vials accepted:** `v5_e19` (11, its intended recipe) and `field_v17`, `v27`, `v28` (99, 0.98–1.00).
- **Unfamiliar recipes accepted:** 6 → 12, 7 → 11, 9 → 8, 14 → 7, 41 → 12, 50 → 60, 60 → 50 (2), and clear 99 → 60/50 (2).

Interpretation:

- **Labels were part of the problem.** Removing the barcode and print (but not the paper) improves v4 on every bad-vial and unfamiliar-recipe measure except bad later vials, while keeping fill height. That supports re-recording without labels.
- **The recording-context shortcut is unchanged.** Grad-CAM (`gradcam_delabel_model.png`) for field vials (`field_v07, v11, v12, v14, v25`) still peaks at the top of the tube and the nozzle, as in v4. Label removal does not address it; recordings with several recipes each do.
- **Recipe 99 bad later vials** (`v17`, `v27`, `v28`) are accepted by every version, so recipe recognition cannot catch those defects.

**Assessment:** not usable as supporting evidence. v7 is the strongest argument so far for
recording without labels, and it does not replace that.

## Artifacts (`outputs/model/`)

`model2_head_crop.json`: classes 5–14, 41, 50, 60, 99 in the head's stored order
(string-sorted, `10, 11, …, 9, 99`; always read the order from `classes`), scaler, coefficients,
preprocessing `station-crop-v1`, threshold, backbone hash and `calibrated: false`.
`model2_head_holder.json`: the same for `station-holder-crop-v1` (v5 test; not deployed).
`model2_head_below_holder.json`: the same for `station-below-holder-crop-v1` (v6 test; not deployed).
`model2_head_delabel.json`: the same for `station-crop-delabel-v1` (v7 test; not deployed; needs `remove_labels`).
`model2_head_fullframe_comparison.json` is for the shortcut comparison only.
Saved v4 model: `checkpoints/v4-station-crop/`.
