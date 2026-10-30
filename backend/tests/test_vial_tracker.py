import unittest
from dataclasses import replace
from threading import Event
from unittest.mock import patch

from recipes import Dispense, InspectionRepository, Recipe, RecipeRepository, VialInspectionService
from recipes.tracker_config import TrackerConfig
from recipes.vial_tracker import ActiveVialTracker, TrackerEvent


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class VialTrackerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.recipes = RecipeRepository()
        self.inspections = InspectionRepository()
        self.service = VialInspectionService(self.recipes, self.inspections)
        self.tracker = ActiveVialTracker(self.service, TrackerConfig(finalization_grace_ms=200), clock=self.clock)
        self.tracker.start_filling("RUN", "VIAL", 10)

    def event(self, identifier, kind, captured_at, dispense_id=None, color=None, source=None):
        return TrackerEvent(identifier, "RUN", "VIAL", kind, captured_at, dispense_id, color, source)

    def dispense(self, identifier="D1", start=10, end=12, color="blue"):
        self.tracker.submit(self.event(identifier+"-start", "DISPENSE_STARTED", start, identifier, color))
        self.tracker.submit(self.event(identifier+"-stop", "DISPENSE_STOPPED", end, identifier))

    def finish(self, captured_at=12, color="blue"):
        self.tracker.finish_filling(captured_at, color)
        self.tracker.update()
        self.clock.now += .21
        return self.tracker.update()

    def test_whole_cycle_calls_inspection_once_with_capture_duration(self):
        self.recipes.add_recipe(Recipe(1, "INTENDED", (Dispense("blue", 2),), "blue"))
        self.dispense()
        with patch.object(self.service, "inspect", wraps=self.service.inspect) as inspect:
            self.tracker.finish_filling(12, "blue")
            first = self.tracker.update()
            self.assertEqual(first.state, "FINALIZING")
            self.assertEqual(inspect.call_count, 0)
            self.clock.now = .21
            result = self.tracker.update()
            self.clock.now = 5
            self.assertIs(self.tracker.update().inspection, result.inspection)
            self.assertEqual(inspect.call_count, 1)
        self.assertEqual(result.state, "INSPECTED")
        self.assertEqual(result.inspection.verification_status, "PASS")
        self.assertEqual(result.observation.dispenses[0].duration_seconds, 2)

    def test_pause_does_not_finish_vial(self):
        self.dispense()
        self.tracker.update()
        self.clock.now = 50
        snapshot = self.tracker.update()
        self.assertEqual(snapshot.state, "FILLING")
        self.assertIsNone(snapshot.inspection)
        self.dispense("D2", 14, 17, "yellow")
        result = self.finish(17, "green")
        self.assertEqual([d.duration_seconds for d in result.observation.dispenses], [2, 3])
        self.assertTrue(result.inspection.created_new_recipe)

    def test_configured_cadence_and_active_progress_use_only_new_evidence(self):
        self.tracker.update()
        self.tracker.submit(self.event("start", "DISPENSE_STARTED", 10, "D1", "blue"))
        self.clock.now = .05
        self.assertEqual(self.tracker.update().active_dispense_ids, ())
        self.clock.now = .1
        self.assertEqual(self.tracker.update().active_dispense_ids, ("D1",))
        self.tracker.submit(self.event("color", "DISPENSE_COLOR", 10.5, "D1", "blue"))
        self.clock.now = .21
        snapshot = self.tracker.update()
        self.assertEqual(snapshot.active_dispenses[0].duration_so_far_seconds, .5)
        self.clock.now = 10
        empty_tick = self.tracker.update()
        self.assertEqual(empty_tick.active_dispenses, snapshot.active_dispenses)
        self.assertEqual(empty_tick.last_processed_capture_at, 10.5)

    def test_out_of_order_arrival_rebuilds_by_capture_time_during_grace(self):
        self.tracker.submit(self.event("stop", "DISPENSE_STOPPED", 12, "D1"))
        self.tracker.finish_filling(12, "blue")
        self.assertTrue(self.tracker.update().issues)
        self.clock.now = .1
        self.tracker.submit(self.event("start", "DISPENSE_STARTED", 10, "D1", "blue"))
        self.clock.now = .21
        result = self.tracker.update()
        self.assertEqual(result.issues, ())
        self.assertEqual(result.observation.dispenses[0].duration_seconds, 2)
        self.assertEqual(result.inspection.verification_status, "FAIL")

    def test_missing_stop_or_color_does_not_create_recipe(self):
        self.tracker.submit(self.event("start", "DISPENSE_STARTED", 10, "D1", "blue"))
        result = self.finish()
        self.assertIn("D1: missing stop timestamp", result.issues)
        self.assertEqual(result.inspection.verification_status, "INSUFFICIENT_DATA")
        self.assertEqual(self.recipes.list_recipes("UNMATCHED"), ())

    def test_missing_final_color_produces_unresolved_inspection(self):
        self.dispense()
        result = self.finish(color=None)
        self.assertIn("Missing final color", result.issues)
        self.assertEqual(result.inspection.verification_status, "INSUFFICIENT_DATA")

    def test_missing_dispense_color_is_not_silently_dropped_from_count(self):
        self.dispense(color=None)
        result = self.finish()
        self.assertFalse(result.observation.filling_complete)
        self.assertIn("D1: missing dispense color", result.issues)
        self.assertEqual(result.inspection.verification_status, "INSUFFICIENT_DATA")

    def test_late_color_and_final_color_can_complete_observation(self):
        self.dispense(color=None)
        self.tracker.finish_filling(12)
        self.tracker.update()
        self.clock.now = .1
        self.tracker.submit(self.event("dc", "DISPENSE_COLOR", 11, "D1", "blue"))
        self.tracker.submit(self.event("fc", "FINAL_COLOR", 12, color="blue"))
        self.clock.now = .21
        result = self.tracker.update()
        self.assertEqual(result.issues, ())
        self.assertTrue(result.inspection.created_new_recipe)

    def test_duplicate_events_are_idempotent_and_conflicts_rejected(self):
        event = self.event("start", "DISPENSE_STARTED", 10, "D1", "blue")
        self.tracker.submit(event)
        self.tracker.submit(event)
        with self.assertRaises(ValueError):
            self.tracker.submit(replace(event, color="red"))
        self.tracker.submit(self.event("stop", "DISPENSE_STOPPED", 12, "D1"))
        result = self.finish()
        self.tracker.submit(event)  # Exact delivery retry after finalization.
        self.assertEqual(len(result.observation.dispenses), 1)

    def test_invalid_temporal_boundaries_and_cross_vial_events_are_rejected(self):
        for event in (self.event("early", "FINAL_COLOR", 9, color="blue"),
                      replace(self.event("other", "FINAL_COLOR", 11, color="blue"), vial_id="OTHER")):
            with self.assertRaises(ValueError):
                self.tracker.submit(event)
        self.tracker.finish_filling(12, "blue")
        with self.assertRaises(ValueError):
            self.tracker.submit(self.event("late-time", "FINAL_COLOR", 13, color="blue"))
        self.clock.now = .3
        with self.assertRaises(RuntimeError):
            self.tracker.submit(self.event("late-arrival", "FINAL_COLOR", 11, color="blue"))

    def test_overlapping_or_duplicate_starts_are_unresolved(self):
        self.dispense()
        self.dispense("D2", 11, 13)
        result = self.finish(13)
        self.assertTrue(any("Overlapping" in issue for issue in result.issues))
        self.assertEqual(result.inspection.verification_status, "INSUFFICIENT_DATA")

    def test_settings_only_change_between_cycles_and_next_vial_resets(self):
        with self.assertRaises(RuntimeError):
            self.tracker.configure(TrackerConfig(update_interval_ms=200))
        with self.assertRaises(RuntimeError):
            self.tracker.start_filling("RUN", "OTHER", 10)
        self.dispense()
        result = self.finish()
        self.tracker.configure(TrackerConfig(update_interval_ms=200))
        with self.assertRaises(ValueError):
            self.tracker.start_filling("RUN", "VIAL", 20)
        snapshot = self.tracker.start_filling("RUN", "VIAL-2", 20)
        self.assertEqual(snapshot.state, "FILLING")
        self.assertEqual(snapshot.observation.dispenses, ())
        self.assertIsNone(snapshot.inspection)
        self.assertEqual(result.state, "INSPECTED")
        self.assertEqual(self.tracker.config.update_interval_ms, 200)

    def test_storage_failure_keeps_finalizing_and_can_retry(self):
        self.dispense()
        self.tracker.finish_filling(12, "blue")
        self.clock.now = .21
        with patch.object(self.service, "inspect", side_effect=RuntimeError("Storage unavailable")):
            with self.assertRaises(RuntimeError):
                self.tracker.update()
        self.assertEqual(self.tracker.snapshot().state, "FINALIZING")
        self.assertEqual(self.tracker.update().state, "INSPECTED")

    def test_scheduler_runs_to_deadline_without_real_sleep(self):
        self.dispense()
        self.tracker.finish_filling(12, "blue")
        clock = self.clock
        class Stop:
            calls = 0
            def is_set(self):
                return self.calls >= 3
            def wait(self, delay):
                clock.now += delay
                self.calls += 1
        self.tracker.run(Stop())
        self.assertEqual(self.tracker.snapshot().state, "INSPECTED")
        stopped = Event()
        stopped.set()
        self.tracker.run(stopped)

    def test_no_finalization_when_scheduler_stops(self):
        stopped = Event()
        stopped.set()
        self.tracker.run(stopped)
        self.assertEqual(self.tracker.snapshot().state, "FILLING")

    def test_invalid_config_and_event_fields(self):
        for config in (dict(update_interval_ms=0), dict(finalization_grace_ms=-1),
                       dict(update_interval_ms=True), dict(update_interval_ms=float("nan"))):
            with self.assertRaises((TypeError, ValueError)):
                TrackerConfig(**config)
        base = self.event("id", "DISPENSE_STARTED", 10, "D1", "blue")
        for values in (dict(captured_at=-1), dict(kind="UNKNOWN"), dict(dispense_id=None),
                       dict(event_id=""), dict(kind="DISPENSE_COLOR", color=None)):
            with self.assertRaises((TypeError, ValueError)):
                replace(base, **values)


if __name__ == "__main__":
    unittest.main()
