import unittest
from dataclasses import replace
from threading import Event
from unittest.mock import patch

from app import create_app
from recipes import Dispense, Recipe


class TrackerAPITests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"INFERENCE_TOKEN": "tracker-test-token"})
        environment.start()
        self.addCleanup(environment.stop)
        self.now = 0.0
        self.app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock"}, tracker_clock=lambda: self.now)
        self.manager = self.app.extensions["tracker_manager"]
        self.addCleanup(self.manager.shutdown)
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer tracker-test-token"}
        self.base = "/api/stations/FILL_1/tracker"

    def post(self, suffix, body, base=None):
        return self.client.post((base or self.base) + suffix, json=body, headers=self.headers)

    def get(self, suffix="", base=None):
        return self.client.get((base or self.base) + suffix, headers=self.headers)

    def start(self, vial="VIAL-1", base=None):
        return self.post("/start", {"run_id": "RUN", "vial_id": vial, "captured_at": 10}, base)

    def events(self, vial="VIAL-1", base=None, color="blue"):
        for identifier, kind, timestamp in (("start", "DISPENSE_STARTED", 10), ("stop", "DISPENSE_STOPPED", 12)):
            body = {"event_id": identifier, "run_id": "RUN", "vial_id": vial,
                    "kind": kind, "captured_at": timestamp, "dispense_id": "D1"}
            if kind == "DISPENSE_STARTED":
                body["color"] = color
            self.assertEqual(self.post("/events", body, base).status_code, 202)

    def finish(self, vial="VIAL-1", base=None, color="blue"):
        return self.post("/finish", {"event_id": "done", "run_id": "RUN", "vial_id": vial,
                                     "captured_at": 12, "final_color": color}, base)

    def test_http_flow_verifies_intended_and_exposes_stored_inspection(self):
        self.app.extensions["recipe_repository"].add_recipe(Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue"))
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.post("/config", {"update_interval_ms": 200}).status_code, 409)
        self.events()
        self.assertEqual(self.finish().status_code, 202)
        self.manager.update_all()
        self.assertEqual(self.get().json["tracker"]["state"], "FINALIZING")
        self.now = 1.1
        self.manager.update_all()
        snapshot = self.get().json["tracker"]
        self.assertEqual(snapshot["state"], "INSPECTED")
        self.assertEqual(snapshot["inspection"]["verification_status"], "PASS")
        identifier = snapshot["inspection"]["inspection_id"]
        detail = self.client.get("/api/inspections/" + identifier, headers=self.headers)
        self.assertEqual(detail.json["inspection"], snapshot["inspection"])
        self.assertEqual(self.client.get("/api/recipes/1/inspections", headers=self.headers).json["count"], 1)

    def test_http_unmatched_learning_reuses_pattern_for_next_vial(self):
        self.post("/config", {"finalization_grace_ms": 0})
        links = []
        for vial in ("VIAL-1", "VIAL-2"):
            self.start(vial)
            self.events(vial)
            self.finish(vial)
            self.manager.update_all()
            inspection = self.get().json["tracker"]["inspection"]
            self.assertEqual(inspection["verification_status"], "FAIL")
            links.append(inspection["recipe_id"])
        self.assertEqual(links[0], links[1])
        self.assertEqual(len(self.app.extensions["recipe_repository"].list_recipes("UNMATCHED")), 1)

    def test_reads_do_not_tick_and_empty_intervals_do_not_finalize(self):
        self.start()
        self.events()
        self.manager.update_all()
        before = self.get().json["tracker"]
        self.now = 100
        self.assertEqual(self.get().json["tracker"], before)
        self.manager.update_all()
        self.assertEqual(self.get().json["tracker"]["state"], "FILLING")

    def test_station_configuration_and_isolation(self):
        response = self.post("/config", {"update_interval_ms": 200, "finalization_grace_ms": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get("/config").json["config"]["update_interval_ms"], 200)
        self.start()
        other = "/api/stations/FILL_2/tracker"
        self.assertEqual(self.start(base=other).status_code, 409)
        self.assertEqual(self.start("VIAL-2", other).status_code, 200)
        self.events()
        self.finish()
        self.manager.update_all()
        self.assertEqual(self.get(base=other).json["tracker"]["state"], "FILLING")
        self.assertEqual(self.post("/config", {"update_interval_ms": 300}).status_code, 200)
        self.assertEqual(self.get().json["config"]["finalization_grace_ms"], 0)

    def test_identical_start_and_event_retries_do_not_duplicate_cycle(self):
        self.start()
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.start("VIAL-2").status_code, 409)
        self.events()
        self.events()
        self.finish()
        self.assertEqual(self.finish().status_code, 202)
        self.now = 1.1
        self.manager.update_all()
        self.assertEqual(self.start().json["tracker"]["state"], "INSPECTED")
        self.assertEqual(len(self.app.extensions["recipe_repository"].list_recipes("UNMATCHED")), 1)

    def test_late_old_vial_finish_cannot_finish_next_vial(self):
        self.post("/config", {"finalization_grace_ms": 0})
        self.start()
        self.events()
        self.finish()
        self.manager.update_all()
        self.start("VIAL-2")
        self.assertEqual(self.finish().status_code, 400)
        self.assertEqual(self.get().json["tracker"]["state"], "FILLING")

    def test_missing_boundary_yields_unresolved_inspection_without_learning(self):
        self.start()
        self.finish()
        self.now = 1.1
        self.manager.update_all()
        result = self.get().json["tracker"]
        self.assertEqual(result["inspection"]["verification_status"], "INSUFFICIENT_DATA")
        self.assertTrue(result["issues"])

    def test_missing_station_invalid_payloads_and_bad_settings(self):
        self.assertEqual(self.get().status_code, 404)
        self.assertEqual(self.get("/config").status_code, 404)
        for body in ({}, [], {"run_id": "RUN"}, {"run_id": "RUN", "vial_id": "V", "captured_at": True},
                     {"run_id": "RUN", "vial_id": "V", "captured_at": 10, "extra": 1}):
            self.assertEqual(self.post("/start", body).status_code, 400)
        for settings in ({}, {"extra": 1}, {"update_interval_ms": 0}, {"update_interval_ms": 5e-324},
                         {"finalization_grace_ms": -1}, {"update_interval_ms": True}):
            self.assertEqual(self.post("/config", settings).status_code, 400)
        self.assertEqual(self.post("/start", {"run_id": "R", "vial_id": "V", "captured_at": 1},
                                   "/api/stations/bad%20station/tracker").status_code, 400)

    def test_token_and_origin_policy_apply_to_all_tracker_writes(self):
        body = {"run_id": "R", "vial_id": "V", "captured_at": 1}
        self.assertEqual(self.client.post(self.base + "/start", json=body).status_code, 401)
        with patch.dict("os.environ", {"INFERENCE_TOKEN": ""}):
            self.assertEqual(self.post("/start", body).status_code, 503)
        denied = self.client.post(self.base + "/start", json=body,
                                  headers={**self.headers, "Origin": "https://elsewhere.example"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.client.options(self.base + "/start", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type"}).status_code, 200)

    def test_scheduler_failure_is_reported_and_recovers(self):
        self.post("/config", {"finalization_grace_ms": 0})
        self.start()
        self.events()
        self.finish()
        service = self.app.extensions["vial_inspection_service"]
        with patch.object(service, "inspect", side_effect=RuntimeError("Storage error")):
            with self.assertLogs("recipes.tracker_manager", level="ERROR"):
                self.manager.update_all()
        self.assertEqual(self.get().json["tracker"]["state"], "FINALIZING")
        self.assertIsNotNone(self.get().json["scheduler"]["last_error"])
        self.manager.update_all()
        self.assertIsNone(self.get().json["scheduler"]["last_error"])
        self.assertEqual(self.get().json["tracker"]["state"], "INSPECTED")

    def test_scheduler_finishes_without_any_status_request_and_shuts_down(self):
        app = create_app({}, {"TESTING": True, "MODEL_MODE": "mock", "TRACKER_SCHEDULER_ENABLED": True})
        manager = app.extensions["tracker_manager"]
        self.addCleanup(manager.shutdown)
        client = app.test_client()
        completed = Event()
        service = app.extensions["vial_inspection_service"]
        inspect = service.inspect
        def recording(*args, **kwargs):
            result = inspect(*args, **kwargs)
            completed.set()
            return result
        with patch.object(service, "inspect", side_effect=recording):
            client.post(self.base + "/config", json={"finalization_grace_ms": 0}, headers=self.headers)
            client.post(self.base + "/start", json={"run_id": "RUN", "vial_id": "VIAL-1", "captured_at": 10}, headers=self.headers)
            for identifier, kind, timestamp in (("start", "DISPENSE_STARTED", 10), ("stop", "DISPENSE_STOPPED", 12)):
                body = {"event_id": identifier, "run_id": "RUN", "vial_id": "VIAL-1", "kind": kind,
                        "captured_at": timestamp, "dispense_id": "D1"}
                if kind == "DISPENSE_STARTED":
                    body["color"] = "blue"
                client.post(self.base + "/events", json=body, headers=self.headers)
            client.post(self.base + "/finish", json={"event_id": "done", "run_id": "RUN", "vial_id": "VIAL-1",
                                                      "captured_at": 12, "final_color": "blue"}, headers=self.headers)
            self.assertTrue(completed.wait(2), "Scheduler did not finalize independently")
        self.assertEqual(manager.get("FILL_1").snapshot().state, "INSPECTED")
        manager.shutdown()
        self.assertFalse(manager.scheduler_status("FILL_1")["running"])
        self.assertEqual(client.post(self.base + "/start", json={"run_id": "RUN", "vial_id": "VIAL-2",
                                                               "captured_at": 20}, headers=self.headers).status_code, 409)


if __name__ == "__main__":
    unittest.main()
