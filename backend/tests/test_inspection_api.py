import unittest
from dataclasses import replace
from unittest.mock import patch

from app import create_app
from recipes import Dispense, InspectionRepository, Recipe, RecipeRepository, VialObservation


class InspectionAPITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"INFERENCE_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.recipes = RecipeRepository()
        self.inspections = InspectionRepository()
        self.app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"},
                              recipe_repository=self.recipes, inspection_repository=self.inspections)
        self.client = self.app.test_client()
        self.service = self.app.extensions["vial_inspection_service"]
        self.observation = VialObservation("RUN", "VIAL-1", (Dispense("blue", 2),), "blue", True)

    def seed(self):
        self.recipes.add_recipe(Recipe(1, "INTENDED", self.observation.dispenses, "blue"))

    def test_pass_detail_contains_measurements_recipe_and_comparison_metadata(self):
        self.seed()
        self.service.inspect(self.observation, "INS-1")
        response = self.client.get("/api/inspections/INS-1")
        self.assertEqual(response.status_code, 200)
        item = response.json["inspection"]
        self.assertEqual(item["inspection_id"], "INS-1")
        self.assertEqual(item["verification_status"], "PASS")
        self.assertEqual(item["recipe_id"], 1)
        self.assertEqual(item["recipe_collection"], "INTENDED")
        self.assertEqual(item["observation"]["dispense_count"], 1)
        self.assertEqual(item["observation"]["dispenses"][0]["duration_seconds"], 2)
        self.assertEqual(item["recipe_snapshot"]["dispense_count"], 1)
        comparison = item["intended_comparison"]
        self.assertEqual(comparison["similarity_score"], 1)
        self.assertEqual(comparison["threshold_used"], .9)
        self.assertEqual(comparison["config"]["duration_weight"], .35)
        self.assertEqual(comparison["feature_scores"]["duration"], 1)
        self.assertEqual(comparison["differences"], [])
        self.assertIsNone(item["unmatched_comparison"])
        self.assertFalse(item["created_new_recipe"])
        self.assertTrue(item["inspected_at"].endswith("+00:00"))

    def test_failed_inspection_exposes_expected_and_observed_field_differences(self):
        self.seed()
        observation = replace(self.observation, final_color="red")
        result = self.service.inspect(observation, "FAIL-1")
        item = self.client.get("/api/inspections/FAIL-1").json["inspection"]
        self.assertEqual(item["verification_status"], "FAIL")
        self.assertEqual(item["recipe_collection"], "UNMATCHED")
        self.assertEqual(item["recipe_id"], result.recipe_id)
        difference = next(d for d in item["intended_comparison"]["differences"] if d["field"] == "final_color")
        self.assertEqual((difference["expected"], difference["observed"]), ("blue", "red"))
        self.assertEqual(item["unmatched_comparison"]["status"], "NO_MATCH")

    def test_extra_dispense_differences_serialize_nested_dataclasses(self):
        self.seed()
        self.service.inspect(replace(self.observation, dispenses=self.observation.dispenses + (Dispense("yellow", 3),)), "EXTRA")
        response = self.client.get("/api/inspections/EXTRA")
        self.assertEqual(response.status_code, 200)
        differences = response.json["inspection"]["intended_comparison"]["differences"]
        extra = next(d for d in differences if d["reason"].startswith("Extra dispense"))
        self.assertEqual(extra["observed"]["color"], "yellow")
        self.assertIsNone(extra["expected"])

    def test_unresolved_inspections_have_null_links_and_no_new_recipe(self):
        self.service.inspect(replace(self.observation, final_color=None), "UNRESOLVED")
        item = self.client.get("/api/inspections/UNRESOLVED").json["inspection"]
        self.assertEqual(item["verification_status"], "INSUFFICIENT_DATA")
        self.assertIsNone(item["recipe_id"])
        self.assertIsNone(item["recipe_snapshot"])
        self.assertIsNone(item["intended_comparison"]["similarity_score"])

    def test_recipe_occurrences_are_ordered_and_retries_are_not_counted_twice(self):
        self.seed()
        first = self.service.inspect(self.observation, "INS-1")
        self.service.inspect(self.observation, "INS-1")
        self.service.inspect(replace(self.observation, vial_id="VIAL-2"), "INS-2")
        self.service.inspect(replace(self.observation, vial_id="OTHER", final_color="red"), "OTHER")
        response = self.client.get("/api/recipes/1/inspections")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["recipe_id"], first.recipe_id)
        self.assertEqual(response.json["count"], 2)
        self.assertEqual([item["inspection_id"] for item in response.json["inspections"]], ["INS-1", "INS-2"])
        self.assertEqual(response.json["inspections"][0], self.client.get("/api/inspections/INS-1").json["inspection"])

    def test_existing_recipe_without_occurrences_returns_empty_list(self):
        self.seed()
        self.assertEqual(self.client.get("/api/recipes/1/inspections").json,
                         {"recipe_id": 1, "count": 0, "inspections": []})

    def test_reads_preserve_history_after_promotion_and_metadata_update(self):
        result = self.service.inspect(self.observation, "INS-1")
        before = self.client.get("/api/inspections/INS-1").json
        promoted = self.recipes.promote_to_intended(result.recipe_id, "operator", "Approved")
        self.recipes.update_recipe(replace(promoted, final_color="green"))
        self.assertEqual(self.client.get("/api/inspections/INS-1").json, before)
        item = self.client.get(f"/api/recipes/{result.recipe_id}/inspections").json["inspections"][0]
        self.assertEqual(item["recipe_collection"], "UNMATCHED")
        self.assertEqual(item["recipe_snapshot"]["final_color"], "blue")

    def test_missing_and_invalid_identifiers_return_json_errors(self):
        for path in ("/api/inspections/missing", "/api/recipes/99/inspections"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIn("error", response.json)
        for identifier in ("0", "01", "-1", "abc"):
            self.assertEqual(self.client.get(f"/api/recipes/{identifier}/inspections").status_code, 400)
        self.assertEqual(self.client.get("/api/inspections/%20").status_code, 400)

    def test_authentication_origin_and_preflight_cover_both_paths(self):
        self.seed()
        self.service.inspect(self.observation, "INS-1")
        for path in ("/api/inspections/INS-1", "/api/recipes/1/inspections"):
            with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(self.client.get(path, headers={"Authorization": "Bearer test-token"}).status_code, 200)
                self.assertEqual(self.client.options(path, headers={
                    "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization"}).status_code, 200)
            self.assertEqual(self.client.get(path, headers={"Origin": "https://elsewhere.example"}).status_code, 403)

    def test_shared_repositories_and_service_are_app_scoped_and_reads_are_independent_of_inference(self):
        self.assertIs(self.service.recipes, self.recipes)
        self.assertIs(self.service.inspections, self.inspections)
        self.assertIs(self.app.extensions["inspection_repository"], self.inspections)
        self.seed()
        self.service.inspect(self.observation, "INS-1")
        with self.app.extensions["inference_gate"]:
            self.assertEqual(self.client.get("/api/inspections/INS-1").status_code, 200)
        other = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"})
        self.assertEqual(other.test_client().get("/api/inspections/INS-1").status_code, 404)

    def test_endpoints_are_read_only(self):
        for path in ("/api/inspections/INS-1", "/api/recipes/1/inspections"):
            self.assertEqual(self.client.post(path, json={}).status_code, 405)


if __name__ == "__main__":
    unittest.main()
