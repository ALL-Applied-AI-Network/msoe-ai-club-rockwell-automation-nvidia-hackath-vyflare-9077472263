import unittest
from dataclasses import replace

from recipes import Dispense, Recipe
from recipes.matching_config import MatchingConfig
from recipes.models import VialObservation
from recipes.recipe_matcher import RecipeMatcher


class RecipeMatcherTests(unittest.TestCase):
    def setUp(self):
        self.recipe = Recipe(1, "INTENDED", (
            Dispense("blue", 2, "T100"), Dispense("yellow", 4, "T200")), "green")
        self.observation = VialObservation("RUN-1", "VIAL-1", self.recipe.dispenses, "green", True)
        self.matcher = RecipeMatcher()

    def match(self, observation=None, recipe=None, config=None):
        recipe = recipe or self.recipe
        matcher = RecipeMatcher(config) if config else self.matcher
        return matcher.find_best_match(observation or self.observation, [recipe], recipe.collection)

    def test_exact_match_has_full_score_and_config_snapshot(self):
        result = self.match()
        self.assertEqual(result.status, "MATCH")
        self.assertEqual(result.similarity_score, 1)
        self.assertEqual(result.differences, ())
        self.assertEqual(result.threshold_used, 0.9)
        self.assertEqual(result.config, MatchingConfig())

    def test_exactly_ninety_percent_matches_despite_both_order_features(self):
        observation = replace(self.observation, dispenses=tuple(reversed(self.recipe.dispenses)))
        result = self.match(observation)
        self.assertEqual(result.status, "MATCH")
        self.assertEqual(result.similarity_score, 0.9)
        self.assertTrue(result.meets_threshold)
        self.assertEqual(dict(result.feature_scores)["duration"], 1)
        self.assertTrue(any(d.field == "dispenses[0].color" for d in result.differences))

    def test_duration_tolerance_is_inclusive_and_reports_expected_observed(self):
        observation = replace(self.observation, dispenses=(Dispense("blue", 2.3, "T100"), self.recipe.dispenses[1]))
        result = self.match(observation)
        self.assertEqual(result.status, "MATCH")
        difference = next(d for d in result.differences if d.field.endswith("duration_seconds"))
        self.assertEqual((difference.expected, difference.observed, difference.tolerance), (2, 2.3, 0.3))
        self.assertTrue(difference.within_tolerance)

    def test_duration_failure_cannot_be_compensated_by_high_score(self):
        config = replace(MatchingConfig(), duration_relative_tolerance=0)
        recipe = replace(self.recipe, dispenses=(Dispense("blue", 100, "T100"),))
        observation = replace(self.observation, dispenses=(Dispense("blue", 100.4, "T100"),))
        result = self.match(observation, recipe, config)
        self.assertGreater(result.similarity_score, 0.9)
        self.assertEqual(result.status, "NO_MATCH")
        self.assertFalse(result.meets_threshold)

    def test_count_failure_remains_mandatory_with_low_count_weight(self):
        config = MatchingConfig(duration_weight=.01, count_weight=.01, final_color_weight=.98,
                                color_order_weight=0, source_order_weight=0)
        observation = replace(self.observation, dispenses=self.observation.dispenses + (Dispense("blue", 3),))
        result = self.match(observation, config=config)
        self.assertGreater(result.similarity_score, .9)
        self.assertEqual(result.status, "NO_MATCH")
        self.assertTrue(any(d.field == "dispense_count" for d in result.differences))
        self.assertTrue(any("Extra dispense" in d.reason for d in result.differences))
        missing = self.match(replace(self.observation, dispenses=self.observation.dispenses[:1]))
        self.assertTrue(any("Missing dispense" in d.reason for d in missing.differences))

    def test_final_color_is_mandatory_even_at_a_low_threshold(self):
        result = self.match(replace(self.observation, final_color="red"), config=MatchingConfig(threshold=.5))
        self.assertEqual(result.status, "NO_MATCH")
        self.assertTrue(any(d.field == "final_color" for d in result.differences))

    def test_missing_or_unfinished_observations_are_insufficient(self):
        for observation in (replace(self.observation, filling_complete=False),
                            replace(self.observation, final_color=None),
                            replace(self.observation, dispenses=())):
            with self.subTest(observation=observation):
                self.assertEqual(self.match(observation).status, "INSUFFICIENT_DATA")

    def test_hex_tolerance_is_shared_and_adjustable(self):
        recipe = replace(self.recipe, final_color="#008000")
        observation = replace(self.observation, final_color="#008800")
        self.assertEqual(self.match(observation, recipe).status, "NO_MATCH")
        result = self.match(observation, recipe, MatchingConfig(final_color_tolerance=.03))
        self.assertEqual(result.status, "MATCH")
        self.assertTrue(next(d for d in result.differences if d.field == "final_color").within_tolerance)
        self.assertEqual(self.match(replace(self.observation, final_color=" GREEN ")).status, "MATCH")

    def test_shared_duration_settings_change_both_collection_comparisons(self):
        observation = replace(self.observation, dispenses=(Dispense("blue", 2.5, "T100"), self.recipe.dispenses[1]))
        for collection in ("INTENDED", "UNMATCHED"):
            recipe = replace(self.recipe, collection=collection)
            self.assertEqual(self.match(observation, recipe).status, "NO_MATCH")
            self.assertEqual(self.match(observation, recipe, MatchingConfig(
                duration_absolute_tolerance_seconds=.6)).status, "MATCH")

    def test_unmatched_reuses_shared_threshold_unless_overridden(self):
        recipe = replace(self.recipe, collection="UNMATCHED")
        observation = replace(self.observation, dispenses=tuple(reversed(self.recipe.dispenses)))
        result = self.match(observation, recipe)
        self.assertEqual((result.status, result.compared_collection, result.threshold_used),
                         ("MATCH", "UNMATCHED", .9))
        result = self.match(observation, recipe, MatchingConfig(unmatched_threshold=.95))
        self.assertEqual(result.status, "NO_MATCH")
        self.assertEqual(result.threshold_used, .95)

    def test_missing_optional_source_is_omitted_without_rejecting_observation(self):
        observation = replace(self.observation, dispenses=tuple(replace(d, source=None) for d in self.recipe.dispenses))
        result = self.match(observation)
        self.assertEqual(result.status, "MATCH")
        self.assertEqual(result.similarity_score, 1)
        self.assertNotIn("source_order", dict(result.feature_scores))

    def test_best_candidate_selection_and_stable_tie_break(self):
        lower = replace(self.recipe, id=3)
        higher = replace(self.recipe, id=4)
        for candidates in ([higher, lower], [lower, higher]):
            result = self.matcher.find_best_match(self.observation, candidates, "INTENDED")
            self.assertEqual(result.candidate_recipe_id, 3)
        failing = replace(self.recipe, id=5, final_color="red")
        result = self.matcher.find_best_match(self.observation, [failing], "INTENDED")
        self.assertEqual((result.status, result.candidate_recipe_id), ("NO_MATCH", 5))

    def test_qualifying_candidate_wins_over_higher_score_with_failed_gate(self):
        observation = replace(self.observation, dispenses=(Dispense("red", 100, "X"),))
        failing = Recipe(1, "INTENDED", (Dispense("red", 100.4, "X"),), "green")
        passing = Recipe(2, "INTENDED", (Dispense("blue", 100, "Y"),), "green")
        matcher = RecipeMatcher(MatchingConfig(duration_relative_tolerance=0))
        result = matcher.find_best_match(observation, [failing, passing], "INTENDED")
        self.assertEqual((result.status, result.candidate_recipe_id), ("MATCH", 2))

    def test_empty_and_incomplete_reference_collections(self):
        empty = self.matcher.find_best_match(self.observation, [], "INTENDED")
        self.assertEqual((empty.status, empty.candidate_recipe_id), ("NO_MATCH", None))
        incomplete = replace(self.recipe, final_color=None)
        self.assertEqual(self.match(recipe=incomplete).status, "INSUFFICIENT_DATA")
        failing = replace(self.recipe, id=2, final_color="red")
        result = self.matcher.find_best_match(self.observation, [incomplete, failing], "INTENDED")
        self.assertEqual(result.status, "INSUFFICIENT_DATA")
        self.assertEqual(result.candidate_recipe_id, 2)
        passing = replace(self.recipe, id=3)
        self.assertEqual(self.matcher.find_best_match(
            self.observation, [incomplete, passing], "INTENDED").status, "MATCH")

    def test_mixed_collections_duplicate_ids_and_wrong_types_are_rejected(self):
        for recipes in ([replace(self.recipe, collection="UNMATCHED")], [self.recipe, self.recipe], ["recipe"]):
            with self.subTest(recipes=recipes):
                with self.assertRaises((TypeError, ValueError)):
                    self.matcher.find_best_match(self.observation, recipes, "INTENDED")
        with self.assertRaises(TypeError):
            self.matcher.find_best_match(self.recipe, [self.recipe], "INTENDED")

    def test_configuration_rejects_invalid_settings(self):
        for settings in ({"threshold": 1.1}, {"threshold": True}, {"threshold": float("nan")},
                         {"unmatched_threshold": -.1}, {"duration_weight": .8},
                         {"final_color_tolerance": -1}, {"duration_absolute_tolerance_seconds": float("inf")},
                         {"duration_weight": 0, "count_weight": .65}):
            with self.subTest(settings=settings):
                with self.assertRaises((TypeError, ValueError)):
                    MatchingConfig(**settings)

    def test_observation_copies_sequence_and_validates_fields(self):
        dispenses = list(self.recipe.dispenses)
        observation = replace(self.observation, dispenses=dispenses)
        dispenses.clear()
        self.assertEqual(len(observation.dispenses), 2)
        for values in ({"run_id": ""}, {"vial_id": " "}, {"filling_complete": 1},
                       {"dispenses": [None]}, {"final_color": ""}):
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    replace(self.observation, **values)


if __name__ == "__main__":
    unittest.main()
