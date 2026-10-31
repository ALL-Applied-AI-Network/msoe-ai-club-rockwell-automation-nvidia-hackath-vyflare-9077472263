"""App-owned station trackers and a single in-process scheduling thread."""

import atexit
from dataclasses import replace
import logging
import re
from threading import Event, RLock, Thread
from time import monotonic

from .models import _validate_text
from .tracker_config import TrackerConfig
from .vial_tracker import ActiveVialTracker


class TrackerConflict(RuntimeError):
    pass


class TrackerManager:
    """Share one manager per app/process; no thread starts until a vial starts.

    Test code can disable the scheduler and call update_all with an injected
    clock. Real scheduling is independent of HTTP requests and model inference.
    """

    def __init__(self, service, *, scheduler_enabled=True, clock=monotonic):
        if not isinstance(scheduler_enabled, bool):
            raise TypeError("scheduler_enabled must be a boolean")
        self._service = service
        self._enabled = scheduler_enabled
        self._clock = clock
        self._trackers = {}
        self._vial_owners = {}
        self._errors = {}
        self._lock = RLock()
        self._stop = Event()
        self._wake = Event()
        self._thread = None
        self._closed = False
        self._log = logging.getLogger(__name__)

    @staticmethod
    def validate_station(station_id):
        _validate_text("station_id", station_id)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", station_id):
            raise ValueError("station_id must be 1-64 letters, digits, underscores, or hyphens")

    def get(self, station_id):
        self.validate_station(station_id)
        with self._lock:
            if station_id not in self._trackers:
                raise KeyError("Station not found")
            return self._trackers[station_id]

    def _get_or_create(self, station_id):
        self.validate_station(station_id)
        with self._lock:
            if self._closed:
                raise TrackerConflict("Tracker manager is shut down")
            if station_id not in self._trackers:
                self._trackers[station_id] = ActiveVialTracker(self._service, clock=self._clock)
            return self._trackers[station_id]

    def start_filling(self, station_id, run_id, vial_id, captured_at, inspection_id=None):
        _validate_text("run_id", run_id)
        _validate_text("vial_id", vial_id)
        with self._lock:
            tracker = self._get_or_create(station_id)
            owner = self._vial_owners.get((run_id, vial_id))
            if owner is not None and owner != station_id:
                raise TrackerConflict("Run/vial is already assigned to another station")
            tracker.start_filling(run_id, vial_id, captured_at, inspection_id=inspection_id)
            self._vial_owners[(run_id, vial_id)] = station_id
            self._ensure_scheduler()
            self._wake.set()
        return tracker

    def configure(self, station_id, changes):
        with self._lock:
            tracker = self._get_or_create(station_id)
            tracker.configure(replace(tracker.config, **changes))
            self._wake.set()
            return tracker

    def submit(self, station_id, event):
        with self._lock:
            if self._closed:
                raise TrackerConflict("Tracker manager is shut down")
            tracker = self.get(station_id)
        tracker.submit(event)
        self._wake.set()
        return tracker

    def scheduler_status(self, station_id):
        with self._lock:
            return {"enabled": self._enabled,
                    "running": self._thread is not None and self._thread.is_alive(),
                    "last_error": self._errors.get(station_id), "closed": self._closed}

    def update_all(self):
        """Advance every station; isolate failures and retry on subsequent ticks."""
        with self._lock:
            if self._closed:
                return
            stations = tuple(self._trackers.items())
        for station_id, tracker in stations:
            try:
                tracker.update()
            except Exception:
                with self._lock:
                    first_failure = station_id not in self._errors
                    self._errors[station_id] = "Tracker update failed; retry pending"
                if first_failure:
                    self._log.exception("Tracker update failed at station %s", station_id)
            else:
                with self._lock:
                    self._errors.pop(station_id, None)

    def _ensure_scheduler(self):
        # Called while holding the manager lock.
        if self._enabled and (self._thread is None or not self._thread.is_alive()):
            self._thread = Thread(target=self._run, name="vial-tracker-scheduler", daemon=True)
            self._thread.start()
            atexit.register(self.shutdown)

    def _run(self):
        while not self._stop.is_set():
            self._wake.clear()
            self.update_all()
            with self._lock:
                stations = tuple(self._trackers.items())
                errors = set(self._errors)
            delays = [1.0]
            for station_id, tracker in stations:
                try:
                    delay = tracker.next_update_delay()
                except Exception:
                    delay = .1
                if delay is not None:
                    # Prevent a failed finalization from spinning on an expired
                    # deadline. Keep other stations on their own target cadence.
                    delays.append(max(.05, delay) if station_id in errors else delay)
            self._wake.wait(min(delays))

    def shutdown(self, timeout=2.0):
        """Stop scheduling; never infer completion or discard a filling cycle."""
        with self._lock:
            self._closed = True
            self._stop.set()
            self._wake.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                raise RuntimeError("Tracker scheduler did not stop within timeout")
        atexit.unregister(self.shutdown)
