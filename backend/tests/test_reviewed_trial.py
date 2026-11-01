from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import create_app
from recipes.reviewed_trial import ASSETS, ReviewedTrialEngine, compare_color, compare_timing, validate_shape
from recipes.workflow_api import load_reference_catalog


def profile(recipe_id=7, bounds=None, rgb=None, uid="reference"):
    return {"recipe_id": recipe_id, "duration_bounds_s": bounds or [[1, 1]], "vial_uid": uid,
            "raw_rgb": {"nominal": rgb or [0, 0, 0]}}


class TrialComparisonTests(unittest.TestCase):
    def setUp(self):
        catalog, sha = load_reference_catalog()
        self.engine = ReviewedTrialEngine(catalog, sha)

    def test_interval_edges_and_full_containment_are_distinct(self):
        p = [profile()]
        self.assertEqual(compare_timing([[1, 2]], p, 1)["status"], "UNIQUE_TIMING_CANDIDATE")
        self.assertEqual(compare_timing([[2, 3]], p, 1)["status"], "BOUNDARY_UNCERTAIN")
        self.assertEqual(compare_timing([[2.000001, 3]], p, 1)["status"], "NO_COMPATIBLE_REFERENCE")

    def test_ambiguity_is_by_recipe_id_not_reference_count(self):
        same_id = [profile(uid="a"), profile(uid="b")]
        self.assertEqual(compare_timing([[1, 1]], same_id, 1)["status"], "UNIQUE_TIMING_CANDIDATE")
        other_id = same_id + [profile(8, uid="c")]
        self.assertEqual(compare_timing([[1, 1]], other_id, 1)["status"], "AMBIGUOUS")

    def test_no_merging_profiles_or_reordering_or_discarding_episodes(self):
        p = [profile(bounds=[[1, 1], [8, 8]], uid="a"), profile(bounds=[[8, 8], [1, 1]], uid="b")]
        self.assertEqual(compare_timing([[1, 1], [1, 1]], p, 1)["possible_recipe_ids"], [])
        self.assertEqual(compare_timing([[8, 8], [1, 1]], p[:1], 1)["possible_recipe_ids"], [])
        self.assertEqual(compare_timing([[1, 1]], p, 1)["possible_recipe_ids"], [])

    def test_invalid_intervals_and_nonfinite_allowances_rejected(self):
        for bounds, allowance in [([[2, 1]], 1), ([[float("nan"), 2]], 1), ([[1, 1]], -1), ([[1, 1]], float("inf"))]:
            with self.subTest(bounds=bounds, allowance=allowance), self.assertRaises(ValueError):
                compare_timing(bounds, [profile()], allowance)

    def color(self, rgb=None, temporal=2.24, region=2.45, candidates=None, failures=None):
        return compare_color({"raw_rgb": {"nominal": rgb or [24.10, 0, 0], "temporal_distance": temporal,
            "region_distance": region}, "phase_note": "Synthetic unit fixture", "qualitative_reliability_failures": failures or []},
            [7] if candidates is None else candidates, [profile()], self.engine.rules)

    def test_literal_color_limit_edges(self):
        self.assertEqual(self.color()["status"], "CONSISTENT")
        self.assertEqual(self.color([24.100001, 0, 0])["status"], "CONFLICTING")
        self.assertEqual(self.color(temporal=2.240001)["status"], "UNRELIABLE")
        self.assertEqual(self.color(region=2.450001)["status"], "UNRELIABLE")

    def test_qualitative_failure_overrides_numeric_agreement(self):
        c = self.color(failures=["GLARE_AFFECTED_REGION"])
        self.assertEqual(c["status"], "UNRELIABLE")
        self.assertIn("GLARE_AFFECTED_REGION", c["reasons"])

    def test_unreliable_and_not_evaluated_precedence(self):
        self.assertEqual(self.color(candidates=[])["status"], "NOT_EVALUATED")
        self.assertEqual(self.color(candidates=[], region=3)["status"], "UNRELIABLE")
        absent = {"raw_rgb": None, "phase_note": "Missing window"}
        self.assertEqual(compare_color(absent, [7], [profile()], self.engine.rules)["status"], "UNRELIABLE")
        p = profile(); p["raw_rgb"] = None
        sample = {"raw_rgb": {"nominal": [1, 2, 3], "temporal_distance": 0, "region_distance": 0}, "phase_note": "fixture"}
        self.assertEqual(compare_color(sample, [7], [p], self.engine.rules)["reasons"], ["MISSING_REFERENCE_COLOR"])

    def test_color_does_not_prune_ambiguous_timing_candidates(self):
        profiles = [profile(7, rgb=[0, 0, 0], uid="a"), profile(8, rgb=[100, 100, 100], uid="b")]
        timing = compare_timing([[1, 1]], profiles, 1)
        before = deepcopy(timing)
        c = compare_color({"raw_rgb": {"nominal": [0, 0, 0], "temporal_distance": 0, "region_distance": 0}, "phase_note": "fixture"},
                          timing["possible_recipe_ids"], profiles, self.engine.rules)
        self.assertEqual([p["experimental_band_result"] for p in c["comparisons"]], ["CONSISTENT", "CONFLICTING"])
        self.assertEqual(timing, before)
        self.assertEqual(timing["status"], "AMBIGUOUS")

    def test_changed_evidence_references_or_rules_changes_revision(self):
        original = self.engine.assess("video-1", "V1-V01")
        self.assertEqual(original["revision"], self.engine.assess("video-1", "V1-V01")["revision"])
        changes = [lambda e: e.rules.update(color_distance_limit=24.09),
                   lambda e: e.profiles[0].update(recording_id="corrected-provenance"),
                   lambda e: e.observations[("video-1", "V1-V01")]["reviewed_observation"].update(reviewNotes="new review")]
        for change in changes:
            catalog, sha = load_reference_catalog()
            engine = ReviewedTrialEngine(catalog, sha)
            change(engine)
            self.assertNotEqual(original["revision"], engine.assess("video-1", "V1-V01")["revision"])

    def test_actual_sample_timestamps_must_remain_inside_reviewed_window(self):
        observation = self.engine.observations[("video-1", "V1-V01")]
        before = self.engine.assess("video-1", "V1-V01")
        observation["reviewed_observation"]["flowEndUpper"] = observation["sampled_frames"][0]["actual_seconds"]
        after = self.engine.assess("video-1", "V1-V01")
        self.assertEqual(after["color"]["status"], "UNRELIABLE")
        self.assertIn("NO_VALIDATED_POSTFILL_WINDOW", after["color"]["reasons"])
        self.assertEqual(after["timing"], before["timing"])

    def test_tampered_assets_fail_closed(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)
            for source in ASSETS.iterdir():
                if source.is_file():
                    (target / source.name).write_bytes(source.read_bytes())
            catalog, sha = load_reference_catalog()
            with self.assertRaises(ValueError):
                ReviewedTrialEngine(catalog, "wrong-catalog", target)
            (target / "reviewed_trial.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "integrity"):
                ReviewedTrialEngine(catalog, sha, target)


class TrialAPITests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"INFERENCE_TOKEN": ""})
        env.start(); self.addCleanup(env.stop)
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "trial.sqlite3"
        self.apps = []
        self.addCleanup(self.close_apps)
        self.app = self.make_app()
        self.client = self.app.test_client()

    def close_apps(self):
        for app in self.apps:
            app.extensions["tracker_manager"].shutdown()
            if app.extensions["recipe_store"]:
                app.extensions["recipe_store"].close()

    def make_app(self, memory=False):
        config = {"TESTING": True, "MODEL_MODE": "mock", "RECIPE_DB_PATH": None if memory else str(self.path)}
        app = create_app({}, config)
        self.apps.append(app)
        return app

    def post(self, video="video-1", vial="V1-V11", client=None):
        response = (client or self.client).post(f"/api/recipe-workflow/trial/recorded/{video}/{vial}", json={})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["assessment"]

    def test_all_22_api_results_match_frozen_offline_examples(self):
        expected = json.loads((Path(__file__).parent / "fixtures/recipe_trial_expected.json").read_text())
        schema = self.app.extensions["recipe_trial_engine"].schema
        for wanted in expected:
            with self.subTest(vial=wanted["source"]["label"]):
                s = wanted["source"]
                actual = self.post(f'video-{s["video_number"]}', f'V{s["video_number"]}-V{s["vial_number"]:02}')
                validate_shape(actual, schema)
                for key in ("status", "possible_recipe_ids", "contained_recipe_ids", "duration_bounds_seconds",
                            "compatible_reference_profile_ids", "containing_reference_profile_ids"):
                    self.assertEqual(actual["timing"][key], wanted["timing"][key])
                for key in ("status", "rgb", "temporal_distance", "region_distance", "comparisons", "reasons"):
                    self.assertEqual(actual["color"][key], wanted["color"][key])
                for key in ("review_flags", "overall", "coverage", "source"):
                    self.assertEqual(actual[key], wanted[key])
        self.assertEqual(self.client.get("/api/recipe-workflow/trial/status").json["saved_assessment_count"], 22)
        self.assertEqual(self.client.get("/api/recipe-workflow/status").json["saved_assessment_count"], 0)
        for collection in ("INTENDED", "UNMATCHED"):
            self.assertFalse(self.app.extensions["recipe_repository"].list_recipes(collection))

    def test_retries_restart_and_new_versions_preserve_existing_assessments(self):
        self.client.post("/api/recipe-workflow/recorded/video-1/V1-V01", json={})
        store = self.app.extensions["recipe_store"]
        old_payload = store.connection.execute("SELECT payload FROM recipe_state").fetchone()[0]
        first = self.post()
        self.assertEqual(first, self.post())
        reopened = self.make_app()
        self.assertEqual(first, self.post(client=reopened.test_client()))
        self.app.extensions["recipe_trial_engine"].rules["color_distance_limit"] = 24.09
        second = self.post()
        self.assertNotEqual(first["assessment_id"], second["assessment_id"])
        history = self.client.get("/api/recipe-workflow/trial/videos/video-1/assessments").json
        self.assertTrue(history["includes_history"])
        self.assertEqual(history["assessments"], [second, first])
        self.assertEqual(store.connection.execute("SELECT payload FROM recipe_state").fetchone()[0], old_payload)
        self.assertEqual(self.client.get("/api/recipe-workflow/status").json["saved_assessment_count"], 1)

    def test_two_connections_retry_atomically(self):
        other = self.make_app()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda app: self.post(client=app.test_client()), [self.app, other]))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.app.extensions["recipe_store"].trial_assessment_count(), 1)

    def test_transaction_failure_rolls_back_trial_insert(self):
        store = self.app.extensions["recipe_store"]
        result = self.app.extensions["recipe_trial_engine"].assess("video-1", "V1-V11")
        with self.assertRaises(RuntimeError):
            with store.transaction():
                store.save_trial_assessment("video-1", "V1-V11", result)
                raise RuntimeError("injected failure")
        self.assertEqual(store.trial_assessment_count(), 0)

    def test_saved_result_cannot_be_mutated_under_same_revision(self):
        saved = self.post()
        changed = deepcopy(saved); changed["color"]["limitations"].append("unhashed mutation")
        store = self.app.extensions["recipe_store"]
        with self.assertRaises(ValueError):
            store.save_trial_assessment("video-1", "V1-V11", changed)
        self.assertEqual(store.list_trial_assessments("video-1"), [saved])

    def test_no_browser_observations_unknown_sources_and_authentication(self):
        url = "/api/recipe-workflow/trial/recorded/video-1/V1-V11"
        for payload in (None, [], {"recipe_id": 7}, {"raw_rgb": [1, 2, 3]}):
            self.assertEqual(self.client.post(url, json=payload).status_code, 400)
        self.assertEqual(self.client.post(url.replace("V1-V11", "V1-V99"), json={}).status_code, 404)
        self.assertEqual(self.client.get("/api/recipe-workflow/trial/videos/video-3/assessments").status_code, 404)
        with patch.dict("os.environ", {"INFERENCE_TOKEN": "test-token"}):
            for path in ("/api/recipe-workflow/trial/status", "/api/recipe-workflow/trial/videos/video-1/assessments"):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(self.client.get(path, headers={"Authorization": "Bearer test-token"}).status_code, 200)
            self.assertEqual(self.client.post(url, json={}).status_code, 401)
            self.assertEqual(self.client.post(url, json={}, headers={"Authorization": "Bearer test-token"}).status_code, 200)
        self.assertEqual(self.client.post(url, json={}, headers={"Origin": "https://foreign.invalid"}).status_code, 403)

    def test_in_memory_fixture_mode(self):
        client = self.make_app(memory=True).test_client()
        self.assertEqual(self.post(client=client), self.post(client=client))
        self.assertEqual(client.get("/api/recipe-workflow/trial/status").json["persistence"], "in_memory")
        self.assertEqual(len(client.get("/api/recipe-workflow/trial/videos/video-1/assessments").json["assessments"]), 1)


if __name__ == "__main__":
    unittest.main()
