# Model 3: current-state assessment, audit, v2 changes and evaluation

Scope: the Model 3 training work on `Amy's-Model` (`Training model 3/`). The backend branch
`recipe-detection-backend` was read for the integration contract and was **not modified**. Nothing was
committed upstream or pushed. All numbers below were produced in this environment by the scripts in this
folder unless marked "reported by the notebook".

## 1. Current state (original notebook, `training model 3.ipynb`)

| | |
|---|---|
| Task | Regress r100, r200, r400 = t*_ml / total_ml (volume fractions) from one image |
| Data | Video 5 stills (`video5_frame_labels.csv`, 845 images, Sep 23), recipes 5-14, 30 vials |
| Frame selection | Rows with `in_fill == 1`, then the last 10 stills per vial by timestamp: 300 rows |
| Splits | 3 folds; fold k tests the k-th vial of every recipe (vial-separated, same recording) |
| Models | ResNet-18 (ImageNet weights, 3 linear outputs, MSE, 10 epochs, full 224x224 resized frame); ResNet-18 on a tight vial crop; linear regression on RGB mean/std of the crop |
| Reported results | Full-frame ResNet 3-fold MAE 0.198 (R2 -0.06); tight crop fold 1 MAE 0.240; colour baseline 3-fold MAE 0.247 / 0.199 / 0.217 |
| Artifacts | `cleaned_regression_dataset.csv`; no checkpoint, split manifest or inference code in Git |
| Output validity | None enforced (raw regression outputs; they can be negative or not sum to 1) |

## 2. Data and label audit

**A. Most training labels point at the wrong vial (critical).** The video is ~24.7 fps but saved as
30 fps, so video time runs 0.82x real time, and `video5_frame_labels.csv` assumed 1:1. Matching every
still to its video frame by content (`fix_frame_labels.py` in the earlier `model3_improved` work; Model 4
independently uses the same 0.8223 scale) gives, for the notebook's 300 training rows:
- 23 / 300 show the vial they are labelled with; 63 / 300 show any vial of the labelled recipe;
- 118 / 300 show no fill at all (between vials);
- the 23 correct ones are mid-pour (median 28% through the fill, maximum 77%): none show the finished mix;
- only 3 of 30 vials have even one correctly labelled still. Stills also stop ~1395 s into the video,
  so vials 25-30 (recipes 13, 14) have no correct stills at all.

So the notebook's labels mostly describe a different vial, an empty vial, or a partial fill. This alone
explains results close to the mean baseline, and it means the notebook's numbers should not be used as
evidence for or against any method.

**B. "Last 10 filling frames" are not finished vials.** Even with correct timing, a fill takes 20-45 s
and stills are ~2 s apart, so the last 10 stills cover the last ~20 s of pouring. v2 instead takes frames
from the video in the last stable second before the conveyor moves (after pouring stops).

**C. Notebook bug in the colour baseline.** Cells 60-61 index the feature matrix with
`train_df.index` / `test_df.index` after `reset_index(drop=True)`, i.e. rows 0-199 and 0-99 of the full
table, not the fold's rows. The baseline was trained and tested on the wrong images, and the markdown
cell's MAE 0.145 does not match any printed output (0.247). The baseline is re-run correctly here.

**D. Leakage and context.** The full-frame ResNet sees the timestamp overlay, neighbouring vials, the
barcode label and machine context. Within one recording, time correlates with vial and recipe, so these
can stand in for colour. v2 uses only the liquid ROI (no overlay, labels or neighbours) and an empty
reference of the same vial; ROI choice was fixed before the field data was seen.

**E. Ratio calculations are correct.** Missing tank volumes mean 0 mL (filled with 0); all totals are
positive; ratios sum to 1. Recipes 5 and 8 have identical fractions (1/3 each) and differ only in total
volume: no colour model can separate them, and v2 does not claim to.

**F. First vials after a recipe change are not their label.** Video 5: the first vial of each batch fits
a blend of the previous and current recipe much better than its label. Field data (Oct 28): every one of
6 recipe changes gave an off-recipe first vial, and the 2nd vial after a dark recipe was still tinted
(absorbance residue share 0.25-0.45). v2 trains only on 2nd/3rd vials of video 5 and reports positions
separately. Labels everywhere are the **commanded** recipe; no delivered amounts were measured.

**G. Other data issues recorded in the outputs.** Video 5 vial 1 started filling before the recording,
so its empty reference contains liquid (noted in `frame_features.csv`). Dark mixes saturate the camera:
the lower vial is seen against the dark conveyor rail, so recipe 50 reads ~1.0 absorbance on every
channel. Lighting/camera differ between sessions (video 5 vs a 4K USB camera with auto-exposure and a
white backdrop on Oct 28); the empty-frame ratio removes the static part of that, and background
brightness changed by 3% or less between empty and full frames for 29 of 30 field vials (6% for one).

## 3. What v2 changes

| | Notebook | v2 |
|---|---|---|
| Frames | Stills with drifted labels, mid-pour | Video frames: empty window after arrival, 4 frames in the last stable second |
| Vial association | Label timestamps | Automatic segmentation at conveyor moves; video 5 labels matched by end frame (30/30) |
| Features | Full image / RGB stats | Absorbance vs the same vial empty, linear light, liquid ROI only |
| Model | ResNet-18 / linear | Linear least squares, no hyperparameters |
| Training vials | All | 2nd/3rd vial of each video-5 batch (20 vials, 80 frames) |
| Evaluation | 3-fold vial split, frame level | Vial split, leave-one-recipe-out, held-out session; vial and frame level |
| Validity | None | Euclidean projection onto the simplex; explicit rejection |
| Interface | None | `model3.inference.Model3Composition`, CLI, config, checkpoint with hash |

## 4. Evaluation

Split manifest: `artifacts/split_manifest.csv` (one row per vial; frames never cross splits).
- `vial3fold_v5`: unseen vials of known recipes, same recording (not evidence of cross-run generalisation).
- `loro_v5`: unseen compositions, same recording.
- `cross_session`: train video 5, test all 30 field vials (new run, camera, lighting and compositions).
Nothing was tuned on any test fold: v2 has no hyperparameters. Two choices were made on video 5 only
(simplex projection vs clipping: 6.36 vs 6.90 pp leave-one-recipe-out). **Disclosure:** the saturation
thresholds (camera floor 15 sRGB, 2x headroom) were set while looking at the field data, so the field
data is not an independent test of the TOO_DARK gate.

Errors are absolute errors of the fractions in **percentage points (pp)**, averaged over t100/t200/t400.

**Steady vials, identical vials for every method** (video 5 position >= 2, field position >= 3, vials
Model 3 accepts):

| Split | Vials | Mean composition | Colour baseline (notebook features, fixed) | Model 3 v2 |
|---|---|---|---|---|
| Unseen vials, known recipes (video 5) | 20 | 19.9 | 8.2 | **5.9** |
| Unseen recipes (video 5) | 20 | 22.1 | 12.0 | **6.4** |
| New session / camera (field) | 15 | 32.8 | **9.3** | 11.2 |

Per component, Model 3 (t100 / t200 / t400): 6.8 / 6.5 / 4.3 pp; 6.6 / 7.7 / 4.8 pp; 16.8 / 11.4 / 5.4 pp.

**All vials, ungated** (includes transition vials, whose errors are mostly real carryover; see
`artifacts/eval/metrics.csv`):

| Split | Mean | Colour | Model 3 all | Model 3, PREDICTED only (coverage) | Model 3 by position 1 / 2 / 3+ |
|---|---|---|---|---|---|
| Unseen vials | 19.9 | 12.8 | 11.3 | 11.3 (100%) | 22.2 / 6.4 / 5.3 |
| Unseen recipes | 22.1 | 15.7 | 11.7 | 11.7 (100%) | 22.4 / 6.7 / 6.0 |
| New session | 31.3 | 14.4 | 16.5 | 14.6 (83%) | 30.4 / 13.1 / 12.9 |

Frame-level MAE (each finished frame alone; correlated, not independent): 11.2, 11.6, 17.0 pp, close to
vial level because finished frames of one vial agree.

Validity: all returned ratios are in [0,1] and sum to 1 (projection). Before projection, 77-83% of
Model 3 vials and 73-87% of colour-baseline vials were already valid.

Quality gate (field): 5/30 vials rejected as TOO_DARK (recipe 50 vials 2-5 and the first water vial after
recipe 50); their error would have been 25.6 pp vs 14.6 pp for accepted vials. The informational flags
(CHANNEL_SATURATED_*, OUTSIDE_TRAINING_RANGE, RAW_OUTSIDE_SIMPLEX) were **not** associated with larger
errors (e.g. video 5 flagged 2-3 pp vs unflagged 12-13 pp), so they must not be read as confidence.

By recipe (field, all vials): 41: 13.7, 60: 11.4, 99 (water): 15.2, 50: 28.1 pp (4 of 5 rejected).
Failure examples: field 50 v1 (58 pp; the vial really received water + orange and almost no blue, a
genuine off-recipe vial); first vials of recipes 14, 10 and 6 in video 5 (32-42 pp, carryover);
the first water vial after recipe 60 (33 pp, blue-teal residue in the line).

Sensitivity (not used for selection): clipping instead of projection would give 9.7 pp on the field
steady vials (vs 11.2), but was worse on video 5. Clean water reads as 4-13% orange in the field session,
the main cross-session error.

**ResNet-18 baseline.** Not re-run: PyTorch is not installable in this environment (package index
blocked). The notebook's reported ResNet numbers (MAE 0.198 = 19.8 pp, R2 -0.06) were trained and tested
on the misaligned stills (section 2A), so they are not comparable to the table above. Re-running ResNet
on the v2 frames and split manifest is the remaining baseline task.

**Is the task supported?** Within one session, yes for compositions that differ in colour: steady vials
of unseen recipes are estimated to ~6 pp. Across sessions the error roughly doubles and Model 3 does not
beat the simple colour baseline on 15 vials from 3 recipes, which is too little data for a firm
ranking. It is not supported for equal-proportion recipes, dark mixes on this camera setup, or as a
measurement of delivered amounts. The objective (fractions + explicit rejection) is kept; no change of
objective is proposed. Model 4 on the backend branch estimates the same quantity with the same feature
idea (absorbance, kernel ridge, trained on video 5 + field). The two should be compared on one shared
split manifest and one kept, rather than integrating both.

## 5. Integration with the backend workflow

- **Model 3 supplies:** per vial, `ratios` (t100/t200/t400) or `UNABLE_TO_ESTIMATE`, quality flags,
  model id/version, the caller's `captured_at`. Vial-level aggregation over 1..n finished frames.
- **Model 3 does not supply:** DISPENSE_STARTED/STOPPED, DISPENSE_COLOR, FINAL_COLOR, FILLING_COMPLETED,
  durations, counts, millilitres, recipe identity, carryover decisions, or pass/fail. Ratios are not a
  substitute for final colour.
- **Other components must supply:** vial identity and run id (tracker); the empty frame (captured after
  the vial arrives, before the first DISPENSE_STARTED) and finished frames (after FILLING_COMPLETED,
  before the vial moves); dispense events and durations (flow-event detection); batch position / recipe
  change information for carryover review; the camera black floor for the station.
- **Association:** the caller passes `run_id`, `vial_id`, `frame_id` and `captured_at`; the adapter echoes
  them unchanged. `segmentation.py` shows how frames map to vials in recorded video; it is offline (it looks
  ahead to the next conveyor move). A live tracker needs a frame buffer and must not emit
  FILLING_COMPLETED from a conveyor move alone.
- **Backend extension needed (to be agreed with the backend team):** an optional `composition` evidence
  field on `VialObservation` holding the adapter output, stored with the inspection. No change to matching
  weights, mandatory rules or pass/fail; whether and how composition is scored is a backend decision.
  `UNABLE_TO_ESTIMATE` should be stored as missing evidence, not as a mismatch.

## 6. Changed files

All new, under `Training model 3/composition_v2/` on local branch `model3/composition-v2` (from
`origin/Amy's-Model`); not committed or pushed:
`config.json`, `requirements.txt`, `README.md`, `REPORT.md`, `model3/{__init__,preprocess,segmentation,
fit,inference}.py`, `scripts/{build_dataset,make_splits,train,evaluate,predict}.py`,
`tests/test_inference.py`, `artifacts/{frame_features.csv, segments.csv, split_manifest.csv,
checkpoint.json}`, `artifacts/eval/{metrics.csv, vial_predictions.csv, frame_predictions.csv,
eval_report.md}`.

Commands run here (Python 3.13.18, Linux x86_64, CPU): `build_dataset.py` on video 5 + the 6 field videos,
`make_splits.py`, `train.py`, `evaluate.py`, `python -m unittest discover -s tests -v` (7 tests pass,
including parity between the adapter and the stored evaluation output), and `predict.py` on real field
frames (recipe 41 vial 3: PREDICTED; recipe 50 vial 3: UNABLE_TO_ESTIMATE, TOO_DARK).

## 7. Remaining blockers

1. ResNet-18 baseline on the v2 frames and split manifest (needs PyTorch).
2. Only one held-out session (15 steady vials, 3 recipes); more sessions are needed for a reliable
   cross-session conclusion and a decision between Model 3, the colour baseline and Model 4.
3. Labels are commanded recipes; delivered amounts (scale or tank levels) are needed to measure real
   composition error and to label carryover.
4. Dark mixes: needs a white card or backlight behind the lower vial; the black floor must be set per camera.
5. A live (streaming) vial tracker providing empty/finished frames; the backend composition field.
6. Shared, hashed download location for video 5 and the field data.
7. Not tested on DGX Spark.
