"""Model 2 recipe-resemblance classifier: supporting evidence only, never a release."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np

CAMERA_PROFILE = "vial-fill-640x480"
FEATURES = 512


def stream_scores(rgb):
    """Training frame-QC rule (frame_qc.py); channel order does not affect either score."""
    roi = rgb[90:145].astype(np.float32)
    center = roi[:, 305:316].mean(axis=(0, 1))
    side = np.concatenate([roi[:, 288:298], roi[:, 323:333]], axis=1).mean(axis=(0, 1))
    profile = roi[:, 295:326].mean(axis=0)
    return float(np.abs(center - side).sum()), float(np.abs(profile - np.median(profile, axis=0)).sum(axis=1).max())


def assess(observation, *, intended_recipe_id, batch_position, supported, approved, input_ok):
    """Compare an observation with the intended recipe. Never clears a flag or releases a vial."""
    flags = ["expected_transition_contamination"] if batch_position == 1 else []
    intended_supported = intended_recipe_id in supported
    if observation is None:
        relation = "no_inference"
    elif not input_ok:
        relation = "abstained_input_rejected"
    elif observation["status"] != "accepted_observation":
        relation = "abstained"
    elif not intended_supported:
        # A known-class resemblance cannot verify a recipe the model was never trained on.
        relation = "intended_recipe_unsupported"
    elif observation["predicted_recipe_id"] == intended_recipe_id:
        relation = "matches_intended_recipe"
    else:
        relation = "recipe_disagreement"
        flags.append("recipe_disagreement")
    counts = relation == "matches_intended_recipe" and approved
    if relation == "matches_intended_recipe" and not approved:
        note = "Match recorded but not counted: this checkpoint is not approved as supporting evidence"
    elif counts:
        note = "Supporting evidence only; other checks and review still apply"
    else:
        note = "No supporting evidence from Model 2; other checks continue"
    return {"intended_recipe_id": intended_recipe_id, "intended_recipe_supported": intended_supported,
            "relation": relation, "counts_as_supporting_evidence": counts, "note": note, "flags": flags,
            "review_required": True, "automatic_release": False, "can_clear_other_flags": False}


class Model2Model:
    def __init__(self, *, mock=False, assets=None, backbone_weights=None):
        self.mock = mock
        root = Path(assets) if assets else Path(__file__).with_name("model2_assets")
        self.manifest = json.loads((root / "manifest.json").read_text())
        data = (root / "head.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != self.manifest["sha256"]["head.json"]:
            raise ValueError("Model 2 asset integrity check failed: head.json")
        head = json.loads(data)
        classes = head["classes"]
        if (not classes or len(set(classes)) != len(classes)
                or not all(isinstance(c, str) and c.isdigit() and int(c) > 0 for c in classes)):
            raise ValueError("Model 2 classes must be unique positive recipe IDs")
        self.classes = [int(c) for c in classes]
        self.coef = np.array(head["coef"], dtype=np.float64)
        self.intercept = np.array(head["intercept"], dtype=np.float64)
        self.mean = np.array(head["scaler_mean"], dtype=np.float64)
        self.scale = np.array(head["scaler_scale"], dtype=np.float64)
        k = len(classes)
        for name, array, shape in (("coef", self.coef, (k, FEATURES)), ("intercept", self.intercept, (k,)),
                                   ("scaler_mean", self.mean, (FEATURES,)), ("scaler_scale", self.scale, (FEATURES,))):
            if array.shape != shape or not np.isfinite(array).all():
                raise ValueError(f"Invalid packaged {name}")
        if (self.scale <= 0).any():
            raise ValueError("Invalid packaged scaler scale")
        self.threshold = float(head["accept_threshold"])
        if not 0 < self.threshold < 1 or head["calibrated"] is not False:
            raise ValueError("Unexpected Model 2 threshold or calibration contract")
        self.pre = head["preprocessing"]
        if self.pre.get("version") != "station-crop-v1":
            raise ValueError("Unknown Model 2 preprocessing version")
        self.head = head
        self.approved = self.manifest.get("approved_for_supporting_evidence") is True
        self.stream_rule = self.manifest["stream_rule"]
        self.net = None
        if not mock:
            self._load_backbone(backbone_weights or os.getenv("MODEL2_BACKBONE_WEIGHTS"))

    def _load_backbone(self, path):
        import torch
        import torchvision
        url = self.head["backbone_weights_url"]
        if not path:
            path = Path(torch.hub.get_dir()) / "checkpoints" / os.path.basename(url)
            if not path.exists():
                torch.hub.load_state_dict_from_url(url, map_location="cpu", check_hash=True)
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != self.head["backbone_sha256"]:
            raise ValueError("Model 2 backbone weights do not match the trained backbone hash")
        net = torchvision.models.resnet18(weights=None)
        net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        net.fc = torch.nn.Identity()
        self.net = net.eval()
        for p in self.net.parameters():
            p.requires_grad_(False)
        self._torch = torch

    def describe(self):
        return {"model_id": self.manifest["model_id"], "head_sha256": self.manifest["sha256"]["head.json"],
                "config_version": self.head["config_version"], "preprocessing_version": self.pre["version"],
                "calibrated": False, "calibration_version": None, "classes_in_head_order": self.classes,
                "supported_recipe_ids": sorted(self.classes), "accept_threshold": self.threshold,
                "score_semantics": self.head["score_semantics"], "backbone_sha256": self.head["backbone_sha256"],
                "camera_profile": CAMERA_PROFILE, "image_size": [640, 480],
                "frames_required": self.manifest["frames_required"],
                "approved_for_supporting_evidence": self.approved, "validation": self.manifest["validation"],
                "automatic_release": False, "mock": self.mock}

    def _stream_visible(self, rgb):
        center, profile = stream_scores(rgb)
        return center >= self.stream_rule["center_limit"] or profile >= self.stream_rule["profile_limit"]

    def _input(self, rgb):
        import cv2
        pre = self.pre
        fill = np.array(pre["letterbox_fill_rgb"], dtype=np.uint8)
        rgb = rgb.copy()
        rgb[pre["overlay_mask_rows_from"]:] = fill
        x0, y0, x1, y1 = pre["crop_xyxy"]
        img = rgb[y0:y1, x0:x1]
        h, w = img.shape[:2]
        s = max(h, w)
        canvas = np.empty((s, s, 3), np.uint8)
        canvas[:] = fill
        canvas[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = img
        return cv2.resize(canvas, tuple(pre["resize"]), interpolation=cv2.INTER_AREA)

    def _frame_probabilities(self, rgbs):
        torch = self._torch
        x = torch.from_numpy(np.stack([self._input(r) for r in rgbs])).permute(0, 3, 1, 2).float() / 255.0
        x = (x - torch.tensor(self.pre["normalize_mean"]).view(1, 3, 1, 1)) / torch.tensor(self.pre["normalize_std"]).view(1, 3, 1, 1)
        with torch.no_grad():
            feats = self.net(x).numpy().astype(np.float64)
        logits = ((feats - self.mean) / self.scale) @ self.coef.T + self.intercept
        probs = np.exp(logits - logits.max(axis=1, keepdims=True))
        return probs / probs.sum(axis=1, keepdims=True)

    def predict_vial(self, images, *, intended_recipe_id, batch_position):
        if isinstance(batch_position, bool) or not isinstance(batch_position, int) or batch_position < 1:
            raise ValueError("batch_position must be a positive integer")
        if isinstance(intended_recipe_id, bool) or not isinstance(intended_recipe_id, int) or intended_recipe_id < 1:
            raise ValueError("recipe_id must be a positive integer")
        if len(images) != 3:
            raise ValueError("Exactly three early post-flow images are required")
        rgbs = []
        for image in images:
            if image.size != (640, 480):
                raise ValueError("Model 2 requires registered 640x480 frames; images are not resized")
            rgbs.append(np.asarray(image.convert("RGB"), dtype=np.uint8))
        streams = [i for i, r in enumerate(rgbs) if self._stream_visible(r)]
        warnings = [f"liquid stream visible in frame {i + 1}: not an early post-flow frame" for i in streams]
        observation = None
        if not self.mock:
            # The intended recipe and batch metadata are never inputs to the classifier.
            probs = self._frame_probabilities(rgbs)
            mean = probs.mean(axis=0)
            order = np.argsort(mean)[::-1]
            top = float(mean[order[0]])
            observation = {
                "predicted_recipe_id": self.classes[order[0]], "top_score": round(top, 6),
                "second_recipe_id": self.classes[order[1]], "second_score": round(float(mean[order[1]]), 6),
                "status": "accepted_observation" if top >= self.threshold and not streams else "unknown_uncertain",
                "score_calibrated": False,
                "per_frame": [{"top_recipe_id": self.classes[int(p.argmax())], "top_score": round(float(p.max()), 6)} for p in probs],
                "scores": {str(c): round(float(s), 6) for c, s in zip(self.classes, mean)},
            }
        result = {"observation": observation,
                  "verification": assess(observation, intended_recipe_id=intended_recipe_id, batch_position=batch_position,
                                         supported=set(self.classes), approved=self.approved, input_ok=not streams),
                  "input_quality": {"stream_visible_frames": [i + 1 for i in streams], "warnings": warnings},
                  "model_metadata": self.describe(),
                  "interpretation": ("Which supported recipe the vial visually resembles. Not a quality judgement, "
                                     "not a measured composition, and not a probability of correctness.")}
        if self.mock:
            result.update(mock=True, message="Transport test only; no recipe inference.")
        return result
