#!/usr/bin/env bash
set -euo pipefail
base=/workspace/vial-baseline
batch=$base/clip-test-20261025
mkdir "$batch"
tar -xzf "$base/vyflare-clips-20261025.tar.gz" -C "$batch"
repo=$base/cosmos-framework
export PATH="$repo/.venv/bin:$PATH"
export LD_LIBRARY_PATH=''
export HF_HUB_CACHE=/workspace/hf/hub
export WANDB_MODE=disabled
export OMP_NUM_THREADS=4
npp_dir="$(python -c 'from importlib.metadata import distribution; print(distribution("nvidia-npp").locate_file("nvidia/cu13/lib"))')"
export LD_PRELOAD="$npp_dir/libnppc.so.13:$npp_dir/libnppicc.so.13"
cd "$repo"
python -m cosmos_framework.scripts.inference --parallelism-preset=latency -i "$batch"/cosmos-model-data/*/input/oberservation.json -o "$batch/results" --checkpoint-path Cosmos3-Nano --seed=0 --keep-going 2>&1 | tee "$batch/inference.log"
