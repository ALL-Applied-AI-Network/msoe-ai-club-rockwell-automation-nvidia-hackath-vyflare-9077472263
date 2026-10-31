# Checkpoint: Model 2 v4, full-vial crop

Frozen copy of the model before the holder-crop test. Git tag `model2-v4-station-crop`
(commit `af8c850`). This is the head currently served by the backend
(`backend/model2_assets/head.json`, same SHA-256).

| File | Contents |
|---|---|
| `model2_head_crop.json` | Linear head: classes, scaler, coefficients, preprocessing `station-crop-v1` (crop x 250–390, y 40–430), threshold 0.90, uncalibrated |
| `metrics.json` | All evaluation results (crop and full-frame comparison) |
| `predictions_per_vial.csv` | Every per-vial prediction |
| `vials_manifest.csv` | Labels, eligibility and folds used (workbook `771c86ea…6aea`) |
| `analysis.json` | Occlusion and head-weight analysis |
| `backend_manifest.json` | Backend asset manifest (head hash, approval `false`, validation summary) |

Backbone: torchvision ResNet18 `IMAGENET1K_V1` (`f37072fd…07ec`), frozen, not stored here.

Headline (crop, cross-validation, 0.90): good known recipes top-1 0.775, coverage 0.650,
accepted accuracy 0.962 (40 vials); unfamiliar false acceptance 0.325; bad first 5/15 and
bad later 3/4 accepted.

To restore it, copy `model2_head_crop.json` to `backend/model2_assets/head.json` and
`backend_manifest.json` to `backend/model2_assets/manifest.json`.
