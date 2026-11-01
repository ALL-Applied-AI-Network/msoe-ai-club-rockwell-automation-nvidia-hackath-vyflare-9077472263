import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from flask.testing import FlaskClient

from app import create_app
from model2 import Model2Model, assess
from model4 import Model4Model

FIXTURES = Path(__file__).parent / "fixtures/model2"
ASSETS = Path(__file__).resolve().parents[1] / "model2_assets"


def cached_backbone():
    """Locally cached ImageNet ResNet18 weights; real-inference tests skip without them."""
    explicit = os.getenv("MODEL2_BACKBONE_WEIGHTS")
    if explicit:
        return explicit
    try:
        import torch
    except ImportError:
        return None
    name = "resnet18-f37072fd.pth"
    for root in (Path(torch.hub.get_dir()), Path.home() / ".cache/torch/hub", Path(__file__).resolve().parents[1] / ".model-cache/hub"):
        if (root / "checkpoints" / name).exists():
            return str(root / "checkpoints" / name)
    return None


class ClosingClient(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs["buffered"] = True
        response = super().open(*args, **kwargs)
        response.request.input_stream.close()
        return response


class AssessTests(unittest.TestCase):
    SUPPORTED = {5, 41, 60, 99}

    def obs(self, recipe, status="accepted_observation"):
        return {"predicted_recipe_id": recipe, "status": status}

    def run_assess(self, observation, intended=41, position=2, approved=True, input_ok=True):
        return assess(observation, intended_recipe_id=intended, batch_position=position, supported=self.SUPPORTED,
                      approved=approved, input_ok=input_ok)

    def test_review_is_always_required_and_nothing_is_released_or_cleared(self):
        for observation in (self.obs(41), self.obs(99), self.obs(41, "unknown_uncertain"), None):
            for position in (1, 2):
                v = self.run_assess(observation, position=position)
                self.assertTrue(v["review_required"])
                self.assertFalse(v["automatic_release"])
                self.assertFalse(v["can_clear_other_flags"])

    def test_match_counts_only_when_checkpoint_is_approved(self):
        self.assertTrue(self.run_assess(self.obs(41))["counts_as_supporting_evidence"])
        v = self.run_assess(self.obs(41), approved=False)
        self.assertEqual(v["relation"], "matches_intended_recipe")
        self.assertFalse(v["counts_as_supporting_evidence"])

    def test_disagreement_stays_visible(self):
        v = self.run_assess(self.obs(99))
        self.assertEqual(v["relation"], "recipe_disagreement")
        self.assertIn("recipe_disagreement", v["flags"])
        self.assertFalse(v["counts_as_supporting_evidence"])

    def test_uncertain_abstains(self):
        v = self.run_assess(self.obs(41, "unknown_uncertain"))
        self.assertEqual(v["relation"], "abstained")
        self.assertEqual(v["flags"], [])
        self.assertFalse(v["counts_as_supporting_evidence"])

    def test_first_vial_flag_survives_a_confident_match(self):
        v = self.run_assess(self.obs(41), position=1)
        self.assertIn("expected_transition_contamination", v["flags"])
        self.assertTrue(v["review_required"])

    def test_unsupported_intended_recipe_is_not_verified(self):
        v = self.run_assess(self.obs(41), intended=1)
        self.assertEqual(v["relation"], "intended_recipe_unsupported")
        self.assertFalse(v["intended_recipe_supported"])
        self.assertFalse(v["counts_as_supporting_evidence"])
        self.assertNotIn("recipe_disagreement", v["flags"])

    def test_rejected_input_abstains_even_when_scores_match(self):
        v = self.run_assess(self.obs(41), input_ok=False)
        self.assertEqual(v["relation"], "abstained_input_rejected")
        self.assertFalse(v["counts_as_supporting_evidence"])


class Model2AssetTests(unittest.TestCase):
    def copy_assets(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        for name in ("head.json", "manifest.json"):
            shutil.copyfile(ASSETS / name, root / name)
        return root

    def test_tampered_head_fails_loading(self):
        root = self.copy_assets()
        data = (root / "head.json").read_bytes()
        (root / "head.json").write_bytes(data.replace(b'"accept_threshold": 0.9', b'"accept_threshold": 0.5'))
        with self.assertRaisesRegex(ValueError, "integrity"):
            Model2Model(mock=True, assets=root)

    def test_wrong_backbone_weights_fail_loading(self):
        root = self.copy_assets()
        weights = root / "other.pth"
        weights.write_bytes(b"not the trained backbone")
        with self.assertRaisesRegex(ValueError, "backbone"):
            Model2Model(assets=root, backbone_weights=weights)

    def test_mock_mode_never_returns_scores(self):
        model = Model2Model(mock=True)
        image = Image.new("RGB", (640, 480), (200, 200, 200))
        result = model.predict_vial([image] * 3, intended_recipe_id=41, batch_position=1)
        self.assertIsNone(result["observation"])
        self.assertTrue(result["mock"])
        self.assertEqual(result["verification"]["relation"], "no_inference")
        self.assertIn("expected_transition_contamination", result["verification"]["flags"])

    def test_metadata_exposes_versions_and_uncalibrated_scores(self):
        meta = Model2Model(mock=True).describe()
        self.assertFalse(meta["calibrated"])
        self.assertIsNone(meta["calibration_version"])
        self.assertEqual(meta["preprocessing_version"], "station-crop-v1")
        self.assertEqual(meta["supported_recipe_ids"], [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 41, 50, 60, 99])
        self.assertFalse(meta["approved_for_supporting_evidence"])
        self.assertFalse(meta["automatic_release"])


@unittest.skipUnless(cached_backbone(), "ImageNet ResNet18 weights not cached; set MODEL2_BACKBONE_WEIGHTS")
class Model2APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model2Model(backbone_weights=cached_backbone())
        cls.frames = np.load(FIXTURES / "frames.npz", allow_pickle=False)
        cls.oracle = json.loads((FIXTURES / "oracle.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.frames.close()

    def setUp(self):
        self.model.approved = False
        self.model4 = Model4Model()
        self.app = create_app({"model2": self.model, "model4": self.model4},
                              {"TESTING": True, "MODEL_MODE": "real", "TRACKER_SCHEDULER_ENABLED": False})
        self.app.test_client_class = ClosingClient
        self.client = self.app.test_client()
        self.addCleanup(self.app.extensions["tracker_manager"].shutdown)

    def pil(self, vial, i):
        return Image.fromarray(self.frames[f"{vial}_{i}"])

    def upload(self, array):
        data = io.BytesIO()
        Image.fromarray(array).save(data, "PNG")
        data.seek(0)
        return data, "frame.png"

    def data(self, vial="field_v04", recipe="41", position="4", **overrides):
        data = {"frame_id": "f-1", "vial_id": vial, "batch_id": "test-batch", "batch_position": position,
                "camera_profile": "vial-fill-640x480", "recipe_id": recipe,
                "images": [self.upload(self.frames[f"{vial}_{i}"]) for i in range(3)]}
        data.update(overrides)
        return data

    def post(self, path="/predict/model2", **kwargs):
        return self.client.post(path, data=self.data(**kwargs), content_type="multipart/form-data")

    def test_matches_training_pipeline_oracle(self):
        classes = [int(c) for c in self.oracle["classes"]]
        for vial, expected in self.oracle["vials"].items():
            obs = self.model.predict_vial([self.pil(vial, i) for i in range(3)], intended_recipe_id=41,
                                          batch_position=2)["observation"]
            for c, p in zip(classes, expected["mean_probabilities"]):
                self.assertAlmostEqual(obs["scores"][str(c)], p, places=5)
            self.assertEqual(obs["predicted_recipe_id"], classes[int(np.argmax(expected["mean_probabilities"]))])

    def test_intended_recipe_and_position_cannot_change_the_observation(self):
        images = [self.pil("field_v04", i) for i in range(3)]
        a = self.model.predict_vial(images, intended_recipe_id=41, batch_position=4)["observation"]
        b = self.model.predict_vial(images, intended_recipe_id=99, batch_position=1)["observation"]
        self.assertEqual(a, b)

    def test_match_is_recorded_but_not_counted_while_unapproved(self):
        body = self.post().get_json()
        v = body["result"]["verification"]
        self.assertEqual(body["result"]["observation"]["status"], "accepted_observation")
        self.assertEqual(v["relation"], "matches_intended_recipe")
        self.assertFalse(v["counts_as_supporting_evidence"])
        self.assertEqual(v["flags"], [])

    def test_disagreement_is_flagged(self):
        v = self.post(recipe="60").get_json()["result"]["verification"]
        self.assertEqual(v["relation"], "recipe_disagreement")
        self.assertIn("recipe_disagreement", v["flags"])

    def test_confident_wrong_first_vial_keeps_contamination_and_disagreement(self):
        # field_v11: bad first vial of recipe 60, confidently scored as 99.
        result = self.post(vial="field_v11", recipe="60", position="1").get_json()["result"]
        self.assertEqual(result["observation"]["status"], "accepted_observation")
        self.assertEqual(result["observation"]["predicted_recipe_id"], 99)
        self.assertEqual(result["verification"]["flags"], ["expected_transition_contamination", "recipe_disagreement"])

    def test_approval_never_clears_first_vial_flag(self):
        self.model.approved = True
        v = self.post(position="1").get_json()["result"]["verification"]
        self.assertTrue(v["counts_as_supporting_evidence"])
        self.assertIn("expected_transition_contamination", v["flags"])
        self.assertTrue(v["review_required"])
        self.assertFalse(v["automatic_release"])

    def test_uncertain_vial_abstains(self):
        result = self.post(vial="v5_e10", recipe="8", position="1").get_json()["result"]
        self.assertEqual(result["observation"]["status"], "unknown_uncertain")
        self.assertEqual(result["verification"]["relation"], "abstained")

    def test_unsupported_intended_recipe_is_not_verified(self):
        v = self.post(recipe="1").get_json()["result"]["verification"]
        self.assertEqual(v["relation"], "intended_recipe_unsupported")
        self.assertFalse(v["counts_as_supporting_evidence"])

    def test_visible_stream_rejects_input(self):
        frames = [self.frames[f"field_v04_{i}"].copy() for i in range(3)]
        frames[0][90:145, 307:313] = (200, 120, 40)
        data = self.data(images=[self.upload(f) for f in frames])
        result = self.client.post("/predict/model2", data=data, content_type="multipart/form-data").get_json()["result"]
        self.assertEqual(result["input_quality"]["stream_visible_frames"], [1])
        self.assertEqual(result["observation"]["status"], "unknown_uncertain")
        self.assertEqual(result["verification"]["relation"], "abstained_input_rejected")

    def test_request_validation(self):
        self.assertEqual(self.post(recipe="").status_code, 400)
        self.assertEqual(self.post(camera_profile="phone").status_code, 422)
        self.assertEqual(self.post(extra="x").status_code, 400)
        data = self.data()
        data["images"] = data["images"][:2]
        self.assertEqual(self.client.post("/predict/model2", data=data, content_type="multipart/form-data").status_code, 400)
        small = np.zeros((240, 320, 3), np.uint8)
        data = self.data(images=[self.upload(small)] * 3)
        self.assertEqual(self.client.post("/predict/model2", data=data, content_type="multipart/form-data").status_code, 422)
        generic = self.client.post("/predict", data={"frame_id": "f", "model": "model2", "image": self.upload(small)},
                                   content_type="multipart/form-data")
        self.assertEqual(generic.status_code, 400)

    def test_shared_gate_and_auth(self):
        gate = self.app.extensions["inference_gate"]
        gate.acquire()
        try:
            self.assertEqual(self.post().status_code, 429)
        finally:
            gate.release()
        with patch.dict(os.environ, {"INFERENCE_TOKEN": "secret"}):
            self.assertEqual(self.post().status_code, 401)
            self.assertEqual(self.client.get("/model2").status_code, 401)

    def test_vial_evidence_keeps_model4_result_intact(self):
        for vial, recipe, position in (("field_v04", "41", "4"), ("field_v11", "60", "1")):
            alone = self.client.post("/predict/model4", content_type="multipart/form-data", data={
                k: v for k, v in self.data(vial, recipe, position).items()}).get_json()
            both = self.post("/predict/vial-evidence", vial=vial, recipe=recipe, position=position).get_json()
            self.assertEqual(both["model4"], alone["result"])
            combined = both["combined_review"]
            self.assertEqual(combined["model4_review"], alone["result"]["review"])
            self.assertTrue(combined["required"])
            self.assertFalse(combined["automatic_release"])
            if position == "1":
                self.assertEqual(combined["flags"], ["expected_transition_contamination", "recipe_disagreement"])
            else:
                self.assertIn("model4_needs_review", combined["flags"])

    def test_vial_evidence_requires_both_models_and_known_recipe(self):
        self.assertEqual(self.post("/predict/vial-evidence", recipe="9999").status_code, 400)
        app = create_app({"model2": self.model}, {"TESTING": True, "MODEL_MODE": "real", "TRACKER_SCHEDULER_ENABLED": False})
        self.addCleanup(app.extensions["tracker_manager"].shutdown)
        app.test_client_class = ClosingClient
        response = app.test_client().post("/predict/vial-evidence", data=self.data(), content_type="multipart/form-data")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
