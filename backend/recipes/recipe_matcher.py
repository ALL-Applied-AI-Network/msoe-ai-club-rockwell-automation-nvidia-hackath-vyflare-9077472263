"""Weighted recipe comparison without storage access or workflow side effects."""

from dataclasses import dataclass
import math
import re
from typing import Iterable, Literal

from .matching_config import MatchingConfig
from .models import Recipe, RecipeCollection, VialObservation


@dataclass(frozen=True)
class FieldDifference:
    field: str
    expected: object
    observed: object
    reason: str
    dispense_number: int | None = None
    tolerance: float | None = None
    within_tolerance: bool = False


@dataclass(frozen=True)
class MatchResult:
    compared_collection: RecipeCollection
    candidate_recipe_id: int | None
    similarity_score: float | None
    meets_threshold: bool
    status: Literal["MATCH", "NO_MATCH", "INSUFFICIENT_DATA"]
    differences: tuple[FieldDifference, ...]
    reasons: tuple[str, ...]
    feature_scores: tuple[tuple[str, float], ...]
    threshold_used: float
    config: MatchingConfig
    method_version: str = "weighted-recipe/1.0"


def _color_similarity(expected: str, observed: str) -> float:
    """Case-insensitive labels; normalized RGB distance for two hex colors.

    Labels have no inferred shade relationship. A label versus a hex value
    receives no similarity: callers must use a consistent representation.
    """
    expected, observed = expected.strip().casefold(), observed.strip().casefold()
    if expected == observed:
        return 1.0
    if all(re.fullmatch(r"#[0-9a-f]{6}", value) for value in (expected, observed)):
        left = tuple(int(expected[i:i+2], 16) for i in (1, 3, 5))
        right = tuple(int(observed[i:i+2], 16) for i in (1, 3, 5))
        return 1 - math.dist(left, right) / (255 * math.sqrt(3))
    return 0.0


class RecipeMatcher:
    """Share one immutable configuration across intended and unmatched searches.

    Count equality, all duration tolerances, and final-color tolerance are hard
    requirements independent of the score. Missing optional source data omits
    that feature and renormalizes remaining weights. MatchResult describes
    similarity within a collection; matching UNMATCHED is never a verification
    pass. The workflow decides that separately.
    """

    def __init__(self, config: MatchingConfig | None = None) -> None:
        self.config = config if config is not None else MatchingConfig()
        if not isinstance(self.config, MatchingConfig):
            raise TypeError("config must be a MatchingConfig")

    def find_best_match(self, observation: VialObservation, recipes: Iterable[Recipe],
                        collection: RecipeCollection) -> MatchResult:
        threshold = self.config.threshold_for(collection)
        if not isinstance(observation, VialObservation):
            raise TypeError("observation must be a VialObservation")
        candidates = tuple(recipes)
        if any(not isinstance(recipe, Recipe) for recipe in candidates):
            raise TypeError("candidates must be Recipe objects")
        if any(recipe.collection != collection for recipe in candidates):
            raise ValueError("all candidates must belong to the requested collection")
        if len({recipe.id for recipe in candidates}) != len(candidates):
            raise ValueError("candidate recipe IDs must be unique")
        if not observation.filling_complete or not observation.dispenses or observation.final_color is None:
            return self._result(collection, threshold, "INSUFFICIENT_DATA",
                                "Completed filling, dispenses, and final color are required")
        if not candidates:
            return self._result(collection, threshold, "NO_MATCH", "Recipe collection is empty")
        compared = [self._compare(observation, recipe, threshold)
                    for recipe in candidates if recipe.final_color is not None]
        skipped = len(compared) != len(candidates)
        if not compared:
            return self._result(collection, threshold, "INSUFFICIENT_DATA",
                                "Candidate recipes are missing required final color")
        # Prefer qualifying candidates over higher-scoring candidates that fail
        # a hard requirement. Resolve equal scores by lowest recipe ID.
        best = max(compared, key=lambda result: (
            result.status == "MATCH", result.similarity_score, -result.candidate_recipe_id))
        if best.status != "MATCH" and skipped:
            return self._result(collection, threshold, "INSUFFICIENT_DATA",
                                "Some candidates lack final color; no complete candidate matched",
                                best)
        return best

    def _result(self, collection, threshold, status, reason, candidate=None):
        return MatchResult(
            compared_collection=collection,
            candidate_recipe_id=candidate.candidate_recipe_id if candidate else None,
            similarity_score=candidate.similarity_score if candidate else None,
            meets_threshold=False, status=status,
            differences=candidate.differences if candidate else (), reasons=(reason,),
            feature_scores=candidate.feature_scores if candidate else (),
            threshold_used=threshold, config=self.config,
        )

    def _compare(self, observation: VialObservation, recipe: Recipe, threshold: float) -> MatchResult:
        config = self.config
        expected, observed = recipe.dispenses, observation.dispenses
        differences = []
        failures = []
        count_ok = len(expected) == len(observed)
        count_score = min(len(expected), len(observed)) / max(len(expected), len(observed))
        if not count_ok:
            failures.append("Dispense count must match exactly")
            differences.append(FieldDifference("dispense_count", len(expected), len(observed), failures[-1]))

        # Sorting both duration sequences provides the minimum absolute-error
        # pairing on this one-dimensional feature without trusting color/order.
        expected_durations = sorted(enumerate(expected), key=lambda item: item[1].duration_seconds)
        observed_durations = sorted(enumerate(observed), key=lambda item: item[1].duration_seconds)
        duration_scores = []
        for (expected_index, reference), (observed_index, actual) in zip(expected_durations, observed_durations):
            error = abs(reference.duration_seconds - actual.duration_seconds)
            tolerance = max(config.duration_absolute_tolerance_seconds,
                            config.duration_relative_tolerance * reference.duration_seconds)
            within = error <= tolerance or math.isclose(error, tolerance, rel_tol=0, abs_tol=1e-12)
            duration_scores.append(min(reference.duration_seconds, actual.duration_seconds) /
                                   max(reference.duration_seconds, actual.duration_seconds))
            if not within:
                failures.append(f"Observed dispense {observed_index + 1} exceeds duration tolerance")
            if error:
                differences.append(FieldDifference(
                    f"dispenses[{observed_index}].duration_seconds", reference.duration_seconds,
                    actual.duration_seconds,
                    f"Compared with reference dispense {expected_index + 1} by sorted duration (seconds)",
                    observed_index + 1, tolerance, within))
        for index, dispense in expected_durations[len(observed_durations):]:
            differences.append(FieldDifference(f"dispenses[{index}]", dispense, None,
                                               "Missing dispense (duration pairing)", index + 1))
        for index, dispense in observed_durations[len(expected_durations):]:
            differences.append(FieldDifference(f"dispenses[{index}]", None, dispense,
                                               "Extra dispense (duration pairing)", index + 1))
        duration_score = sum(duration_scores) / max(len(expected), len(observed))

        final_score = _color_similarity(recipe.final_color, observation.final_color)
        color_distance = 1 - final_score
        color_ok = color_distance <= config.final_color_tolerance or math.isclose(
            color_distance, config.final_color_tolerance, rel_tol=0, abs_tol=1e-12)
        if not color_ok:
            failures.append("Final color exceeds tolerance")
        if final_score != 1:
            differences.append(FieldDifference("final_color", recipe.final_color, observation.final_color,
                                               "Normalized RGB distance, or exact label comparison",
                                               tolerance=config.final_color_tolerance,
                                               within_tolerance=color_ok))

        color_order_score = sum(_color_similarity(left.color, right.color)
                                for left, right in zip(expected, observed)) / max(len(expected), len(observed))
        for index, (left, right) in enumerate(zip(expected, observed)):
            if _color_similarity(left.color, right.color) != 1:
                differences.append(FieldDifference(f"dispenses[{index}].color", left.color, right.color,
                                                   "Low-weight sequence comparison", index + 1))
        scores = {"duration": duration_score, "count": count_score,
                  "final_color": final_score, "color_order": color_order_score}
        weights = {"duration": config.duration_weight, "count": config.count_weight,
                   "final_color": config.final_color_weight, "color_order": config.color_order_weight}
        if all(dispense.source is not None for dispense in (*expected, *observed)):
            source_scores = []
            for index, (left, right) in enumerate(zip(expected, observed)):
                same = left.source.strip().casefold() == right.source.strip().casefold()
                source_scores.append(float(same))
                if not same:
                    differences.append(FieldDifference(f"dispenses[{index}].source", left.source, right.source,
                                                       "Low-weight source-order comparison", index + 1))
            scores["source_order"] = sum(source_scores) / max(len(expected), len(observed))
            weights["source_order"] = config.source_order_weight
        score = math.fsum(scores[name] * weight for name, weight in weights.items()) / math.fsum(weights.values())
        # Round only machine arithmetic noise, not to a display percentage.
        score = round(score, 12)
        matches = count_ok and not failures and score >= threshold
        if not failures and not matches:
            failures.append("Weighted similarity is below threshold")
        return MatchResult(recipe.collection, recipe.id, score, matches,
                           "MATCH" if matches else "NO_MATCH", tuple(differences),
                           tuple(failures) if failures else ("Mandatory checks and threshold passed",),
                           tuple(scores.items()), threshold, config)
