"""Task 5 command-service tests.

Every test drives an injected fake monotonic clock; nothing sleeps and nothing
reads wall-clock time.
"""

import unittest

from scoreboard.application.service import ScoreboardService
from scoreboard.application.snapshots import state_to_snapshot
from scoreboard.domain import commands as cmd
from scoreboard.domain.clocks import GameClock, PlayClock
from scoreboard.domain.state import MAX_SCORE, QUARTER_LABELS, GameState, default_state


class FakeMonotonic:
    def __init__(self, value: float = 0.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


SNAPSHOT_KEYS = frozenset(state_to_snapshot(default_state()))


def make_service(start: float = 0.0):
    fake = FakeMonotonic(start)
    return ScoreboardService(monotonic_clock=fake), fake


def running_play_clock(service, fake, preset: float = 25.0) -> None:
    """Load a preset and start the play clock through the service."""

    service.submit(cmd.play_clock_preset(preset))
    service.submit(cmd.play_clock_start())


class AcceptedCommandContractTests(unittest.TestCase):
    """F-002: one revision and one complete snapshot per accepted command."""

    def accepted_cases(self):
        return [
            ("home +6", lambda s, f: None, cmd.add_score("home", 6)),
            ("away +3", lambda s, f: None, cmd.add_score("away", 3)),
            (
                "home -2 correction",
                lambda s, f: s.submit(cmd.add_score("home", 6)),
                cmd.correct_score("home", 2),
            ),
            ("home direct set", lambda s, f: None, cmd.set_score("home", 21)),
            ("home name", lambda s, f: None, cmd.set_team_name("home", "Tigers")),
            ("quarter forward", lambda s, f: None, cmd.quarter_forward(confirmed=True)),
            (
                "quarter back",
                lambda s, f: s.submit(cmd.set_quarter("2nd", confirmed=True)),
                cmd.quarter_back(confirmed=True),
            ),
            ("quarter direct", lambda s, f: None, cmd.set_quarter("3rd", confirmed=True)),
            (
                "undo",
                lambda s, f: s.submit(cmd.add_score("home", 6)),
                cmd.undo(),
            ),
            ("new game", lambda s, f: None, cmd.new_game(confirmed=True)),
            ("end game", lambda s, f: None, cmd.end_game()),
            ("game clock start", lambda s, f: None, cmd.game_clock_start()),
            (
                "game clock stop",
                lambda s, f: s.submit(cmd.game_clock_start()),
                cmd.game_clock_stop(),
            ),
            ("game clock reset", lambda s, f: None, cmd.game_clock_reset()),
            ("game clock correct", lambda s, f: None, cmd.game_clock_correct(300.0)),
            ("play clock 25", lambda s, f: None, cmd.play_clock_preset(25.0)),
            ("play clock 40", lambda s, f: None, cmd.play_clock_preset(40.0)),
            ("play clock 25 and start", lambda s, f: None, cmd.play_clock_preset_start(25.0)),
            ("play clock start", running_play_clock, cmd.play_clock_start()),
            ("play clock stop", running_play_clock, cmd.play_clock_stop()),
            ("play clock clear", running_play_clock, cmd.play_clock_clear()),
            ("play clock reset", running_play_clock, cmd.play_clock_reset()),
            ("play clock correct", running_play_clock, cmd.play_clock_correct(12.0)),
            ("set down", lambda s, f: None, cmd.set_down(3)),
            ("clear down", lambda s, f: s.submit(cmd.set_down(3)), cmd.set_down(None)),
            ("set distance", lambda s, f: None, cmd.set_distance(7)),
            ("clear distance", lambda s, f: s.submit(cmd.set_distance(7)), cmd.set_distance(None)),
            ("set possession", lambda s, f: None, cmd.set_possession("home")),
            (
                "clear possession",
                lambda s, f: s.submit(cmd.set_possession("home")),
                cmd.set_possession(None),
            ),
            ("set ball on", lambda s, f: None, cmd.set_ball_on("away", 22)),
            ("timeout used", lambda s, f: None, cmd.timeout_used("home")),
            ("timeout correction", lambda s, f: None, cmd.timeout_correct("home", -1)),
            ("set timeouts", lambda s, f: None, cmd.set_timeouts("away", 1)),
        ]

    def test_accepted_command_advances_exactly_one_revision(self) -> None:
        for label, setup, command in self.accepted_cases():
            with self.subTest(command=label):
                service, fake = make_service()
                setup(service, fake)
                before = service.revision

                result = service.submit(command)

                self.assertTrue(result.accepted, msg=result.error)
                self.assertIsNone(result.error)
                self.assertEqual(result.state.revision, before + 1)
                self.assertEqual(service.revision, before + 1)

    def test_accepted_command_returns_complete_snapshot_and_event(self) -> None:
        for label, setup, command in self.accepted_cases():
            with self.subTest(command=label):
                service, fake = make_service()
                setup(service, fake)

                result = service.submit(command)

                self.assertEqual(frozenset(result.snapshot), SNAPSHOT_KEYS)
                self.assertEqual(result.snapshot["state_revision"], result.state.revision)
                self.assertEqual(result.snapshot, service.snapshot)
                self.assertIsNotNone(result.event)
                self.assertEqual(result.event.command, command.type)
                self.assertTrue(result.event.field)

    def test_returned_snapshot_is_detached_from_authoritative_state(self) -> None:
        service, _ = make_service()

        result = service.submit(cmd.add_score("home", 6))
        result.snapshot["teams"]["home"]["score"] = 99

        self.assertEqual(service.state.home_score, 6)
        self.assertEqual(service.snapshot["teams"]["home"]["score"], 6)


class RejectedCommandContractTests(unittest.TestCase):
    """U-007: rejections change nothing and explain themselves."""

    def rejected_cases(self):
        return [
            ("unsupported delta", lambda s, f: None, cmd.add_score("home", 4), cmd.INVALID_SCORE_DELTA),
            ("unknown team", lambda s, f: None, cmd.add_score("visitor", 6), cmd.INVALID_TEAM),
            (
                "correction below zero",
                lambda s, f: None,
                cmd.correct_score("home", 6),
                cmd.SCORE_BELOW_ZERO,
            ),
            (
                "increment above 199",
                lambda s, f: s.submit(cmd.set_score("home", 199)),
                cmd.add_score("home", 6),
                cmd.SCORE_ABOVE_MAXIMUM,
            ),
            ("direct set 200", lambda s, f: None, cmd.set_score("home", 200), cmd.SCORE_ABOVE_MAXIMUM),
            ("direct set -1", lambda s, f: None, cmd.set_score("home", -1), cmd.INVALID_SCORE_TARGET),
            (
                "direct set without a target",
                lambda s, f: None,
                cmd.Command(cmd.CommandType.SET_SCORE, team="home"),
                cmd.INVALID_SCORE_TARGET,
            ),
            ("invalid quarter label", lambda s, f: None, cmd.set_quarter("5th"), cmd.INVALID_QUARTER),
            ("quarter back from PRE", lambda s, f: None, cmd.quarter_back(), cmd.QUARTER_OUT_OF_RANGE),
            (
                "quarter forward from FINAL",
                lambda s, f: s.submit(cmd.set_quarter("FINAL", confirmed=True)),
                cmd.quarter_forward(),
                cmd.QUARTER_OUT_OF_RANGE,
            ),
            ("empty team name", lambda s, f: None, cmd.set_team_name("home", "   "), cmd.INVALID_TEAM_NAME),
            (
                "team name over 24 characters",
                lambda s, f: None,
                cmd.set_team_name("home", "T" * 25),
                cmd.INVALID_TEAM_NAME,
            ),
            (
                "team name after the game ends",
                lambda s, f: s.submit(cmd.end_game()),
                cmd.set_team_name("home", "Tigers"),
                cmd.TEAM_NAME_NOT_ALLOWED,
            ),
            (
                "game clock above the quarter length",
                lambda s, f: None,
                cmd.game_clock_correct(1801.0),
                cmd.INVALID_CLOCK_TIME,
            ),
            (
                "negative game clock correction",
                lambda s, f: None,
                cmd.game_clock_correct(-5.0),
                cmd.INVALID_CLOCK_TIME,
            ),
            (
                "play clock above 40",
                lambda s, f: None,
                cmd.play_clock_correct(50.0),
                cmd.INVALID_CLOCK_TIME,
            ),
            (
                "unsupported play clock preset",
                lambda s, f: None,
                cmd.play_clock_preset(30.0),
                cmd.INVALID_PLAY_CLOCK_PRESET,
            ),
            (
                "unsupported play clock preset and start",
                lambda s, f: None,
                cmd.play_clock_preset_start(30.0),
                cmd.INVALID_PLAY_CLOCK_PRESET,
            ),
            ("unconfirmed new game", lambda s, f: None, cmd.new_game(), cmd.CONFIRMATION_REQUIRED),
            ("nothing to undo", lambda s, f: None, cmd.undo(), cmd.NOTHING_TO_UNDO),
            (
                "stale revision",
                lambda s, f: s.submit(cmd.add_score("home", 6)),
                cmd.Command(cmd.CommandType.ADD_SCORE, team="home", points=6, expected_revision=0),
                cmd.STALE_REVISION,
            ),
            ("down out of range", lambda s, f: None, cmd.set_down(5), cmd.INVALID_DOWN),
            (
                "distance out of range",
                lambda s, f: None,
                cmd.set_distance(100),
                cmd.INVALID_DISTANCE,
            ),
            (
                "possession for an unknown team",
                lambda s, f: None,
                cmd.Command(cmd.CommandType.SET_POSSESSION, team="visitor"),
                cmd.INVALID_POSSESSION,
            ),
            (
                "ball on an unknown team",
                lambda s, f: None,
                cmd.Command(cmd.CommandType.SET_BALL_ON, team="visitor", value=35),
                cmd.INVALID_TEAM,
            ),
            (
                "ball on yard line out of range",
                lambda s, f: None,
                cmd.set_ball_on("home", 51),
                cmd.INVALID_BALL_ON,
            ),
            (
                "timeout used with none remaining",
                lambda s, f: s.submit(cmd.set_timeouts("home", 0)),
                cmd.timeout_used("home"),
                cmd.TIMEOUT_BELOW_ZERO,
            ),
            (
                "timeout correction is not +-1",
                lambda s, f: None,
                cmd.timeout_correct("home", 2),
                cmd.INVALID_TIMEOUT_DELTA,
            ),
            (
                "timeout correction above the maximum",
                lambda s, f: None,
                cmd.timeout_correct("home", 1),
                cmd.TIMEOUT_ABOVE_MAXIMUM,
            ),
            (
                "set timeouts out of range",
                lambda s, f: None,
                cmd.set_timeouts("home", 4),
                cmd.INVALID_TIMEOUT_TARGET,
            ),
        ]

    def test_rejected_command_changes_nothing_and_reports_an_error(self) -> None:
        for label, setup, command, expected_code in self.rejected_cases():
            with self.subTest(command=label):
                service, fake = make_service()
                setup(service, fake)
                before_state = service.state
                before_snapshot = service.snapshot
                before_game_clock = service.game_clock
                before_play_clock = service.play_clock

                result = service.submit(command)

                self.assertFalse(result.accepted)
                self.assertIsNotNone(result.error)
                self.assertEqual(result.error.code, expected_code)
                self.assertTrue(result.error.message.strip())
                self.assertIsNone(result.event)
                self.assertIs(service.state, before_state)
                self.assertEqual(service.revision, before_state.revision)
                self.assertEqual(service.snapshot, before_snapshot)
                self.assertIs(service.game_clock, before_game_clock)
                self.assertIs(service.play_clock, before_play_clock)
                self.assertEqual(result.snapshot, before_snapshot)

    def test_programmer_errors_still_raise(self) -> None:
        service, _ = make_service()

        with self.assertRaises(TypeError):
            service.submit("add_score")


class ScoringTests(unittest.TestCase):
    def test_every_increment_for_both_teams(self) -> None:
        for team in ("home", "away"):
            for points in cmd.SCORE_INCREMENTS:
                with self.subTest(team=team, points=points):
                    service, _ = make_service()

                    result = service.submit(cmd.add_score(team, points))

                    self.assertTrue(result.accepted)
                    self.assertEqual(getattr(result.state, f"{team}_score"), points)
                    self.assertEqual(result.event.team, team)
                    self.assertEqual(result.event.field, f"{team}_score")
                    self.assertEqual(result.event.old_value, 0)
                    self.assertEqual(result.event.new_value, points)

    def test_every_correction_for_both_teams(self) -> None:
        for team in ("home", "away"):
            for points in cmd.SCORE_INCREMENTS:
                with self.subTest(team=team, points=points):
                    service, _ = make_service()
                    service.submit(cmd.set_score(team, 20))

                    result = service.submit(cmd.correct_score(team, points))

                    self.assertTrue(result.accepted)
                    self.assertEqual(getattr(result.state, f"{team}_score"), 20 - points)
                    self.assertEqual(result.event.old_value, 20)
                    self.assertEqual(result.event.new_value, 20 - points)

    def test_correction_accepts_a_negative_magnitude(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("away", 6))

        result = service.submit(cmd.correct_score("away", -6))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.away_score, 0)

    def test_correction_below_zero_is_rejected_without_changing_state(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 3))
        before = service.state

        result = service.submit(cmd.correct_score("home", 6))

        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, cmd.SCORE_BELOW_ZERO)
        self.assertIs(service.state, before)
        self.assertEqual(service.state.home_score, 3)

    def test_direct_set_reports_old_and_new_values(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 6))

        result = service.submit(cmd.set_score("home", 14))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.home_score, 14)
        self.assertEqual(result.event.old_value, 6)
        self.assertEqual(result.event.new_value, 14)

    def test_direct_set_supports_the_documented_display_range(self) -> None:
        for value in (0, 99, 100, MAX_SCORE):
            with self.subTest(value=value):
                service, _ = make_service()

                result = service.submit(cmd.set_score("away", value))

                self.assertTrue(result.accepted)
                self.assertEqual(result.state.away_score, value)


class UndoTests(unittest.TestCase):
    def test_undo_restores_the_previous_score_as_a_forward_transition(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 6))
        revision_after_score = service.revision

        result = service.submit(cmd.undo())

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.home_score, 0)
        self.assertEqual(result.state.revision, revision_after_score + 1)
        self.assertEqual(result.event.command, cmd.CommandType.UNDO)
        self.assertEqual(result.event.field, "home_score")
        self.assertEqual(result.event.old_value, 6)
        self.assertEqual(result.event.new_value, 0)

    def test_undo_restores_the_previous_quarter(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("2nd", confirmed=True))
        service.submit(cmd.quarter_forward(confirmed=True))
        self.assertEqual(service.state.quarter, "HALF")

        result = service.submit(cmd.undo())

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.quarter, "2nd")

    def test_undo_reverses_only_the_most_recent_reversible_command(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 6))
        service.submit(cmd.add_score("home", 1))

        service.submit(cmd.undo())

        self.assertEqual(service.state.home_score, 6)

    def test_undo_cannot_be_undone(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 6))
        service.submit(cmd.undo())

        result = service.submit(cmd.undo())

        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, cmd.NOT_UNDOABLE)
        self.assertEqual(service.state.home_score, 0)

    def test_new_game_and_end_game_cannot_be_undone(self) -> None:
        for label, dangerous in (
            ("new game", cmd.new_game(confirmed=True)),
            ("end game", cmd.end_game()),
        ):
            with self.subTest(command=label):
                service, _ = make_service()
                service.submit(cmd.add_score("home", 6))
                service.submit(dangerous)
                before = service.state

                result = service.submit(cmd.undo())

                self.assertFalse(result.accepted)
                self.assertEqual(result.error.code, cmd.NOT_UNDOABLE)
                self.assertIs(service.state, before)

    def test_a_confirmed_quarter_change_cannot_be_undone(self) -> None:
        service, fake = make_service()
        service.submit(cmd.set_quarter("2nd", confirmed=True))
        service.submit(cmd.game_clock_start())
        fake.advance(30.0)
        service.submit(cmd.quarter_forward(confirmed=True))
        before = service.state

        result = service.submit(cmd.undo())

        self.assertFalse(result.accepted)
        self.assertEqual(result.error.code, cmd.NOT_UNDOABLE)
        self.assertIs(service.state, before)


class QuarterTests(unittest.TestCase):
    def test_quarter_change_confirms_while_both_clocks_are_stopped(self) -> None:
        service, fake = make_service()

        prompt = service.submit(cmd.quarter_forward())
        result = service.submit(cmd.quarter_forward(confirmed=True))

        self.assertTrue(result.accepted)
        self.assertTrue(prompt.confirmation_required)
        self.assertEqual(result.state.quarter, "1st")
        self.assertFalse(result.state.game_clock.running)
        self.assertFalse(result.state.play_clock.running)

    def test_every_label_is_reachable_by_direct_selection(self) -> None:
        for label in QUARTER_LABELS:
            with self.subTest(label=label):
                service, _ = make_service()

                result = service.submit(cmd.set_quarter(label, confirmed=True))

                self.assertTrue(result.accepted)
                self.assertEqual(result.state.quarter, label)

    def test_running_game_clock_requires_confirmation_then_commits_once(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(20.0)
        before_state = service.state
        before_revision = service.revision

        first = service.submit(cmd.quarter_forward())

        self.assertFalse(first.accepted)
        self.assertTrue(first.confirmation_required)
        self.assertEqual(first.error.code, cmd.CONFIRMATION_REQUIRED)
        self.assertIs(service.state, before_state)
        self.assertEqual(service.revision, before_revision)
        self.assertTrue(service.game_clock.current_value(fake()).running)

        second = service.submit(cmd.quarter_forward(confirmed=True))

        self.assertTrue(second.accepted)
        self.assertEqual(second.state.revision, before_revision + 1)
        self.assertEqual(second.state.quarter, "1st")
        self.assertFalse(second.state.game_clock.running)
        self.assertFalse(second.state.play_clock.running)
        self.assertAlmostEqual(second.state.game_clock.seconds, 720.0)

    def test_running_play_clock_alone_also_requires_confirmation(self) -> None:
        service, fake = make_service()
        running_play_clock(service, fake, 40.0)
        fake.advance(5.0)
        before_state = service.state

        first = service.submit(cmd.set_quarter("3rd"))

        self.assertFalse(first.accepted)
        self.assertEqual(first.error.code, cmd.CONFIRMATION_REQUIRED)
        self.assertIs(service.state, before_state)

        second = service.submit(cmd.set_quarter("3rd", confirmed=True))

        self.assertTrue(second.accepted)
        self.assertEqual(second.state.quarter, "3rd")
        self.assertFalse(second.state.play_clock.running)
        self.assertAlmostEqual(second.state.play_clock.seconds, 35.0)

    def test_live_quarter_transition_at_zero_loads_the_full_stopped_clock_and_blocks_undo(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("1st", confirmed=True))
        service.submit(cmd.game_clock_correct(0.0))

        result = service.submit(cmd.quarter_forward(confirmed=True))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.quarter, "2nd")
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, 12 * 60)
        undo = service.submit(cmd.undo())
        self.assertFalse(undo.accepted)
        self.assertEqual(undo.error.code, cmd.NOT_UNDOABLE)

    def test_live_quarter_transition_preserves_a_nonzero_game_clock(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("1st", confirmed=True))
        service.submit(cmd.game_clock_correct(5 * 60 + 30))

        result = service.submit(cmd.quarter_forward(confirmed=True))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.quarter, "2nd")
        self.assertAlmostEqual(result.state.game_clock.seconds, 5 * 60 + 30)

    def test_non_live_quarter_does_not_reset_but_halftime_to_live_does(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("2nd", confirmed=True))
        service.submit(cmd.game_clock_correct(0.0))

        halftime = service.submit(cmd.quarter_forward(confirmed=True))
        self.assertTrue(halftime.accepted)
        self.assertEqual(halftime.state.quarter, "HALF")
        self.assertAlmostEqual(halftime.state.game_clock.seconds, 0.0)

        second_half = service.submit(cmd.set_quarter("3rd", confirmed=True))
        self.assertTrue(second_half.accepted)
        self.assertEqual(second_half.state.quarter, "3rd")
        self.assertFalse(second_half.state.game_clock.running)
        self.assertAlmostEqual(second_half.state.game_clock.seconds, 12 * 60)

    def test_quarter_back_applies_the_same_live_quarter_zero_rule(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_quarter("HALF", confirmed=True))
        service.submit(cmd.game_clock_correct(0.0))

        result = service.submit(cmd.quarter_back(confirmed=True))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.quarter, "2nd")
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, 12 * 60)


class LifecycleTests(unittest.TestCase):
    def test_new_game_requires_confirmation(self) -> None:
        service, _ = make_service()
        service.submit(cmd.add_score("home", 6))
        before = service.state

        result = service.submit(cmd.new_game())

        self.assertFalse(result.accepted)
        self.assertTrue(result.confirmation_required)
        self.assertIs(service.state, before)
        self.assertEqual(service.state.home_score, 6)

    def test_confirmed_new_game_replaces_the_previous_game(self) -> None:
        service, fake = make_service()
        service.submit(cmd.set_team_name("home", "Tigers"))
        service.submit(cmd.set_team_name("away", "Eagles"))
        self.assertTrue(service.submit(cmd.set_score("home", 21)).accepted)
        service.submit(cmd.set_quarter("3rd", confirmed=True))
        service.submit(cmd.game_clock_start())
        running_play_clock(service, fake, 25.0)
        fake.advance(12.0)
        previous_revision = service.revision
        clean = default_state()

        result = service.submit(cmd.new_game(confirmed=True))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.revision, previous_revision + 1)
        self.assertEqual(result.state.home_name, clean.home_name)
        self.assertEqual(result.state.away_name, clean.away_name)
        self.assertEqual(result.state.home_score, 0)
        self.assertEqual(result.state.away_score, 0)
        self.assertEqual(result.state.quarter, clean.quarter)
        self.assertEqual(result.state.lifecycle, clean.lifecycle)
        self.assertFalse(result.state.game_clock.running)
        self.assertFalse(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, clean.game_clock.seconds)
        self.assertAlmostEqual(result.state.play_clock.seconds, clean.play_clock.seconds)

        # The replacement is a genuinely fresh game, not a paused old one.
        fake.advance(30.0)
        self.assertFalse(service.game_clock.running)
        self.assertAlmostEqual(service.game_clock.remaining_at(), clean.game_clock.seconds)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 0.0)

    def test_end_game_stops_both_clocks_without_erasing_the_game(self) -> None:
        service, fake = make_service()
        service.submit(cmd.set_team_name("home", "Tigers"))
        self.assertTrue(service.submit(cmd.set_score("home", 21)).accepted)
        self.assertTrue(service.submit(cmd.set_score("away", 14)).accepted)
        service.submit(cmd.set_quarter("4th", confirmed=True))
        service.submit(cmd.game_clock_start())
        running_play_clock(service, fake, 25.0)
        fake.advance(10.0)

        result = service.submit(cmd.end_game())

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.lifecycle, "FINAL")
        self.assertFalse(result.state.game_clock.running)
        self.assertFalse(result.state.play_clock.running)
        self.assertEqual(result.state.home_name, "Tigers")
        self.assertEqual(result.state.home_score, 21)
        self.assertEqual(result.state.away_score, 14)
        self.assertEqual(result.state.quarter, "4th")
        self.assertEqual(result.event.old_value, "IN_PROGRESS")
        self.assertEqual(result.event.new_value, "FINAL")

        fake.advance(60.0)
        self.assertAlmostEqual(service.game_clock.remaining_at(), 710.0)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 15.0)


class TeamNameTests(unittest.TestCase):
    def test_name_is_trimmed_and_reported(self) -> None:
        service, _ = make_service()

        result = service.submit(cmd.set_team_name("home", "  Tigers  "))

        self.assertTrue(result.accepted)
        self.assertEqual(result.state.home_name, "Tigers")
        self.assertEqual(result.event.old_value, "HOME")
        self.assertEqual(result.event.new_value, "Tigers")

    def test_boundary_lengths(self) -> None:
        for length, accepted in ((1, True), (24, True), (25, False)):
            with self.subTest(length=length):
                service, _ = make_service()

                result = service.submit(cmd.set_team_name("away", "T" * length))

                self.assertEqual(result.accepted, accepted)


class PlayClockPresetStartCommandTests(unittest.TestCase):
    def test_preset_start_loads_and_runs_in_one_command(self) -> None:
        service, fake = make_service()

        result = service.submit(cmd.play_clock_preset_start(25.0))

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 25.0)
        fake.advance(1.0)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 24.0)

    def test_preset_start_reloads_and_restarts_an_already_running_play_clock(self) -> None:
        service, fake = make_service()
        running_play_clock(service, fake, 40.0)
        fake.advance(8.0)

        result = service.submit(cmd.play_clock_preset_start(25.0))

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 25.0)
        fake.advance(1.0)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 24.0)


class GameClockCommandTests(unittest.TestCase):
    def test_start_matches_the_engine_and_materializes_into_state(self) -> None:
        service, fake = make_service()
        reference = GameClock(monotonic_clock=fake).start(now=0.0)

        result = service.submit(cmd.game_clock_start())

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, reference.remaining_at(0.0))

        fake.advance(45.0)
        self.assertAlmostEqual(service.game_clock.remaining_at(), reference.remaining_at(45.0))
        self.assertAlmostEqual(service.game_clock.remaining_at(), 675.0)

    def test_stop_matches_the_engine(self) -> None:
        service, fake = make_service()
        reference = GameClock(monotonic_clock=fake).start(now=0.0)
        service.submit(cmd.game_clock_start())
        fake.advance(31.5)

        result = service.submit(cmd.game_clock_stop())
        reference = reference.stop(now=31.5)

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, reference.remaining_at(31.5))
        self.assertAlmostEqual(result.state.game_clock.seconds, 688.5)

    def test_reset_restores_the_quarter_length_while_stopped(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(100.0)

        result = service.submit(cmd.game_clock_reset())

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(
            result.state.game_clock.seconds, 1800.0
        )

    def test_correction_stops_the_clock_and_applies_the_validated_value(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(10.0)

        result = service.submit(cmd.game_clock_correct(125.5))

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, 125.5)
        self.assertEqual(result.event.old_value["running"], True)
        self.assertEqual(result.event.new_value["running"], False)
        self.assertAlmostEqual(result.event.new_value["seconds"], 125.5)

        fake.advance(30.0)
        self.assertAlmostEqual(service.game_clock.remaining_at(), 125.5)

    def test_repeated_start_is_idempotent(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(5.0)
        revision_before = service.revision

        first = service.submit(cmd.game_clock_start())
        second = service.submit(cmd.game_clock_start())

        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(service.revision, revision_before + 2)
        self.assertTrue(service.state.game_clock.running)
        self.assertAlmostEqual(first.state.game_clock.seconds, 1795.0)
        self.assertAlmostEqual(second.state.game_clock.seconds, 1795.0)
        fake.advance(10.0)
        self.assertAlmostEqual(service.game_clock.remaining_at(), 1785.0)

    def test_repeated_stop_is_idempotent(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(7.25)
        service.submit(cmd.game_clock_stop())

        result = service.submit(cmd.game_clock_stop())

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.game_clock.running)
        self.assertAlmostEqual(result.state.game_clock.seconds, 1792.75)


class PlayClockCommandTests(unittest.TestCase):
    def test_preset_loads_the_exact_value_while_stopped(self) -> None:
        for preset in (25.0, 40.0):
            with self.subTest(preset=preset):
                service, fake = make_service()

                result = service.submit(cmd.play_clock_preset(preset))

                self.assertTrue(result.accepted)
                self.assertFalse(result.state.play_clock.running)
                self.assertAlmostEqual(result.state.play_clock.seconds, preset)

    def test_start_stop_and_clear_match_the_engine(self) -> None:
        service, fake = make_service()
        reference = PlayClock(monotonic_clock=fake).load_preset(25.0, now=0.0).start(now=0.0)

        service.submit(cmd.play_clock_preset(25.0))
        started = service.submit(cmd.play_clock_start())
        self.assertTrue(started.state.play_clock.running)

        fake.advance(6.5)
        stopped = service.submit(cmd.play_clock_stop())
        reference = reference.stop(now=6.5)

        self.assertAlmostEqual(stopped.state.play_clock.seconds, reference.remaining_at(6.5))
        self.assertAlmostEqual(stopped.state.play_clock.seconds, 18.5)

        cleared = service.submit(cmd.play_clock_clear())
        self.assertAlmostEqual(cleared.state.play_clock.seconds, 0.0)
        self.assertFalse(cleared.state.play_clock.running)

    def test_reset_restores_the_loaded_preset(self) -> None:
        service, fake = make_service()
        service.submit(cmd.play_clock_preset(40.0))
        service.submit(cmd.play_clock_start())
        fake.advance(11.0)
        service.submit(cmd.play_clock_stop())

        result = service.submit(cmd.play_clock_reset())

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 40.0)

    def test_correction_stops_the_play_clock_and_applies_the_value(self) -> None:
        service, fake = make_service()
        running_play_clock(service, fake, 40.0)
        fake.advance(4.0)

        result = service.submit(cmd.play_clock_correct(9.5))

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 9.5)
        fake.advance(20.0)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 9.5)

    def test_play_clock_commands_never_change_the_game_clock(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        fake.advance(10.0)
        expected = service.game_clock.remaining_at()

        for command in (
            cmd.play_clock_preset(25.0),
            cmd.play_clock_start(),
            cmd.play_clock_stop(),
            cmd.play_clock_reset(),
            cmd.play_clock_correct(5.0),
            cmd.play_clock_clear(),
        ):
            with self.subTest(command=command.type.value):
                result = service.submit(command)

                self.assertTrue(result.accepted, msg=result.error)
                self.assertTrue(result.state.game_clock.running)
                self.assertAlmostEqual(service.game_clock.remaining_at(), expected)


class ClockCouplingTests(unittest.TestCase):
    """F-048: a stopped-to-running game clock clears the play clock."""

    def test_game_clock_start_clears_a_running_play_clock(self) -> None:
        service, fake = make_service()
        running_play_clock(service, fake, 25.0)
        fake.advance(3.0)
        self.assertTrue(service.play_clock.current_value(fake()).running)

        result = service.submit(cmd.game_clock_start())

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.game_clock.running)
        self.assertFalse(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 0.0)

    def test_redundant_game_clock_start_leaves_the_play_clock_alone(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        running_play_clock(service, fake, 25.0)
        fake.advance(4.0)

        result = service.submit(cmd.game_clock_start())

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 21.0)
        fake.advance(1.0)
        self.assertAlmostEqual(service.play_clock.remaining_at(), 20.0)

    def test_game_clock_stop_clears_a_running_play_clock_in_the_same_commit(self) -> None:
        service, fake = make_service()
        service.submit(cmd.game_clock_start())
        running_play_clock(service, fake, 40.0)
        fake.advance(8.0)

        result = service.submit(cmd.game_clock_stop())

        self.assertTrue(result.accepted)
        self.assertFalse(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 0.0)
        self.assertTrue(result.state.play_clock_cleared)

    def test_redundant_game_clock_stop_leaves_an_independent_play_clock_running(self) -> None:
        service, fake = make_service()
        service.submit(cmd.play_clock_preset(40.0))
        service.submit(cmd.play_clock_start())
        fake.advance(8.0)

        result = service.submit(cmd.game_clock_stop())

        self.assertTrue(result.accepted)
        self.assertTrue(result.state.play_clock.running)
        self.assertAlmostEqual(result.state.play_clock.seconds, 32.0)


class SerializationAndTimeSourceTests(unittest.TestCase):
    def test_commands_apply_in_submission_order(self) -> None:
        service, _ = make_service()
        sequence = [
            cmd.add_score("home", 6),
            cmd.add_score("home", 1),
            cmd.add_score("away", 3),
            cmd.correct_score("home", 1),
            cmd.add_score("away", 6),
        ]

        revisions = [service.submit(command).state.revision for command in sequence]

        self.assertEqual(revisions, [1, 2, 3, 4, 5])
        self.assertEqual(service.state.home_score, 6)
        self.assertEqual(service.state.away_score, 9)

    def test_rapid_repeated_commands_are_deterministic(self) -> None:
        first, first_fake = make_service()
        second, second_fake = make_service()
        burst = [cmd.game_clock_start()] * 3 + [cmd.add_score("home", 6)] * 2

        for command in burst:
            first.submit(command)
        for command in burst:
            second.submit(command)

        self.assertEqual(first.snapshot, second.snapshot)
        self.assertEqual(first.revision, len(burst))
        self.assertEqual(first.state.home_score, 12)
        self.assertTrue(first.state.game_clock.running)

    def test_nested_submission_is_a_programmer_error(self) -> None:
        holder: dict[str, ScoreboardService] = {}

        def reentrant_clock() -> float:
            holder["service"].submit(cmd.add_score("away", 1))
            return 0.0

        holder["service"] = ScoreboardService(monotonic_clock=reentrant_clock)

        with self.assertRaises(RuntimeError):
            holder["service"].submit(cmd.add_score("home", 6))

        self.assertEqual(holder["service"].revision, 0)

    def test_all_timing_flows_through_the_injected_clock(self) -> None:
        fake = FakeMonotonic(1000.0)
        service = ScoreboardService(monotonic_clock=fake)

        self.assertIs(service.monotonic_clock, fake)
        self.assertIs(service.game_clock.monotonic_clock, fake)
        self.assertIs(service.play_clock.monotonic_clock, fake)

        service.submit(cmd.game_clock_start())
        service.submit(cmd.play_clock_preset(25.0))
        service.submit(cmd.play_clock_start())

        # Without advancing the fake clock, no time passes at all.
        for _ in range(5):
            result = service.submit(cmd.add_score("home", 1))
            self.assertAlmostEqual(result.state.game_clock.seconds, 1800.0)
            self.assertAlmostEqual(result.state.play_clock.seconds, 25.0)

        fake.advance(9.0)
        result = service.submit(cmd.add_score("home", 1))
        self.assertAlmostEqual(result.state.game_clock.seconds, 1791.0)
        self.assertAlmostEqual(result.state.play_clock.seconds, 16.0)

    def test_engines_are_replaced_not_mutated(self) -> None:
        service, fake = make_service()
        original_state = service.state
        original_clock = service.game_clock

        service.submit(cmd.game_clock_start())

        self.assertIsNot(service.state, original_state)
        self.assertIsNot(service.game_clock, original_clock)
        self.assertFalse(original_clock.running)
        self.assertEqual(original_state.revision, 0)
        self.assertIsInstance(service.state, GameState)


class FootballStateTests(unittest.TestCase):
    """Down, distance, possession, ball-on, and timeouts (docs/PHASE_2_BACKLOG.md
    "Deferred scoreboard fields"). None of these touch a clock, a score, or the
    quarter, and none of them are derived automatically from another command.
    """

    def test_down_and_distance_default_to_not_applicable(self) -> None:
        service, _ = make_service()

        self.assertIsNone(service.state.down)
        self.assertIsNone(service.state.distance)
        self.assertIsNone(service.state.possession)
        self.assertEqual(service.state.home_timeouts, 3)
        self.assertEqual(service.state.away_timeouts, 3)
        self.assertEqual(service.state.ball_on.team, "home")
        self.assertEqual(service.state.ball_on.yard_line, 50)

    def test_set_down_is_undoable(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_down(2))

        result = service.submit(cmd.set_down(3))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.down, 3)

        undone = service.submit(cmd.undo())
        self.assertTrue(undone.accepted)
        self.assertEqual(undone.state.down, 2)

    def test_clearing_down_and_distance_round_trips_through_undo(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_down(3))
        service.submit(cmd.set_distance(7))

        cleared = service.submit(cmd.set_distance(None))
        self.assertTrue(cleared.accepted)
        self.assertIsNone(cleared.state.distance)
        self.assertEqual(cleared.state.down, 3, "distance and down are independent fields")

        undone = service.submit(cmd.undo())
        self.assertEqual(undone.state.distance, 7)

    def test_a_quarter_change_does_not_touch_down_distance_or_possession(self) -> None:
        """No command couples these to the quarter; only an operator sets them."""

        service, _ = make_service()
        service.submit(cmd.set_down(3))
        service.submit(cmd.set_distance(7))
        service.submit(cmd.set_possession("home"))

        result = service.submit(cmd.set_quarter("2nd", confirmed=True))

        self.assertEqual(result.state.down, 3)
        self.assertEqual(result.state.distance, 7)
        self.assertEqual(result.state.possession, "home")

    def test_new_game_resets_every_football_field(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_down(4))
        service.submit(cmd.set_distance(0))
        service.submit(cmd.set_possession("away"))
        service.submit(cmd.set_ball_on("away", 3))
        service.submit(cmd.timeout_used("home"))

        result = service.submit(cmd.new_game(confirmed=True))

        self.assertIsNone(result.state.down)
        self.assertIsNone(result.state.distance)
        self.assertIsNone(result.state.possession)
        self.assertEqual(result.state.ball_on.team, "home")
        self.assertEqual(result.state.ball_on.yard_line, 50)
        self.assertEqual(result.state.home_timeouts, 3)

    def test_set_possession_can_be_cleared_and_undone(self) -> None:
        service, _ = make_service()
        service.submit(cmd.set_possession("home"))

        cleared = service.submit(cmd.set_possession(None))
        self.assertTrue(cleared.accepted)
        self.assertIsNone(cleared.state.possession)

        undone = service.submit(cmd.undo())
        self.assertEqual(undone.state.possession, "home")

    def test_ball_on_is_one_field_and_undo_restores_it_whole(self) -> None:
        """Side and yard line change together; Undo must not mix old/new halves."""

        service, _ = make_service()
        service.submit(cmd.set_ball_on("home", 40))

        moved = service.submit(cmd.set_ball_on("away", 22))
        self.assertTrue(moved.accepted)
        self.assertEqual((moved.state.ball_on.team, moved.state.ball_on.yard_line), ("away", 22))

        undone = service.submit(cmd.undo())
        self.assertEqual((undone.state.ball_on.team, undone.state.ball_on.yard_line), ("home", 40))

    def test_ball_on_event_reports_a_plain_dictionary_not_a_domain_object(self) -> None:
        service, _ = make_service()

        result = service.submit(cmd.set_ball_on("away", 22))

        self.assertEqual(result.event.old_value, {"team": "home", "yard_line": 50})
        self.assertEqual(result.event.new_value, {"team": "away", "yard_line": 22})

    def test_timeout_used_decrements_and_stops_at_zero(self) -> None:
        service, _ = make_service()

        for expected in (2, 1, 0):
            result = service.submit(cmd.timeout_used("home"))
            self.assertTrue(result.accepted)
            self.assertEqual(result.state.home_timeouts, expected)

        exhausted = service.submit(cmd.timeout_used("home"))
        self.assertFalse(exhausted.accepted)
        self.assertEqual(exhausted.error.code, cmd.TIMEOUT_BELOW_ZERO)
        self.assertEqual(service.state.home_timeouts, 0)

    def test_timeout_correct_is_undoable_and_bounded(self) -> None:
        service, _ = make_service()
        service.submit(cmd.timeout_used("away"))

        corrected = service.submit(cmd.timeout_correct("away", 1))
        self.assertTrue(corrected.accepted)
        self.assertEqual(corrected.state.away_timeouts, 3)

        undone = service.submit(cmd.undo())
        self.assertEqual(undone.state.away_timeouts, 2)

    def test_home_and_away_timeouts_are_independent(self) -> None:
        service, _ = make_service()

        service.submit(cmd.timeout_used("home"))

        self.assertEqual(service.state.home_timeouts, 2)
        self.assertEqual(service.state.away_timeouts, 3)

    def test_set_timeouts_direct_entry_is_undoable(self) -> None:
        service, _ = make_service()

        result = service.submit(cmd.set_timeouts("home", 1))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.home_timeouts, 1)

        undone = service.submit(cmd.undo())
        self.assertEqual(undone.state.home_timeouts, 3)


if __name__ == "__main__":
    unittest.main()
