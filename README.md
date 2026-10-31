# Cosmos3-Nano vial inspection fine-tuning

Minimal **image/video + question → text** supervised fine-tuning for liquid appearance and synthetic render-control classification. This branch contains training preparation, configuration, launch instructions, the pilot tester, and a direct worker interface for `model4/recipe-detection-backend-integration` at `956d5d2`.

The [current technical report](reports/cosmos-technical-report-2026-10-31.md) covers training results, data exclusions, measured Spark usage, backend compatibility, screening limitations and remaining acceptance work. A [shareable PDF](output/pdf/Cosmos_Vial_Inspection_Technical_Report_2026-10-31.pdf) contains the same report.

## Model choice

Use [nvidia/Cosmos3-Nano](https://huggingface.co/nvidia/Cosmos3-Nano) in **reasoner mode**. The complete omni model is listed as 16B; this recipe trains its extracted Qwen3-VL-shaped reasoner, not the diffusion/generation pathway. NVIDIA's conversion utility preserves the base Nano checkpoint's trained visual tower and language weights. It does not silently substitute an unmodified Qwen checkpoint.

The supplied photos show differences in liquid color/clarity and level: 164006 and 164011 appear colorless, 164119 olive green, and 163859 green/teal. Lighting, reflections, and occlusion limit interpretation. The supplied vial-2/clip.mp4 has 823 frames at 30 fps, 640×480, lasting 27.43 seconds. Six sampled frames show green liquid accumulating in the left tube beneath a nozzle. These observations do **not** establish recipe correctness, chemical identity, calibrated volume, or defect labels.

The [linked examples collection](https://huggingface.co/collections/nvidia/cosmos3-examples) contains specialized generation/simulation/policy checkpoints. None is a vial-inspection reasoner specialization. Nano is the recommended starting point for this project's existing inspection objective. Super-Image2Video is relevant if the goal changes to synthetic footage; Sim/Transfer/Policy variants need different targets and data. Edge is a smaller alternative to evaluate if compute is constrained; its accuracy on these vials is untested.

## Contents and limits

- `scripts/prepare_data.py`: stage/probe private media, collect editable labels, emit native ShareGPT video JSON arrays. Rejects unreviewed answers, session leakage, changed files, and identical media across splits.
- `scripts/train.py`: check revision/checkpoint/data, then launch the native trainer.
- `configs/vial_reasoner.toml`: full reasoner SFT, BF16, four-way FSDP, initial learning rate 1e-5, **20-update smoke run**. This is not a tuned production schedule or LoRA implementation.
- `framework-revision.txt`: exact upstream revision inspected for this setup.

The native video recipe does not accept still-image records. Inventory keeps the four JPEGs as `usage: reference` for appearance review and evaluation. They are not automatically converted to repeated-frame videos or training labels. Image SFT requires a separate image-data adapter. No ground-truth answers are fabricated. No application, inference server, weights, datasets, or Framework source are committed.

## 1. Inventory and annotate locally

Requires Python 3.11+ for these helpers. Install the optional media package in a **separate preparation environment**, not over the Framework environment:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-media.txt
python scripts/prepare_data.py inventory --group provided-capture --media "C:/Users/vuelu/Downloads/video-5-separated/video-5-separated/vial-2/clip.mp4" "C:/Users/vuelu/Downloads/vialimages/20261028_164006.jpg" "C:/Users/vuelu/Downloads/vialimages/20261028_164011.jpg" "C:/Users/vuelu/Downloads/vialimages/20261028_164119.jpg" "C:/Users/vuelu/Downloads/vialimages/20261028_163859.jpg"
```

Creates ignored `data/local/media/` and `data/local/annotations.jsonl`, refusing to overwrite existing labels. For more videos, inventory to another root, then merge its rows and media into `data/local/` (media names are content-addressed). `data/annotations.example.jsonl` documents the fields; its empty targets are deliberately unusable.

Edit the private manifest:

1. Assign each training video a `split` of `train` or `val`. Use the **same group for an entire source recording/session**, including nearby clips, crops, synchronized cameras, and photos from that session. All members of a group must remain in one split. Do not divide this single supplied clip into train/validation to manufacture independent data.
2. Write a short factual `answer` to the `question`, then set `reviewed: true`. Include uncertainty for ambiguous liquid boundaries/colors. Questions may target color, clarity, relative level, or observable changes. For pass/fail, obtain recipe targets/tolerances and verified outcome labels first.
3. Keep stills as references. Collect independently recorded videos covering expected/abnormal outcomes, lighting, and recipes. One clip plus four similar photos is insufficient for a useful fine-tune. Reserve separate test sessions outside the training manifest.

```powershell
python scripts/prepare_data.py build
```

Build requires reviewed videos from different groups in both splits. It writes `train.json` and `val.json` under `data/local/`. Transfer the **whole** private `data/local/` directory to the GPU machine. Relative media paths remain portable. Do not commit it.

## 2. Prepare Linux/NVIDIA training

Training targets Linux/CUDA, not native Windows or macOS. This recipe uses **4 GPUs**; 4×80 GB is a planning starting point, not a measured memory guarantee. NVIDIA's general SFT guide reports testing on 8×H100 80 GB. Actual memory depends on frame/pixel/context budgets. No GPU training has been run on this Windows machine.

From this branch's root on Linux:

```bash
git clone https://github.com/NVIDIA/cosmos-framework.git .local-tools/cosmos-framework
git -C .local-tools/cosmos-framework checkout "$(cat framework-revision.txt)"
```

Follow the [pinned setup guide](https://github.com/NVIDIA/cosmos-framework/blob/1a2f03ab6111b457633827736f94f67d55bd5202/docs/setup.md), including system FFmpeg/media dependencies, driver checks, and required uv version. Synchronize its locked environment (CUDA 13.0 shown; select cu128-train when appropriate):

```bash
cd .local-tools/cosmos-framework
uv sync --all-extras --group=cu130-train
source .venv/bin/activate
```

Accept model access terms where required and authenticate with Hugging Face tooling. Keep tokens out of Git. Allow disk space for the omni checkpoint and extracted reasoner. The pinned Framework's catalog resolves model revisions; preserve downloaded snapshot IDs in experiment records.

Convert the actual Cosmos base checkpoint using the supported utility:

```bash
python -m cosmos_framework.scripts.convert_model_to_vlm_safetensors \
  --checkpoint-path Cosmos3-Nano \
  -o ../../checkpoints/Cosmos3-Nano-VLM
cd ../..
```

Use this activated Framework Python for all remaining commands. Do not install the media requirements into this environment or replace its locked torch/transformers versions.

## 3. Check and launch

```bash
python scripts/train.py \
  --framework .local-tools/cosmos-framework \
  --checkpoint checkpoints/Cosmos3-Nano-VLM --check-only

python scripts/train.py \
  --framework .local-tools/cosmos-framework \
  --checkpoint checkpoints/Cosmos3-Nano-VLM
```

The launcher uses four ranks from the TOML, unique run names, local checkpoints, and disabled W&B upload. `--check-only` validates files/data contracts, not weight contents or GPU compatibility. The Framework validates the TOML and loads actual weights at training startup.

Defaults sample **32 uniformly spaced frames** per clip at a 153,600-pixel per-frame budget. This preserves more appearance detail than upstream smoke defaults, with greater memory cost. Over the supplied 27.4-second video this is approximately 1.2 fps. For fast filling/slosh events, shorten clips with session groups preserved or raise `COSMOS_VIDEO_NUM_FRAMES`; NVIDIA recommends 4 fps for reasoner inputs. Confirm sampled frames cover each labeled event. `COSMOS_VIDEO_MAX_PIXELS` controls detail/memory. CPU TorchCodec decode is initially selected to avoid requiring a verified CUDA decoder.

First verify the 20-update smoke run. For real experiments, adjust `num_epochs`, `steps_per_epoch`, `max_iter`, scheduler cycle/warmup, and validation/checkpoint cadence together for distributed dataset size. Ensure enough videos for the topology. Changing GPU count also requires changing FSDP topology and validating memory/runtime; single-GPU training is not validated.

## 4. Export and evaluate

Runs land in `outputs/vyflare/vial_reasoner/nano_<timestamp>/`. From the activated Framework environment, set the actual run directory:

```bash
RUN_DIR=/absolute/path/to/outputs/vyflare/vial_reasoner/nano_TIMESTAMP
CHECKPOINT_ITER=$(cat "$RUN_DIR/checkpoints/latest_checkpoint.txt")
python -m cosmos_framework.scripts.export_model \
  --checkpoint-path "$RUN_DIR/checkpoints/$CHECKPOINT_ITER" \
  --config-file "$RUN_DIR/config.yaml" -o "$RUN_DIR/model"
```

Compare base and fine-tuned models on untouched test sessions with identical prompts/sampling. Report color/clarity agreement, calibrated level error when available, and precision/recall for verified event/defect labels. Inspect false positives, missed abnormalities, uncertainty, latency, and peak GPU memory. Lower training loss alone does not establish inspection accuracy. This branch does not wire the export into the original backend; validate inference separately with NVIDIA's guide.

## Verification and sources

```bash
python -m unittest discover -s tests -v
```

Local verification covers data contracts and leakage rejection. GPU loading, training, export, and quality remain unverified until run on the target hardware.

- [Model card](https://huggingface.co/nvidia/Cosmos3-Nano)
- [Pinned training guide](https://github.com/NVIDIA/cosmos-framework/blob/1a2f03ab6111b457633827736f94f67d55bd5202/docs/training.md)
- [Native video recipe](https://github.com/NVIDIA/cosmos-framework/blob/1a2f03ab6111b457633827736f94f67d55bd5202/examples/toml/sft_config/video_sft_nano.toml)
- [Checkpoint conversion](https://github.com/NVIDIA/cosmos-framework/blob/1a2f03ab6111b457633827736f94f67d55bd5202/cosmos_framework/scripts/convert_model_to_vlm_safetensors.py)
- [Reasoner inference](https://github.com/NVIDIA/cosmos-framework/blob/1a2f03ab6111b457633827736f94f67d55bd5202/docs/inference.md#reasoner)

Respect model/data licenses and retain attribution when distributing derivatives. No upstream implementation or checkpoint is redistributed here.

## Import the team's human verification

The added hackathon data is under ignored `data/csi-vial-fill-dataset/` and the 30 separated clips under ignored `data/video-5-separated/`. The original dataset contains five synchronized recording runs across three camera stations. Video 5 has 30 recipe-labeled vials. Recipe amounts describe dosing targets and do not establish observed liquid colors or measured volumes.

The verification workbook supplies whole-clip human color descriptions. Import it in the preparation environment:

```powershell
python -m pip install -r requirements-labels.txt
python scripts/import_verification.py --workbook C:/Users/vuelu/Downloads/vial-verification.xlsx --clips data/video-5-separated/video-5-separated
```

This creates `data/local/video5/annotations.jsonl` and copies the 30 clips. Human colors become ordered JSON color-sequence targets. Existing model predictions remain metadata and are excluded by the native data builder from both prompts and targets. The original workbook is read without changes. Whole-clip labels must not be assigned to every frame: transition times have not been labeled.

All 30 clips share `group=real-recording-video5` and initially have no split. Label additional independent real recordings before assigning train/validation/test partitions. A within-video experiment can test whether adapters learn, but cannot establish accuracy on independent recording sessions. The existing launcher still uses its four-GPU full-SFT recipe; a single-Spark LoRA configuration requires a separate runtime validation before launch.

Audit findings from the supplied workbook: 12/30 recorded model descriptions exactly match human descriptions. Of 17 human descriptions containing transitions, 3 match exactly. These are string-agreement counts, not a fresh controlled model benchmark. The pass/error formula uses at least one dispense-color match although the workbook note describes two. It is a separate rule from agreement between the model and human color descriptions. The workbook calls T200 red; the dataset documentation calls it orange. Resolve that vocabulary difference before using tank-color labels as training targets. A visible mixed color in the vial during a dispense does not identify the incoming tank fluid by itself.

For Isaac Sim additions, retain simulator version, scene ID, seed, camera settings, lighting, material parameters, and label provenance. Keep related synthetic scenes in one split. Compare real-only versus real-plus-synthetic adaptation on the same untouched real test recordings. Avoid hue-altering augmentation when color is the target, and visually validate translucent-liquid rendering before using simulated color labels.

## Single-Spark LoRA pilot

The pilot path uses the existing Spark PyTorch/Transformers/PEFT environment directly, independently of the native four-GPU Framework launcher. Do not run `scripts/train.py` for this pilot.

`prepare_spark_pilot.py` creates 21 training clips and 9 validation clips by holding out ALL vials from recipes 6, 9, and 13. This deliberately permits a **within-session development experiment**, not an independent test. It does not weaken the session-separation requirements of `prepare_data.py`. No unlinked field photos, unlabeled field footage, simulated mixing, recipe appearance guesses, or baseline predictions enter the targets.

`extract_cosmos_reasoner.py` streams the cached omni checkpoint into a Qwen3-VL-shaped reasoner. It maps the Diffusers attention names, checks every expected tensor name and shape, and preserves the original checkpoint. It never initializes missing weights from another model. Its `base_provenance.json` records the source snapshot and source blobs. The diffusion pathway is excluded.

`train_spark_lora.py` trains rank-8 language-attention adapters only, with BF16 base weights, SDPA attention, gradient checkpointing, and assistant-answer-only loss. It rejects any other trainable parameters. Video sampling retains original frame timestamps. The pixel budget is a TOTAL VIDEO budget (default 2,621,440 pixels over 32 frames), which is different from a per-frame budget. At these settings the 640x480 source is reduced to approximately 320x224, so small details and fast transitions can remain unobservable.

Example commands in a compatible GPU environment:

```bash
python scripts/prepare_spark_pilot.py
python scripts/extract_cosmos_reasoner.py --source /path/to/cached/Cosmos3-Nano/snapshot --out /path/to/base-reasoner
python scripts/train_spark_lora.py --checkpoint /path/to/base-reasoner --data data/local/spark-pilot-v1 --output outputs/pilot-v1 --preflight
python scripts/train_spark_lora.py --checkpoint /path/to/base-reasoner --data data/local/spark-pilot-v1 --output outputs/pilot-v1 --steps 20
```

The trainer saves base/adapted generation outputs on the same validation clips, exact normalized sequence/final-label metrics, training losses, adapter checkpoints every five updates, script/dataset/source identifiers, and library versions. Invalid JSON counts as an error. These strict label metrics are not chemical-identification accuracy. An adapter is not automatically promoted into the backend.

Repeat training by creating a new versioned dataset and choosing a new output directory. The base remains unchanged. Starting a fresh adapter from the same base is the preferred comparison when labels are corrected; do not blindly continue an adapter trained on incorrect labels. The runner now supports `--initial-adapter` for continuing adapter weights with a **fresh optimizer**, not resuming optimizer state or the original schedule. It checks the parent's base snapshot and records the source adapter hash. Keep a fixed independent-session test set once one is labeled, and keep a replay sample of older valid data when extending task coverage.

The completed Spark pilot results and remaining failure cases are recorded in [reports/spark-pilot-v1.md](reports/spark-pilot-v1.md).

## Browser testing

The private-network Spark tester supports base/adapter comparisons, video and exploratory photo uploads, result downloads, and optional reviewed feedback. See [reports/model-tester-guide.md](reports/model-tester-guide.md) for access and service instructions.

## Cosmos interface for the Model 4 backend

The integration reference is `model4/recipe-detection-backend-integration`, pinned
to commit `956d5d24d19f80b99f85d4841e678d20d533e0fb`. The existing Version 1
worker now exposes `POST /backend/predict` for that branch's `RemoteCosmosModel`
client. It accepts the client's image, prompt, frame ID and worker model name,
and returns text with actual Spark execution metadata. The browser tester remains
available on the same service. No new weights or Model 4 measurement code are
introduced by this interface change.

See [the current integration guide](reports/model4-backend-integration-guide.md)
and [the correction report](reports/model4-integration-correction.md).
The branch contains the direct worker integration only. This LoRA worker is an
experimental alternative to its native Cosmos worker; it does not supply the
native worker's Framework guardrail screening.

## Synthetic image and real-video adaptation

The earlier image exclusions describe the original native video-only recipe.
The custom Spark runner now accepts image render-control targets and verified
video appearance targets in the same experiment. It uses the real Cosmos
vision encoder for images rather than turning stills into repeated-frame videos.

`scripts/prepare_synthetic.py` verifies all archive images, retains label
provenance, and prepares an explicit frame-block development partition. The last
20% of authored frame settings are held out, two frame settings form a gap, and
identical-image hashes are deduplicated and purged across partitions. The fixed
scene is still shared; this does not constitute independent-scene validation.
It includes the original 21 reviewed real training clips and nine regression
clips. Provisional field labels never enter this dataset.

Install `requirements-synthetic.txt` only in the local preparation environment
if Pillow is missing. The Spark training environment already supplies Pillow;
do not replace its existing Torch/Transformers/PEFT stack with preparation dependencies.

```bash
python scripts/prepare_synthetic.py --archive /path/to/brev-research-dataset.zip --real-pilot data/local/spark-pilot-v1 --out data/local/synthetic-mixed-v1
python scripts/train_spark_lora.py --checkpoint /path/to/base-reasoner --data data/local/synthetic-mixed-v1 --output outputs/synthetic-mixed-v1 --initial-adapter /path/to/pilot-v1/adapter-step-020 --balance-modalities --eval-limit 21 --preflight
python scripts/train_spark_lora.py --checkpoint /path/to/base-reasoner --data data/local/synthetic-mixed-v1 --output outputs/synthetic-mixed-v1 --initial-adapter /path/to/pilot-v1/adapter-step-020 --balance-modalities --eval-limit 21 --steps 20 --accumulation 4
```

Synthetic images use a separate `render_color_class` JSON-string target from a
12-class palette. This predicts a renderer's control class, not chemical identity
or measured composition. Real videos retain `observed_color_sequence` lists.
`--balance-modalities` alternates image/video microbatches; at 20 updates and
accumulation four, each modality has 40 presentations. Dataset size does not
mean every record is presented during this pilot.

Image pixel budget defaults to 262,144 separately from the total-video pixel
budget. Preflight checks both modalities, assistant-only loss boundaries, media
hashes, split groups, and duplicate leakage. With `--initial-adapter`, evaluation
records base, initial adapter, and continued adapter results on identical inputs.
For this 21-case diagnostic, all nine real regression clips and 12 synthetic
holdout images (one per color at the first held-out frame) are evaluated; the
other prepared validation images are not scored. Omit `--eval-limit` to evaluate
the full prepared development set. Synthetic and real metrics are reported
separately. The existing browser tester is not automatically changed and its
color-list parser does not implement the new render-control task.

The completed continuation pilot and its measured regression are documented in
[reports/synthetic-training-v1.md](reports/synthetic-training-v1.md). It remains
experimental; the browser tester continues using Version 1.
