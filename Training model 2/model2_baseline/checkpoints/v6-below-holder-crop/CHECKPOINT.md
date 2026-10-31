# Checkpoint: Model 2 v6, below-holder crop (labels removed by cropping)

Frozen copy of the label-free crop test model before the whole-vial label-removal test.
Git tag `model2-v6-below-holder-crop` (commit `3c02c46`). Not deployed; the backend
serves v4 (`../v4-station-crop/`).

| File | Contents |
|---|---|
| `model2_head_below_holder.json` | Linear head, preprocessing `station-below-holder-crop-v1` (crop x 250–390, y 265–430), threshold 0.90, uncalibrated |
| `metrics.json` | All evaluation results (full-vial, holder, below-holder and full-frame inputs) |
| `predictions_per_vial.csv` | Every per-vial prediction |
| `vials_manifest.csv` | Labels, eligibility and folds (workbook `771c86ea…6aea`, 40 training vials) |
| `gradcam_below_model.png` | Attribution maps |

Backbone: torchvision ResNet18 `IMAGENET1K_V1` (`f37072fd…07ec`), frozen.

Headline (below holder, cross-validation, 0.90): good known recipes top-1 0.850, accepted
accuracy 0.963; unfamiliar false acceptance 19/40; bad first 2/15 and bad later 2/4 accepted.
No vial label is visible in this crop, but fills of 60 mL and more fill it entirely.
