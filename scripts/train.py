"""Validate local inputs and launch the pinned native Cosmos3 reasoner trainer."""
import argparse
import json
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from prepare_data import validate_records

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--data", type=Path, default=ROOT / "data/local")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/vial_reasoner.toml")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        framework, checkpoint, data = (p.resolve() for p in (args.framework, args.checkpoint, args.data))
        revision = (ROOT / "framework-revision.txt").read_text().strip()
        head = subprocess.check_output(["git", "-C", str(framework), "rev-parse", "HEAD"], text=True).strip()
        if head != revision:
            raise ValueError(f"Framework revision mismatch; expected {revision}, found {head}")
        config = tomllib.loads(args.config.read_text())
        gpu_count = config["model"]["parallelism"]["data_parallel_shard_degree"]
        if not isinstance(gpu_count, int) or gpu_count < 1:
            raise ValueError("Set an explicit positive FSDP shard degree in the recipe")
        for name in ("config.json", "tokenizer_config.json", "preprocessor_config.json"):
            if not (checkpoint / name).is_file():
                raise ValueError(f"Missing converted reasoner artifact: {checkpoint / name}")
        if not list(checkpoint.glob("*.safetensors")):
            raise ValueError("Converted Cosmos3-Nano safetensors not found")
        rows = [json.loads(line) for line in (data / "annotations.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        expected = validate_records(rows, data)
        for split in ("train", "val"):
            actual = json.loads((data / f"{split}.json").read_text())
            if actual != expected[split]:
                raise ValueError("Built data is stale; rerun prepare_data.py build")
        print(f"Preflight passed: pinned Framework, converted weights, {len(expected['train'])} train / {len(expected['val'])} val videos.")
        if args.check_only:
            print("This checks files/data contracts; GPU runtime and model loading are not tested.")
            return
        if sys.platform != "linux":
            raise ValueError("Training requires the Framework Linux/CUDA environment")
        env = os.environ.copy()
        for split in ("train", "val"):
            prefix = "COSMOS_VIDEO_" + split.upper()
            env[prefix + "_ANNOTATION"] = str(data / f"{split}.json")
            env[prefix + "_MEDIA"] = str(data)
            env[prefix + "_LIMIT"] = ""
        env["VLM_SAFETENSORS_PATH"] = str(checkpoint)
        # 32 uniform frames over 27 s ~1.2 fps. For rapid events, shorten clips or increase the budget.
        env.setdefault("COSMOS_VIDEO_NUM_FRAMES", "32")
        env.setdefault("COSMOS_VIDEO_MAX_PIXELS", "153600")
        env.setdefault("COSMOS_VIDEO_DECODER_DEVICE", "cpu")
        env["IMAGINAIRE_OUTPUT_ROOT"] = str(args.output.resolve())
        env["PYTHONPATH"] = str(framework) + os.pathsep + env.get("PYTHONPATH", "")
        run_name = datetime.now(timezone.utc).strftime("nano_%Y%m%dT%H%M%S_%fZ")
        command = [sys.executable, "-m", "torch.distributed.run", "--standalone",
                   f"--nproc_per_node={gpu_count}", "-m", "cosmos_framework.scripts.train",
                   f"--sft-toml={args.config.resolve()}", "--", f"job.name={run_name}"]
        subprocess.run(command, cwd=framework, env=env, check=True)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
