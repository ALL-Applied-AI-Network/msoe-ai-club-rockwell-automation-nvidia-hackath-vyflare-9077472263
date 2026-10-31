import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

from recipes import Dispense, Recipe, RecipeMatcher, RecipeRepository, VialObservation
from recipes.inspection_repository import InspectionRepository
from recipes.vial_inspection_service import VialInspectionService


class VialInspectionTests(unittest.TestCase):
    def setUp(self):
        self.recipes = RecipeRepository()
        self.inspections = InspectionRepository()
        self.service = VialInspectionService(self.recipes, self.inspections)
        self.observation = VialObservation("RUN-1", "VIAL-1", (Dispense("blue", 2),), "blue", True)

    def seed(self, identifier=1, collection="INTENDED", color="blue"):
        recipe = Recipe(identifier, collection, self.observation.dispenses, color)
        self.recipes.add_recipe(recipe)
        return recipe

    def test_intended_match_passes_and_skips_unmatched_search(self):
        recipe = self.seed()
        with patch.object(self.service.matcher, "find_best_match",
                          wraps=self.service.matcher.find_best_match) as matching:
            result = self.service.inspect(self.observation, "INS-1")
        self.assertEqual(matching.call_count, 1)
        self.assertEqual(result.verification_status, "PASS")
        self.assertEqual(result.recipe_snapshot, recipe)
        self.assertEqual(result.recipe_collection, "INTENDED")
        self.assertIsNone(result.unmatched_comparison)
        self.assertFalse(result.created_new_recipe)
        self.assertEqual(self.inspections.get_inspection("INS-1"), result)
        self.assertEqual(self.inspections.get_for_vial("RUN-1", "VIAL-1"), result)

    def test_reuses_unmatched_pattern_but_keeps_failed_verification_and_differences(self):
        self.seed(color="green")
        self.seed(identifier=2, collection="UNMATCHED")
        result = self.service.inspect(self.observation)
        self.assertEqual(result.verification_status, "FAIL")
        self.assertEqual(result.recipe_id, 2)
        self.assertEqual(result.unmatched_comparison.status, "MATCH")
        self.assertFalse(result.created_new_recipe)
        self.assertEqual(result.intended_comparison.candidate_recipe_id, 1)
        self.assertTrue(any(d.field == "final_color" for d in result.intended_comparison.differences))
        self.assertEqual(len(self.recipes.list_recipes("UNMATCHED")), 1)

    def test_creates_unique_unmatched_pattern_and_reuses_it_for_another_vial(self):
        self.seed(identifier=20, color="green")
        self.seed(identifier=30, collection="UNMATCHED", color="red")
        first = self.service.inspect(self.observation)
        second = self.service.inspect(replace(self.observation, vial_id="VIAL-2"))
        self.assertEqual(first.recipe_id, 31)
        self.assertTrue(first.created_new_recipe)
        self.assertEqual(first.unmatched_comparison.status, "NO_MATCH")
        self.assertEqual(second.recipe_id, first.recipe_id)
        self.assertFalse(second.created_new_recipe)
        self.assertEqual(second.unmatched_comparison.status, "MATCH")
        self.assertEqual(self.inspections.list_inspections_for_recipe(31), (first, second))

    def test_empty_reference_collection_learns_only_unmatched(self):
        result = self.service.inspect(self.observation)
        self.assertEqual((result.verification_status, result.recipe_collection), ("FAIL", "UNMATCHED"))
        self.assertTrue(result.created_new_recipe)
        self.assertEqual(self.recipes.list_recipes("INTENDED"), ())

    def test_insufficient_observations_are_saved_without_recipe_creation(self):
        for index, changes in enumerate((dict(filling_complete=False), dict(final_color=None), dict(dispenses=()))):
            observation = replace(self.observation, vial_id=f"VIAL-{index}", **changes)
            result = self.service.inspect(observation)
            self.assertEqual(result.verification_status, "INSUFFICIENT_DATA")
            self.assertIsNone(result.recipe_id)
            self.assertIsNone(result.recipe_snapshot)
            self.assertFalse(result.created_new_recipe)
            self.assertEqual(self.inspections.get_inspection(result.inspection_id), result)
        self.assertEqual(self.recipes.list_recipes("UNMATCHED"), ())

    def test_incomplete_intended_reference_blocks_learning(self):
        self.recipes.add_recipe(Recipe(1, "INTENDED", self.observation.dispenses))
        result = self.service.inspect(self.observation)
        self.assertEqual(result.verification_status, "INSUFFICIENT_DATA")
        self.assertIsNone(result.unmatched_comparison)
        self.assertEqual(self.recipes.list_recipes("UNMATCHED"), ())

    def test_incomplete_unmatched_reference_blocks_learning_and_retains_intended_failure(self):
        self.seed(color="green")
        self.recipes.add_recipe(Recipe(2, "UNMATCHED", self.observation.dispenses))
        result = self.service.inspect(self.observation)
        self.assertEqual(result.verification_status, "INSUFFICIENT_DATA")
        self.assertEqual(result.intended_comparison.status, "NO_MATCH")
        self.assertEqual(result.unmatched_comparison.status, "INSUFFICIENT_DATA")
        self.assertIsNone(result.recipe_id)
        self.assertEqual(len(self.recipes.list_recipes("UNMATCHED")), 1)

    def test_retries_return_original_without_recounting_or_creating_patterns(self):
        first = self.service.inspect(self.observation, "INS-1")
        self.assertIs(self.service.inspect(self.observation, "INS-1"), first)
        self.assertIs(self.service.inspect(self.observation), first)
        self.assertEqual(len(self.inspections.list_inspections_for_recipe(first.recipe_id)), 1)
        self.assertEqual(len(self.recipes.list_recipes("UNMATCHED")), 1)

    def test_conflicting_retry_and_reused_id_do_not_overwrite_history(self):
        first = self.service.inspect(self.observation, "INS-1")
        for observation, identifier in ((replace(self.observation, final_color="red"), "INS-1"),
                                        (self.observation, "INS-2"),
                                        (replace(self.observation, vial_id="VIAL-2"), "INS-1")):
            with self.subTest(observation=observation, identifier=identifier):
                with self.assertRaises(ValueError):
                    self.service.inspect(observation, identifier)
        self.assertEqual(self.inspections.get_inspection("INS-1"), first)
        self.assertIsNone(self.inspections.get_inspection("INS-2"))
        self.assertEqual(len(self.recipes.list_recipes("UNMATCHED")), 1)

    def test_promotion_affects_future_vials_without_rewriting_history(self):
        first = self.service.inspect(self.observation)
        self.recipes.promote_to_intended(first.recipe_id, "operator", "Approved")
        second = self.service.inspect(replace(self.observation, vial_id="VIAL-2"))
        self.assertEqual(second.verification_status, "PASS")
        self.assertEqual(second.recipe_id, first.recipe_id)
        self.assertEqual(first.verification_status, "FAIL")
        self.assertEqual(first.recipe_collection, "UNMATCHED")
        self.assertEqual(first.recipe_snapshot.collection, "UNMATCHED")
        self.assertIs(self.service.inspect(self.observation), first)
        self.assertEqual(len(self.inspections.list_inspections_for_recipe(first.recipe_id)), 2)

    def test_recipe_metadata_update_does_not_change_snapshot(self):
        original = self.seed()
        result = self.service.inspect(self.observation)
        self.recipes.update_recipe(replace(original, final_color="red"))
        self.assertEqual(result.recipe_snapshot.final_color, "blue")
        self.assertEqual(result.observation.final_color, "blue")
        with self.assertRaises(FrozenInstanceError):
            result.verification_status = "FAIL"

    def test_failure_after_inspection_save_rolls_back_both_repositories(self):
        save = self.inspections.save_inspection
        def save_then_fail(inspection):
            save(inspection)
            raise RuntimeError("Storage failed")
        with patch.object(self.inspections, "save_inspection", side_effect=save_then_fail):
            with self.assertRaises(RuntimeError):
                self.service.inspect(self.observation, "INS-1")
        self.assertEqual(self.recipes.list_recipes("UNMATCHED"), ())
        self.assertIsNone(self.inspections.get_inspection("INS-1"))
        self.assertIsNone(self.inspections.get_for_vial("RUN-1", "VIAL-1"))
        result = self.service.inspect(self.observation, "INS-1")
        self.assertTrue(result.created_new_recipe)

    def test_concurrent_vials_and_services_share_one_unmatched_pattern(self):
        other = VialInspectionService(self.recipes, self.inspections)
        def inspect(index):
            service = self.service if index % 2 else other
            return service.inspect(replace(self.observation, vial_id=f"VIAL-{index}"))
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(inspect, range(12)))
        self.assertEqual(sum(result.created_new_recipe for result in results), 1)
        self.assertEqual(len({result.recipe_id for result in results}), 1)
        self.assertEqual(len(self.recipes.list_recipes("UNMATCHED")), 1)
        self.assertEqual(len(self.inspections.list_inspections_for_recipe(results[0].recipe_id)), 12)

    def test_concurrent_retries_create_one_inspection(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.service.inspect(self.observation), range(12)))
        self.assertEqual(len({result.inspection_id for result in results}), 1)
        self.assertEqual(len(self.inspections.list_inspections_for_recipe(results[0].recipe_id)), 1)

    def test_inspection_repository_rejects_overwrites_and_keeps_snapshots(self):
        first = self.service.inspect(self.observation)
        self.assertIs(self.inspections.save_inspection(first), first)
        for candidate in (replace(first, inspection_id="ANOTHER"), replace(first, inspected_at=first.inspected_at.replace(year=2025))):
            with self.assertRaises(ValueError):
                self.inspections.save_inspection(candidate)
        snapshot = self.inspections.list_inspections_for_recipe(first.recipe_id)
        self.service.inspect(replace(self.observation, vial_id="VIAL-2"))
        self.assertEqual(snapshot, (first,))

    def test_invalid_inspection_state_and_inputs_are_rejected(self):
        result = self.service.inspect(self.observation)
        for changes in ({"verification_status": "PASS"}, {"recipe_id": 99},
                        {"recipe_snapshot": None}, {"inspection_id": ""},
                        {"inspected_at": result.inspected_at.replace(tzinfo=None)}):
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    replace(result, **changes)
        with self.assertRaises(TypeError):
            self.service.inspect(self.recipes.get_recipe(result.recipe_id))
        with self.assertRaises(ValueError):
            self.service.inspect(self.observation, " ")
        with self.assertRaises(TypeError):
            self.inspections.list_inspections_for_recipe(True)
        self.assertIsNone(self.inspections.get_inspection("missing"))

    def test_recipe_transaction_restores_metadata_and_history_on_failure(self):
        original = self.seed(collection="UNMATCHED")
        with self.assertRaises(RuntimeError):
            with self.recipes.transaction():
                self.recipes.promote_to_intended(1, "operator", "Approved")
                raise RuntimeError("Failure")
        self.assertEqual(self.recipes.get_recipe(1), original)
        self.assertEqual(self.recipes.list_collection_changes(1), ())

    def test_same_vial_identifier_in_different_runs_gets_separate_inspections(self):
        first = self.service.inspect(self.observation)
        second = self.service.inspect(replace(self.observation, run_id="RUN-2"))
        self.assertNotEqual(first.inspection_id, second.inspection_id)
        self.assertEqual(first.recipe_id, second.recipe_id)


if __name__ == "__main__":
    unittest.main()
