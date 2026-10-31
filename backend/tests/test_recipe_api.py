import unittest
from unittest.mock import patch

from app import create_app
from recipes import Dispense, Recipe, RecipeRepository


class RecipeAPITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"INFERENCE_TOKEN": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.repository = RecipeRepository()
        self.intended = Recipe(1, "INTENDED", (Dispense("blue", 2, "T100"),), "blue")
        self.unmatched = Recipe(2, "UNMATCHED", (Dispense("yellow", 3),))
        self.repository.add_recipe(self.intended)
        self.repository.add_recipe(self.unmatched)
        self.app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"}, recipe_repository=self.repository)
        self.client = self.app.test_client()

    def test_default_lists_only_intended_recipes_with_complete_metadata(self):
        response = self.client.get("/api/recipes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            "collection": "INTENDED", "recipes": [{
                "id": 1, "collection": "INTENDED", "dispense_count": 1,
                "dispenses": [{"color": "blue", "duration_seconds": 2, "source": "T100"}],
                "final_color": "blue",
            }],
        })

    def test_explicit_collection_filter_and_nullable_optional_values(self):
        response = self.client.get("/api/recipes?collection=UNMATCHED")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["collection"], "UNMATCHED")
        recipe = response.json["recipes"][0]
        self.assertEqual(recipe["id"], 2)
        self.assertIsNone(recipe["final_color"])
        self.assertIsNone(recipe["dispenses"][0]["source"])
        self.assertEqual(self.client.get("/api/recipes?collection=INTENDED").json["recipes"][0]["id"], 1)

    def test_retrieves_from_either_collection_using_shared_serialization(self):
        for collection, identifier in (("INTENDED", 1), ("UNMATCHED", 2)):
            response = self.client.get(f"/api/recipes/{identifier}")
            listing = self.client.get(f"/api/recipes?collection={collection}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["recipe"], listing.json["recipes"][0])

    def test_not_found_and_invalid_ids_return_json_errors(self):
        self.assertEqual(self.client.get("/api/recipes/99").status_code, 404)
        for identifier in ("0", "-1", "1.5", "abc", "true", "01", "1e2"):
            with self.subTest(identifier=identifier):
                response = self.client.get(f"/api/recipes/{identifier}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json)

    def test_invalid_or_ambiguous_filters_are_rejected(self):
        for query in ("collection=", "collection=intended", "collection=MATCHED",
                      "collection=INTENDED&collection=UNMATCHED", "collecton=UNMATCHED"):
            with self.subTest(query=query):
                response = self.client.get("/api/recipes?" + query)
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json)

    def test_repository_lives_across_requests_and_reflects_collection_moves(self):
        self.assertIs(self.app.extensions["recipe_repository"], self.repository)
        self.repository.promote_to_intended(2, "operator", "Approved")
        self.assertEqual(self.client.get("/api/recipes/2").json["recipe"]["collection"], "INTENDED")
        self.assertEqual(len(self.client.get("/api/recipes").json["recipes"]), 2)
        self.assertEqual(self.client.get("/api/recipes?collection=UNMATCHED").json["recipes"], [])

    def test_new_apps_default_to_separate_empty_repositories(self):
        first = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"})
        second = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"})
        first.extensions["recipe_repository"].add_recipe(self.intended)
        self.assertEqual(first.test_client().get("/api/recipes").json["recipes"][0]["id"], 1)
        self.assertEqual(second.test_client().get("/api/recipes").json["recipes"], [])

    def test_recipe_reads_do_not_wait_for_model_inference(self):
        with self.app.extensions["inference_gate"]:
            self.assertEqual(self.client.get("/api/recipes").status_code, 200)
            self.assertEqual(self.client.get("/api/recipes/1").status_code, 200)

    def test_origin_policy_also_applies_to_recipe_routes(self):
        allowed = self.client.get("/api/recipes", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], "http://localhost:3000")
        denied = self.client.get("/api/recipes", headers={"Origin": "https://elsewhere.example"})
        self.assertEqual(denied.status_code, 403)

    def test_configured_token_protects_both_routes_but_allows_preflight(self):
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
            for path in ("/api/recipes", "/api/recipes/1"):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(self.client.get(path, headers={"Authorization": "Bearer wrong"}).status_code, 401)
                self.assertEqual(self.client.get(path, headers={"Authorization": "Bearer test-token"}).status_code, 200)
            response = self.client.options("/api/recipes", headers={
                "Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn("Authorization", response.headers["Access-Control-Allow-Headers"])

    def test_api_does_not_expose_write_operations(self):
        for path in ("/api/recipes", "/api/recipes/1"):
            self.assertEqual(self.client.post(path, json={}).status_code, 405)


if __name__ == "__main__":
    unittest.main()
