"""Command-line inference: one vial -> JSON in the integration contract.

Usage:
  python scripts/predict.py --empty empty.png --finished f1.png [f2.png ...] \
      --run-id RUN-1 --vial-id VIAL-43 --frame-id f-1287 --captured-at 52.1 [--black-floor 15]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model3.inference import Model3Composition  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--empty", required=True)
ap.add_argument("--finished", nargs="+", required=True)
ap.add_argument("--run-id", required=True)
ap.add_argument("--vial-id", required=True)
ap.add_argument("--frame-id", required=True)
ap.add_argument("--captured-at", type=float, required=True, help="capture time, caller's clock (seconds)")
ap.add_argument("--black-floor", type=float, default=None, help="camera black floor, sRGB (default: config)")
a = ap.parse_args()
m = Model3Composition(black_floor_srgb=a.black_floor)
print(json.dumps(m.predict_vial(a.empty, a.finished, run_id=a.run_id, vial_id=a.vial_id,
                                frame_id=a.frame_id, captured_at=a.captured_at), indent=2))
