# Field inference diagnostic - October 29, 2026

## Scope and model identity

Completed 12 paired inference requests on the DGX Spark: six video windows and
six photos. Each request compares the unchanged Cosmos3-Nano reasoner with the
existing Version 1 step-20 LoRA adapter, using the resident browser tester.
No training, checkpoint replacement, or server change was performed.

There is no trained Version 2 checkpoint. Version 2 is field-data preparation,
so it cannot be evaluated as a different neural model. The base model in this
comparison is NOT Version 2. Using the same Version 1 checkpoint inside a future
Version 2 application would not by itself change its perception capability.

## Inputs and controls

- Source: the six recordings and corresponding photo folders in field-data.zip.
- Videos: fixed 20-50-second source interval in every recording, re-encoded to
  MP4 at the original frame rate and resolution. No selection by model output.
- Photos: first lexicographic JPEG filename in each corresponding folder.
- These are folder-level associations, not verified same-vial photo/video pairs.
- Same input bytes, prompt, sampler, decoding, and output budget for both models
  within each comparison. Recipe IDs and source filenames are not supplied in
  the model prompt. The service does not crop or track a vial automatically.
- Videos: 32 uniformly sampled frames and 2,621,440 total video pixels.
- Photos: existing exploratory single-image prompt and preprocessing; this is a
  different modality and prompt, so video/photo results are reported separately.
- Greedy generation, maximum 96 new tokens; same base snapshot
  e59a53c25979a090fa8706c9acc0c254a6e89b92 and Version 1 adapter-step-020.
- All provisional field observations remain unverified. These 12 inputs are a
  diagnostic sample, not an independent labeled accuracy benchmark, an 80/20
  test split, or coverage of all 30 field vials or all 52 recipes.

## Measured outcome

| Measure | Base reasoner | Version 1 adapter |
|---|---:|---:|
| Required color-list schema on videos | 5/6 (83.3%) | 6/6 (100%) |
| Required color-list schema on photos | 1/6 (16.7%) | 0/6 (0%) |
| Video answers reduced to one color | 0/6 | 5/6 |
| Verified visual/ingredient/recipe accuracy | Not measurable | Not measurable |

All 12 HTTP requests returned status 200. Summed server request processing time
was 88.65 seconds; average 7.39 seconds per paired request, including both
predictions and media processing. Six paired video requests totaled 59.86
seconds; six paired photo requests totaled 28.79 seconds. These are request
times, not exclusive GPU-kernel time or per-model latency measurements. Transfers
and local media preparation are excluded. No additional training steps occurred.

## Video outputs

Group names below identify sources for review, not verified ingredient labels.

| Source group | Base output | Version 1 output |
|---|---|---|
| 41 | clear > green > yellow | blue > green > yellow |
| 50 | clear > light brown > dark brown | brown |
| 60 | clear > light brown > dark brown | yellow |
| 99 / 41-flush | Repeated orange until response was truncated; invalid schema | orange |
| 99 / 50-flush | green > clear | green |
| 99 / 60-flush | clear > green > clear | green |

The adapter is more concise and avoids the base model's repeated-orange failure
on this sample, but its one-color answers may omit real temporal changes. More
stages from the base model are not automatically more correct: they could reflect
an empty vial, a neighboring vial, reflections, or an actual change. Independent
review of sampled frames and video is needed to score correctness.

## Photo outputs

| Source group | Base color value | Version 1 color value |
|---|---|---|
| 41 | yellow (list; passes schema) | yellow (string; fails schema) |
| 50 | yellow (string) | yellow (string) |
| 60 | green (string) | green (string) |
| 99 / 41-flush | yellow (string) | brown (string) |
| 99 / 50-flush | green (string) | green (string) |
| 99 / 60-flush | green (string) | green (string) |

The photo string outputs are syntactically parseable JSON after fence removal,
but fail the application's required nonempty list contract. This is a schema
failure, not necessarily a wrong color. The single-image prompt says "containing
one observed color" without explicitly repeating "ordered list"; that ambiguity
may contribute to the failure, but was not experimentally isolated. The video-
trained adapter has no demonstrated photo-supervision benefit. No prompt was
changed during this diagnostic.

## Implications for new datasets and Version 2

Version 1 can be used to draft color observations for reviewer assistance on
new field footage. Its tested video formatting is useful, but it should not
automatically label ingredients, delivered amounts, contamination, or recipes.
It has no calibrated match confidence or known/unknown recipe decision.

Version 2 currently contributes traceability, intended-recipe separation, and
review flags. It offers no measured neural accuracy improvement. Its future
event-focused training and backend recipe matching remain unimplemented.

Before another adapter is trained, prioritize review of these six video outputs,
especially recipe-60 and water-flush intervals; confirm target-vial tracking and
event boundaries; acquire independently measured volume/calibration where needed;
and collect independent labeled sessions. For photo support, first make the
single-image output contract explicit and separately evaluate any prompt/schema
fix; robust visual correctness still needs verified photo labels. Repairing a
string into a list would improve parsing, not demonstrate better color accuracy.

## Artifacts

- Private local inputs, source hashes, selection manifest and raw responses:
  outputs/field-diagnostic-v1/samples.json and results.json, plus media/.
- Preparation/execution helper: .local-tools/field_diagnostic.py (ignored).
- Spark run folder: /home/yt-vyflare71b7/workspace/vial-finetune-20261029/field-diagnostic-v1/.
- Spark execution log: field-diagnostic-v1.log in the parent experiment folder.
- Model identity, exact rendered prompts, per-request timestamps, source/input
  hashes, raw text, parsed output, schema validity, and processing times are
  preserved in results.json. No reviewer feedback was submitted or auto-labeled.

The remote unzip binary was unavailable; Python's standard zipfile extractor
was used for the locally generated diagnostic archive. No package installation
or changes to existing GPU workloads were needed.
