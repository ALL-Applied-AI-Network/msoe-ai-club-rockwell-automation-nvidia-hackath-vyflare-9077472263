# Field fine-tuning preparation — October 29, 2026

Status: preparation completed; **no new weight updates or training job started**.
The user explicitly requested that provisional field labels remain unverified.
The existing adapter and browser tester have not been replaced or modified.

## Prepared data

`scripts/prepare_field_review.py` reads the correct `recipes.xlsx` and
`field-data.zip`, without changing either source. It exports a private recipe
bank, recording inventory, per-vial review records, and a source-hashed audit
under ignored `data/local/field-review-v1/`.

The review inventory has 30 vials, six videos, and 30 photos. Recipes 41, 50,
and 60 each have five vial records; recipe 99 has 15. Intended recipe quantities
are separate from provisional durations and visual tank assignments. Blank
quantities and unknown durations remain blank; they are not measured zeroes.
Every review record has `reviewed: false`, an empty answer, an unassigned split,
and `training_eligible: false`. These files are not SFT trainer inputs.

## Audit findings

- All 30 observed targets and video links remain unverified; actual delivered
  ingredient volumes have not been independently established.
- 15 records have different expected and provisionally observed dispense orders:
  vials 1–5, 11–15, and 21–25.
- 12 records list an ingredient dispense duration longer than the complete vial
  window: vials 7–9, 17–20, and 26–30. This may reflect inconsistent boundary
  definitions or timing errors; it is not proof of a physical process failure.
- Vial 1 lacks a duration for an ingredient required by its intended recipe.
- Candidate local video links were generated for 29 records by tentatively
  concatenating recording durations in chronological order. This timeline
  hypothesis is NOT verified alignment. Vial 21 does not fit a unique window;
  boundary precision and timeline origins need review. No clips were cut using
  these candidate links and no filename or intended recipe was used as an
  observed-ingredient training target.

## Training and evaluation decision

Do not randomly divide connected field vials into 24 training and six test
examples. Keep this connected batch in one session group. Collect independent
sessions for a useful assessment of generalization. Retain any historical
development benchmark as a development benchmark, not a substitute for a
verified field test.

Before the next supervised experiment:

1. Confirm video filename, local start/end, and physical vial identity.
2. Verify individual incoming-stream identity and start/end boundaries using
   human review or controller evidence. Preserve disagreements and uncertainty.
3. For volume estimation, obtain per-fluid flow calibration or independent
   measured delivery. Intended mL values are not delivered-volume truth.
4. Freeze independent-session evaluation labels and define ingredient accuracy,
   timing error, volume error (where measurable), recipe accuracy, and rejection
   of unknown/insufficient-evidence cases.
5. Train a separate versioned LoRA adapter on eligible records, compare against
   the unchanged base and previous adapter, and review results before promotion.

The current trainer targets `observed_color_sequence` only. Structured event,
timing, and recipe targets require a separate validated training/evaluation
contract; this preparation does not claim to implement it. Recipe lookup and
volume arithmetic should live in the backend, with model observations as inputs.

## Expected effectiveness and resource use

No defensible field accuracy percentage can be assigned yet. The prior pilot's
4/9 exact color-sequence matches and 5/9 final-color matches were within-session
development results and do not measure ingredient, volume, recipe, or unknown
recipe performance. Six test vials would move accuracy by 16.7 percentage
points per changed prediction.

The Spark was reachable over SSH and the extracted base checkpoint exists.
The read-only check found a GB10 GPU, 121 GiB host unified RAM with 69 GiB
available, and existing GPU workloads including the tester. No workloads were
stopped. **Additional training steps: zero. Additional training GPU time: zero.**
This excludes the existing serving workloads and the resource-check overhead.

Validation: 22 local tests discovered, 16 passed and six server tests skipped
because Flask is absent in the local preparation environment. New checks cover
impossible durations, preserving missing values, conflicting orders, and never
promoting provisional observations when they agree with a recipe. Original
source files and model weights were not edited.

## Reproduce the preparation

Use the preparation Python with `openpyxl` installed:

```powershell
python scripts/prepare_field_review.py --workbook C:/Users/vuelu/Downloads/recipes.xlsx --archive C:/Users/vuelu/Downloads/field-data.zip --out data/local/field-review-v1
```

Choose a new output version when rerunning; the script refuses overwrite.
Private outputs include source hashes for identifying the exact inputs.
