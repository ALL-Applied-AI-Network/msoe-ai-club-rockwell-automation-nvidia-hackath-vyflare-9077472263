#!/usr/bin/env bash
set -euo pipefail
# Run in the configured Linux/NVIDIA Cosmos environment (e.g. YAAD Spark).
: "${COSMOS_REPO:?Set COSMOS_REPO to your Cosmos checkout on the Spark}"
input_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
package_dir="$(dirname -- "$input_dir")"
# A fresh subfolder keeps previous results; OUTPUT_DIR can override this.
output_dir="${OUTPUT_DIR:-$package_dir/output/$(date -u +%Y%m%dT%H%M%SZ)-$$}"
checkpoint="${COSMOS_CHECKPOINT:-Cosmos3-Nano}"
if [[ -x "$COSMOS_REPO/.venv/bin/python" ]]; then
  export PATH="$COSMOS_REPO/.venv/bin:$PATH"
fi
[[ -d "$COSMOS_REPO/cosmos_framework" ]] || { echo 'Invalid COSMOS_REPO' >&2; exit 1; }
[[ -f "$input_dir/clip.mp4" ]] || { echo 'Missing clip.mp4' >&2; exit 1; }
mkdir -p "$output_dir"
cp "$input_dir/recipe.labels.json" "$output_dir/recipe.labels.reference.json"
cp "$input_dir/oberservation.json" "$output_dir/input-record.json"
cp "$input_dir/observation-prompt.json" "$output_dir/prompt-record.json"
cd "$COSMOS_REPO"
if [[ -f SOURCE_COMMIT ]]; then
  cp SOURCE_COMMIT "$output_dir/cosmos-commit.txt"
else
  git rev-parse HEAD > "$output_dir/cosmos-commit.txt"
fi
export LD_LIBRARY_PATH=''
export WANDB_MODE="${WANDB_MODE:-disabled}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
# Reuse the existing YAAD weight cache without changing Hugging Face authentication.
if [[ -d /workspace/hf/hub ]]; then
  export HF_HUB_CACHE="${HF_HUB_CACHE:-/workspace/hf/hub}"
fi
npp_dir="$(python - <<'NPP'
from importlib.metadata import distribution, PackageNotFoundError
try:
    print(distribution('nvidia-npp').locate_file('nvidia/cu13/lib'))
except PackageNotFoundError:
    print('')
NPP
)"
if [[ -n "$npp_dir" && -f "$npp_dir/libnppicc.so.13" ]]; then
  export LD_PRELOAD="$npp_dir/libnppc.so.13:$npp_dir/libnppicc.so.13${LD_PRELOAD:+:$LD_PRELOAD}"
fi
python -m cosmos_framework.scripts.inference \
  --parallelism-preset=latency \
  -i "$input_dir/oberservation.json" \
  -o "$output_dir" \
  --checkpoint-path "$checkpoint" \
  --seed=0 2>&1 | tee "$output_dir/inference.log"
# Preserve raw model output, and save parsed JSON separately if it is valid.
python - "$output_dir" <<'PARSE'
import json, sys
from pathlib import Path
root=Path(sys.argv[1]); report=[]
for path in root.rglob('reasoner_text.txt'):
    raw=path.read_text().strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw=raw.split('\n',1)[1].rsplit('```',1)[0].strip()
    try:
        result=json.loads(raw)
        (path.parent/'observation-parsed.json').write_text(json.dumps(result,indent=2)+'\n')
        report.append({'file':str(path.relative_to(root)),'json_valid':True})
    except (ValueError, IndexError) as exc:
        report.append({'file':str(path.relative_to(root)),'json_valid':False,'error':str(exc)})
(root/'json-validation.json').write_text(json.dumps(report,indent=2)+'\n')
PARSE
