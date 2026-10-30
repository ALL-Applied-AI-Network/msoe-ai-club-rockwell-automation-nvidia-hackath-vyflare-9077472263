"""Central defaults for one station's observation update loop."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class TrackerConfig:
    update_interval_ms: float = 100.0
    finalization_grace_ms: float = 1000.0

    def __post_init__(self) -> None:
        for name in ("update_interval_ms", "finalization_grace_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.update_interval_ms == 0:
            raise ValueError("update_interval_ms must be positive")

    @property
    def update_interval_seconds(self) -> float:
        return self.update_interval_ms / 1000

    @property
    def finalization_grace_seconds(self) -> float:
        return self.finalization_grace_ms / 1000
