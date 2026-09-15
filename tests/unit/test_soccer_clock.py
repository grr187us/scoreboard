"""Unit tests for scoreboard.domain.soccer.clocks (mirrors tests/unit/test_game_clock.py)."""

from __future__ import annotations

import unittest

from scoreboard.domain.soccer.clocks import SoccerGameClock, SoccerStatusCountdown, event_phase_for
from scoreboard.domain.soccer.state import ClockValue, SoccerState


class FakeMonotonic:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class SoccerGameClockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock_source = FakeMonotonic()

    def test_from_state_reads_the_state_clock(self) -> None:
        state = SoccerState(game_clock=ClockValue(2400.0, False, 2400.0))
        clock = SoccerGameClock.from_state(state, monotonic_clock=self.clock_source)
        self.assertEqual(clock.seconds, 2400.0)
        self.assertFalse(clock.running)

    def test_start_and_advance_counts_down(self) -> None:
        clock = SoccerGameClock(value=ClockValue(100.0, False, 100.0), monotonic_clock=self.clock_source)
        started = clock.start()
        self.clock_source.advance(30.0)
        self.assertAlmostEqual(started.remaining_at(), 70.0)

    def test_stop_freezes_the_remaining_time(self) -> None:
        clock = SoccerGameClock(value=ClockValue(100.0, False, 100.0), monotonic_clock=self.clock_source).start()
        self.clock_source.advance(40.0)
        stopped = clock.stop()
        self.clock_source.advance(50.0)
        self.assertAlmostEqual(stopped.remaining_at(), 60.0)
        self.assertFalse(stopped.running)

    def test_expire_at_zero_stops_the_clock(self) -> None:
        clock = SoccerGameClock(value=ClockValue(10.0, False, 100.0), monotonic_clock=self.clock_source).start()
        self.clock_source.advance(15.0)
        expired = clock.expire()
        self.assertEqual(expired.seconds, 0.0)
        self.assertFalse(expired.running)

    def test_reset_returns_to_the_maximum(self) -> None:
        clock = SoccerGameClock(value=ClockValue(10.0, False, 2400.0), monotonic_clock=self.clock_source)
        self.assertEqual(clock.reset().seconds, 2400.0)

    def test_correct_sets_a_target(self) -> None:
        clock = SoccerGameClock(value=ClockValue(100.0, False, 2400.0), monotonic_clock=self.clock_source)
        corrected = clock.correct(target=500.0)
        self.assertEqual(corrected.seconds, 500.0)

    def test_apply_to_state_round_trips(self) -> None:
        state = SoccerState()
        clock = SoccerGameClock.from_state(state, monotonic_clock=self.clock_source).start()
        self.clock_source.advance(5.0)
        next_state = clock.apply_to_state(state)
        self.assertEqual(next_state.game_clock.running, True)


class SoccerStatusCountdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock_source = FakeMonotonic()

    def test_load_preset_and_start(self) -> None:
        clock = SoccerStatusCountdown(monotonic_clock=self.clock_source)
        loaded = clock.load_preset(1800.0)
        started = loaded.start()
        self.clock_source.advance(10.0)
        self.assertAlmostEqual(started.remaining_at(), 1790.0)

    def test_clear_blanks_the_countdown(self) -> None:
        clock = SoccerStatusCountdown(monotonic_clock=self.clock_source).load_preset(300.0).start()
        cleared = clock.clear()
        self.assertEqual(cleared.seconds, 0.0)
        self.assertFalse(cleared.running)


class EventPhaseForTests(unittest.TestCase):
    def test_pregame_is_always_pregame(self) -> None:
        self.assertEqual(event_phase_for("PREGAME", 5.0), "PREGAME")

    def test_halftime_flips_to_warmup_at_threshold(self) -> None:
        self.assertEqual(event_phase_for("HALFTIME", 200.0, warmup_threshold=180.0), "HALFTIME")
        self.assertEqual(event_phase_for("HALFTIME", 180.0, warmup_threshold=180.0), "WARMUP")


if __name__ == "__main__":
    unittest.main()
