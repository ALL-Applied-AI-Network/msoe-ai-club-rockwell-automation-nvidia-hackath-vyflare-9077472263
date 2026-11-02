# Adaptive Fill Intelligence

*Vision-based recipe verification and carryover detection for a fluid mixing station*

**Executive Summary — Team Vyflare** · MSOE AI Club × Rockwell Automation × NVIDIA Hackathon, Fall 2026 · November 1, 2026

## Problem

The station fills vials from three dye tanks in a fixed order: T-200 orange, T-400 blue, T-100 clear. The existing inspection matches vial color against known colors. It does not check the commanded recipe and cannot detect carryover, where the first vial after a recipe change picks up residue from the shared mixing path. The objective is to flag vials that do not match their recipe and attribute the likely cause.

## System

- **Inspection Console** (React, Express, Python). Replays station video, detects each vial and dispense, measures final color and logs recipe candidates against a 52-recipe reference bank.
- **Composition models.**
  - **Model 4** (kernel ridge, integrated in the console): estimates the orange, blue and clear fractions from post-pour frames.
  - **Model 3 v2** (linear model on absorbance): a hyperparameter-free alternative that runs in milliseconds on a CPU.
- **NVIDIA Cosmos3-Nano.** LoRA fine-tuned on the DGX Spark; describes fill appearance in natural language for operator review.
- **Isaac Sim digital twin.** 600 synthetic renders used to evaluate synthetic pretraining.

## Data Preparation

1. **Label timing.** The vial video was recorded at about 24.7 fps but encoded at 30 fps, misaligning the supplied labels: 92% of training stills showed the wrong vial or no fill. Labels were realigned (`video_s = 0.8225 × still_s − 0.39`) and frames were re-extracted from video.
2. **Frame selection.** Only finished, stream-free frames are used, each paired with an empty-vial reference.
3. **Features.** Per-channel absorbance, `−log10(full ÷ empty)` in linear light, cancels lighting and background.
4. **Leakage control.** Timestamps are masked and inputs cropped to the vial. Carryover vials are excluded from training. Evaluation holds out whole recipes and whole sessions.

## Key Results

| Composition error, unseen recipes (pp per component) | Mean baseline | Model 3 (original) | Model 3 v2 |
|---|---|---|---|
| Video 5, leave-one-recipe-out | 22.1 | ≈ baseline | **6.4** |
| New session, different camera | 32.8 | — | **11.2** |

- **Carryover.** First vials fit a blend of the current and previous recipes (error 0.045 vs. 0.203 for the nominal label). Model 4's residual detector flagged all 5 known carryover vials.
- **Model 4.** Leave-one-recipe-out MAE of 0.103 (blue) and 0.146 (orange), vs. 0.168 and 0.200 for the mean.
- **Cosmos3-Nano.** The pretrained model's color descriptions were accepted for 24 of 30 clips. Fine-tuning raised final-color agreement on held-out recipes from 3/9 to 5/9.
- **ResNet classifiers.** These learned recording-context shortcuts and are excluded from automated decisions.
- **Digital twin.** The rendered liquid is opaque rather than transmissive, so it cannot yet train composition models.

## Compute Cost (market value at on-demand cloud rates, USD 1.50–2.50 per GPU-hour)

| DGX Spark: Cosmos inference and fine-tuning (45 min logged) | DGX Spark: inference worker (10–20 h est.) | Brev: Isaac Sim rendering (5–10 h est.) | CPU: Models 1–4 | **Total** |
|---|---|---|---|---|
| USD 1–2 | USD 15–50 | USD 8–25 | < USD 1 | **USD 24–77** |

## Limitations and Next Steps

The data comprise a single labeled recording (10 recipes, 30 vials), and labels are commanded rather than measured doses. Dark mixtures saturate the camera, and fill level is hidden above about 60 mL. Recommended next steps:

- Record additional sessions with gravimetric fill measurements.
- Add a white reference patch to the camera view.
- Re-render the twin with a transmissive liquid and fraction labels.
- Issue pre-fill carryover warnings when the recipe queue changes.

**Team Vyflare:** Amy, Jefferson, Jeremy, Nadia, Nova, Ryan, Cloud, Toua. **Data:** Rockwell Automation and UWM Connected Systems Institute. **Platforms:** NVIDIA Cosmos3-Nano, Isaac Sim, DGX Spark, Brev.
