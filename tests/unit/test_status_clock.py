"""F3 crowd-status countdown tests, mirroring test_play_clock.py's coverage.

``StatusCountdown`` is modelled directly on ``PlayClock``: same frozen
dataclass, same monotonic-deadline math, same revision bookkeeping. Every test
here drives an injected fake monotonic clock; nothing sleeps and nothing reads
wall-clock time.
"""

import unittest

from scoreboard.domain.clocks import STATUS_CLOCK_PRESETS, StatusCountdown
from scoreboard.domain.state import StateValidationError, default_state


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class StatusCountdownTests(unittest.TestCase):
    def test_initial_stopped_blank_state(self) -> None:
        state = default_state()
        clock = StatusCountdown.from_state(state)

        self.assertEqual(state.status_clock.seconds, 0.0)
        self.assertFalse(state.status_clock.running)
        self.assertEqual(clock.remaining_at(), 0.0)
        self.assertFalse(clock.running)

    def test_documented_presets_are_30_60_and_90(self) -> None:
        self.assertEqual(STATUS_CLOCK_PRESETS, (30.0, 60.0, 90.0))

    def test_preset_loads_exact_value_while_stopped(self) -> None:
        clock = StatusCountdown().start(now=0.0)

        loaded_30 = clock.load_preset(30.0, now=5.0)
        self.assertFalse(loaded_30.running)
        self.assertAlmostEqual(loaded_30.remaining_at(5.0), 30.0)

        loaded_90 = StatusCountdown().load_preset(90.0, now=0.0)
        self.assertFalse(loaded_90.running)
        self.assertAlmostEqual(loaded_90.remaining_at(0.0), 90.0)

    def test_invalid_preset_is_rejected_without_changing_state(self) -> None:
        clock = StatusCountdown().load_preset(30.0, now=0.0)

        with self.assertRaises(StateValidationError):
            clock.load_preset(45.5, now=0.0)

        self.assertEqual(clock.revision, 1)
        self.assertAlmostEqual(clock.remaining_at(0.0), 30.0)

    def test_start_stop_behavior(self) -> None:
        clock = StatusCountdown().load_preset(60.0, now=0.0)
        clock = clock.start(now=0.0)

        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(10.0), 50.0)

        clock = clock.stop(now=10.0)
        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(10.0), 50.0)

    def test_repeated_start_and_stop_are_idempotent(self) -> None:
        clock = StatusCountdown().load_preset(60.0, now=0.0).start(now=0.0)
        self.assertIs(clock, clock.start(now=10.0))

        stopped = clock.stop(now=10.0)
        self.assertIs(stopped, stopped.stop(now=20.0))

    def test_fake_time_advances_without_wall_clock_dependency(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = StatusCountdown(monotonic_clock=fake).load_preset(90.0, now=0.0)
        clock = clock.start(now=0.0)

        fake.advance(12.5)
        self.assertAlmostEqual(clock.remaining_at(), 77.5)

        new_state = clock.apply_to_state(default_state())
        self.assertAlmostEqual(new_state.status_clock.seconds, 77.5)

    def test_a_delayed_callback_creates_no_drift(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = StatusCountdown(monotonic_clock=fake).load_preset(90.0, now=0.0)
        clock = clock.start(now=0.0)

        fake.advance(10.0)
        self.assertAlmostEqual(clock.remaining_at(10.0), 80.0)
        self.assertAlmostEqual(clock.remaining_at(33.0), 57.0)

    def test_sub_second_pause_resume_preserves_remainder(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = StatusCountdown(monotonic_clock=fake).load_preset(30.0, now=0.0).start(now=0.0)

        fake.advance(1.25)
        clock = clock.stop(now=1.25)
        self.assertAlmostEqual(clock.remaining_at(1.25), 28.75)

        fake.advance(0.25)
        clock = clock.start(now=1.5)
        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(1.75), 28.5)

    def test_clear_blanks_the_status_clock(self) -> None:
        clock = StatusCountdown().load_preset(60.0, now=0.0).start(now=0.0)
        clock = clock.clear(now=15.0)

        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(15.0), 0.0)

    def test_no_correct_or_reset_method_exists(self) -> None:
        """The design deliberately omits both: the operator reloads a preset."""

        clock = StatusCountdown()
        self.assertFalse(hasattr(clock, "correct"))
        self.assertFalse(hasattr(clock, "reset"))

    def test_expiration_clamps_at_zero_and_stops(self) -> None:
        clock = StatusCountdown().load_preset(30.0, now=0.0).start(now=0.0)

        self.assertAlmostEqual(clock.remaining_at(30.0), 0.0)
        self.assertFalse(clock.current_value(30.0).running)
        self.assertAlmostEqual(clock.remaining_at(45.0), 0.0)

    def test_never_goes_below_zero(self) -> None:
        clock = StatusCountdown().load_preset(30.0, now=0.0).start(now=0.0)

        self.assertAlmostEqual(clock.remaining_at(1000.0), 0.0)
        self.assertGreaterEqual(clock.remaining_at(1000.0), 0.0)

    def test_expired_status_clock_remains_visible_at_zero_and_stops(self) -> None:
        clock = StatusCountdown().load_preset(30.0, now=0.0).start(now=0.0)

        expired = clock.expire(now=30.0)
        self.assertFalse(expired.running)
        self.assertAlmostEqual(expired.remaining_at(30.0), 0.0)
        self.assertEqual(expired.revision, clock.revision + 1)

        self.assertIs(expired, expired.expire(now=40.0))

    def test_wall_clock_changes_do_not_affect_monotonic_time(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = StatusCountdown(monotonic_clock=fake).load_preset(60.0, now=0.0).start(now=0.0)
        fake.advance(5.0)

        self.assertAlmostEqual(clock.remaining_at(100_000.0), 0.0)
        self.assertAlmostEqual(clock.remaining_at(5.0), 55.0)

    def test_rejected_operations_leave_state_and_revision_unchanged(self) -> None:
        state = default_state()
        engine = StatusCountdown.from_state(state)

        with self.assertRaises(StateValidationError):
            engine.load_preset(301.0)

        self.assertEqual(engine.revision, 0)
        self.assertEqual(state.revision, 0)

    def test_a_non_preset_value_is_rejected(self) -> None:
        # Since September 9, 2026 the crowd TIMEOUT loads the configured
        # timeout length, so any whole second from 1 to 300 loads; what is
        # still refused is zero, negative, over the clock's maximum, a
        # fraction, or not a number at all.
        clock = StatusCountdown()
        for bad in (0.0, -1.0, 301.0, 45.5, "60", None, True):
            with self.subTest(bad=bad):
                with self.assertRaises(StateValidationError):
                    clock.load_preset(bad)
        for fine in (15.0, 45.0, 120.0):
            with self.subTest(fine=fine):
                self.assertAlmostEqual(clock.load_preset(fine, now=0.0).remaining_at(0.0), fine)


if __name__ == "__main__":
    unittest.main()
