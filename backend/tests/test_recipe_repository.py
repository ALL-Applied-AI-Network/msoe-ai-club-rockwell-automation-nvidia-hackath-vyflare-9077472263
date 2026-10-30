import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from unittest.mock import patch

from recipes import Dispense, Recipe
from recipes.recipe_repository import RecipeRepository


class RecipeRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repository = RecipeRepository()
        self.intended = Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue")
        self.unmatched = Recipe(2, "UNMATCHED", (Dispense("yellow", 3),))

    def test_add_get_and_list_keep_collections_separate(self):
        self.repository.add_recipe(self.unmatched)
        self.repository.add_recipe(self.intended)
        self.assertEqual(self.repository.get_recipe(2), self.unmatched)
        self.assertEqual(self.repository.list_recipes("INTENDED"), (self.intended,))
        self.assertEqual(self.repository.list_recipes("UNMATCHED"), (self.unmatched,))
        self.assertIsNone(self.repository.get_recipe(99))
        self.assertEqual(self.repository.list_collection_changes(1), ())

    def test_duplicate_id_is_rejected_even_in_another_collection(self):
        self.repository.add_recipe(self.intended)
        for recipe in (self.intended, replace(self.intended, collection="UNMATCHED")):
            with self.assertRaises(ValueError):
                self.repository.add_recipe(recipe)
        self.assertEqual(self.repository.get_recipe(1), self.intended)
        self.assertEqual(self.repository.list_recipes("UNMATCHED"), ())

    def test_update_changes_metadata_without_changing_original(self):
        self.repository.add_recipe(self.intended)
        updated = replace(self.intended, dispenses=(Dispense("green", 4),), final_color="green")
        self.assertEqual(self.repository.update_recipe(updated), updated)
        self.assertEqual(self.repository.get_recipe(1), updated)
        self.assertEqual(self.intended.final_color, "blue")
        self.assertEqual(self.repository.list_collection_changes(1), ())

    def test_unknown_updates_and_implicit_moves_leave_storage_unchanged(self):
        self.repository.add_recipe(self.intended)
        with self.assertRaises(KeyError):
            self.repository.update_recipe(self.unmatched)
        with self.assertRaises(ValueError):
            self.repository.update_recipe(replace(self.intended, collection="UNMATCHED"))
        self.assertEqual(self.repository.get_recipe(1), self.intended)
        self.assertIsNone(self.repository.get_recipe(2))

    def test_promotion_and_demotion_preserve_identity_and_record_history(self):
        self.repository.add_recipe(self.unmatched)
        promoted = self.repository.promote_to_intended(2, "operator-7", "Approved new pattern")
        first_history = self.repository.list_collection_changes(2)
        self.assertEqual(promoted.id, 2)
        self.assertEqual(promoted.dispenses, self.unmatched.dispenses)
        self.assertEqual(self.repository.list_recipes("UNMATCHED"), ())
        self.assertEqual(self.repository.list_recipes("INTENDED"), (promoted,))
        self.assertEqual(self.unmatched.collection, "UNMATCHED")
        demoted = self.repository.demote_to_unmatched(2, "operator-8", "Reference withdrawn")
        changes = self.repository.list_collection_changes(2)
        self.assertEqual(demoted, self.unmatched)
        self.assertEqual(self.repository.list_recipes("INTENDED"), ())
        self.assertEqual(len(changes), 2)
        self.assertEqual(len(first_history), 1)  # Prior snapshots stay unchanged.
        self.assertEqual(changes[0].previous_collection, "UNMATCHED")
        self.assertEqual(changes[0].new_collection, "INTENDED")
        self.assertEqual(changes[1].previous_collection, "INTENDED")
        self.assertEqual(changes[1].new_collection, "UNMATCHED")
        self.assertEqual(changes[0].recipe_id, 2)
        self.assertEqual(changes[0].changed_by, "operator-7")
        self.assertEqual(changes[0].reason, "Approved new pattern")
        self.assertNotEqual(changes[0].change_id, changes[1].change_id)
        self.assertEqual(changes[0].changed_at.utcoffset(), timedelta(0))
        with self.assertRaises(FrozenInstanceError):
            changes[0].reason = "changed"

    def test_repeated_moves_are_idempotent(self):
        self.repository.add_recipe(self.unmatched)
        self.repository.demote_to_unmatched(2, "operator", "Already unmatched")
        self.assertEqual(self.repository.list_collection_changes(2), ())
        self.repository.promote_to_intended(2, "operator", "Approved")
        self.repository.promote_to_intended(2, "operator", "Retry")
        self.assertEqual(len(self.repository.list_collection_changes(2)), 1)

    def test_unknown_move_and_history_lookup_raise_not_found(self):
        for operation in (lambda: self.repository.promote_to_intended(99, "operator", "Approved"),
                          lambda: self.repository.demote_to_unmatched(99, "operator", "Removed"),
                          lambda: self.repository.list_collection_changes(99)):
            with self.assertRaises(KeyError):
                operation()

    def test_invalid_change_metadata_leaves_collection_and_history_unchanged(self):
        self.repository.add_recipe(self.unmatched)
        for actor, reason in (("", "Approved"), ("operator", "  "), (None, "Approved"), ("operator", 3)):
            with self.subTest(actor=actor, reason=reason):
                with self.assertRaises((TypeError, ValueError)):
                    self.repository.promote_to_intended(2, actor, reason)
        self.assertEqual(self.repository.get_recipe(2), self.unmatched)
        self.assertEqual(self.repository.list_collection_changes(2), ())

    def test_history_preparation_failure_does_not_partially_move_recipe(self):
        self.repository.add_recipe(self.unmatched)
        with patch("recipes.recipe_repository.uuid4", side_effect=RuntimeError("ID failure")):
            with self.assertRaises(RuntimeError):
                self.repository.promote_to_intended(2, "operator", "Approved")
        self.assertEqual(self.repository.get_recipe(2), self.unmatched)
        self.assertEqual(self.repository.list_recipes("INTENDED"), ())
        self.assertEqual(self.repository.list_collection_changes(2), ())

    def test_invalid_inputs_do_not_alias_integer_identifiers(self):
        self.repository.add_recipe(self.intended)
        for identifier in (True, "1", None, 0, -1):
            with self.subTest(identifier=identifier):
                with self.assertRaises((TypeError, ValueError)):
                    self.repository.get_recipe(identifier)
                with self.assertRaises((TypeError, ValueError)):
                    self.repository.promote_to_intended(identifier, "operator", "Approved")
        with self.assertRaises(ValueError):
            self.repository.list_recipes("MATCHED")
        for operation in (self.repository.add_recipe, self.repository.update_recipe):
            with self.assertRaises(TypeError):
                operation({"id": 3})

    def test_list_returns_snapshot_and_repositories_are_independent(self):
        self.repository.add_recipe(self.intended)
        snapshot = self.repository.list_recipes("INTENDED")
        self.repository.demote_to_unmatched(1, "operator", "Removed")
        self.assertEqual(snapshot, (self.intended,))
        self.assertEqual(RecipeRepository().list_recipes("UNMATCHED"), ())

    def test_concurrent_promotions_create_only_one_history_entry(self):
        self.repository.add_recipe(self.unmatched)
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(
                lambda _: self.repository.promote_to_intended(2, "operator", "Approved"), range(12)))
        self.assertTrue(all(recipe.collection == "INTENDED" for recipe in results))
        self.assertEqual(len(self.repository.list_collection_changes(2)), 1)
        self.assertEqual(len(self.repository.list_recipes("INTENDED")), 1)
        self.assertEqual(self.repository.list_recipes("UNMATCHED"), ())


if __name__ == "__main__":
    unittest.main()
