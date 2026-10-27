# Team Vyflare CSI Synthetic Vial Dataset

> **SYNTHETIC EXPERIMENT:** These images are simulated observations for research. Color names and hex values are rendering controls only. They are not recipes, chemicals, mixture ratios, quality labels, or defects. Animation frames are not measured liquid volumes or calibrated fill percentages.

## Dataset contents

- 600 PNG images at 640 x 480 pixels.
- 12 display-color folders with exactly 50 distinct authored animation frames per color.
- Fixed existing FillCam, lighting, and vial pose; only authored animation frame and liquid `inputs:diffuseColor` were varied.
- `dataset_manifest.jsonl` and `dataset_manifest.csv` contain one record per image.
- `verification_summary.json` records counts, decode checks, and source-integrity checks.
- `pilot_contact_sheet.png` shows one representative frame for all 12 color settings.

Colors:

- `navy` — `#2446A8`
- `blue` — `#2078D9`
- `cyan` — `#20C7D9`
- `teal` — `#159A9C`
- `green` — `#35B779`
- `lime` — `#8BC34A`
- `yellow` — `#F4D03F`
- `amber` — `#F2A51A`
- `orange` — `#E76F2E`
- `red` — `#D94A4A`
- `magenta` — `#C64BD8`
- `violet` — `#7656C9`

Authored frame settings: `30, 43, 57, 70, 84, 97, 110, 124, 137, 150, 164, 177, 191, 204, 217, 231, 244, 258, 271, 284, 298, 311, 325, 338, 351, 365, 378, 391, 405, 418, 432, 445, 458, 472, 485, 499, 512, 525, 539, 552, 566, 579, 592, 606, 619, 632, 646, 659, 673, 686`

## Layout

```text
/workspace/data output/
  navy/ ... violet/       # 50 verified PNGs in each of 12 folders
  dataset_manifest.jsonl
  dataset_manifest.csv
  verification_summary.json
  pilot_contact_sheet.png
  _staging/               # raw pilot/full outputs and logs
```

## Reproduce on Brev

From `/workspace/csi_digital_twin_v1` on the running Isaac Sim 6.0.1 instance:

```bash
python3 tools/generate_12color_manifests_v5.py
/isaac-sim/python.sh tools/render_synthetic_experiments.py \
  --config experiments/synthetic_12color_pilot_v5.json \
  --out-dir '/workspace/data output/_staging/pilot_raw' --subframes 32
/isaac-sim/python.sh tools/render_synthetic_experiments.py \
  --config experiments/synthetic_12color_remaining_v5.json \
  --out-dir '/workspace/data output/_staging/remaining_raw' --subframes 32
/isaac-sim/python.sh tools/finalize_12color_dataset_v5.py
```

The render script edits `inputs:diffuseColor` in an anonymous USD session layer and reports `source_files_saved: false`. Both run manifests showed identical source state before and after generation. Existing digital-twin and prior synthetic-output files were not overwritten.

## Verification

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path('/workspace/data output')
summary = json.loads((root / 'verification_summary.json').read_text())
print(summary['total_images'])
print(summary['counts_by_color'])
print(summary['all_images_readable_640x480'])
print(summary['source_integrity'])
PY
```

Expected: 600 total, 50 per color, readable images `true`, and source integrity `true` for both runs.

## Research-use limitations

This dataset can help pretraining, augmentation, pipeline debugging, and controlled sensitivity studies, but synthetic performance alone does not establish real-world performance. Compare distributions with Amy's real vial data and evaluate final models on held-out real vials or held-out acquisition sessions. Avoid splitting near-duplicate frames across train and validation sets; group splits by real vial/session where possible.
