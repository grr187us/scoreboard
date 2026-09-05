import unittest

from scoreboard.domain.clocks import (
    PLAY_CLOCK_PRESETS,
    GameClock,
    PlayClock,
    clear_play_clock_on_game_clock_start,
)
from scoreboard.domain.state import StateValidationError, default_state


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class PlayClockTests(unittest.TestCase):
    def test_initial_stopped_blank_state(self) -> None:
        state = default_state()
        clock = PlayClock.from_state(state)

        self.assertEqual(state.play_clock.seconds, 0.0)
        self.assertFalse(state.play_clock.running)
        self.assertEqual(clock.remaining_at(), 0.0)
        self.assertFalse(clock.running)

    def test_preset_loads_exact_value_while_stopped(self) -> None:
        clock = PlayClock().start(now=0.0)

        loaded_25 = clock.load_preset(25.0, now=5.0)
        self.assertFalse(loaded_25.running)
        self.assertAlmostEqual(loaded_25.remaining_at(5.0), 25.0)

        loaded_40 = PlayClock().load_preset(40.0, now=0.0)
        self.assertFalse(loaded_40.running)
        self.assertAlmostEqual(loaded_40.remaining_at(0.0), 40.0)

    def test_invalid_preset_is_rejected_without_changing_state(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0)

        with self.assertRaises(StateValidationError):
            clock.load_preset(30.0, now=0.0)

        self.assertEqual(clock.revision, 1)
        self.assertAlmostEqual(clock.remaining_at(0.0), 25.0)

    def test_start_stop_behavior(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0)
        clock = clock.start(now=0.0)

        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(10.0), 15.0)

        clock = clock.stop(now=10.0)
        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(10.0), 15.0)

    def test_repeated_start_and_stop_are_idempotent(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0).start(now=0.0)
        self.assertIs(clock, clock.start(now=10.0))

        stopped = clock.stop(now=10.0)
        self.assertIs(stopped, stopped.stop(now=20.0))

    def test_fake_time_advances_without_wall_clock_dependency(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = PlayClock(monotonic_clock=fake).load_preset(40.0, now=0.0)
        clock = clock.start(now=0.0)

        fake.advance(12.5)
        self.assertAlmostEqual(clock.remaining_at(), 27.5)

        new_state = clock.apply_to_state(default_state())
        self.assertAlmostEqual(new_state.play_clock.seconds, 27.5)

    def test_callback_stalls_do_not_accumulate_error(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = PlayClock(monotonic_clock=fake).load_preset(40.0, now=0.0)
        clock = clock.start(now=0.0)

        fake.advance(10.0)
        self.assertAlmostEqual(clock.remaining_at(10.0), 30.0)
        self.assertAlmostEqual(clock.remaining_at(33.0), 7.0)

    def test_sub_second_pause_resume_preserves_remainder(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = PlayClock(monotonic_clock=fake).load_preset(25.0, now=0.0).start(now=0.0)

        fake.advance(1.25)
        clock = clock.stop(now=1.25)
        self.assertAlmostEqual(clock.remaining_at(1.25), 23.75)

        fake.advance(0.25)
        clock = clock.start(now=1.5)
        self.assertTrue(clock.running)
        self.assertAlmostEqual(clock.remaining_at(1.75), 23.5)

    def test_clear_blanks_the_play_clock(self) -> None:
        clock = PlayClock().load_preset(40.0, now=0.0).start(now=0.0)
        clock = clock.clear(now=15.0)

        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(15.0), 0.0)
        self.assertEqual(clock.preset_seconds, 0.0)

    def test_reset_restores_the_configured_preset_and_stops(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0).start(now=0.0)

        clock = clock.reset()
        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(), 25.0)

    def test_reset_without_a_loaded_preset_restores_blank(self) -> None:
        clock = PlayClock().reset()

        self.assertFalse(clock.running)
        self.assertAlmostEqual(clock.remaining_at(), 0.0)

    def test_valid_and_invalid_corrections(self) -> None:
        original = PlayClock().load_preset(40.0, now=0.0)
        corrected = original.correct(target=10.0, now=0.0)
        self.assertAlmostEqual(corrected.remaining_at(0.0), 10.0)

        with self.assertRaises(StateValidationError):
            original.correct(target=-1.0)
        self.assertEqual(original.revision, 1)

        with self.assertRaises(StateValidationError):
            original.correct(target=999.0)
        self.assertEqual(original.revision, 1)

    def test_expiration_clamps_at_zero_and_stops(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0).start(now=0.0)
        clock = clock.correct(target=3.0, now=0.0)

        self.assertAlmostEqual(clock.remaining_at(3.0), 0.0)
        self.assertFalse(clock.current_value(3.0).running)
        self.assertAlmostEqual(clock.remaining_at(20.0), 0.0)

    def test_expired_play_clock_remains_visible_at_zero_without_alarm(self) -> None:
        clock = PlayClock().load_preset(25.0, now=0.0).start(now=0.0)
        clock = clock.correct(target=1.0, now=0.0)

        expired = clock.expire(now=5.0)
        self.assertFalse(expired.running)
        self.assertAlmostEqual(expired.remaining_at(5.0), 0.0)
        self.assertEqual(expired.revision, clock.revision + 1)

        self.assertIs(expired, expired.expire(now=10.0))

    def test_wall_clock_changes_do_not_affect_monotonic_time(self) -> None:
        fake = FakeMonotonic(0.0)
        clock = PlayClock(monotonic_clock=fake).load_preset(40.0, now=0.0).start(now=0.0)
        fake.advance(5.0)

        self.assertAlmostEqual(clock.remaining_at(100_000.0), 0.0)
        self.assertAlmostEqual(clock.remaining_at(5.0), 35.0)

    def test_rejected_operations_leave_state_and_revision_unchanged(self) -> None:
        state = default_state()
        engine = PlayClock.from_state(state)

        with self.assertRaises(StateValidationError):
            engine.correct(target=-0.1)

        with self.assertRaises(StateValidationError):
            engine.load_preset(99.0)

        self.assertEqual(engine.revision, 0)
        self.assertEqual(state.revision, 0)

    def test_documented_presets_are_25_and_40(self) -> None:
        self.assertEqual(PLAY_CLOCK_PRESETS, (25.0, 40.0))

    def test_game_clock_stopped_to_running_transition_clears_play_clock(self) -> None:
        game = GameClock()
        play = PlayClock().load_preset(25.0, now=0.0).start(now=0.0)

        was_running = game.running
        game = game.start(now=0.0)
        play = clear_play_clock_on_game_clock_start(
            play, game_clock_was_running=was_running, now=0.0
        )

        self.assertFalse(play.running)
        self.assertAlmostEqual(play.remaining_at(0.0), 0.0)
        self.assertEqual(play.preset_seconds, 0.0)

    def test_already_running_game_clock_start_does_not_affect_play_clock(self) -> None:
        game = GameClock().start(now=0.0)
        play = PlayClock().load_preset(40.0, now=0.0).start(now=0.0)

        was_running = game.running
        redundant_start = game.start(now=5.0)
        self.assertIs(game, redundant_start)

        play_after = clear_play_clock_on_game_clock_start(
            play, game_clock_was_running=was_running, now=5.0
        )

        self.assertIs(play, play_after)
        self.assertTrue(play_after.running)
        self.assertAlmostEqual(play_after.remaining_at(5.0), 35.0)

    def test_no_play_clock_command_changes_game_clock_state(self) -> None:
        game = GameClock().start(now=0.0)
        play = PlayClock().load_preset(25.0, now=0.0)

        play.start(now=0.0)
        play.clear(now=0.0)
        play.reset()
        play.correct(target=10.0, now=0.0)

        self.assertTrue(game.running)
        self.assertAlmostEqual(game.remaining_at(0.0), 720.0)


if __name__ == "__main__":
    unittest.main()
