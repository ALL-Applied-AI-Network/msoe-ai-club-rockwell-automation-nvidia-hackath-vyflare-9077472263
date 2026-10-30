# Digital-twin archive review and inference diagnostic

Date: October 29, 2026 (America/Chicago). No training or weight changes.

## Archive evidence

Reviewed the user-supplied brev-research-dataset ZIP in Downloads. The extracted
dataset content inside the archive includes 600 labeled PNGs, a contact sheet,
CSV/JSONL metadata, verification summary, documentation, and two technical PDFs.
The older first PDF describes 240 earlier images; the current manifest and
archive contain the later 600-image corpus. The nested data output.zip is a Git
LFS pointer, but the actual images are available in the outer archive.

Independently checked all 600 manifest image hashes against archive bytes: all
match. All 600 image headers report 640x480. There are 12 display-color settings,
50 authored animation frames per color, and 565 distinct file hashes (35 files
repeat an existing image exactly). Fixed camera, lighting and vial pose are
recorded throughout. The varied controls are animation frame and liquid shader
diffuse color. These are not 600 independent physical experiments.

The manifest explicitly identifies color names as render controls, not chemical,
recipe, mixture-ratio, quality, or defect labels. Animation frames are not
measured volumes or calibrated fill percentages. The rendering documentation
describes sampling an authored animation rather than a fluid-physics solver.
Document instructions were treated as source content, not user requests.

## Inference procedure

Selected one raw image for each of the 12 color controls at the same authored
frame, 391. Uploaded with neutral sample-01.png through sample-12.png names;
control labels and metadata were not provided in the model prompt. No labeled
contact sheet was used as model input. Compared unchanged base and Version 1
step-20 adapter using the resident Spark tester's existing photo prompt, greedy
decoding and 96-new-token budget. Version 2 has no separate trained checkpoint.

This is a 12-image, one-frame synthetic sensitivity check, not a random test of
all 600 images or a real-world performance benchmark. The photo pathway remains
exploratory because the adapter was trained on video color-sequence labels.

| Render-control name | Base output | Version 1 output |
|---|---|---|
| amber | orange | orange |
| blue | blue | blue |
| cyan | cyan | cyan |
| green | green | green |
| lime | green | green |
| magenta | purple | purple |
| navy | blue | blue |
| orange | orange | orange |
| red | red | red |
| teal | cyan | cyan |
| violet | purple | purple |
| yellow | yellow | yellow |

Both configurations returned the required nonempty color-list schema on 12/12
requests. After JSON/fence parsing, output color lists agree on 12/12. Exact
case-insensitive agreement with render-control names is 6/12 for each. This is
control-name agreement, not calibrated visual-label or chemical accuracy: a
shader's chosen name does not uniquely determine the perceived output shade.
The existing adaptation demonstrates no additional benefit over the base on
this sample. Good synthetic photo formatting does not negate the earlier real-
photo schema failures; inputs differ and no prompt fix was made.

All 12 HTTP comparisons succeeded, with summed server processing time 56.98
seconds for both models plus preprocessing. This is not exclusive GPU time or
per-model latency. No GPU training occurred. Raw prompts, identity, hashes,
responses, and timings are in ignored outputs/synthetic-diagnostic-v1/results.json
and samples.json. Input hashes returned by the service match all staged inputs.

## Use and limits

The corpus can support controlled color-sensitivity studies, appearance
augmentation, authored-state recognition, and development of vial localization.
It does not contain verified ingredient, recipe, chemical, mixing, carryover,
contamination, or mL targets. Localization supervision would need boxes/masks
from the simulator or annotation; these are not supplied in this manifest.
No clear/water or brown display-control class is included among the 12, which
limits relevance to important real flush and mixed-color cases.

Passing an image through inference does not change model weights. To investigate
training value, implement verified image-target support (the current SFT runner
is video-only), group exact/near duplicates, introduce genuinely distinct scene
and lighting conditions, and compare real-only versus real-plus-synthetic
adapters with matched training budgets on a frozen, verified real-session test.
Use synthetic labels only for quantities actually represented by the renderer.
Do not fabricate color-transition or mixture targets by arranging independent
color renders into a sequence, or infer volume from an animation frame.

Synthetic augmentation can help appearance coverage, but fixed scenes can teach
shortcuts and simplified materials can degrade real-world transfer. An image
can support a color description; it cannot uniquely identify a visually
ambiguous chemical or recipe. Use confirmed source identity, event history,
flow/weight calibration, and backend recipe matching for the expanded task.
