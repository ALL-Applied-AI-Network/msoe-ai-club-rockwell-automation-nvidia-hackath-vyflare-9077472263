"""Post included reference frames to a running API using the Python standard library."""
import argparse
import io
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

import numpy as np
from PIL import Image


def payload(fixture):
    folder = Path(__file__).resolve().parents[1] / "tests/fixtures/model4"
    oracle = json.loads((folder / "oracle.json").read_text())
    transition = fixture == "transition"
    fields = {"frame_id": "example-fill", "vial_id": "example-vial", "batch_id": "example-batch",
              "batch_position": "1" if transition else "2", "camera_profile": "vial-fill-640x480",
              "recipe_id": "99" if transition else "6"}
    files = []
    with np.load(folder / "registered_frames.npz", allow_pickle=False) as frames:
        def image(field, key):
            data = io.BytesIO(); Image.fromarray(frames[key]).save(data, "PNG")
            files.append((field, key + ".png", data.getvalue()))
        for i in range(1, 4):
            image("images", ("transition_post_" if transition else "post_") + str(i))
        if transition:
            fields["events"] = json.dumps([{"event_number": 1, "duration_s": oracle["transition_duration_s"]}])
            image("event_1_before", "transition_before")
            image("event_1_during", "transition_during")
    boundary = "model4-" + uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    for field, filename, data in files:
        parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode(), data, b"\r\n"])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def send(url, fixture="transition"):
    body, content_type = payload(fixture)
    headers = {"Content-Type": content_type}
    token = os.getenv("INFERENCE_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url.rstrip("/") + "/predict/model4", data=body, headers=headers, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.load(response)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--fixture", choices=["normal", "transition"], default="transition")
    args = parser.parse_args()
    print(json.dumps(send(args.url, args.fixture), indent=2))
