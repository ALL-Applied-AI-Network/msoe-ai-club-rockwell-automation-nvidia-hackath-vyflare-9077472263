# Cosmos3-Nano vial inspection fine-tuning

Minimal **video + question → text** supervised fine-tuning for liquid appearance and filling observations. This branch contains only training preparation, configuration, and launch instructions. The application/backend remains on `implement-backend` at `b9184d9`.

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
