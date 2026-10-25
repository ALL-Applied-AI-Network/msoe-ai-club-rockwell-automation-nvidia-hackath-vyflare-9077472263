"""Adapters are loaded once by create_app; ML dependencies are optional in mock mode."""
import json
import os
import platform
import socket
import uuid
from io import BytesIO
from pathlib import Path
from urllib import error, request
from urllib.parse import urlsplit


class MockModel:
    def __init__(self, name):
        self.name = name

    def predict(self, image, prompt):
        return {"mock": True, "message": "Transport test only; no model inference.",
                "model": self.name, "image_size": list(image.size)}


class ResNet18Model:
    def __init__(self):
        import torch
        from torchvision.models import ResNet18_Weights, resnet18
        self.torch = torch
        self.device = torch.device(os.getenv("RESNET_DEVICE", "cpu"))
        weights = ResNet18_Weights.DEFAULT
        checkpoint = os.getenv("RESNET_CHECKPOINT", "")
        if checkpoint:
            labels_path = os.getenv("RESNET_LABELS", "")
            if not labels_path:
                raise ValueError("RESNET_LABELS is required for a custom checkpoint")
            self.labels = json.loads(Path(labels_path).read_text())
            if not isinstance(self.labels, list) or not self.labels or not all(
                isinstance(x, str) for x in self.labels
            ):
                raise ValueError("Labels must be a non-empty JSON array in training class order")
            self.model = resnet18(weights=None, num_classes=len(self.labels))
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
            if "state_dict" in state:
                state = state["state_dict"]
            self.model.load_state_dict(state, strict=True)
        else:
            self.labels = weights.meta["categories"]
            self.model = resnet18(weights=weights)
        # Replace this with training-time validation transforms for custom weights.
        self.transform = weights.transforms()
        self.model.to(self.device).eval()

    def predict(self, image, prompt):
        with self.torch.inference_mode():
            tensor = self.transform(image).unsqueeze(0).to(self.device)
            scores = self.model(tensor).softmax(dim=1)[0]
            values, indices = scores.topk(min(5, len(self.labels)))
            predictions = [{"label": self.labels[i], "class_id": i, "score": score}
                           for score, i in zip(values.tolist(), indices.tolist())]
        return {"predictions": predictions}


class SafetyBlocked(Exception):
    """A safety classifier declined the input or output."""


class RemoteInferenceError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class RemoteCosmosModel:
    """Forward to a persistent DGX worker using the same /predict contract."""

    def __init__(self):
        self.url = os.getenv("COSMOS_FULL_URL", "http://127.0.0.1:8001/predict")
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("COSMOS_FULL_URL must be an HTTP(S) inference URL")
        self.timeout = float(os.getenv("COSMOS_FULL_TIMEOUT_SECONDS", "120"))
        if not 0 < self.timeout <= 3600:
            raise ValueError("COSMOS_FULL_TIMEOUT_SECONDS must be in (0, 3600]")
        self.model = os.getenv("COSMOS_FULL_REMOTE_MODEL", "cosmos")
        if self.model not in {"cosmos", "cosmos_lite"}:
            raise ValueError("Remote worker model must be cosmos or cosmos_lite (local execution)")

    def predict(self, image, prompt):
        boundary = uuid.uuid4().hex
        frame_id = uuid.uuid4().hex
        chunks = []
        for name, value in {"frame_id": frame_id, "model": self.model, "prompt": prompt}.items():
            chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                           f'\r\n\r\n{value}\r\n').encode("utf-8"))
        encoded = BytesIO()
        image.save(encoded, format="JPEG")
        chunks.extend([
            (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
             'filename="frame.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode(),
            encoded.getvalue(), f'\r\n--{boundary}--\r\n'.encode(),
        ])
        outbound = request.Request(self.url, data=b"".join(chunks), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }, method="POST")
        try:
            with request.urlopen(outbound, timeout=self.timeout) as response:
                payload = json.load(response)
        except error.HTTPError as exc:
            exc.close()
            if exc.code == 422:
                raise SafetyBlocked("DGX Cosmos safety check rejected this request") from exc
            if exc.code == 429:
                raise RemoteInferenceError("DGX Cosmos is busy; skip this frame", 429) from exc
            raise RemoteInferenceError("DGX Cosmos inference failed") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RemoteInferenceError("DGX Cosmos request timed out", 504) from exc
        except error.URLError as exc:
            status = 504 if isinstance(exc.reason, (TimeoutError, socket.timeout)) else 503
            raise RemoteInferenceError("DGX Cosmos is unavailable", status) from exc
        except (ValueError, OSError) as exc:
            raise RemoteInferenceError("DGX Cosmos returned an invalid response") from exc
        if (not isinstance(payload, dict) or payload.get("frame_id") != frame_id
                or payload.get("model") != self.model or payload.get("mode") != "real"
                or not isinstance(payload.get("result"), dict)
                or payload["result"].get("mock")
                or not isinstance(payload["result"].get("text"), str)):
            raise RemoteInferenceError("DGX Cosmos returned an invalid or non-real result")
        execution = payload["result"].get("execution")
        if (not isinstance(execution, dict)
                or execution.get("system") != "Linux"
                or execution.get("machine") != "aarch64"
                or execution.get("gpu") != "NVIDIA GB10"):
            raise RemoteInferenceError("Full Cosmos requires a DGX Spark GB10 worker")
        return payload["result"]


class Cosmos3Model:
    """Single-GPU Cosmos Framework adapter; integration requires GPU validation."""
    def __init__(self):
        import tempfile
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("Cosmos3-Nano requires the Linux/CUDA Cosmos Framework environment")
        self.execution = {"hostname": socket.gethostname(), "system": platform.system(),
                          "machine": platform.machine(),
                          "gpu": torch.cuda.get_device_name(torch.cuda.current_device())}
        from cosmos_framework.inference.common.init import init_script
        init_script()
        from cosmos_framework.inference.args import OmniSetupOverrides, reasoner_only_overrides
        self.work = tempfile.TemporaryDirectory(prefix="cosmos-api-")
        self.root = Path(self.work.name)
        self.setup = OmniSetupOverrides(
            checkpoint_path=os.getenv("COSMOS_CHECKPOINT", "Cosmos3-Nano"),
            output_dir=self.root, guardrails=True,
            offload_guardrail_models=True, parallelism_preset="latency",
        ).build_setup()
        self.setup.experiment_overrides.extend(reasoner_only_overrides())
        # Retain the visual guardrail to explicitly screen uploaded frames below.
        self.pipe = self.setup.get_inference_cls().create(self.setup)
        if self.pipe.guardrails is None or self.pipe.guardrails.video is None:
            raise RuntimeError("Cosmos text and visual guardrails must be loaded")
        self.max_tokens = int(os.getenv("COSMOS_MAX_NEW_TOKENS", "256"))
        if not 1 <= self.max_tokens <= 4096:
            raise ValueError("COSMOS_MAX_NEW_TOKENS must be between 1 and 4096")

    def predict(self, image, prompt):
        import tempfile
        import numpy as np
        from PIL import Image
        from cosmos_framework.auxiliary.guardrail.common import presets
        # Fail closed: exceptions propagate; rejected content never reaches Cosmos.
        if not presets.run_text_guardrail(prompt, self.pipe.guardrails.text):
            raise SafetyBlocked("Prompt rejected by text safety check")
        frames = np.asarray(image)[None, ...].copy()
        safe, _ = self.pipe.guardrails.video.run_safety_check(frames)
        if not safe:
            raise SafetyBlocked("Image rejected by visual safety check")
        frames = self.pipe.guardrails.video.postprocess(frames)
        with tempfile.TemporaryDirectory(dir=self.root, prefix="frame-") as folder:
            folder = Path(folder)
            image_path = folder / "input.png"
            Image.fromarray(frames[0]).save(image_path)
            spec = folder / "sample.json"
            spec.write_text(json.dumps({
                "name": "frame", "model_mode": "reasoner", "prompt": prompt,
                "vision_path": str(image_path), "max_new_tokens": self.max_tokens,
                "do_sample": False,
            }))
            overrides = self.setup.get_sample_overrides_cls().from_files([spec])[0]
            overrides.output_dir = folder / "result"
            overrides.output_dir.mkdir()
            sample = overrides.build_sample(model_config=self.pipe.model_config)
            receipts = self.pipe.generate([sample])
            if len(receipts) != 1 or receipts[0].status != "success":
                raise RuntimeError("Cosmos returned no successful, screened result")
            text = receipts[0].outputs[0].content["reasoner_text"]
            # Explicit output check, even if an upstream version changes its defaults.
            if not presets.run_text_guardrail(text, self.pipe.guardrails.text):
                raise SafetyBlocked("Response rejected by text safety check")
            return {"text": text, "execution": self.execution, "safety": {
                "input_text": "passed", "input_image": "passed", "output_text": "passed",
                "provider": "Cosmos Framework (Cosmos-Guardrail1 / Qwen3Guard)",
            }}


def load_models(mode):
    names = [x.strip() for x in os.getenv("ENABLED_MODELS", "resnet18,cosmos_lite,cosmos_full").split(",")]
    factories = {"resnet18": ResNet18Model, "cosmos": Cosmos3Model,
                 "cosmos_lite": Cosmos3Model, "cosmos_full": RemoteCosmosModel}
    if not names or any(name not in factories for name in names):
        raise ValueError("ENABLED_MODELS supports resnet18, cosmos_lite, cosmos_full, cosmos")
    if mode == "mock":
        return {name: MockModel(name) for name in names}
    if mode != "real":
        raise ValueError("MODEL_MODE must be mock or real")
    # Fail startup on bad weights/dependencies; never silently switch to fake results.
    return {name: factories[name]() for name in names}
