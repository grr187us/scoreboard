import unittest

from scoreboard.domain.clocks import GameClock
from scoreboard.domain.state import StateValidationError, default_state


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class GameClockTests(unittest.TestCase):
    def test_initial_stopped_12_00_state(self) -> None:
        state = default_state()
        clock = GameClock.from_state(state)

        self.assertEqual(state.game_clock.seconds, 720.0)
        self.assertFalse(state.game_clock.running)
        self.assertEqual(clock.remaining_at(), 720.0)
        self.assertFalse(clock.running)

    def test_start_stop_behavior(self) -> None:
        clock = GameClock()
        clock = clock.start(now=0.0)

        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(30.0), 690.0)

        clock = clock.stop(now=30.0)
        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(30.0), 690.0)

    def test_repeated_start_and_stop_are_idempotent(self) -> None:
        clock = GameClock().start(now=0.0)
        self.assertIs(clock, clock.start(now=10.0))

        stopped = clock.stop(now=10.0)
        self.assertIs(stopped, stopped.stop(now=20.0))

    def test_fake_time_advances_without_wall_clock_dependency(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = GameClock(monotonic_clock=fake)
        clock = clock.start(now=0.0)

        fake.advance(45.5)
        self.assertAlmostEqual(clock.remaining_at(), 674.5)

        new_state = clock.apply_to_state(default_state())
        self.assertAlmostEqual(new_state.game_clock.seconds, 674.5)

    def test_callback_stalls_do_not_accumulate_error(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = GameClock(monotonic_clock=fake)
        clock = clock.start(now=0.0)

        fake.advance(100.0)
        self.assertAlmostEqual(clock.remaining_at(100.0), 620.0)
        self.assertAlmostEqual(clock.remaining_at(250.0), 470.0)

    def test_sub_second_pause_resume_preserves_remainder(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = GameClock(monotonic_clock=fake).start(now=0.0)

        fake.advance(1.25)
        clock = clock.stop(now=1.25)
        self.assertAlmostEqual(clock.remaining_at(1.25), 718.75)

        fake.advance(0.25)
        clock = clock.start(now=1.5)
        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(1.75), 718.5)

    def test_reset_restores_full_quarter_length_and_stops(self) -> None:
        clock = GameClock().start(now=0.0)
        clock = clock.stop(now=30.0)
        clock = clock.reset()

        self.assertFalse(clock.running)
        self.assertEqual(clock.remaining_at(), 720.0)

    def test_valid_and_invalid_corrections(self) -> None:
        original = GameClock()
        corrected = original.correct(target=300.0, now=0.0)
        self.assertAlmostEqual(corrected.remaining_at(0.0), 300.0)

        with self.assertRaises(StateValidationError):
            original.correct(target=-1.0)
        self.assertEqual(original.revision, 0)

        with self.assertRaises(StateValidationError):
            original.correct(target=9999.0)
        self.assertEqual(original.revision, 0)

    def test_expiration_clamps_at_zero_and_stops(self) -> None:
        clock = GameClock().start(now=0.0)
        clock = clock.correct(target=5.0, now=0.0)

        self.assertAlmostEqual(clock.remaining_at(5.0), 0.0)
        self.assertFalse(clock.current_value(5.0).running)
        self.assertAlmostEqual(clock.remaining_at(12.0), 0.0)

    def test_wall_clock_changes_do_not_affect_monotonic_time(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = GameClock(monotonic_clock=fake).start(now=0.0)
        fake.advance(10.0)

        self.assertAlmostEqual(clock.remaining_at(100_000.0), 0.0)
        self.assertAlmostEqual(clock.remaining_at(10.0), 710.0)

    def test_rejected_operations_leave_state_and_revision_unchanged(self) -> None:
        state = default_state()
        engine = GameClock.from_state(state)

        with self.assertRaises(StateValidationError):
            engine.correct(target=-0.1)

        self.assertEqual(engine.revision, 0)
        self.assertEqual(state.revision, 0)


if __name__ == "__main__":
    unittest.main()
