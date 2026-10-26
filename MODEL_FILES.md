# Training model folders

This branch contains the three original training notebooks, CSV labels and indexes,
and available CSV/JSON result reports. Notebook contents and outputs are preserved.

- `Training model 1/`: training notebook, labels, cleaned-data reports, and tank,
  vial, and fusion ResNet18 evaluation artifacts (CSV/JSON).
- `Training model 2/`: training notebook and recipe/frame labels.
- `Training model 3/`: training notebook, indexes, recipe/frame labels, and cleaned
  regression dataset.

## External assets

Dataset images, ZIP archives, and `.pth` model weights were intentionally excluded
from this Git upload. The original files remain in the source download folders.
`external-assets.csv` lists their relative paths, byte sizes, and SHA-256 hashes.
It is an inventory, not a download service; a shared download location still needs
to be provided before teammates can reproduce runs requiring these assets.

Restore required assets to their original relative paths and adjust notebook
machine-specific paths before running. Install Python dependencies in a fresh
environment rather than copying `.venv`. The root requirements files belong to
the existing branch and are not a verified dependency lock for these notebooks.

This upload does not retrain or validate the models and does not connect them to
the Render dashboard. Notebook checkpoints, bytecode, and local environments are
excluded by `.gitignore`.
