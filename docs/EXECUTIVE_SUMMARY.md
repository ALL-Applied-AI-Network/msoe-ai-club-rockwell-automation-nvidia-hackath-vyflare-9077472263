# Executive Summary — Team Vyflare, Fluid Mixing Station

MSOE AI Club × Rockwell Automation × NVIDIA Physical AI Hackathon, Fall 2026 · Dataset 2: Fluid Mixing Station
Prepared November 1, 2026 from the contents of this repository and its branches.

## The problem

The mixing station fills vials from three dye tanks (T-100 clear, T-200 orange, T-400 blue; T-300 is out of service) in a fixed order. The existing Teledyne inspection compares a vial's color against a database of known colors. It does not know what recipe the vial *should* be, and it cannot tell a dosing error from **carryover**: the first vial after a recipe change picks up residue from the shared mixing path (for example, a blue recipe that comes out green after an orange one). Our goal was to detect vials whose color does not match their commanded recipe and explain the likely cause.

## What we built

| Component | What it does | Where |
|---|---|---|
| **Vyflare Inspection Console** | React + Express + Python workspace. Replays a station recording, automatically detects each vial visit and dispense, measures final color, and writes a timestamped inspection log with recipe candidates and review reasons. Includes a 52-recipe reference bank and an experimental bank that records new timing/color patterns. | `client/`, `server/`, `backend/` |
| **Model 4 — mixture estimator** (in the console API) | Kernel-ridge model that estimates the orange/blue/clear fractions from three frames after the pour stops and compares them with the commanded recipe. First vials in a batch are always flagged for carryover review. | `backend/model4*`, `research/model-4-anomaly-detection/` |
| **Model 3 v2 — physics-based composition** | Absorbance (full vs. empty vial, linear light) → linear map → valid mix. No hyperparameters; CPU, milliseconds per vial. | branch `model-3-improved` |
| **NVIDIA Cosmos3-Nano** | Pretrained baseline on 30 clips, then a LoRA fine-tune served from the DGX Spark that describes liquid color and color changes in natural language for the operator. | `research/cosmos-baseline/`, branch `codex/cosmos3-nano-finetune` |
| **Isaac Sim digital twin data** | 600 synthetic FillCam renders (12 colors × 50 animation frames) from the CSI digital twin. | branch `brev-research-dataset` |
| **Model 2 — ResNet18 recipe classifier** | Frozen ResNet18 + logistic head on cropped post-pour frames; available as an experimental API only. | branch `Model2`, `backend/model2*` |

## Data cleaning process

Most of our accuracy gains came from fixing the data, not from bigger models.

1. **Fixed a clock mismatch in the labels.** The vial camera recorded at about 24.7 fps but the video was saved as 30 fps, so video time runs at about 0.82× real time. The supplied still-image labels assumed 1:1 timing. Matching every still to its closest video frame gave a fit of `video_s ≈ 0.8225 × still_s − 0.39` (Model 4 found 0.8223 independently). Under the old labels, only 23 of the 300 Model 3 training stills showed the vial they were labeled with, and 118 showed no fill at all. Stills also stop about 1,395 s in, so vials 25–30 had no usable stills. We rebuilt training sets from the **video** at each vial's labeled start/end frames and published corrected labels.
2. **Used finished vials, not mid-pour frames.** A fill takes 20–45 s, so the "last 10 filling stills" were still pouring. We took frames from the last stable moment after the stream stops (and an empty frame of the same vial before its first dispense). Model 2 measured the true end of flow from video and moved eight field vials' boundaries 0.2–4.1 s later.
3. **Rejected frames with a visible stream.** A stream detector in a fixed region above the vial rejects any frame where liquid is still falling; all retained frames passed visual review.
4. **Removed shortcut cues.** We masked the burned-in timestamp and cropped to the vial or a liquid-only region, so models cannot learn "time in the recording" instead of color.
5. **Separated carryover vials.** First vials after a recipe change were excluded from training and reported separately, because their true contents are a blend, not their label.
6. **Converted color to absorbance.** Per-channel `−log10(full ÷ empty)` after sRGB-to-linear conversion cancels lighting, glass and background, and turns dye amount into a near-linear signal.
7. **Audited labels and quantities.** Blank tank volumes mean 0 mL. Recipes 5 and 8 have identical fractions and differ only in volume, so no color model can separate them. The October 28 field session audit found 15 order conflicts between intended and observed ingredient order and 12 durations longer than their vial windows; all 30 field records were kept out of training until verified.
8. **Grouped splits to prevent leakage.** Evaluation holds out whole vials, whole recipes (leave-one-recipe-out) or a whole session (train on video 5, test on field data). The twin set was de-duplicated (565 unique of 600) and split by animation frame with a gap.

## Key findings

**1. Fixing the labels mattered more than any model change.** Model 3's original notebook (ResNet18, MAE 0.198) did no better than predicting the average (0.199). With corrected labels, finished-vial frames and absorbance, error on clean vials of *unseen recipes* fell to about **6.4 percentage points** per fraction (vs. 22.1 for predicting the mean). On a new session with a different camera and lighting, error was 11.2 points.

| Model 3, steady vials (error in percentage points) | Unseen vials | Unseen recipes | New session |
|---|---|---|---|
| Predict the mean | 19.9 | 22.1 | 32.8 |
| Color baseline (fixed) | 8.2 | 12.0 | **9.3** |
| Model 3 v2 (absorbance) | **5.9** | **6.4** | 11.2 |

**2. Carryover is real and detectable.** In video 5, first-vial predictions fit a blend of the current and previous recipes with error 0.045, vs. 0.203 for their nominal label. In the field session, every one of six recipe changes produced an off-recipe first vial, and second vials after dark recipes were still tinted. Model 4's residual detector flagged **5 of 5** known carryover-suspected vials (precision about 0.5 with only 10 recipes).

**3. Model 4 beats the baseline under leave-one-recipe-out.** Blue fraction MAE 0.103 vs. 0.168 for the mean; orange 0.146 vs. 0.200. It is integrated into the console API.

**4. Deep classifiers learned shortcuts.** Model 1's recipe classifier on held-out vials reached 44% (vial camera), 27% (tank camera) and 39% (both). Model 2 scored 96% on known good vials, but at its 0.90 threshold it accepted 33% of good vials from unseen recipes and 5 of 15 bad first vials; attribution showed a recording-context shortcut. It stays out of automatic decisions.

**5. Cosmos is useful for explanations, not measurement.** The pretrained Cosmos3-Nano described 24 of 30 clips' colors correctly in one reviewer's check; the misses were mostly color transitions and shade. The LoRA fine-tune (rank 8, 7.7 M trainable parameters, 21 training clips) raised exact final-color agreement on nine held-out-recipe clips from 3/9 to 5/9 and schema validity from 7/9 to 9/9.

**6. The digital twin, as rendered, cannot train a mixing model.** The twin liquid shades like an opaque surface rather than a transmissive dye, giving negative absorbance on some channels, and its labels are display colors, not recipes or ratios. Adding twin images to Cosmos training restored output format on synthetic images but cost one real final-color match, so it was not promoted. A transmissive liquid, empty-vial renders and fraction labels are needed (render spec prepared).

**7. Fill volume cannot be read from the camera above about 60 mL**, because the liquid rises behind the black vial holder.

## Estimated credit and compute usage

These figures estimate what the compute itself would cost at on-demand cloud GPU rates, not what the team paid. No billing export is in the repository, so they are built from logged run times. DGX Spark job times are recorded; worker uptime and Brev instance time are not logged and are estimated. All GPU time is priced at an assumed **$1.50–$2.50 per GPU-hour** (typical on-demand rate for an L40S-class GPU); CPU time at about $0.10 per hour.

| Resource | Work | Recorded / estimated time | Estimated compute cost (USD) |
|---|---|---|---|
| **DGX Spark** (GB10) | Cosmos3-Nano baseline batch, 30 clips | ~24 min (recorded) | $0.60–$1.00 |
| | LoRA smoke run + v1 pilot + synthetic continuation | ~18.4 min (recorded) | $0.45–$0.75 |
| | Field and synthetic diagnostics | ~2.4 min (recorded) | ~$0.10 |
| | Persistent Cosmos inference worker (development and demo, Oct 26–Nov 1) | Estimated 10–20 hours of uptime | $15–$50 |
| **Brev** (Isaac Sim 6.0.1 instance) | Digital-twin setup and 600-frame render (32 subframes each) | Estimated 5–10 instance-hours, including setup, pilot run and idle time | $8–$25 |
| **build.nvidia.com** | Not used by any committed code | 0 | $0 |
| **Laptops (CPU)** | Models 1–4 training and evaluation, console, tests | ~1–2 CPU-hours (Model 2 full run ~5 min; Models 3 and 4 seconds) | < $1 |
| **Total** | | ≈ 16–31 GPU-hours | **≈ $24–$77 (midpoint ≈ $50)** |

Most of the cost is GPUs kept running (the Cosmos worker and the Brev instance), not training: the recorded training and inference jobs themselves come to under $2.

The cheapest models were also the strongest: Models 3 and 4 run on CPU in milliseconds per vial. GPU time went to Cosmos (explanations) and the digital twin (synthetic data).

## Limitations

- **One labeled recording.** Ten recipes, 30 vials in video 5, plus 30 unverified field vials. All numbers are rough, and same-session results overstate generalization.
- **Labels are commanded recipes, not measured doses.** No delivered amounts were measured, so a dosing error and a labeling error look the same.
- **Dark mixes saturate the camera.** Recipe 50 reads near maximum absorbance on every channel, so Model 3 returns "unable to estimate" for those vials.
- **Fresh video processing in the console requires macOS** (native AVFoundation decoder). Linux/Render hosting needs a decoder adapter.
- **Still to do:** Cosmos is not wired into the automatic recipe decision, and live camera mode is preview-only.
- **Unexplained case:** vial 25 (recipe 13, first vial) looks plain orange at its labeled end.

## Recommended next steps

1. Record more sessions, with measured fill weights, so models can be tested across sessions and doses.
2. Add a white reference patch to the station to make absorbance comparable across cameras and lighting.
3. Re-render the twin with a transmissive liquid and fraction labels, then run the real-only vs. twin-pretrained comparison at 3/6/12 real vials.
4. Promote the carryover rule into a pre-fill warning when the queue changes recipe, and connect Cosmos explanations to flagged vials.

## Team and credits

Team: Amy, Jefferson, Jeremy, Nadia, Nova, Ryan, Cloud, Toua.

Data: Rockwell Automation / UWM Connected Systems Institute `csi-vial-fill-dataset` and the CSI digital twin. Models and tools: NVIDIA Cosmos3-Nano, Isaac Sim 6.0.1, DGX Spark, Brev; PyTorch, torchvision ResNet18 (ImageNet weights), scikit-learn, NumPy, Pillow, FFmpeg, Flask/Waitress, React, Vite, Express. AI coding assistants (Claude, Codex) were used for analysis and code.
