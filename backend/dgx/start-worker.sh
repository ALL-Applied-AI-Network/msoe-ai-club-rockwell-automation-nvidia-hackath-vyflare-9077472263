#!/usr/bin/env bash
set -euo pipefail

worker_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${YAAD_WORKSPACE:-/home/yt-vyflare71b7/workspace}"
framework="${COSMOS_FRAMEWORK_DIR:-$workspace/vial-baseline/cosmos-framework}"
python="$framework/.venv/bin/python"
export PATH="$framework/.venv/bin:$PATH"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$workspace/hf/hub}"
export WANDB_MODE=disabled
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
# Match the working DGX batch environment; avoid incompatible system libraries.
export LD_LIBRARY_PATH=''
npp_dir="$($python -c 'from importlib.metadata import distribution; print(distribution("nvidia-npp").locate_file("nvidia/cu13/lib"))')"
export LD_PRELOAD="$npp_dir/libnppc.so.13:$npp_dir/libnppicc.so.13"
export PYTHONUNBUFFERED=1
cd "$framework"
exec "$python" "$worker_dir/app.py"
