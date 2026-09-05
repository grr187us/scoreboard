"""Event-countdown engine and command tests (F-025 through F-028).

Task 7 lists event-countdown controls in its boundary, so the engine and its
Start/Stop/Reset/Edit-Current-Time commands are built as a named prerequisite
rather than leaving the operator view bound to commands that do not exist.

Everything runs on an injected fake monotonic clock; nothing sleeps.
"""

import unittest

from scoreboard.application.service import ScoreboardService
from scoreboard.domain import commands as cmd
from scoreboard.domain.clocks import (
    EVENT_COUNTDOWN_LENGTHS,
    EventCountdown,
    event_phase_for,
    selected_event,
)
from scoreboard.domain.formatting import format_event_countdown
from scoreboard.domain.state import StateValidationError, default_state


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


def make_service(start: float = 0.0):
    fake = FakeMonotonic(start)
    return ScoreboardService(monotonic_clock=fake), fake


class PhaseDerivationTests(unittest.TestCase):
    """F-026: HALFTIME above a displayed 3:00, WARMUP at 3:00 or less."""

    def test_documented_boundaries(self) -> None:
        cases = [
            (15 * 60.0, "15:00", "HALFTIME"),
            (181.0, "3:01", "HALFTIME"),
            (180.5, "3:01", "HALFTIME"),
            (180.0, "3:00", "WARMUP"),
            (179.9, "3:00", "WARMUP"),
            (0.0, "0:00", "WARMUP"),
        ]
        for seconds, display, phase in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_event_countdown(seconds), display)
                self.assertEqual(event_phase_for("HALFTIME", seconds), phase)

    def test_the_phase_changes_between_a_shown_301_and_a_shown_300(self) -> None:
        # The label must not flip while 3:01 is still on the board.
        self.assertEqual(format_event_countdown(180.01), "3:01")
        self.assertEqual(event_phase_for("HALFTIME", 180.01), "HALFTIME")
        self.assertEqual(format_event_countdown(180.0), "3:00")
        self.assertEqual(event_phase_for("HALFTIME", 180.0), "WARMUP")

    def test_the_pregame_countdown_has_one_phase(self) -> None:
        for seconds in (30 * 60.0, 181.0, 180.0, 0.0):
            with self.subTest(seconds=seconds):
                self.assertEqual(event_phase_for("PREGAME", seconds), "PREGAME")

    def test_warmup_belongs_to_the_halftime_countdown(self) -> None:
        self.assertEqual(selected_event("WARMUP"), "HALFTIME")
        self.assertEqual(selected_event("HALFTIME"), "HALFTIME")
        self.assertEqual(selected_event("PREGAME"), "PREGAME")


class EngineTests(unittest.TestCase):
    """The engine uses the same monotonic-deadline model as the game clock."""

    def setUp(self) -> None:
        self.fake = FakeMonotonic()
        self.clock = EventCountdown(monotonic_clock=self.fake)

    def test_the_default_is_the_stopped_pregame_countdown(self) -> None:
        self.assertEqual(self.clock.seconds, 30 * 60.0)
        self.assertFalse(self.clock.running)

    def test_select_loads_a_configured_length_while_stopped(self) -> None:
        for phase, length in EVENT_COUNTDOWN_LENGTHS.items():
            with self.subTest(phase=phase):
                loaded = self.clock.select(phase)
                self.assertEqual(loaded.seconds, length)
                self.assertFalse(loaded.running)

    def test_warmup_is_not_selectable(self) -> None:
        with self.assertRaises(StateValidationError):
            self.clock.select("WARMUP")

    def test_running_time_is_derived_from_elapsed_monotonic_time(self) -> None:
        running = self.clock.select("HALFTIME").start()

        self.fake.advance(90.25)

        self.assertAlmostEqual(running.remaining_at(), 900.0 - 90.25, places=6)
        self.assertTrue(running.running)

    def test_a_stalled_callback_produces_the_correct_value(self) -> None:
        running = self.clock.select("HALFTIME").start()

        self.fake.advance(3.0)  # a three-second repaint stall
        self.fake.advance(1.5)

        self.assertAlmostEqual(running.remaining_at(), 900.0 - 4.5, places=6)

    def test_repeated_pause_and_resume_preserves_the_remainder(self) -> None:
        clock = self.clock.select("HALFTIME")
        for _ in range(10):
            clock = clock.start(now=self.fake.value)
            self.fake.advance(0.35)
            clock = clock.stop(now=self.fake.value)

        self.assertAlmostEqual(clock.seconds, 900.0 - 3.5, places=6)

    def test_start_and_stop_are_idempotent(self) -> None:
        running = self.clock.select("PREGAME").start()

        self.assertIs(running.start(), running)
        stopped = running.stop()
        self.assertIs(stopped.stop(), stopped)

    def test_it_stops_at_zero_without_going_below(self) -> None:
        running = self.clock.select("HALFTIME").start()

        self.fake.advance(1000.0)

        self.assertEqual(running.remaining_at(), 0.0)
        self.assertFalse(running.current_value().running)
        self.assertTrue(running.expired)

    def test_an_expired_countdown_does_not_restart(self) -> None:
        running = self.clock.select("HALFTIME").start()
        self.fake.advance(1000.0)

        restarted = running.start()

        self.assertEqual(restarted.remaining_at(), 0.0)
        self.assertFalse(restarted.current_value().running)

    def test_reset_restores_the_selected_length(self) -> None:
        clock = self.clock.select("HALFTIME").start()
        self.fake.advance(120.0)
        clock = clock.stop()

        reset = clock.reset()

        self.assertEqual(reset.seconds, 900.0)
        self.assertFalse(reset.running)

    def test_correct_validates_the_requested_value(self) -> None:
        clock = self.clock.select("HALFTIME")

        self.assertEqual(clock.correct(target=61.0).seconds, 61.0)
        for invalid in (-1.0, 30 * 60.0 + 1.0, float("nan")):
            with self.subTest(invalid=invalid):
                with self.assertRaises(StateValidationError):
                    clock.correct(target=invalid)

    def test_it_restores_the_selected_length_from_state(self) -> None:
        state = default_state()
        pregame = EventCountdown.from_state(state, monotonic_clock=self.fake)
        self.assertEqual(pregame.reset().seconds, 30 * 60.0)

        halftime_state = state.evolve(event_phase="WARMUP")
        halftime = EventCountdown.from_state(halftime_state, monotonic_clock=self.fake)
        self.assertEqual(halftime.reset().seconds, 15 * 60.0)


class CommandTests(unittest.TestCase):
    """F-027, F-028: validated, logged commands with the same timing model."""

    def test_every_control_has_a_command(self) -> None:
        service, fake = make_service()

        commands = [
            cmd.event_countdown_select("HALFTIME"),
            cmd.event_countdown_start(),
            cmd.event_countdown_stop(),
            cmd.event_countdown_reset(),
            cmd.event_countdown_correct(120.0),
        ]
        for command in commands:
            with self.subTest(command=command.type.value):
                before = service.revision
                result = service.submit(command)
                self.assertTrue(result.accepted, result.error)
                self.assertEqual(result.state.revision, before + 1)
                self.assertIsNotNone(result.event)
                self.assertEqual(result.event.field, "event_countdown")

    def test_selecting_an_event_loads_it_stopped(self) -> None:
        service, _ = make_service()

        result = service.submit(cmd.event_countdown_select("PREGAME"))

        self.assertEqual(result.state.event_countdown.seconds, 30 * 60.0)
        self.assertFalse(result.state.event_countdown.running)
        self.assertEqual(result.state.event_phase, "PREGAME")

    def test_an_invalid_event_is_rejected_without_changing_state(self) -> None:
        service, _ = make_service()
        before = service.state

        result = service.submit(cmd.event_countdown_select("WARMUP"))

        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, "INVALID_EVENT_PHASE")
        self.assertIs(service.state, before)

    def test_an_invalid_correction_is_rejected_without_changing_state(self) -> None:
        service, _ = make_service()
        before = service.state

        result = service.submit(cmd.event_countdown_correct(-1.0))

        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, "INVALID_CLOCK_TIME")
        self.assertIs(service.state, before)

    def test_editing_the_current_time_stops_a_running_countdown(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())
        fake.advance(30.0)

        result = service.submit(cmd.event_countdown_correct(600.0))

        self.assertEqual(result.state.event_countdown.seconds, 600.0)
        self.assertFalse(result.state.event_countdown.running)

    def test_remaining_stopped_is_the_default_after_an_edit(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())

        service.submit(cmd.event_countdown_correct(600.0))
        fake.advance(10.0)

        # No Start command was issued, so no time elapsed.
        self.assertEqual(service.materialized_state().event_countdown.seconds, 600.0)

    def test_start_after_applying_is_a_second_deliberate_command(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))

        service.submit(cmd.event_countdown_correct(600.0))
        service.submit(cmd.event_countdown_start())
        fake.advance(10.0)

        self.assertAlmostEqual(
            service.materialized_state().event_countdown.seconds, 590.0, places=6
        )

    def test_the_phase_label_changes_while_the_countdown_runs(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())

        fake.advance(900.0 - 180.5)
        self.assertEqual(service.materialized_state().event_phase, "HALFTIME")

        fake.advance(0.6)
        self.assertEqual(service.materialized_state().event_phase, "WARMUP")

    def test_the_phase_label_is_committed_by_the_next_command(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())
        fake.advance(900.0 - 100.0)

        result = service.submit(cmd.event_countdown_stop())

        self.assertEqual(result.state.event_phase, "WARMUP")


class IndependenceTests(unittest.TestCase):
    """F-025: a countdown never alters the game or play clock, or the reverse."""

    def countdown_commands(self):
        return [
            cmd.event_countdown_select("HALFTIME"),
            cmd.event_countdown_start(),
            cmd.event_countdown_stop(),
            cmd.event_countdown_reset(),
            cmd.event_countdown_correct(90.0),
        ]

    def test_no_countdown_command_changes_the_game_or_play_clock(self) -> None:
        service, fake = make_service()
        # The game clock starts first: a stopped-to-running transition clears
        # the play clock (F-048), so the preset must be loaded after it.
        service.submit(cmd.game_clock_start())
        service.submit(cmd.play_clock_preset(40.0))
        service.submit(cmd.play_clock_start())
        fake.advance(5.0)
        expected_game = service.materialized_state().game_clock
        expected_play = service.materialized_state().play_clock

        for command in self.countdown_commands():
            with self.subTest(command=command.type.value):
                result = service.submit(command)
                self.assertTrue(result.accepted, result.error)
                self.assertAlmostEqual(
                    result.state.game_clock.seconds, expected_game.seconds, places=6
                )
                self.assertTrue(result.state.game_clock.running)
                self.assertAlmostEqual(
                    result.state.play_clock.seconds, expected_play.seconds, places=6
                )
                self.assertTrue(result.state.play_clock.running)

    def test_a_running_countdown_survives_game_and_play_clock_commands(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())
        fake.advance(60.0)

        for command in (
            cmd.game_clock_start(),
            cmd.game_clock_stop(),
            cmd.game_clock_reset(),
            cmd.play_clock_preset(25.0),
            cmd.play_clock_start(),
            cmd.play_clock_clear(),
            cmd.add_score("home", 6),
        ):
            with self.subTest(command=command.type.value):
                result = service.submit(command)
                self.assertTrue(result.accepted, result.error)
                self.assertTrue(result.state.event_countdown.running)

        fake.advance(30.0)
        self.assertAlmostEqual(
            service.materialized_state().event_countdown.seconds, 810.0, places=6
        )

    def test_a_new_game_returns_the_countdown_to_the_stopped_pregame_default(self) -> None:
        service, fake = make_service()
        service.submit(cmd.event_countdown_select("HALFTIME"))
        service.submit(cmd.event_countdown_start())
        fake.advance(120.0)

        result = service.submit(cmd.new_game(confirmed=True))

        self.assertEqual(result.state.event_countdown.seconds, 30 * 60.0)
        self.assertFalse(result.state.event_countdown.running)
        self.assertEqual(result.state.event_phase, "PREGAME")


if __name__ == "__main__":
    unittest.main()
