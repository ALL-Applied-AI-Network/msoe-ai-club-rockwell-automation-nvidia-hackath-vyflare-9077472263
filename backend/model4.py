"""Frozen mixture-estimation checkpoint and a separately reported challenger."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

TANKS = ("T100", "T200", "T400")
CAMERA_PROFILE = "vial-fill-640x480"


def simplex(values):
    values = np.atleast_2d(values)
    ordered = np.sort(values, axis=1)[:, ::-1]
    cumulative = ordered.cumsum(axis=1) - 1
    count = np.arange(1, values.shape[1] + 1)
    index = (ordered - cumulative / count > 0).sum(axis=1) - 1
    offset = cumulative[np.arange(len(values)), index] / (index + 1)
    return np.maximum(values - offset[:, None], 0)


def finite_array(value, shape, name):
    array = np.array(value, dtype=float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"Invalid packaged {name}")
    return array


def proportions(values):
    return dict(zip(TANKS, (float(x) for x in values)))


class Model4Model:
    def __init__(self, *, mock=False, assets=None):
        self.mock = mock
        root = Path(assets) if assets else Path(__file__).with_name("model4_assets")
        self.manifest = json.loads((root / "manifest.json").read_text())
        contents = {}
        for filename in ("checkpoint.json", "stream_challenger.json", "recipes.json"):
            data = (root / filename).read_bytes()
            if hashlib.sha256(data).hexdigest() != self.manifest["sha256"][filename]:
                raise ValueError(f"Model 4 asset integrity check failed: {filename}")
            contents[filename] = json.loads(data)
        self.checkpoint = contents["checkpoint.json"]
        self.challenger = contents["stream_challenger.json"]
        self.catalog = contents["recipes.json"]
        cp, challenger = self.checkpoint, self.challenger
        if cp["output_order"] != ["r100", "r200", "r400"] or cp["selected_config"]["family"] != "kernel_ridge":
            raise ValueError("Unexpected Model 4 checkpoint contract")
        n = len(cp["training_vials"])
        finite_array(cp["training_features_scaled"], (n, 3), "kernel centers")
        finite_array(cp["dual_coefficients"], (n, 3), "kernel coefficients")
        for key in ("feature_mean", "feature_scale", "target_mean"):
            finite_array(cp[key], (3,), key)
        if min(cp["feature_scale"]) <= 0 or not math.isfinite(cp["gamma"]) or cp["gamma"] <= 0:
            raise ValueError("Invalid checkpoint scale or kernel")
        if challenger["family"] != "ridge" or challenger["feature_variant"] != "final_stream_changes":
            raise ValueError("Unexpected stream challenger contract")
        for key in ("imputation_medians", "feature_mean", "feature_scale", "ridge_feature_mean"):
            finite_array(challenger[key], (21,), key)
        finite_array(challenger["coefficients"], (21, 3), "stream coefficients")
        finite_array(challenger["target_mean"], (3,), "stream target mean")
        if min(challenger["feature_scale"]) <= 0:
            raise ValueError("Invalid challenger scale")
        for recipe in self.catalog["recipes"].values():
            self._amounts(recipe["amounts_ml"])
        # Used only to expose extrapolation, never to force estimates toward a recipe.
        training = np.array(cp["training_features_scaled"]) * np.array(cp["feature_scale"]) + np.array(cp["feature_mean"])
        self.feature_bounds = (training.min(0), training.max(0))

    @staticmethod
    def _amounts(value):
        if not isinstance(value, dict) or set(value) != set(TANKS):
            raise ValueError("expected_ml must contain exactly T100, T200 and T400")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in value.values()):
            raise ValueError("Expected amounts must be numbers")
        try:
            amounts = np.array([float(value[k]) for k in TANKS])
        except (OverflowError, ValueError):
            raise ValueError("Expected amounts must be finite") from None
        if not np.isfinite(amounts).all() or (amounts < 0).any():
            raise ValueError("Expected amounts must be finite, nonnegative and have a positive total")
        try:
            total = math.fsum(amounts)
        except OverflowError:
            raise ValueError("Expected amount total must be finite") from None
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Expected amounts must be finite, nonnegative and have a positive total")
        return amounts, total

    def expected_recipe(self, recipe_id=None, expected_ml=None):
        if (recipe_id is None) == (expected_ml is None):
            raise ValueError("Supply exactly one of recipe_id or expected_ml")
        if recipe_id is not None:
            if isinstance(recipe_id, bool) or not isinstance(recipe_id, int) or recipe_id <= 0:
                raise ValueError("recipe_id must be a positive integer")
            recipe = self.catalog["recipes"].get(str(recipe_id))
            if recipe is None:
                raise ValueError("Unknown Model 4 recipe ID")
            expected_ml = recipe["amounts_ml"]
        amounts, total = self._amounts(expected_ml)
        return {"recipe_id": recipe_id, "amounts_ml": proportions(amounts), "total_ml": total,
                "proportions": proportions(amounts / total), "basis": "recipe_settings_not_measured_delivery",
                "source": "recipes.xlsx/Recipe_Bank snapshot" if recipe_id is not None else "request_expected_ml",
                "catalog_sha256": self.manifest["sha256"]["recipes.json"] if recipe_id is not None else None}

    def describe(self):
        return {"checkpoint_id": self.manifest["checkpoint_id"],
                "checkpoint_sha256": self.manifest["sha256"]["checkpoint.json"],
                "challenger_id": self.manifest["challenger_id"],
                "challenger_sha256": self.manifest["sha256"]["stream_challenger.json"],
                "camera_profile": CAMERA_PROFILE, "image_size": [640, 480],
                "post_fill_frames_required": 3, "challenger_requires": "before/during frames for 1–3 chronological observed pours",
                "default_model": "frozen_checkpoint", "challenger_promoted": False,
                "automatic_release": False, "mock": self.mock}

    @staticmethod
    def _pixels(image):
        if image.size != (640, 480):
            raise ValueError("Model 4 requires registered 640x480 frames; images are not resized")
        return np.asarray(image.convert("RGB"), dtype=float)

    def _final_features(self, images):
        if len(images) != 3:
            raise ValueError("Exactly three post-fill images are required")
        values = []
        for image in images:
            rgb = np.median(self._pixels(image)[370:394, 299:325].reshape(-1, 3), axis=0)
            values.append(-np.log10(np.clip(rgb / 255, 1e-3, 1)))
        return np.median(values, axis=0)

    def _stream_features(self, final, events):
        if not 1 <= len(events) <= 3:
            raise ValueError("The challenger requires 1–3 observed events")
        presence, missing, changes = [], [], []
        for index in range(3):
            if index >= len(events):
                presence.append(0); missing.extend([0, 0]); changes.extend([0.0] * 3)
                continue
            event = events[index]
            duration = event["duration_s"]
            if duration is not None and (isinstance(duration, bool) or not isinstance(duration, (int, float))
                                         or not math.isfinite(duration) or duration <= 0):
                raise ValueError("Observed duration_s must be positive and finite, or null when unknown")
            during = self._pixels(event["during"])[88:145, 304:316].mean(axis=(0, 1)) / 255
            before = event["before"]
            presence.append(1); missing.extend([int(duration is None), int(before is None)])
            if before is None:
                changes.extend([float("nan")] * 3)
            else:
                reference = self._pixels(before)[88:145, 304:316].mean(axis=(0, 1)) / 255
                changes.extend((during - reference).tolist())
        return np.array(final.tolist() + presence + missing + changes)

    def _checkpoint_predict(self, final):
        model = self.checkpoint
        z = (final - np.array(model["feature_mean"])) / np.array(model["feature_scale"])
        delta = z[None, :] - np.array(model["training_features_scaled"])
        kernel = np.exp(-model["gamma"] * np.sum(delta * delta, axis=1))
        estimate = np.einsum("i,ij->j", kernel, np.array(model["dual_coefficients"]), optimize=False) + np.array(model["target_mean"])
        return simplex(estimate)[0]

    def _challenger_predict(self, values):
        model = self.challenger
        values = np.where(np.isnan(values), np.array(model["imputation_medians"]), values)
        z = (values - np.array(model["feature_mean"])) / np.array(model["feature_scale"])
        estimate = np.einsum("i,ij->j", z - np.array(model["ridge_feature_mean"]), np.array(model["coefficients"]), optimize=False) + np.array(model["target_mean"])
        return simplex(estimate)[0]

    @staticmethod
    def _comparison(estimate, target):
        if not np.isfinite(estimate).all():
            raise RuntimeError("Nonfinite mixture estimate")
        difference = (estimate - target) * 100
        return {"estimated_proportions": proportions(estimate), "estimated_percentages": proportions(estimate * 100),
                "signed_difference_percentage_points": proportions(difference),
                "absolute_difference_percentage_points": proportions(np.abs(difference)),
                "mean_dye_difference_percentage_points": float(np.abs(difference[1:]).mean())}

    def predict_vial(self, images, *, expected, batch_position, events=None):
        if isinstance(batch_position, bool) or not isinstance(batch_position, int) or batch_position < 1:
            raise ValueError("batch_position must be a positive integer")
        final = self._final_features(images)
        stream_values = self._stream_features(final, events) if events is not None else None
        review = {"required": True, "status": "expected_transition_contamination" if batch_position == 1 else "needs_review",
                  "expected_transition_contamination": batch_position == 1, "automatic_release": False,
                  "rule_basis": "first vial of batch: user-confirmed expected system carryover",
                  "retained_mean_dye_difference_percentage_points": None}
        result = {"expected": expected, "checkpoint": None,
                  "stream_color_comparison": {"available": False, "promoted": False,
                                              "reason": "observed_event_frames_not_supplied" if events is None else "mock_mode"},
                  "review": review, "model_metadata": self.describe(),
                  "interpretation": "Estimated fractions versus intended recipe settings; actual delivered composition is unmeasured."}
        if self.mock:
            result.update(mock=True, message="Transport test only; no mixture inference.")
            return result
        # Intended proportions and batch metadata are not passed to either predictor.
        target = np.array([expected["proportions"][k] for k in TANKS])
        baseline = self._checkpoint_predict(final)
        result["checkpoint"] = self._comparison(baseline, target)
        result["checkpoint"]["feature_extrapolation"] = bool(((final < self.feature_bounds[0]) | (final > self.feature_bounds[1])).any())
        retained = result["checkpoint"]["mean_dye_difference_percentage_points"]
        if stream_values is not None:
            challenger = self._challenger_predict(stream_values)
            comparison = self._comparison(challenger, target)
            comparison.update(available=True, promoted=False,
                              mean_dye_disagreement_percentage_points=float(np.abs(baseline[1:] - challenger[1:]).mean() * 100))
            result["stream_color_comparison"] = comparison
            retained = max(retained, comparison["mean_dye_difference_percentage_points"])
        review["retained_mean_dye_difference_percentage_points"] = retained
        review["difference_interpretation"] = "Conservative review signal; no calibrated defect or release threshold."
        return result

    def predict(self, image, prompt):
        raise ValueError("Use POST /predict/model4 with three registered post-fill frames")
