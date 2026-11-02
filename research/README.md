# Research

Model experiments, evaluation outputs and Cosmos baseline results. The running
application lives in `backend/`, `client/` and `server/`; see the
[console guide](../docs/console.md). Results are summarized in the
[executive summary](../docs/EXECUTIVE_SUMMARY.md).

| Folder | Contents | Status |
|---|---|---|
| `model-1-recipe-classifier/` | Original ResNet18 recipe classifier notebook (vial, tank and fused cameras), labels, image QC report and per-run metrics | Superseded: trained on drifted still labels |
| `model-2-resnet-classifier/` | Original Model 2 notebook and labels. The full v4–v7 pipeline is on the `Model2` branch | Experimental API in `backend/model2*`; not used for decisions |
| `model-3-mix-regression/` | Original Model 3 regression notebook and dataset. The corrected v2 (absorbance + linear map) is on the `model-3-improved` branch | v2 recommended; not yet wired into the console |
| `model-4-anomaly-detection/` | Absorbance/ridge baseline, leave-one-recipe-out evaluation, residual-based carryover detector, standalone demo | Integrated: the console serves `outputs/demo_data.json` and `demo/thumbs/` |
| `cosmos-baseline/` | 30 video-5 clips with prompts and Cosmos3-Nano outputs, batch summary and the human verification workbook | Baseline; the console serves `batch-results/.../summary.json` |
| `external-assets.csv` | Inventory (path, size, SHA-256) of images, ZIPs and `.pth` weights kept out of Git. Paths are relative to the original `Training model N/` folders | Inventory only |

## Work kept on branches

| Branch | What it adds |
|---|---|
| `model-3-improved` | Model 3 v2 package, checkpoint, splits, evaluation report |
| `Model2` | Model 2 v4 baseline and v5–v7 crop/inpainting checkpoints |
| `codex/cosmos3-nano-finetune` | Cosmos3-Nano LoRA training, DGX Spark worker, technical reports |
| `brev-research-dataset` | 600 Isaac Sim digital-twin renders and twin technical reports |
| `model_api` | Earlier FluidCheck FastAPI service |

## Notes

- **The original `video5_frame_labels.csv` files are misaligned.** The vial video
  was saved at 30 fps but recorded at about 24.7 fps. Use video frames at
  `start_frame`/`end_frame` from `video5_vial_recipes.csv`, or corrected labels.
- **Dataset images, ZIPs and weights are not in Git.** Restore them to their
  original paths before running a notebook, and adjust its machine-specific paths.
- **Notebook outputs are preserved as run.** These folders were renamed from
  `Training model N/`; notebook-internal relative paths may still use the old names.
