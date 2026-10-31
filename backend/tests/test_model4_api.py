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
from model4 import Model4Model, TANKS
from models import load_models

FIXTURES = Path(__file__).parent / "fixtures/model4"


class ClosingClient(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs["buffered"] = True
        response = super().open(*args, **kwargs)
        # Werkzeug spools these multi-frame request bodies to temporary files.
        response.request.input_stream.close()
        return response


class Model4APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = np.load(FIXTURES / "registered_frames.npz", allow_pickle=False)
        cls.oracle = json.loads((FIXTURES / "oracle.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.frames.close()

    def setUp(self):
        self.model = Model4Model()
        self.app = create_app({"model4": self.model}, {"TESTING": True, "MODEL_MODE": "real", "TRACKER_SCHEDULER_ENABLED": False})
        self.app.test_client_class = ClosingClient
        self.client = self.app.test_client()
        self.addCleanup(self.app.extensions["tracker_manager"].shutdown)

    def image(self, key):
        data = io.BytesIO()
        Image.fromarray(self.frames[key]).save(data, "PNG")
        data.seek(0)
        return data, key + ".png"

    def data(self, transition=False, comparison=False, **overrides):
        data = {"frame_id": "f-42", "batch_id": "test-batch", "vial_id": "test-vial",
                "batch_position": "1" if transition else "2", "camera_profile": "vial-fill-640x480",
                "recipe_id": "99" if transition else "6",
                "images": [self.image(("transition_post_" if transition else "post_") + str(i)) for i in range(1, 4)]}
        if comparison:
            data.update(events=json.dumps([{"event_number": 1, "duration_s": self.oracle["transition_duration_s"]}]),
                        event_1_before=self.image("transition_before"), event_1_during=self.image("transition_during"))
        data.update(overrides)
        return data

    def post(self, **kwargs):
        return self.client.post("/predict/model4", data=self.data(**kwargs), content_type="multipart/form-data")

    def assert_ratios(self, actual, expected):
        for tank in TANKS:
            self.assertAlmostEqual(actual[tank], expected[tank], places=10)

    def test_real_checkpoint_matches_frozen_independent_oracle(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        body = response.json
        self.assertEqual(body["mode"], "real")
        self.assertEqual(body["frame_id"], "f-42")
        result = body["result"]
        self.assert_ratios(result["checkpoint"]["estimated_proportions"], self.oracle["post_ratios"])
        self.assertEqual(result["expected"]["amounts_ml"], {"T100": 30.0, "T200": 10.0, "T400": 0.0})
        self.assertEqual(result["expected"]["proportions"], {"T100": .75, "T200": .25, "T400": 0.0})
        expected_difference = (self.oracle["post_ratios"]["T200"] - .25) * 100
        self.assertAlmostEqual(result["checkpoint"]["signed_difference_percentage_points"]["T200"], expected_difference)
        self.assertFalse(result["stream_color_comparison"]["available"])
        self.assertFalse(result["review"]["automatic_release"])

    def test_real_stream_comparison_keeps_visual_discrepancy(self):
        response = self.post(transition=True, comparison=True)
        self.assertEqual(response.status_code, 200)
        result = response.json["result"]
        self.assert_ratios(result["checkpoint"]["estimated_proportions"], self.oracle["transition_checkpoint_ratios"])
        comparison = result["stream_color_comparison"]
        self.assertTrue(comparison["available"])
        self.assertFalse(comparison["promoted"])
        self.assert_ratios(comparison["estimated_proportions"], self.oracle["transition_challenger_ratios"])
        self.assertLess(comparison["mean_dye_difference_percentage_points"], result["checkpoint"]["mean_dye_difference_percentage_points"])
        self.assertGreaterEqual(result["review"]["retained_mean_dye_difference_percentage_points"], result["checkpoint"]["mean_dye_difference_percentage_points"])
        self.assertEqual(result["review"]["status"], "expected_transition_contamination")

    def test_expected_recipe_and_batch_position_cannot_change_estimates(self):
        a = self.post(transition=True, comparison=True).json["result"]
        b = self.post(transition=True, comparison=True, recipe_id="50", batch_position="2").json["result"]
        self.assertEqual(a["checkpoint"]["estimated_proportions"], b["checkpoint"]["estimated_proportions"])
        self.assertEqual(a["stream_color_comparison"]["estimated_proportions"], b["stream_color_comparison"]["estimated_proportions"])
        self.assertTrue(a["review"]["expected_transition_contamination"])
        self.assertFalse(b["review"]["expected_transition_contamination"])

    def test_first_vial_remains_flagged_even_with_expected_ratios_equal_to_prediction(self):
        data = self.data(transition=True)
        del data["recipe_id"]
        data["expected_ml"] = json.dumps(self.oracle["transition_checkpoint_ratios"])
        result = self.client.post("/predict/model4", data=data).json["result"]
        self.assertAlmostEqual(result["checkpoint"]["mean_dye_difference_percentage_points"], 0.0, places=8)
        self.assertTrue(result["review"]["expected_transition_contamination"])
        self.assertTrue(result["review"]["required"])
        self.assertFalse(result["review"]["automatic_release"])

    def test_mock_mode_never_returns_estimated_proportions(self):
        app = create_app({"model4": Model4Model(mock=True)},
                         {"TESTING": True, "MODEL_MODE": "mock", "TRACKER_SCHEDULER_ENABLED": False})
        app.test_client_class = ClosingClient
        client = app.test_client()
        response = client.post("/predict/model4", data=self.data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["mode"], "mock")
        self.assertTrue(response.json["result"]["mock"])
        self.assertIsNone(response.json["result"]["checkpoint"])

    def test_missing_or_wrong_number_of_frames_is_rejected(self):
        for count in [0, 1, 2, 4]:
            self.assertEqual(self.post(images=[self.image("post_1") for _ in range(count)]).status_code, 400)

    def test_registered_geometry_is_enforced_without_resizing(self):
        data = io.BytesIO(); Image.new("RGB", (1280, 960), "white").save(data, "PNG"); data.seek(0)
        self.assertEqual(self.post(images=[(data, "wrong.png"), self.image("post_2"), self.image("post_3")]).status_code, 422)
        self.assertEqual(self.post(camera_profile="phone-camera").status_code, 422)

    def test_corrupt_input_and_inference_failure_release_shared_gate(self):
        self.assertEqual(self.post(images=[(io.BytesIO(b"broken"), "bad.png"), self.image("post_2"), self.image("post_3")]).status_code, 400)
        self.assertEqual(self.post().status_code, 200)
        with patch.object(self.model, "_checkpoint_predict", side_effect=RuntimeError("internal weights")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("internal weights", response.json["error"])
        self.assertEqual(self.post().status_code, 200)

    def test_expected_amount_validation(self):
        invalid = [{"T100": 0, "T200": 0, "T400": 0}, {"T100": True, "T200": 1, "T400": 0},
                   {"T100": -1, "T200": 2, "T400": 0}, {"T100": 1e308, "T200": 1e308, "T400": 0}, {"T100": 1}, [1, 0, 0]]
        for amounts in invalid:
            data = self.data(); del data["recipe_id"]; data["expected_ml"] = json.dumps(amounts)
            self.assertEqual(self.client.post("/predict/model4", data=data).status_code, 400)
        for raw in ['{"T100":NaN,"T200":1,"T400":0}', '{"T100":1,"T100":2,"T200":0,"T400":0}']:
            data = self.data(); del data["recipe_id"]; data["expected_ml"] = raw
            self.assertEqual(self.client.post("/predict/model4", data=data).status_code, 400)
        self.assertEqual(self.post(expected_ml='{"T100":1,"T200":0,"T400":0}').status_code, 400)
        self.assertEqual(self.post(recipe_id="999").status_code, 400)

    def test_observed_events_require_complete_evidence_and_no_expected_tank_labels(self):
        self.assertEqual(self.post(events="[]").status_code, 400)
        self.assertEqual(self.post(events="null").status_code, 400)
        self.assertEqual(self.post(events='[{"event_number":1,"duration_s":2}]').status_code, 400)
        data = self.data(transition=True, comparison=True)
        data["events"] = '[{"event_number":1,"duration_s":2,"expected_tank":"T100"}]'
        self.assertEqual(self.client.post("/predict/model4", data=data).status_code, 400)
        self.assertEqual(self.post(transition=True, comparison=True, events='[{"event_number":2,"duration_s":2}]').status_code, 400)
        self.assertEqual(self.post(transition=True, comparison=True, events='[{"event_number":1,"duration_s":-1}]').status_code, 422)

    def test_explicit_unknown_before_frame_preserves_review(self):
        data = self.data(transition=True, comparison=True)
        del data["event_1_before"]
        data["events"] = '[{"event_number":1,"duration_s":null,"before_missing":true}]'
        response = self.client.post("/predict/model4", data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["result"]["review"]["required"])
        self.assertTrue(response.json["result"]["review"]["expected_transition_contamination"])

    def test_shared_inference_gate_and_limits(self):
        with self.app.extensions["inference_gate"]:
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "1")
        self.app.config["MODEL4_MAX_CONTENT_LENGTH"] = 100
        self.assertEqual(self.post().status_code, 413)

    def test_existing_auth_and_cors_cover_new_endpoints(self):
        self.assertEqual(self.client.post("/predict/model4", headers={"Origin": "https://elsewhere.example"}).status_code, 403)
        with patch.dict(os.environ, {"INFERENCE_TOKEN": "model4-test-token"}):
            self.assertEqual(self.post().status_code, 401)
            self.assertEqual(self.client.get("/model4/recipes").status_code, 401)
            self.assertEqual(self.client.get("/model4", headers={"Authorization": "Bearer model4-test-token"}).status_code, 200)

    def test_metadata_catalog_and_dedicated_route(self):
        self.assertEqual(len(self.client.get("/model4/recipes").json["recipes"]), 52)
        self.assertEqual(self.client.get("/model4").json["default_model"], "frozen_checkpoint")
        self.assertEqual(self.client.post("/predict", data={"model": "model4", "frame_id": "x"}).status_code, 400)
        with patch.dict(os.environ, {"ENABLED_MODELS": "model4"}):
            self.assertIsInstance(load_models("real")["model4"], Model4Model)
            self.assertTrue(load_models("mock")["model4"].mock)

    def test_model4_does_not_learn_or_change_inspection_history(self):
        before = self.app.extensions["recipe_repository"].list_recipes("UNMATCHED")
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.app.extensions["recipe_repository"].list_recipes("UNMATCHED"), before)

    def test_tampered_checkpoint_fails_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            assets = Path(folder) / "assets"
            shutil.copytree(Path(__file__).parents[1] / "model4_assets", assets)
            with (assets / "checkpoint.json").open("a") as out:
                out.write(" ")
            with self.assertRaisesRegex(ValueError, "integrity"):
                Model4Model(assets=assets)


if __name__ == "__main__":
    unittest.main()
