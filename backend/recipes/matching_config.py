"""All matching defaults live here; inject one config into RecipeMatcher.

Timing and RGB tolerances are initial engineering defaults, not calibrated
measurements. Both recipe collections use these rules unless overridden below.
"""

from dataclasses import dataclass, fields
import math


@dataclass(frozen=True)
class MatchingConfig:
    threshold: float = 0.90
    unmatched_threshold: float | None = None
    duration_weight: float = 0.35
    count_weight: float = 0.30
    final_color_weight: float = 0.25
    color_order_weight: float = 0.05
    source_order_weight: float = 0.05
    duration_absolute_tolerance_seconds: float = 0.30
    duration_relative_tolerance: float = 0.10
    final_color_tolerance: float = 0.0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "unmatched_threshold" and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field.name} must be a number")
            try:
                valid = math.isfinite(value) and value >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{field.name} must be finite and nonnegative")
            if field.name != "duration_absolute_tolerance_seconds" and value > 1:
                raise ValueError(f"{field.name} must be between 0 and 1")
        weights = (self.duration_weight, self.count_weight, self.final_color_weight,
                   self.color_order_weight, self.source_order_weight)
        if not math.isclose(sum(weights), 1.0, rel_tol=0, abs_tol=1e-9):
            raise ValueError("feature weights must sum to 1")
        if min(weights[:3]) <= 0:
            raise ValueError("duration, count, and final color must have positive weights")

    def threshold_for(self, collection: str) -> float:
        if collection not in ("INTENDED", "UNMATCHED"):
            raise ValueError("collection must be INTENDED or UNMATCHED")
        if collection == "UNMATCHED" and self.unmatched_threshold is not None:
            return self.unmatched_threshold
        return self.threshold
