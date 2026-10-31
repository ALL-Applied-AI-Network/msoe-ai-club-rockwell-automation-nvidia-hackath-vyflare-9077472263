import unittest
from dataclasses import FrozenInstanceError, replace

from recipes.models import Dispense, Recipe


class RecipeModelTests(unittest.TestCase):
    def test_completed_recipe_preserves_order_and_separate_final_color(self):
        blue = Dispense("blue", 2.5, "T200")
        yellow = Dispense("yellow", 1.8, "T100")
        recipe = Recipe(7, "INTENDED", (blue, yellow), "green")
        self.assertEqual(recipe.dispense_count, 2)
        self.assertEqual(recipe.dispenses, (blue, yellow))
        self.assertEqual(recipe.dispenses[0].source, "T200")
        self.assertEqual(recipe.final_color, "green")

    def test_unmatched_recipe_allows_optional_metadata_to_be_absent(self):
        recipe = Recipe(12, "UNMATCHED", (Dispense("blue", 2),))
        self.assertIsNone(recipe.final_color)
        self.assertIsNone(recipe.dispenses[0].source)

    def test_invalid_durations_are_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), -float("inf"), 10**400):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Dispense("blue", value)
        for value in (True, "2.5", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    Dispense("blue", value)

    def test_missing_or_blank_color_metadata_is_rejected(self):
        for field in ("color", "source"):
            for value in ("", "   ", 42):
                with self.subTest(field=field, value=value):
                    arguments = {"color": "blue", "duration_seconds": 2, field: value}
                    with self.assertRaises((TypeError, ValueError)):
                        Dispense(**arguments)
        with self.assertRaises(TypeError):
            Dispense(None, 2)
        for value in ("", "  ", 42):
            with self.subTest(final_color=value):
                with self.assertRaises((TypeError, ValueError)):
                    Recipe(1, "INTENDED", (Dispense("blue", 2),), value)

    def test_invalid_identifiers_and_collections_are_rejected(self):
        dispenses = (Dispense("blue", 2),)
        for identifier in (0, -1, True, "7", None):
            with self.subTest(identifier=identifier):
                with self.assertRaises((TypeError, ValueError)):
                    Recipe(identifier, "INTENDED", dispenses)
        for collection in ("MATCHED", "intended", "", None):
            with self.subTest(collection=collection):
                with self.assertRaises(ValueError):
                    Recipe(1, collection, dispenses)

    def test_dispenses_require_a_nonempty_ordered_sequence_of_objects(self):
        for dispenses in ([], (), None, "blue", {Dispense("blue", 2)}, [{"color": "blue"}]):
            with self.subTest(dispenses=dispenses):
                with self.assertRaises((TypeError, ValueError)):
                    Recipe(1, "INTENDED", dispenses)

    def test_caller_list_changes_cannot_modify_stored_recipe(self):
        original = [Dispense("blue", 2)]
        recipe = Recipe(1, "INTENDED", original)
        original.append(Dispense("yellow", 1))
        self.assertEqual(recipe.dispense_count, 1)
        self.assertEqual(recipe.dispenses, (Dispense("blue", 2),))
        with self.assertRaises(FrozenInstanceError):
            recipe.dispenses[0].color = "red"
        with self.assertRaises(FrozenInstanceError):
            recipe.collection = "UNMATCHED"

    def test_replacement_preserves_original_recipe_and_revalidates(self):
        recipe = Recipe(1, "UNMATCHED", (Dispense("blue", 2),))
        promoted = replace(recipe, collection="INTENDED")
        self.assertEqual(promoted.id, recipe.id)
        self.assertEqual(promoted.collection, "INTENDED")
        self.assertEqual(recipe.collection, "UNMATCHED")
        with self.assertRaises(ValueError):
            replace(recipe, dispenses=())


if __name__ == "__main__":
    unittest.main()
