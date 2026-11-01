import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import create_app
from recipes import Dispense, Recipe, VialObservation, VialInspectionService


class RecordedRecipeAPITests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"INFERENCE_TOKEN": ""})
        env.start(); self.addCleanup(env.stop)
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recipes.sqlite3"
        self.apps = []
        self.addCleanup(lambda: [(a.extensions["tracker_manager"].shutdown(), a.extensions["recipe_store"].close()) for a in self.apps])
        self.app = self.make_app(); self.client = self.app.test_client()

    def make_app(self):
        app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock", "RECIPE_DB_PATH": str(self.path)})
        self.apps.append(app)
        return app

    def test_source_observations_are_retained_without_inventing_dispense_measurements(self):
        result = self.client.post("/api/recipe-workflow/recorded/video-1/V1-V01", json={})
        self.assertEqual(result.status_code, 200)
        data = result.json["assessment"]
        self.assertEqual(data["assessment_status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(data["recipe_id"])
        self.assertEqual(data["observation"]["dispenses"], [])
        self.assertFalse(data["observation"]["filling_complete"])
        self.assertEqual(data["coverage"]["nominal_reference_count"], 52)
        self.assertEqual(data["coverage"]["comparable_reference_count"], 0)
        self.assertEqual(data["evidence"]["source_observation"]["pulses"][0]["startLower"], 6.5)
        self.assertEqual(self.client.get("/api/recipes?collection=UNMATCHED").json["recipes"], [])
        self.assertEqual(result.headers["X-Recipe-Storage"], "sqlite")

    def test_replay_and_restart_return_same_inspection_without_duplicates(self):
        url = "/api/recipe-workflow/recorded/video-1/V1-V01"
        first = self.client.post(url, json={}).json["assessment"]
        self.assertEqual(self.client.post(url, json={}).json["assessment"]["inspection_id"], first["inspection_id"])
        client = self.make_app().test_client()
        self.assertEqual(client.post(url, json={}).json["assessment"]["inspection_id"], first["inspection_id"])
        saved = client.get("/api/recipe-workflow/videos/video-1/assessments").json["assessments"]
        self.assertEqual(len(saved), 1)
        self.assertFalse(saved[0]["requires_reassessment"])
        self.assertEqual(client.get("/api/recipe-workflow/status").json["saved_assessment_count"], 1)

    def test_reference_changes_create_new_version_without_overwriting_old_result(self):
        url = "/api/recipe-workflow/recorded/video-1/V1-V01"
        first = self.client.post(url, json={}).json["assessment"]
        self.app.extensions["recipe_repository"].add_recipe(Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue"))
        stale = self.client.get("/api/recipe-workflow/videos/video-1/assessments").json["assessments"][0]
        self.assertTrue(stale["requires_reassessment"])
        second = self.client.post(url, json={}).json["assessment"]
        self.assertNotEqual(first["inspection_id"], second["inspection_id"])
        self.assertEqual(self.client.get("/api/recipe-workflow/status").json["saved_assessment_count"], 2)
        self.assertEqual(self.client.get("/api/inspections/" + first["inspection_id"]).json["inspection"]["observation"], first["observation"])

    def test_all_22_reviewed_fills_remain_unresolved_with_current_reference_data(self):
        manifest = json.loads((Path(__file__).resolve().parents[2] / "evidence/recorded-inspection.json").read_text())
        for video in manifest["videos"]:
            for vial in video["vials"]:
                data = self.client.post(f'/api/recipe-workflow/recorded/{video["id"]}/{vial["id"]}', json={}).json["assessment"]
                self.assertEqual(data["assessment_status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(self.client.get("/api/recipe-workflow/status").json["saved_assessment_count"], 22)
        self.assertEqual(self.client.get("/api/recipes?collection=UNMATCHED").json["recipes"], [])

    def test_untrusted_sources_and_unknown_video_paths_are_rejected(self):
        self.assertEqual(self.client.post("/api/recipe-workflow/recorded/video-3/V3-V01", json={}).status_code, 404)
        self.assertEqual(self.client.post("/api/recipe-workflow/recorded/video-1/V1-V01", json={"dispenses": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/recipe-workflow/observations", json={}).status_code, 503)
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
            self.assertEqual(self.client.get("/api/recipe-workflow/status").status_code, 401)
            self.assertEqual(self.client.get("/api/recipe-workflow/status", headers={"Authorization": "Bearer test-token"}).status_code, 200)

    def test_authenticated_observation_adapter_uses_guarded_matching_and_durable_candidates(self):
        # Synthetic reference fixtures exercise transport/workflow only; they
        # are never imported into the application's real recipe bank.
        catalog = json.loads((Path(__file__).resolve().parents[1] / "model4_assets/recipes.json").read_text())
        for identifier in catalog["recipes"]:
            self.app.extensions["recipe_repository"].add_recipe(
                Recipe(int(identifier), "INTENDED", (Dispense("blue", 2),), "blue"))
        payload = {"source": "synthetic adapter fixture", "observation": {
            "run_id": "adapter-test", "vial_id": "one", "dispenses": [{"color": "red", "duration_seconds": 4}],
            "final_color": "red", "filling_complete": True}}
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
            headers = {"Authorization": "Bearer test-token"}
            self.assertEqual(self.client.post("/api/recipe-workflow/observations", json=payload).status_code, 401)
            first = self.client.post("/api/recipe-workflow/observations", json=payload, headers=headers)
            self.assertEqual(first.status_code, 200)
            item = first.json["assessment"]
            self.assertEqual(item["assessment_status"], "UNMATCHED_CANDIDATE")
            self.assertTrue(item["created_new_recipe"])
            self.assertGreater(item["recipe_id"], 99)
            reopened = self.make_app().test_client()
            repeated = reopened.post("/api/recipe-workflow/observations", json=payload, headers=headers).json["assessment"]
            self.assertEqual(repeated["inspection_id"], item["inspection_id"])
            payload["observation"]["vial_id"] = "two"
            reused = reopened.post("/api/recipe-workflow/observations", json=payload, headers=headers).json["assessment"]
            self.assertFalse(reused["created_new_recipe"])
            self.assertEqual(reused["recipe_id"], item["recipe_id"])


if __name__ == "__main__":
    unittest.main()
