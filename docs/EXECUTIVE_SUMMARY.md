# Vision-Based Recipe Verification and Carryover Detection for an Automated Fluid Mixing Station

**Executive Summary — Team Vyflare**
MSOE AI Club × Rockwell Automation × NVIDIA Physical AI Hackathon, Fall 2026 · Dataset 2: Fluid Mixing Station
November 1, 2026

---

## Abstract

This report presents a camera-based inspection system for an automated fluid mixing station. The system estimates the dye composition of each filled vial, compares it with the commanded recipe, and flags vials affected by carryover from the preceding recipe. Correcting a timing misalignment in the supplied labels, together with an absorbance-based color representation, reduced composition error on unseen recipes from chance level to 6.4 percentage points per component. A residual-based detector identified all five known carryover-affected vials. NVIDIA Cosmos3-Nano, fine-tuned on the DGX Spark, provides natural-language descriptions of fill appearance for operator review. The estimated compute cost of the project is USD 24–77 at on-demand cloud rates.

---

## 1. Problem Statement

The station fills vials from three dye tanks in a fixed order: T-200 (orange), then T-400 (blue), then T-100 (clear diluent). Tank T-300 is out of service.

The existing Teledyne inspection compares vial color against a database of known colors. It has two limitations:

- **No recipe context.** It does not compare a vial against the recipe it was commanded to receive.
- **No carryover detection.** It cannot distinguish a dosing error from carryover. The first vial after a recipe change picks up residue from the shared mixing path; for example, a blue recipe following an orange one produces a green vial.

**Objective:** detect vials whose appearance does not match the commanded recipe, and attribute the likely cause to the recipe sequence, tank state or carryover.

---

## 2. System Overview

| Component | Function | Location |
|---|---|---|
| Vyflare Inspection Console | React, Express and Python application. Replays station recordings, detects each vial visit and dispense, measures final color, and produces a timestamped inspection log with recipe candidates and review reasons. Maintains a 52-recipe reference bank. | `client/`, `server/`, `backend/` |
| Model 4: Mixture Estimator | Kernel-ridge regression from absorbance features of three post-pour frames to orange, blue and clear fractions; compared against the commanded recipe. First vials in a batch are always flagged for carryover review. | `backend/model4*`, `research/model-4-anomaly-detection/` |
| Model 3 v2: Composition Model | Absorbance of the full vial relative to the empty vial, in linear light, mapped linearly to a valid mixture. No hyperparameters; CPU inference in milliseconds per vial. | branch `model-3-improved` |
| NVIDIA Cosmos3-Nano | Pretrained baseline on 30 fill clips, followed by a LoRA fine-tune served from the DGX Spark. Produces natural-language descriptions of liquid color and color changes. | `research/cosmos-baseline/`, branch `codex/cosmos3-nano-finetune` |
| Isaac Sim Digital Twin Data | 600 synthetic renders (12 colors × 50 animation frames) from the CSI digital twin. | branch `brev-research-dataset` |
| Model 2: Recipe Classifier | Frozen ResNet18 features with a logistic-regression head on cropped post-pour frames. Experimental API only. | branch `Model2`, `backend/model2*` |

---

## 3. Data Preparation

| Step | Issue | Treatment |
|---|---|---|
| 3.1 Label timing correction | The vial camera recorded at about 24.7 fps, but the video was encoded at 30 fps. The supplied still-image labels assumed 1:1 timing. Only 23 of 300 training stills showed the labeled vial, and 118 showed no fill. Stills end at about 1,395 s, leaving vials 25–30 without coverage. | Each still was matched to its nearest video frame, giving `video_s = 0.8225 × still_s − 0.39`; Model 4 independently found 0.8223. Training frames were extracted from the video at each vial's labeled start and end frames, and corrected labels were published. |
| 3.2 Frame selection | The "last 10 filling stills" covered the final 20 s of an active pour, not the finished mixture. | Frames are taken from the last stable interval after flow stops, with an empty-vial reference frame. End of flow was measured from video; eight field-vial boundaries moved 0.2–4.1 s later. |
| 3.3 Stream rejection | Frames with liquid still falling distort the measured color. | A stream detector in a fixed region above the vial rejects such frames. All retained frames passed visual review. |
| 3.4 Shortcut removal | Burned-in timestamps and neighboring vials correlate with recipe within a single recording. | Timestamps are masked, and inputs are cropped to the vial or to a liquid-only region. |
| 3.5 Carryover separation | First vials after a recipe change contain a blend, not their labeled recipe. | These vials are excluded from training and reported separately. |
| 3.6 Absorbance features | Raw RGB values depend on lighting, glass and background. | Per-channel absorbance, `−log10(full ÷ empty)` after sRGB-to-linear conversion, cancels static effects and is approximately linear in dye quantity. |
| 3.7 Label audit | Missing volumes and inconsistent field records. | Blank tank volumes are set to 0 mL. Recipes 5 and 8 have identical fractions and are not separable by color. The October 28 field session showed 15 ingredient-order conflicts and 12 over-length durations; all 30 field records are excluded from training. |
| 3.8 Leakage control | Adjacent frames and shared sessions inflate scores. | Evaluation uses grouped splits: held-out vials, leave-one-recipe-out, and a held-out session. The synthetic set was de-duplicated (565 unique of 600) and split by animation frame with a gap. |

---

## 4. Results

### 4.1 Composition Estimation (Model 3)

The original Model 3 notebook (ResNet18, MAE 0.198) performed no better than predicting the mean (0.199). After the corrections in Section 3, error is as follows (mean absolute error per component, percentage points, steady-state vials):

| Method | Unseen vials | Unseen recipes | New session |
|---|---|---|---|
| Predict the mean | 19.9 | 22.1 | 32.8 |
| Color baseline (corrected) | 8.2 | 12.0 | **9.3** |
| **Model 3 v2 (absorbance)** | **5.9** | **6.4** | 11.2 |

### 4.2 Carryover Detection

- **Video 5.** First-vial predictions fit a blend of the current and previous recipes with error 0.045, compared with 0.203 for the nominal label.
- **Field session.** All six recipe changes produced an off-recipe first vial. Second vials following dark recipes remained tinted.
- **Model 4 residual detector.** All 5 known carryover-suspected vials were flagged (recall 1.0, precision about 0.5).

### 4.3 Mixture Regression (Model 4)

Leave-one-recipe-out mean absolute error:

| Fraction | Model 4 | Mean baseline |
|---|---|---|
| Blue (T-400) | **0.103** | 0.168 |
| Orange (T-200) | **0.146** | 0.200 |

### 4.4 Image Classifiers (Models 1 and 2)

| Model | Result | Assessment |
|---|---|---|
| Model 1, recipe accuracy on held-out vials | 44% vial camera; 27% tank camera; 39% fused | Trained on misaligned labels |
| Model 2, known good vials | 96% accepted | High in-distribution accuracy |
| Model 2, at 0.90 threshold | Accepted 33% of good vials from unseen recipes and 5 of 15 contaminated first vials | Attribution indicates a recording-context shortcut; excluded from automated decisions |

### 4.5 Vision-Language Model (Cosmos3-Nano)

| Metric | Pretrained | LoRA fine-tuned |
|---|---|---|
| Color descriptions accepted by reviewer (30 clips) | 24 / 30 | — |
| Schema-valid output (9 held-out-recipe clips) | 7 / 9 | 9 / 9 |
| Exact final-color agreement (9 held-out-recipe clips) | 3 / 9 | 5 / 9 |

The fine-tune uses LoRA rank 8 (7.7 M trainable parameters) on 21 training clips. Errors concentrate on color transitions and shade.

### 4.6 Digital Twin

- **Rendering.** The rendered liquid behaves as an opaque surface rather than a transmissive dye, producing negative absorbance on some channels.
- **Labels.** Labels are display colors, not recipes or mixture ratios.
- **Training impact.** Adding synthetic images to Cosmos training improved output formatting on synthetic inputs but reduced real final-color agreement by one clip, so the change was not adopted.
- **Requirements for use.** A transmissive liquid material, empty-vial renders and fraction labels.

### 4.7 Fill Volume

Fill level is not observable above approximately 60 mL, where the liquid is occluded by the vial holder.

---

## 5. Compute Usage and Estimated Cost

Costs represent the market value of the compute at on-demand cloud rates and do not reflect amounts billed.

**Pricing assumptions:**
- GPU time at USD 1.50–2.50 per GPU-hour (L40S-class).
- CPU time at USD 0.10 per hour.

**Basis:**
- DGX Spark job times are taken from run logs.
- Inference-worker uptime and Brev instance time are estimated.

| Resource | Workload | Time | Estimated Cost (USD) |
|---|---|---|---|
| DGX Spark (GB10) | Cosmos3-Nano baseline inference, 30 clips | 24 min (logged) | 0.60–1.00 |
| | LoRA fine-tuning (smoke run, pilot, synthetic continuation) | 18.4 min (logged) | 0.45–0.75 |
| | Field and synthetic diagnostics | 2.4 min (logged) | 0.10 |
| | Persistent Cosmos inference worker, Oct 26 – Nov 1 | 10–20 h (estimated) | 15–50 |
| Brev (Isaac Sim 6.0.1) | Digital-twin setup and rendering, 600 frames at 32 subframes | 5–10 h (estimated) | 8–25 |
| build.nvidia.com | Not used | — | 0 |
| Local CPU | Training and evaluation of Models 1–4; application tests | 1–2 h | < 1 |
| **Total** | | **16–31 GPU-hours** | **24–77 (midpoint 50)** |

Training and inference jobs account for less than USD 2 of the total; the remainder is GPU instance uptime. The best-performing models (Models 3 and 4) run on CPU.

---

## 6. Limitations

- **Limited data.** One labeled recording (10 recipes, 30 vials) and 30 unverified field vials. Same-session results overstate generalization.
- **Commanded, not measured, labels.** No delivered volumes were measured; dosing errors and labeling errors are indistinguishable.
- **Sensor saturation.** Dark mixtures (for example, recipe 50) saturate the camera, and Model 3 returns "unable to estimate."
- **Platform dependency.** Fresh video processing in the console requires macOS (AVFoundation). Linux deployment requires a decoder adapter.
- **Integration scope.** Cosmos output is not part of the automated recipe decision. Live camera mode is preview-only.
- **Open anomaly.** Vial 25 (recipe 13, first vial) appears orange at its labeled end time; the cause is undetermined.

---

## 7. Recommendations

1. Record additional sessions with gravimetric fill measurements to enable cross-session and dose-level validation.
2. Install a white reference patch in the camera view to normalize absorbance across cameras and lighting.
3. Re-render the digital twin with a transmissive liquid and fraction labels, and compare real-only and synthetic-pretrained models at 3, 6 and 12 real vials.
4. Issue a pre-fill carryover warning when the queue changes recipe, and attach Cosmos descriptions to flagged vials.

---

## 8. Team and Acknowledgments

**Team Vyflare:** Amy, Jefferson, Jeremy, Nadia, Nova, Ryan, Cloud, Toua.

**Data:** Rockwell Automation and UWM Connected Systems Institute (`csi-vial-fill-dataset`, CSI digital twin).

**Models and platforms:** NVIDIA Cosmos3-Nano, NVIDIA Isaac Sim 6.0.1, NVIDIA DGX Spark, NVIDIA Brev.

**Software:** PyTorch, torchvision (ResNet18, ImageNet weights), scikit-learn, NumPy, Pillow, FFmpeg, Flask, Waitress, React, Vite, Express.

**AI assistants:** Claude and Codex assisted with analysis and code.
