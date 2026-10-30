# Synthetic-image adaptation pilot - October 30, 2026

Status: implemented image support and completed a separate 20-update continuation
of Version 1. The browser tester remains on Version 1 because final-color
agreement regressed on the old real-video development set.

## Changes

- Native still-image inputs, EXIF/RGB handling and separate 262,144 image-pixel
  budget in scripts/train_spark_lora.py; original video preprocessing retained.
- Synthetic `render_color_class` targets separated from human-reviewed real
  `observed_color_sequence` targets. Neither task establishes chemical identity.
- --initial-adapter continues weights with a new optimizer; checks base snapshot
  and source adapter hash. This is not optimizer-state resume.
- --balance-modalities alternates image and video presentations for replay.
- scripts/prepare_synthetic.py verifies supplied archive hashes and image decode,
  removes exact duplicate leakage, preserves label provenance and imports only
  the original reviewed video pilot for real replay/regression.
- scripts/multimodal_contract.py validates mixed partitions and reports separate
  task metrics. tests/test_multimodal.py covers important failure conditions.
- README documents preparation, preflight, bounded evaluation and launch steps;
  requirements-synthetic.txt specifies the local preparation Pillow dependency.

## Prepared data and actual exposure

427 synthetic training images + 21 reviewed real training clips; 120 synthetic
validation images + nine original real validation clips. Last ten authored frame
settings held out, two settings excluded as a gap, and exact hashes deduplicated
within/across partitions. Fifty-three source cases were excluded in total.
The synthetic scene remains shared and real splits share recording video 5.
These are development partitions, not independent-scene/session tests.

The bounded pilot presented 40 images and 40 videos over 20 updates at accumulation
four. It did not train an epoch over 448 records. Evaluation covered 12 synthetic
images (all colors at frame 566) plus all nine old real regression clips. The
other 108 prepared synthetic validation images were not evaluated.

## Readings

| Metric on fixed development inputs | Base | Version 1 before | Continued adapter |
|---|---:|---:|---:|
| Synthetic exact class with required JSON | 8/12 | 0/12 | 9/12 |
| Synthetic exact class accepting a bare-word answer | 8/12 | 8/12 | 9/12 |
| Synthetic schema validity | 12/12 | 0/12 | 12/12 |
| Real-video exact sequence | 0/9 | 4/9 | 4/9 |
| Real-video exact final color | 3/9 | 5/9 | 4/9 |

The initial adapter returned bare color words for this new synthetic task. Its
zero strict score is therefore a schema effect, not zero visual class agreement.
The synthetic class gain ignoring format is one case. New errors remain for
magenta/violet, navy/blue and teal/cyan. This explicit palette prompt differs
from the earlier generic synthetic-photo diagnostic; those scores cannot be
compared directly.

On real clips, vial 5's extra yellow stage disappeared and vial 26's orange-to-brown
transition was recovered. Vials 25 and 27 gained brown stages absent from the human
targets, and vial 13 gained yellow. Exact sequence count stayed four despite
changed correct cases. Final-color count fell by one; do not promote this adapter
as an improvement to factory inspection.

## Spark and verification

- Job wall time: 479.41 seconds (7.99 minutes), including model loading, base/
  initial/final evaluations and saves; excludes preparation, transfer and preflight.
- Optimizer-loop sum: 179.61 seconds, including batch processing.
- Peak allocated CUDA memory: 19.54 GiB; GB10 GPU, BF16 base.
- Trainable LoRA parameters: 7,667,712; base and vision weights frozen.
- First/last minibatch loss: 0.5129 / 0.0324 on different batches; not an accuracy metric.
- All 288 saved adapter tensors are finite and changed; parameter count and rank
  shapes verified. Source adapter hash unchanged. No existing workloads stopped.
- Local tests: 27 discovered, 21 passed, six server tests skipped (Flask absent).
  Real image/video preflight and CUDA backward/optimizer execution passed.

These measurements are not exclusive GPU-hours or energy/cost readings. No
independent real-field accuracy or manufacturing impact has been measured.

## Artifacts and decision

Private data: data/local/synthetic-mixed-v1/. Private model/log backup:
outputs/synthetic-mixed-v1/ (base.json, initial_adapter.json, adapted.json,
training.jsonl, run.json, artifact-verification.json and checkpoint directories).
Remote experiment: /home/yt-vyflare71b7/workspace/vial-finetune-20261029/runs/synthetic-mixed-v1/.

New step-20 adapter SHA-256:
792345ea39e4118c1f31907f38221ae3265b8cfb0c6480a12b5407d099d89a3e

Current Version 1 remains the serving adapter. This run extends the input and
supervision capabilities, but does not demonstrate improved real inspection.
Matched-budget real-only and mixed continuations on independently verified real
sessions are needed to isolate synthetic-data value. No provisional field labels,
mixing, contamination, calibrated-volume or recipe targets were trained.

Technical references: [PEFT trainable adapter loading](https://huggingface.co/docs/peft/package_reference/peft_model),
[native image/video architecture inputs](https://huggingface.co/docs/transformers/model_doc/qwen3_vl).
