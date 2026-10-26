# Fluid Mixing Station 3 — residual-based anomaly detection

Flags vials whose dye mix doesn't match what the recipe should have produced, using a physics-based
color model instead of a hand-written color rule.

**Live demo:** https://claude.ai/artifact/UisGRG6mFiVt4SPbGFm1kn (needs to be shared from the owner's
Share menu before teammates outside the link can open it)

## Background

The original `csi-vial-fill-dataset` still-camera and video-camera clocks run at different rates
(~0.822x), so most of the still-image labels in `video5_frame_labels.csv` pointed at the wrong vial.
`csi_vial_ai_dataset_v1` is the corrected dataset (see its own `REPORT_EN.md` / `REPORT_KO.md`) — the
scripts here build on that corrected version, not the raw one.

## What's here

- `scripts/model4_baseline.py` — physics-first baseline: absorbance (`-log10(channel/255)`) → Ridge
  regression → dye ratio (r200, r400), evaluated with recipe-grouped folds vs. a guess-the-mean baseline.
- `scripts/model4_eval.py` — leave-one-recipe-out reproduction of the single-dye absorbance line
  (orange absorbs blue light, blue absorbs red light), carryover-suspected vials excluded.
- `scripts/model4_anomaly.py` — the anomaly detector: fits the same regression on vials believed normal,
  then flags any vial whose prediction residual exceeds mean + 1 std of the normal vials' residuals.
  Catches 5/5 known carryover-suspected vials (100% recall), precision ~0.5 with only 10 recipes.
- `scripts/export_demo_data.py` — exports per-vial predictions/residuals/thumbnails as JSON for the demo.
- `demo/index.html` — the standalone HTML demo (same content as the published artifact above); open it
  directly in a browser, no server needed.
- `outputs/` — result JSON/CSV from the scripts above.

## Running it

Needs the corrected dataset's `vials.csv` (from `csi_vial_ai_dataset_v1`, download separately — see
`.gitignore`) at `data/csi_vial_ai_dataset_v1/vials.csv` relative to this folder.

```bash
pip install pandas scikit-learn numpy
python scripts/model4_baseline.py
python scripts/model4_eval.py
python scripts/model4_anomaly.py
python scripts/export_demo_data.py   # refreshes demo/index.html's embedded data if vials.csv changes
```

## Known limitations

- Only 10 recipes recorded so far, so precision on the anomaly flag is ~0.5 — some flagged vials may
  just be ones whose recipe was unfamiliar to the leave-one-recipe-out model, not real contamination.
- No white-reference normalization yet (absorbance uses raw 0–255, no backdrop patch), which likely
  understates the orange-dye signal.
- Next step: collect the expanded 20-recipe session (see the dataset's own collection-review report)
  and add white-reference absorbance.
