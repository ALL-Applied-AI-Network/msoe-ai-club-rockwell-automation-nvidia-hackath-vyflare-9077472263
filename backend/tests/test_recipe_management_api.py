import unittest
from unittest.mock import patch

from app import create_app
from recipes import (Dispense, InspectionRepository, Recipe, RecipeRepository,
                     VialInspectionService, VialObservation)


class RecipeManagementAPITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"INFERENCE_TOKEN": "management-test-token"})
        environment.start()
        self.addCleanup(environment.stop)
        self.repository = RecipeRepository()
        self.recipe = Recipe(1, "UNMATCHED", (Dispense("blue", 2),), "blue")
        self.repository.add_recipe(self.recipe)
        self.app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock",
                                  "RECIPE_MANAGEMENT_ACTOR": "console-service"},
                              recipe_repository=self.repository)
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer management-test-token"}

    def post(self, action="promote", identifier="1", **kwargs):
        kwargs.setdefault("headers", self.headers)
        if "data" not in kwargs:
            kwargs.setdefault("json", {"reason": "Approved new pattern"})
        return self.client.post(f"/api/recipes/{identifier}/{action}", **kwargs)

    def history(self):
        return self.client.get("/api/recipes/1/history", headers=self.headers)

    def test_promote_and_demote_preserve_recipe_and_record_service_actor(self):
        promoted = self.post()
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.json["recipe"]["collection"], "INTENDED")
        self.assertEqual(promoted.json["recipe"]["id"], 1)
        self.assertEqual(promoted.json["recipe"]["dispenses"][0]["duration_seconds"], 2)
        demoted = self.post("demote", json={"reason": "Reference withdrawn"})
        self.assertEqual(demoted.status_code, 200)
        self.assertEqual(demoted.json["recipe"]["collection"], "UNMATCHED")
        history = self.history()
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json["recipe_id"], 1)
        changes = history.json["history"]
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0]["changed_by"], "console-service")
        self.assertEqual(changes[0]["reason"], "Approved new pattern")
        self.assertEqual(changes[0]["previous_collection"], "UNMATCHED")
        self.assertEqual(changes[0]["new_collection"], "INTENDED")
        self.assertEqual(changes[1]["new_collection"], "UNMATCHED")
        self.assertTrue(changes[0]["changed_at"].endswith("+00:00"))
        self.assertNotEqual(changes[0]["change_id"], changes[1]["change_id"])

    def test_empty_history_and_repeat_requests_are_idempotent(self):
        self.assertEqual(self.history().json["history"], [])
        self.assertEqual(self.post("demote").status_code, 200)
        self.assertEqual(self.history().json["history"], [])
        self.post()
        self.post()
        self.assertEqual(len(self.history().json["history"]), 1)

    def test_missing_and_incorrect_credentials_block_both_actions(self):
        for action in ("promote", "demote"):
            for headers in ({}, {"Authorization": "Bearer incorrect"}):
                self.assertEqual(self.post(action, headers=headers).status_code, 401)
        self.assertEqual(self.repository.get_recipe(1), self.recipe)
        self.assertEqual(self.repository.list_collection_changes(1), ())

    def test_management_disabled_without_token_or_audit_actor(self):
        for actor in (None, "", "  ", 42):
            self.app.config["RECIPE_MANAGEMENT_ACTOR"] = actor
            self.assertEqual(self.post().status_code, 503)
        self.app.config["RECIPE_MANAGEMENT_ACTOR"] = "console-service"
        with patch.dict("os.environ", {"INFERENCE_TOKEN": ""}):
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.repository.get_recipe(1), self.recipe)

    def test_invalid_json_reason_and_spoofed_identity_are_rejected(self):
        for body in ({}, [], "approved", {"reason": ""}, {"reason": "  "},
                     {"reason": 42}, {"reason": True},
                     {"reason": "Approved", "changed_by": "admin"}):
            with self.subTest(body=body):
                self.assertEqual(self.post(json=body).status_code, 400)
        self.assertEqual(self.post(data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.post(data="reason=Approved", content_type="application/x-www-form-urlencoded").status_code, 415)
        self.assertEqual(self.repository.list_collection_changes(1), ())

    def test_client_identity_headers_do_not_override_server_actor(self):
        headers = {**self.headers, "X-User": "admin", "X-Forwarded-User": "admin"}
        self.assertEqual(self.post(headers=headers).status_code, 200)
        self.assertEqual(self.history().json["history"][0]["changed_by"], "console-service")

    def test_invalid_and_missing_identifiers(self):
        for action in ("promote", "demote"):
            self.assertEqual(self.post(action, identifier="99").status_code, 404)
            for identifier in ("0", "-1", "01", "abc"):
                self.assertEqual(self.post(action, identifier=identifier).status_code, 400)
        self.assertEqual(self.client.get("/api/recipes/99/history", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get("/api/recipes/abc/history", headers=self.headers).status_code, 400)

    def test_preflight_and_origin_policy_cover_write_actions(self):
        response = self.client.options("/api/recipes/1/promote", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
        denied = self.post(headers={**self.headers, "Origin": "https://elsewhere.example"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.repository.list_collection_changes(1), ())

    def test_history_uses_existing_read_authentication_policy(self):
        self.assertEqual(self.client.get("/api/recipes/1/history").status_code, 401)
        with patch.dict("os.environ", {"INFERENCE_TOKEN": ""}):
            self.assertEqual(self.client.get("/api/recipes/1/history").status_code, 200)

    def test_promotion_does_not_rewrite_previous_inspection(self):
        inspections = InspectionRepository()
        service = VialInspectionService(self.repository, inspections)
        observation = VialObservation("RUN", "VIAL-1", self.recipe.dispenses, "blue", True)
        first = service.inspect(observation)
        self.assertEqual(first.verification_status, "FAIL")
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(first.recipe_collection, "UNMATCHED")
        self.assertEqual(first.verification_status, "FAIL")
        second = service.inspect(VialObservation("RUN", "VIAL-2", self.recipe.dispenses, "blue", True))
        self.assertEqual(second.verification_status, "PASS")


if __name__ == "__main__":
    unittest.main()
