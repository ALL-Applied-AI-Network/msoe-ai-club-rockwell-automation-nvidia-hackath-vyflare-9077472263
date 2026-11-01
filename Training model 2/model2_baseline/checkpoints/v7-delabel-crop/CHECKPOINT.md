# Checkpoint: Model 2 v7, whole vial with label marks inpainted

Approximate label removal (see README "Whole vial with labels inpainted"). Git tag
`model2-v7-delabel-crop` (commit `85a85cc`). Not deployed; the backend serves v4.

| File | Contents |
|---|---|
| `model2_head_delabel.json` | Linear head, preprocessing `station-crop-delabel-v1` (label marks inpainted by `remove_labels`, then crop x 250–390, y 40–430), threshold 0.90, uncalibrated |
| `metrics.json`, `predictions_per_vial.csv` | All results, all inputs |
| `vials_manifest.csv` | Labels, eligibility and folds (workbook `771c86ea…6aea`, 40 training vials) |
| `gradcam_delabel_model.png`, `label_removal_preview.png`, `label_mask_coverage.json` | Attribution, mask review and coverage |

Headline (CV, 0.90): good known top-1 0.800, accepted accuracy 1.000, coverage 0.650;
unfamiliar false acceptance 10/40; bad first 1/15 and bad later 3/4 accepted.
Flaws: label paper remains; 20 of 60 vials have no mask; some liquid is smoothed.
