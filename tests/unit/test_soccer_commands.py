"""Unit tests for scoreboard.domain.soccer.commands (mirrors tests/unit/test_commands.py)."""

from __future__ import annotations

import unittest

from scoreboard.domain.soccer.commands import (
    INVALID_COMMAND,
    INVALID_TEAM,
    SOCCER_ALLOWED_ARGUMENTS,
    SOCCER_NON_UNDOABLE_COMMANDS,
    SOCCER_UNDOABLE_COMMANDS,
    SoccerCommand,
    SoccerCommandError,
    SoccerCommandType,
    add_card,
    add_goal,
    add_stat,
    build_soccer_command,
    finish_shootout,
    set_period,
    set_score,
    shootout_kick,
    validate_soccer_command,
)


class SoccerCommandTypeTests(unittest.TestCase):
    def test_every_command_type_has_an_allowed_argument_set(self) -> None:
        for member in SoccerCommandType:
            self.assertIn(member, SOCCER_ALLOWED_ARGUMENTS)

    def test_undoable_and_non_undoable_are_disjoint(self) -> None:
        self.assertEqual(SOCCER_UNDOABLE_COMMANDS & SOCCER_NON_UNDOABLE_COMMANDS, frozenset())

    def test_crowd_and_clock_commands_are_neither_undoable_nor_barriers(self) -> None:
        exempt = (
            SoccerCommandType.SET_TEAM_NAME,
            SoccerCommandType.SET_GAME_STATUS,
            SoccerCommandType.CLEAR_GAME_STATUS,
            SoccerCommandType.STATUS_CLOCK_START,
            SoccerCommandType.STATUS_CLOCK_STOP,
            SoccerCommandType.GAME_CLOCK_START,
            SoccerCommandType.GAME_CLOCK_STOP,
            SoccerCommandType.GAME_CLOCK_RESET,
            SoccerCommandType.GAME_CLOCK_CORRECT,
        )
        for member in exempt:
            self.assertNotIn(member, SOCCER_UNDOABLE_COMMANDS)
            self.assertNotIn(member, SOCCER_NON_UNDOABLE_COMMANDS)

    def test_finish_shootout_is_a_barrier(self) -> None:
        self.assertIn(SoccerCommandType.FINISH_SHOOTOUT, SOCCER_NON_UNDOABLE_COMMANDS)


class ValidateSoccerCommandTests(unittest.TestCase):
    def test_valid_add_goal(self) -> None:
        self.assertIsNone(validate_soccer_command(add_goal("home")))

    def test_team_command_needs_home_or_away(self) -> None:
        error = validate_soccer_command(SoccerCommand(SoccerCommandType.ADD_GOAL, team="north"))
        self.assertEqual(error.code, INVALID_TEAM)

    def test_set_score_target_out_of_range(self) -> None:
        error = validate_soccer_command(set_score("home", 200))
        self.assertIsNotNone(error)

    def test_set_period_needs_a_known_label(self) -> None:
        error = validate_soccer_command(set_period("5th"))
        self.assertIsNotNone(error)

    def test_add_stat_step_must_be_plus_or_minus_one(self) -> None:
        error = validate_soccer_command(SoccerCommand(SoccerCommandType.ADD_STAT, team="home", stat="shots", step=2))
        self.assertIsNotNone(error)

    def test_add_card_needs_known_kind(self) -> None:
        error = validate_soccer_command(SoccerCommand(SoccerCommandType.ADD_CARD, team="home", kind="blue"))
        self.assertIsNotNone(error)

    def test_shootout_kick_needs_made_boolean(self) -> None:
        error = validate_soccer_command(SoccerCommand(SoccerCommandType.SHOOTOUT_KICK, team="home", made=None))
        self.assertIsNotNone(error)

    def test_valid_shootout_kick(self) -> None:
        self.assertIsNone(validate_soccer_command(shootout_kick("home", True)))

    def test_finish_shootout_winner_must_be_team_or_none(self) -> None:
        error = validate_soccer_command(finish_shootout(winner="north"))
        self.assertIsNotNone(error)

    def test_unknown_type_rejected(self) -> None:
        error = validate_soccer_command(SoccerCommand(type="not-a-type"))  # type: ignore[arg-type]
        self.assertEqual(error.code, INVALID_COMMAND)


class BuildSoccerCommandTests(unittest.TestCase):
    def test_builds_a_valid_command(self) -> None:
        result = build_soccer_command("add_goal", {"team": "home"}, 0)
        self.assertIsInstance(result, SoccerCommand)
        self.assertEqual(result.type, SoccerCommandType.ADD_GOAL)
        self.assertEqual(result.expected_revision, 0)

    def test_unknown_command_name_rejected(self) -> None:
        result = build_soccer_command("add_touchdown", {}, 0)
        self.assertIsInstance(result, SoccerCommandError)
        self.assertEqual(result.code, INVALID_COMMAND)

    def test_disallowed_argument_key_rejected(self) -> None:
        result = build_soccer_command("undo", {"points": 6}, 0)
        self.assertIsInstance(result, SoccerCommandError)
        self.assertEqual(result.code, INVALID_COMMAND)

    def test_shape_error_surfaces_through_the_airlock(self) -> None:
        result = build_soccer_command("set_score", {"team": "home", "value": 500}, 0)
        self.assertIsInstance(result, SoccerCommandError)

    def test_add_card_accepts_optional_player(self) -> None:
        result = build_soccer_command("add_card", {"team": "away", "kind": "yellow", "player": 10}, 3)
        self.assertIsInstance(result, SoccerCommand)
        self.assertEqual(result.player, 10)


if __name__ == "__main__":
    unittest.main()
