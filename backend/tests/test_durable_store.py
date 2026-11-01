from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from recipes import Dispense, Recipe, VialObservation, VialInspectionService
from recipes.durable import SQLiteStore


class DurableWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recipe.sqlite3"
        self.stores = []
        self.addCleanup(lambda: [s.close() for s in self.stores])

    def store(self):
        result = SQLiteStore(self.path)
        self.stores.append(result)
        return result

    def service(self, store, required=(1, 2)):
        return VialInspectionService(store.recipes, store.inspections, required_reference_ids=required)

    def references(self, store):
        store.recipes.add_recipe(Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue"))
        store.recipes.add_recipe(Recipe(2, "INTENDED", (Dispense("green", 3),), "green"))

    def test_empty_reference_coverage_cannot_learn_a_false_candidate(self):
        store = self.store()
        result = self.service(store).inspect(VialObservation("run", "vial", (Dispense("red", 4),), "red", True))
        self.assertEqual(result.verification_status, "INSUFFICIENT_DATA")
        self.assertIn("2 nominal recipes", " ".join(result.intended_comparison.reasons))
        self.assertEqual(store.recipes.list_recipes("UNMATCHED"), ())

    def test_matches_existing_complete_pattern_even_when_other_references_are_missing(self):
        store = self.store()
        store.recipes.add_recipe(Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue"))
        result = self.service(store).inspect(VialObservation("run", "vial", (Dispense("blue", 2),), "blue", True))
        self.assertEqual(result.verification_status, "PASS")
        self.assertEqual(result.recipe_id, 1)

    def test_candidate_reuse_inspection_history_and_approval_survive_reopening(self):
        store = self.store(); self.references(store)
        service = self.service(store)
        first = service.inspect(VialObservation("run", "one", (Dispense("red", 4),), "red", True))
        self.assertTrue(first.created_new_recipe)
        self.assertGreaterEqual(first.recipe_id, 100)
        reopened = self.store(); later = self.service(reopened)
        self.assertEqual(later.inspect(first.observation), first)
        second = later.inspect(VialObservation("run", "two", first.observation.dispenses, "red", True))
        self.assertFalse(second.created_new_recipe)
        self.assertEqual(second.recipe_id, first.recipe_id)
        reopened.recipes.promote_to_intended(first.recipe_id, "test-service", "Reviewed fixture")
        final = self.store()
        self.assertEqual(final.recipes.get_recipe(first.recipe_id).collection, "INTENDED")
        self.assertEqual(len(final.recipes.list_collection_changes(first.recipe_id)), 1)
        historical = final.inspections.get_inspection(first.inspection_id)
        self.assertEqual(historical.recipe_snapshot.collection, "UNMATCHED")
        self.assertEqual(historical.verification_status, "FAIL")
        self.assertEqual(len(final.inspections.list_inspections_for_recipe(first.recipe_id)), 2)

    def test_failure_rolls_back_candidate_and_inspection_together(self):
        store = self.store(); self.references(store)
        with patch.object(store.inspections, "save_inspection", side_effect=RuntimeError("test write failure")):
            with self.assertRaises(RuntimeError):
                self.service(store).inspect(VialObservation("run", "one", (Dispense("red", 4),), "red", True))
        self.assertEqual(self.store().recipes.list_recipes("UNMATCHED"), ())
        self.assertIsNone(store.inspections.get_for_vial("run", "one"))

    def test_two_database_connections_do_not_create_duplicate_candidates(self):
        first = self.store(); self.references(first); second = self.store()
        def inspect(pair):
            store, vial = pair
            return self.service(store).inspect(VialObservation("run", vial, (Dispense("red", 4),), "red", True))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(inspect, [(first, "one"), (second, "two")]))
        self.assertEqual(results[0].recipe_id, results[1].recipe_id)
        self.assertEqual(sum(r.created_new_recipe for r in results), 1)
        self.assertEqual(len(first.recipes.list_recipes("UNMATCHED")), 1)


class ImmutableAssessmentTests(unittest.TestCase):
    def test_assessment_replay_reopen_and_conflict_preserve_saved_history(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipes.sqlite3"
            store = SQLiteStore(path)
            try:
                first = {"assessment_id": "one", "revision": "v1", "generated_at": "original", "status": "INSUFFICIENT_EVIDENCE"}
                self.assertEqual(store.save_trial_assessment("video-1", "vial-1", first), first)
                replay = {**first, "generated_at": "retried"}
                self.assertEqual(store.save_trial_assessment("video-1", "vial-1", replay), first)
                for video, vial, data in (("video-2", "vial-1", first),
                                          ("video-1", "vial-2", first),
                                          ("video-1", "vial-1", {**first, "status": "CHANGED"})):
                    with self.assertRaises(ValueError):
                        store.save_trial_assessment(video, vial, data)
                self.assertEqual(store.trial_assessment_count(), 1)
            finally:
                store.close()
            reopened = SQLiteStore(path)
            try:
                self.assertEqual(reopened.list_trial_assessments("video-1"), [first])
                self.assertEqual(reopened.trial_assessment_count(), 1)
            finally:
                reopened.close()
