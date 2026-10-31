# Checkpoint: Model 2 v5, holder-and-below crop

Frozen copy of the holder-crop test model before the label-removal test. Git tag
`model2-v5-holder-crop` (commit `af64693`). Not deployed; the backend serves v4
(`../v4-station-crop/`).

| File | Contents |
|---|---|
| `model2_head_holder.json` | Linear head, preprocessing `station-holder-crop-v1` (crop x 250–390, y 200–430), threshold 0.90, uncalibrated |
| `metrics.json` | All evaluation results (full-vial, holder and full-frame inputs) |
| `predictions_per_vial.csv` | Every per-vial prediction |
| `vials_manifest.csv` | Labels, eligibility and folds (workbook `771c86ea…6aea`, 40 training vials) |
| `analysis.json`, `gradcam_holder_model.png` | Occlusion, head weights and attribution |

Backbone: torchvision ResNet18 `IMAGENET1K_V1` (`f37072fd…07ec`), frozen.

Headline (holder, cross-validation, 0.90): good known recipes top-1 0.875, coverage 0.675,
accepted accuracy 1.000; unfamiliar false acceptance 0.150; bad first 3/15 and bad later
4/4 accepted. Known issue: the bottom of each vial's label sticker is inside the crop and
is used by the model.

To deploy it, the backend would need preprocessing `station-holder-crop-v1` support
(`backend/model2.py` accepts only `station-crop-v1` today).
