"""Single-vial station tracker consuming timestamped events, not model calls."""

from dataclasses import dataclass
import math
from threading import Event, RLock
from time import monotonic
from typing import Callable, Literal

from .inspection_models import VialInspection
from .models import Dispense, VialObservation, _validate_text
from .tracker_config import TrackerConfig
from .vial_inspection_service import VialInspectionService


EventKind = Literal["DISPENSE_STARTED", "DISPENSE_STOPPED", "DISPENSE_COLOR",
                    "FINAL_COLOR", "FILLING_COMPLETED"]
TrackerState = Literal["IDLE", "FILLING", "FINALIZING", "INSPECTED"]


def _timestamp(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timestamp must be numeric seconds")
    if not math.isfinite(value) or value < 0:
        raise ValueError("timestamp must be finite and nonnegative")


@dataclass(frozen=True)
class TrackerEvent:
    """Capture timestamp in one shared source clock; event IDs deduplicate retries.

    Capture time may be video-relative seconds. It need not share an epoch with
    the monotonic scheduling clock, but all events in a vial must share a clock.
    Producers must report transitions reliably; the tracker cannot infer events
    that were never supplied.
    """

    event_id: str
    run_id: str
    vial_id: str
    kind: EventKind
    captured_at: float
    dispense_id: str | None = None
    color: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        for name in ("event_id", "run_id", "vial_id"):
            _validate_text(name, getattr(self, name))
        _timestamp(self.captured_at)
        if self.kind not in ("DISPENSE_STARTED", "DISPENSE_STOPPED", "DISPENSE_COLOR",
                             "FINAL_COLOR", "FILLING_COMPLETED"):
            raise ValueError("Unknown tracker event kind")
        _validate_text("color", self.color, optional=True)
        _validate_text("source", self.source, optional=True)
        if self.kind.startswith("DISPENSE_"):
            _validate_text("dispense_id", self.dispense_id)
        elif self.dispense_id is not None:
            raise ValueError("Vial-level events cannot specify dispense_id")
        if self.kind in ("DISPENSE_COLOR", "FINAL_COLOR") and self.color is None:
            raise ValueError("Color observations require color")
        if self.kind not in ("DISPENSE_STARTED", "DISPENSE_COLOR") and self.source is not None:
            raise ValueError("source is only valid for dispense observations")
        if self.kind == "DISPENSE_STOPPED" and self.color is not None:
            raise ValueError("Use DISPENSE_COLOR to provide dispense color")


@dataclass(frozen=True)
class ActiveDispenseSnapshot:
    dispense_id: str
    started_at: float
    last_observed_at: float
    color: str | None
    source: str | None
    duration_so_far_seconds: float


@dataclass(frozen=True)
class TrackerSnapshot:
    state: TrackerState
    observation: VialObservation | None
    active_dispense_ids: tuple[str, ...]
    issues: tuple[str, ...]
    last_processed_capture_at: float | None
    last_update_at: float | None
    inspection: VialInspection | None
    active_dispenses: tuple[ActiveDispenseSnapshot, ...] = ()


class ActiveVialTracker:
    """Track one active vial and inspect once after an explicit completion event.

    Call update() from a scheduler, or run(stop_event) in a caller-owned thread.
    No thread is started automatically. Scheduling uses monotonic time; durations
    use source capture time. Late events rebuild the current snapshot in capture
    order, including corrections received during the finalization grace period.
    A bounded grace period is not a guarantee all model results have arrived.
    """

    def __init__(self, service: VialInspectionService, config: TrackerConfig | None = None,
                 *, clock: Callable[[], float] = monotonic) -> None:
        if not isinstance(service, VialInspectionService):
            raise TypeError("service must be a VialInspectionService")
        self._config = config if config is not None else TrackerConfig()
        if not isinstance(self._config, TrackerConfig):
            raise TypeError("config must be a TrackerConfig")
        self._service = service
        self._clock = clock
        self._lock = RLock()
        self._state: TrackerState = "IDLE"
        self._events: dict[str, TrackerEvent] = {}
        self._observation = None
        self._active = ()
        self._active_details = ()
        self._issues = ()
        self._last_capture = None
        self._last_update = None
        self._last_clock = None
        self._next_update = None
        self._deadline = None
        self._completion = None
        self._inspection = None
        self._inspection_id = None
        self._start_request = None

    @property
    def config(self) -> TrackerConfig:
        return self._config

    def configure(self, config: TrackerConfig) -> None:
        """Apply station settings between vial cycles only."""
        if not isinstance(config, TrackerConfig):
            raise TypeError("config must be a TrackerConfig")
        with self._lock:
            if self._state not in ("IDLE", "INSPECTED"):
                raise RuntimeError("Monitoring settings can change only between vial cycles")
            self._config = config

    def start_filling(self, run_id: str, vial_id: str, captured_at: float,
                      *, inspection_id: str | None = None) -> TrackerSnapshot:
        _timestamp(captured_at)
        observation = VialObservation(run_id, vial_id, ())
        _validate_text("inspection_id", inspection_id, optional=True)
        with self._lock:
            start_request = (run_id, vial_id, captured_at, inspection_id)
            if self._start_request == start_request:
                return self.snapshot()
            if self._state not in ("IDLE", "INSPECTED"):
                raise RuntimeError("A vial is already active")
            if self._service.inspections.get_for_vial(run_id, vial_id) is not None:
                raise ValueError("This run/vial already has an inspection")
            if inspection_id is not None and self._service.inspections.get_inspection(inspection_id) is not None:
                raise ValueError("Inspection ID already belongs to another inspection")
            now = self._now()
            self._start_request = start_request
            self._state = "FILLING"
            self._observation = observation
            self._started_at = captured_at
            self._events = {}
            self._active, self._issues = (), ()
            self._active_details = ()
            self._last_capture = None
            self._last_update = None
            self._next_update = now
            self._deadline, self._completion = None, None
            self._inspection = None
            self._inspection_id = inspection_id
            return self.snapshot()

    def submit(self, event: TrackerEvent) -> None:
        """Buffer events, accepting late capture times until finalization closes."""
        if not isinstance(event, TrackerEvent):
            raise TypeError("event must be a TrackerEvent")
        with self._lock:
            if self._state == "IDLE":
                raise RuntimeError("No active vial")
            if (event.run_id, event.vial_id) != (self._observation.run_id, self._observation.vial_id):
                raise ValueError("Event belongs to another run/vial")
            existing = self._events.get(event.event_id)
            if existing is not None:
                if existing != event:
                    raise ValueError("Event ID reused with different data")
                return
            if self._state == "INSPECTED":
                raise RuntimeError("Vial is finalized; late events cannot rewrite history")
            if event.captured_at < self._started_at:
                raise ValueError("Event precedes filling start")
            now = self._now()
            if self._deadline is not None and now > self._deadline:
                raise RuntimeError("Finalization grace period has expired")
            if self._completion is not None and event.captured_at > self._completion.captured_at:
                raise ValueError("Event is outside the completed filling period")
            if event.kind == "FILLING_COMPLETED":
                if self._completion is not None:
                    raise ValueError("Whole-vial completion was already reported")
                if any(item.captured_at > event.captured_at for item in self._events.values()):
                    raise ValueError("Completion precedes previously captured events")
                self._completion = event
                self._state = "FINALIZING"
                self._deadline = now + self._config.finalization_grace_seconds
                self._next_update = now  # Flush promptly on whole-vial completion.
            self._events[event.event_id] = event

    def finish_filling(self, captured_at: float, final_color: str | None = None,
                       *, event_id: str = "filling-completed") -> None:
        """Convenience wrapper for a reliable whole-vial completion signal."""
        with self._lock:
            if self._observation is None:
                raise RuntimeError("No active vial")
            self.submit(TrackerEvent(event_id, self._observation.run_id, self._observation.vial_id,
                                     "FILLING_COMPLETED", captured_at, color=final_color))

    def update(self) -> TrackerSnapshot:
        """Process buffered evidence when due; empty ticks add no observations."""
        with self._lock:
            if self._state in ("IDLE", "INSPECTED"):
                return self.snapshot()
            now = self._now()
            finalizing = self._deadline is not None and now >= self._deadline
            if now < self._next_update and not finalizing:
                return self.snapshot()
            self._rebuild()
            self._last_update = now
            interval = self._config.update_interval_seconds
            if now >= self._next_update:
                steps = math.floor((now - self._next_update) / interval) + 1
                self._next_update += steps * interval
            if finalizing:
                # On storage failure keep FINALIZING and the buffered evidence;
                # a subsequent update retries through the idempotent service.
                self._inspection = self._service.inspect(self._observation, self._inspection_id)
                self._state = "INSPECTED"
            return self.snapshot()

    def snapshot(self) -> TrackerSnapshot:
        with self._lock:
            return TrackerSnapshot(self._state, self._observation, self._active, self._issues,
                                   self._last_capture, self._last_update, self._inspection,
                                   self._active_details)

    def next_update_delay(self) -> float | None:
        """Seconds until the next update/finalization, or None while inactive."""
        with self._lock:
            if self._state in ("IDLE", "INSPECTED"):
                return None
            due = min(self._next_update, self._deadline) if self._deadline is not None else self._next_update
            return max(0.0, due - self._now())

    def run(self, stop_event: Event) -> None:
        """Blocking scheduler for a caller-owned thread; stop does not finish a vial.

        Exceptions (including storage failures) propagate to the caller. The vial
        remains retryable. Delayed ticks skip missed deadlines instead of replaying
        stale evidence or launching model requests.
        """
        while not stop_event.is_set():
            self.update()
            with self._lock:
                now = self._now()
                delay = self._config.update_interval_seconds
                if self._state in ("FILLING", "FINALIZING"):
                    due = min(self._next_update, self._deadline) if self._deadline is not None else self._next_update
                    delay = max(0, due - now)
            stop_event.wait(delay)

    def _now(self) -> float:
        now = self._clock()
        _timestamp(now)
        if self._last_clock is not None and now < self._last_clock:
            raise ValueError("Scheduling clock must be monotonic")
        self._last_clock = now
        return now

    def _rebuild(self) -> None:
        events = sorted(self._events.values(), key=lambda event: (event.captured_at, event.event_id))
        groups = {}
        final_colors = []
        issues = []
        for event in events:
            if event.kind.startswith("DISPENSE_"):
                groups.setdefault(event.dispense_id, []).append(event)
            elif event.color is not None:
                final_colors.append(event)
        dispenses, active, intervals, details = [], [], [], []
        for identifier, group in groups.items():
            starts = [event for event in group if event.kind == "DISPENSE_STARTED"]
            stops = [event for event in group if event.kind == "DISPENSE_STOPPED"]
            if len(starts) != 1 or len(stops) > 1:
                issues.append(f"{identifier}: requires one start and at most one stop")
                continue
            start = starts[0]
            colors = [event for event in group if event.kind in ("DISPENSE_STARTED", "DISPENSE_COLOR")]
            color_events = [event for event in colors if event.color is not None]
            source_events = [event for event in colors if event.source is not None]
            if any(event.captured_at < start.captured_at for event in group):
                issues.append(f"{identifier}: evidence precedes its start")
            if not stops:
                active.append(identifier)
                latest = max(event.captured_at for event in group)
                details.append(ActiveDispenseSnapshot(
                    identifier, start.captured_at, latest,
                    color_events[-1].color if color_events else None,
                    source_events[-1].source if source_events else None,
                    latest - start.captured_at))
                if self._completion is not None:
                    issues.append(f"{identifier}: missing stop timestamp")
                continue
            stop = stops[0]
            if stop.captured_at <= start.captured_at:
                issues.append(f"{identifier}: stop must follow start")
                continue
            if any(event.captured_at > stop.captured_at for event in colors):
                issues.append(f"{identifier}: dispense evidence falls after its stop")
            intervals.append((start.captured_at, stop.captured_at, identifier))
            if not color_events:
                issues.append(f"{identifier}: missing dispense color")
                continue
            dispenses.append((start.captured_at, identifier, Dispense(
                color_events[-1].color, stop.captured_at - start.captured_at,
                source_events[-1].source if source_events else None)))
        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            if current[0] < previous[1]:
                issues.append(f"Overlapping dispenses: {previous[2]} and {current[2]}")
        if self._completion is not None and not final_colors:
            issues.append("Missing final color")
        if self._completion is not None and not groups:
            issues.append("No dispense observations")
        self._observation = VialObservation(
            self._observation.run_id, self._observation.vial_id,
            tuple(item[2] for item in sorted(dispenses)),
            final_colors[-1].color if final_colors else None,
            self._completion is not None and not issues,
        )
        self._active = tuple(sorted(active))
        self._active_details = tuple(sorted(details, key=lambda item: item.dispense_id))
        self._issues = tuple(issues)
        self._last_capture = max((event.captured_at for event in events), default=None)
