"""Game rules and the one-clock intervals (September 9, 2026).

Before this change the halftime countdown was a separate engine with its own
drawer, while the pregame countdown already ran on the game clock. Now every
quarter label -- PRE, the four quarters, HALF, OT -- loads the game-clock
engine with the length the operator's ``GameRules`` give it, and the same
START/STOP/correction/Reset controls run all of them. These tests pin that,
plus the rules value object itself and the moments the service consults it.

Everything runs on an injected fake monotonic clock; nothing sleeps.
"""

import unittest

from scoreboard.application.service import ScoreboardService, initial_state
from scoreboard.domain import commands as cmd
from scoreboard.domain.clocks import event_phase_for
from scoreboard.domain.rules import GameRules, RulesError, default_rules
from scoreboard.domain.state import MAX_TIMEOUTS_CAP, StateValidationError
from scoreboard.host.bridge import spectator_view_model


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


def make_service(rules: GameRules | None = None):
    fake = FakeMonotonic()
    return ScoreboardService(monotonic_clock=fake, rules=rules), fake


class RulesValueTests(unittest.TestCase):
    def test_the_defaults_are_the_shipped_lengths(self) -> None:
        rules = default_rules()
        self.assertEqual(rules.quarter_seconds, 12 * 60)
        self.assertEqual(rules.overtime_seconds, 12 * 60)
        self.assertEqual(rules.pregame_seconds, 30 * 60)
        self.assertEqual(rules.halftime_seconds, 15 * 60)
        self.assertEqual(rules.warmup_seconds, 3 * 60)
        self.assertEqual(rules.timeout_seconds, 60)
        self.assertEqual(rules.timeouts_per_half, 3)

    def test_period_seconds_by_quarter_label(self) -> None:
        rules = GameRules(quarter_seconds=480, overtime_seconds=240,
                          pregame_seconds=600, halftime_seconds=420)
        self.assertEqual(rules.period_seconds("PRE"), 600)
        for label in ("1st", "2nd", "3rd", "4th"):
            self.assertEqual(rules.period_seconds(label), 480, label)
        self.assertEqual(rules.period_seconds("HALF"), 420)
        self.assertEqual(rules.period_seconds("OT"), 240)
        self.assertIsNone(rules.period_seconds("FINAL"))

    def test_from_payload_ignores_unknown_keys_and_keeps_defaults(self) -> None:
        rules = GameRules.from_payload({"quarter_seconds": 600, "colour": "navy"})
        self.assertEqual(rules.quarter_seconds, 600)
        self.assertEqual(rules.halftime_seconds, default_rules().halftime_seconds)

    def test_round_trip_through_to_dict(self) -> None:
        rules = GameRules(quarter_seconds=600, timeouts_per_half=2, warmup_seconds=0)
        self.assertEqual(GameRules.from_payload(rules.to_dict()), rules)

    def test_rejections_name_the_rule(self) -> None:
        cases = [
            ({"quarter_seconds": 30}, "Quarter length"),
            ({"quarter_seconds": 61 * 60}, "Quarter length"),
            ({"quarter_seconds": 90.5}, "whole seconds"),
            ({"quarter_seconds": "12"}, "Quarter length"),
            ({"warmup_seconds": 15 * 60}, "Warmup label"),
            ({"timeout_seconds": 0}, "Timeout countdown"),
            ({"timeout_seconds": 301}, "Timeout countdown"),
            ({"timeouts_per_half": 0}, "Timeouts per half"),
            ({"timeouts_per_half": MAX_TIMEOUTS_CAP + 1}, "Timeouts per half"),
            ({"timeouts_per_half": 2.5}, "Timeouts per half"),
        ]
        for payload, fragment in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(RulesError) as caught:
                    GameRules.from_payload(payload)
                self.assertIn(fragment, str(caught.exception))
        with self.assertRaises(RulesError):
            GameRules.from_payload(["not", "an", "object"])

    def test_a_whole_float_count_is_accepted_as_an_int(self) -> None:
        # JSON from the page arrives as a number; 2.0 means two.
        self.assertEqual(GameRules.from_payload({"timeouts_per_half": 2.0}).timeouts_per_half, 2)


class WarmupLabelTests(unittest.TestCase):
    """F-026 with a configurable threshold, read at the displayed second."""

    def test_the_shipped_threshold_flips_between_301_and_300(self) -> None:
        self.assertEqual(event_phase_for("HALFTIME", 180.01), "HALFTIME")
        self.assertEqual(event_phase_for("HALFTIME", 180.0), "WARMUP")

    def test_a_custom_threshold_and_zero_turn_it_off(self) -> None:
        self.assertEqual(event_phase_for("HALFTIME", 300.0, warmup_threshold=300.0), "WARMUP")
        self.assertEqual(event_phase_for("HALFTIME", 300.5, warmup_threshold=300.0), "HALFTIME")
        self.assertEqual(event_phase_for("HALFTIME", 0.0, warmup_threshold=0.0), "HALFTIME")

    def test_pregame_has_one_phase(self) -> None:
        self.assertEqual(event_phase_for("PREGAME", 0.0), "PREGAME")


class HalftimeOnTheGameClockTests(unittest.TestCase):
    """HALF loads the halftime countdown on the game clock, like PRE does."""

    def test_entering_half_loads_the_halftime_length_stopped(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("2nd", confirmed=True))
        result = service.submit(cmd.set_quarter("HALF", confirmed=True))
        self.assertTrue(result.accepted, result.error)
        clock = result.state.game_clock
        self.assertEqual((clock.seconds, clock.running, clock.maximum_seconds), (900.0, False, 900.0))
        self.assertEqual(result.state.lifecycle, "HALFTIME")

    def test_the_ordinary_game_clock_controls_run_it(self) -> None:
        service, fake = make_service()
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        started = service.submit(cmd.game_clock_start())
        self.assertTrue(started.accepted, started.error)
        fake.advance(12 * 60.0)
        view = spectator_view_model(service.materialized_state(), rules=service.rules)
        self.assertEqual(view["clocks"]["event"]["display"], "3:00")
        self.assertEqual(view["clocks"]["event"]["phase"], "WARMUP")
        self.assertEqual(view["clocks"]["game"]["label"], "HALFTIME COUNTDOWN")
        stopped = service.submit(cmd.game_clock_stop())
        self.assertFalse(stopped.state.game_clock.running)
        corrected = service.submit(cmd.game_clock_correct(181.0))
        self.assertEqual(
            spectator_view_model(corrected.state, rules=service.rules)["clocks"]["event"]["phase"],
            "HALFTIME",
        )
        reset = service.submit(cmd.game_clock_reset())
        self.assertEqual(reset.state.game_clock.seconds, 900.0)

    def test_the_spectator_event_block_reads_the_game_clock_at_halftime(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        view = spectator_view_model(service.state, rules=service.rules)
        event = view["clocks"]["event"]
        self.assertEqual(event["display"], "15:00")
        self.assertEqual(event["title"], "UNTIL SECOND HALF")
        self.assertEqual(event["phase"], "HALFTIME")
        self.assertEqual(event["warmup_follows"], "3:00")
        self.assertEqual(event["warmup_display"], "Warmup follows: 3:00")

    def test_the_warmup_line_follows_the_rules(self) -> None:
        service, _ = make_service(GameRules(warmup_seconds=300))
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        event = spectator_view_model(service.state, rules=service.rules)["clocks"]["event"]
        self.assertEqual(event["warmup_follows"], "5:00")
        service.set_rules(GameRules(warmup_seconds=0))
        event = spectator_view_model(service.state, rules=service.rules)["clocks"]["event"]
        self.assertIsNone(event["warmup_follows"])
        self.assertIsNone(event["warmup_display"])
        self.assertEqual(event["phase"], "HALFTIME")

    def test_natural_expiry_stays_in_half_and_touches_no_play_clock(self) -> None:
        service, fake = make_service()
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        service.submit(cmd.play_clock_preset(40.0))
        service.submit(cmd.game_clock_start())
        self.assertEqual(service.state.play_clock.seconds, 40.0)
        fake.advance(15 * 60.0 + 1.0)
        observation = service.observe_tick()
        self.assertTrue(observation.game_clock_expired)
        self.assertFalse(observation.play_clock_cleared)
        self.assertEqual(observation.state.quarter, "HALF")
        self.assertEqual(observation.state.game_clock.seconds, 0.0)

    def test_leaving_half_with_time_left_asks_to_discard_it(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        asked = service.submit(cmd.set_quarter("3rd"))
        self.assertFalse(asked.accepted)
        self.assertEqual(asked.error.code, cmd.CONFIRMATION_REQUIRED)
        self.assertEqual(asked.confirmation["title"], "Discard remaining halftime time?")
        self.assertIn("The game clock will load 12:00 stopped.", asked.confirmation["detail"])
        self.assertIn("Both teams return to 3 timeouts.", asked.confirmation["detail"])

    def test_the_second_half_starts_with_a_full_timeout_allotment(self) -> None:
        service, _ = make_service(GameRules(timeouts_per_half=2))
        self.assertEqual(service.state.home_timeouts, 2)
        service.submit(cmd.set_quarter("1st", confirmed=True))
        service.submit(cmd.timeout_used("home"))
        service.submit(cmd.timeout_used("away"))
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        self.assertEqual((service.state.home_timeouts, service.state.away_timeouts), (1, 1))
        third = service.submit(cmd.set_quarter("3rd", confirmed=True))
        self.assertEqual((third.state.home_timeouts, third.state.away_timeouts), (2, 2))
        # A barrier, like every quarter move that loads a clock.
        self.assertFalse(service.submit(cmd.undo()).accepted)

    def test_the_removed_countdown_commands_are_unknown(self) -> None:
        for name in ("event_countdown_select", "event_countdown_start",
                     "event_countdown_stop", "event_countdown_reset",
                     "event_countdown_correct"):
            with self.subTest(name=name):
                self.assertNotIn(name, {member.value for member in cmd.CommandType})


class RulesInTheServiceTests(unittest.TestCase):
    def test_a_new_service_loads_the_configured_pregame_and_timeouts(self) -> None:
        rules = GameRules(pregame_seconds=600, timeouts_per_half=2)
        service, _ = make_service(rules)
        self.assertEqual(service.state.game_clock.seconds, 600.0)
        self.assertEqual(service.state.game_clock.maximum_seconds, 600.0)
        self.assertEqual(service.state.home_timeouts, 2)
        self.assertEqual(initial_state(rules).away_timeouts, 2)

    def test_quarters_and_overtime_load_their_configured_lengths(self) -> None:
        service, _ = make_service(GameRules(quarter_seconds=480, overtime_seconds=240))
        first = service.submit(cmd.set_quarter("1st", confirmed=True))
        self.assertEqual(first.state.game_clock.seconds, 480.0)
        service.submit(cmd.game_clock_correct(0.0))
        service.submit(cmd.set_quarter("4th", confirmed=True))
        overtime = service.submit(cmd.set_quarter("OT", confirmed=True))
        self.assertEqual(overtime.state.game_clock.seconds, 240.0)
        self.assertEqual(overtime.state.game_clock.maximum_seconds, 240.0)

    def test_a_live_to_live_move_keeps_the_running_down_clock(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("1st", confirmed=True))
        service.submit(cmd.game_clock_correct(300.0))
        second = service.submit(cmd.quarter_forward(confirmed=True))
        self.assertEqual(second.state.quarter, "2nd")
        self.assertEqual(second.state.game_clock.seconds, 300.0)

    def test_changing_the_rules_is_not_retroactive(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("1st", confirmed=True))
        before = service.revision
        service.set_rules(GameRules(quarter_seconds=480))
        self.assertEqual(service.revision, before)
        self.assertEqual(service.state.game_clock.seconds, 720.0)
        # The next quarter that loads a clock uses the new length: a live
        # target whose configured length differs from the clock's maximum.
        second = service.submit(cmd.quarter_forward(confirmed=True))
        self.assertEqual(second.state.game_clock.seconds, 480.0)
        self.assertEqual(second.state.game_clock.maximum_seconds, 480.0)

    def test_new_game_uses_the_rules_in_force(self) -> None:
        service, _ = make_service()
        service.set_rules(GameRules(pregame_seconds=900, timeouts_per_half=4))
        fresh = service.submit(cmd.new_game(confirmed=True))
        self.assertEqual(fresh.state.game_clock.seconds, 900.0)
        self.assertEqual(fresh.state.home_timeouts, 4)

    def test_timeout_corrections_are_capped_by_the_rules(self) -> None:
        service, _ = make_service(GameRules(timeouts_per_half=2))
        service.submit(cmd.set_quarter("1st", confirmed=True))
        refused = service.submit(cmd.timeout_correct("home", 1))
        self.assertFalse(refused.accepted)
        self.assertEqual(refused.error.code, cmd.TIMEOUT_ABOVE_MAXIMUM)
        refused = service.submit(cmd.set_timeouts("home", 3))
        self.assertEqual(refused.error.code, cmd.TIMEOUT_ABOVE_MAXIMUM)
        self.assertEqual(service.state.home_timeouts, 2)

    def test_the_crowd_timeout_accepts_any_whole_length_the_clock_holds(self) -> None:
        service, _ = make_service()
        result = service.submit(cmd.set_game_status("TIMEOUT", seconds=45.0))
        self.assertTrue(result.accepted, result.error)
        self.assertEqual(result.state.status_clock.seconds, 45.0)
        self.assertTrue(result.state.status_clock.running)

    def test_the_service_refuses_a_non_rules_object(self) -> None:
        with self.assertRaises(TypeError):
            ScoreboardService(rules={"quarter_seconds": 600})  # type: ignore[arg-type]
        service, _ = make_service()
        with self.assertRaises(TypeError):
            service.set_rules(None)  # type: ignore[arg-type]

    def test_a_game_clock_maximum_is_bounded_not_enumerated(self) -> None:
        from scoreboard.domain.state import ClockValue, GameState
        GameState(game_clock=ClockValue(480.0, False, 480.0))
        with self.assertRaises(StateValidationError):
            GameState(game_clock=ClockValue(0.0, False, 61 * 60.0))


if __name__ == "__main__":
    unittest.main()
