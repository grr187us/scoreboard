"""SoccerFieldAssistantBridge contract, per ``.scratch/soccer-mode/spec.md``
section 6 and IMPLEMENTERS.md's Field Assistant row.

Mirrors ``tests/integration/test_field_assistant_rehearsal.py`` in spirit
(exercise the bridge, not internals) but stays at the bridge/mapping layer
rather than a real ``SoccerService``/``SoccerBridge``, because
``host/soccer_bridge.py`` (agent B) and ``domain/soccer/commands.py``
(agent A) had not published their contracts (``api_bridge.md`` /
``SoccerCommandType`` on disk) while this file was written. ``FakeSoccerOperator``
below is a small, self-contained stand-in that implements exactly the surface
``host/soccer_field_assistant.py`` depends on
(``get_snapshot()`` / ``command(name, args, expected_revision, *,
source="operator")``, per IMPLEMENTERS.md) plus just enough soccer-shaped
behaviour (stat counters, cards, a shootout next-kicker rule, a revision
counter, ``STALE_REVISION``) to prove the bridge's contract end to end. It is
not a replacement for the real integration test against ``SoccerBridge``,
which the report flags for the integrator/agent B to add once that module
exists; this file's job is to lock down ``SoccerFieldAssistantBridge`` and the
pure ``map_assist_action``/``describe_assist_preview`` functions it is built
from, which do not change shape when the real bridge lands.
"""

from __future__ import annotations

import unittest
from typing import Any

from scoreboard.host.soccer_field_assistant import (
    ASSIST_ACTION_KINDS,
    SoccerFieldAssistantBridge,
    SoccerFieldAssistantError,
    describe_assist_preview,
    map_assist_action,
)


# ---------------------------------------------------------------------------
# Part 1: map_assist_action -- pure, unit-testable without any service.
# ---------------------------------------------------------------------------


class MapAssistActionTests(unittest.TestCase):
    def test_stat_maps_to_add_stat(self) -> None:
        name, args = map_assist_action({"kind": "stat", "team": "home", "stat": "shots", "step": 1})
        self.assertEqual(name, "add_stat")
        self.assertEqual(args, {"team": "home", "stat": "shots", "step": 1})

    def test_stat_step_must_be_plus_or_minus_one(self) -> None:
        for bad_step in (0, 2, -2, None, "1"):
            with self.subTest(step=bad_step):
                with self.assertRaises(SoccerFieldAssistantError):
                    map_assist_action({"kind": "stat", "team": "home", "stat": "shots", "step": bad_step})

    def test_stat_name_must_be_one_of_the_four(self) -> None:
        with self.assertRaises(SoccerFieldAssistantError):
            map_assist_action({"kind": "stat", "team": "home", "stat": "goals", "step": 1})

    def test_card_maps_to_add_card_with_kind_and_player_keys(self) -> None:
        name, args = map_assist_action(
            {"kind": "card", "team": "away", "card": "yellow", "player_number": 10}
        )
        self.assertEqual(name, "add_card")
        self.assertEqual(args, {"team": "away", "kind": "yellow", "player": 10})

    def test_card_player_number_is_optional(self) -> None:
        name, args = map_assist_action({"kind": "card", "team": "home", "card": "red", "player_number": None})
        self.assertEqual(name, "add_card")
        self.assertIsNone(args["player"])

    def test_card_player_number_out_of_range_is_refused(self) -> None:
        for bad in (-1, 100, True, "9"):
            with self.subTest(player_number=bad):
                with self.assertRaises(SoccerFieldAssistantError):
                    map_assist_action({"kind": "card", "team": "home", "card": "yellow", "player_number": bad})

    def test_card_kind_must_be_yellow_or_red(self) -> None:
        with self.assertRaises(SoccerFieldAssistantError):
            map_assist_action({"kind": "card", "team": "home", "card": "blue", "player_number": None})

    def test_shootout_kick_maps_to_shootout_kick_with_kicker_key(self) -> None:
        name, args = map_assist_action(
            {"kind": "shootout_kick", "team": "home", "made": True, "kicker_number": 9}
        )
        self.assertEqual(name, "shootout_kick")
        self.assertEqual(args, {"team": "home", "made": True, "kicker": 9})

    def test_shootout_kick_made_must_be_boolean(self) -> None:
        with self.assertRaises(SoccerFieldAssistantError):
            map_assist_action({"kind": "shootout_kick", "team": "home", "made": "yes", "kicker_number": None})

    def test_first_kicker_maps_to_set_shootout_first_kicker(self) -> None:
        name, args = map_assist_action({"kind": "first_kicker", "team": "away"})
        self.assertEqual(name, "set_shootout_first_kicker")
        self.assertEqual(args, {"team": "away"})

    def test_team_must_be_home_or_away_for_every_kind(self) -> None:
        for kind, extra in (
            ("stat", {"stat": "shots", "step": 1}),
            ("card", {"card": "yellow", "player_number": None}),
            ("shootout_kick", {"made": True, "kicker_number": None}),
            ("first_kicker", {}),
        ):
            for bad_team in ("HOME", "referee", None, ""):
                with self.subTest(kind=kind, team=bad_team):
                    action: dict[str, Any] = {"kind": kind, "team": bad_team}
                    action.update(extra)
                    with self.assertRaises(SoccerFieldAssistantError):
                        map_assist_action(action)

    def test_action_must_be_a_mapping(self) -> None:
        with self.assertRaises(SoccerFieldAssistantError):
            map_assist_action("stat")  # type: ignore[arg-type]

    # -- the allow-list itself -------------------------------------------

    def test_allow_list_has_exactly_four_kinds(self) -> None:
        self.assertEqual(
            set(ASSIST_ACTION_KINDS), {"stat", "card", "shootout_kick", "first_kicker"}
        )

    def test_goal_score_clock_period_and_undo_are_all_refused(self) -> None:
        forbidden_kinds = (
            "goal", "add_goal", "score", "set_score", "correct_goal",
            "game_clock_start", "game_clock_stop", "game_clock_reset", "game_clock_correct",
            "period_forward", "period_back", "set_period",
            "undo", "new_game", "end_game",
            "status_clock_start", "status_clock_stop", "set_game_status", "clear_game_status",
        )
        for kind in forbidden_kinds:
            with self.subTest(kind=kind):
                with self.assertRaises(SoccerFieldAssistantError):
                    map_assist_action({"kind": kind, "team": "home"})

    def test_an_unrecognised_kind_is_refused_not_silently_ignored(self) -> None:
        with self.assertRaises(SoccerFieldAssistantError):
            map_assist_action({"kind": "shoot_the_moon", "team": "home"})


# ---------------------------------------------------------------------------
# Part 2: describe_assist_preview -- pure, reads a plain snapshot dict.
# ---------------------------------------------------------------------------


class DescribeAssistPreviewTests(unittest.TestCase):
    def test_stat_preview_reports_the_resulting_count(self) -> None:
        snapshot = {"soccer": {"home": {"shots": 8}}}
        described = describe_assist_preview(snapshot, "stat", {"team": "home", "stat": "shots", "step": 1})
        self.assertEqual(described["resulting"], "HOME SHOT #9")
        self.assertEqual(described["label"], "CONFIRM → HOME SHOT #9")

    def test_stat_preview_clamps_a_decrement_at_zero(self) -> None:
        snapshot = {"soccer": {"home": {"shots": 0}}}
        described = describe_assist_preview(snapshot, "stat", {"team": "home", "stat": "shots", "step": -1})
        self.assertEqual(described["resulting"], "HOME SHOT #0")

    def test_card_preview_includes_player_number_when_given(self) -> None:
        described = describe_assist_preview({}, "card", {"team": "away", "kind": "yellow", "player": 10})
        self.assertEqual(described["resulting"], "AWAY YELLOW #10")

    def test_card_preview_omits_the_number_sign_when_absent(self) -> None:
        described = describe_assist_preview({}, "card", {"team": "away", "kind": "red", "player": None})
        self.assertEqual(described["resulting"], "AWAY RED")

    def test_shootout_kick_preview_names_made_or_missed(self) -> None:
        made = describe_assist_preview({}, "shootout_kick", {"team": "home", "made": True, "kicker": 9})
        missed = describe_assist_preview({}, "shootout_kick", {"team": "away", "made": False, "kicker": None})
        self.assertEqual(made["resulting"], "HOME MADE #9")
        self.assertEqual(missed["resulting"], "AWAY MISSED")

    def test_first_kicker_preview(self) -> None:
        described = describe_assist_preview({}, "first_kicker", {"team": "away"})
        self.assertEqual(described["resulting"], "AWAY KICKS FIRST")


# ---------------------------------------------------------------------------
# Part 3: SoccerFieldAssistantBridge -- preview never submits; finalize does.
# ---------------------------------------------------------------------------


class FakeSoccerOperator:
    """A minimal stand-in for the eventual ``SoccerBridge`` (agent B).

    Implements only what ``SoccerFieldAssistantBridge`` needs
    (``get_snapshot``/``command``), plus just enough soccer domain behaviour
    -- stat counters, cards, a next-kicker rule, revisions, and
    ``STALE_REVISION`` -- to exercise the bridge contract realistically.
    """

    def __init__(self) -> None:
        self.revision = 0
        self.stats = {"home": {"shots": 4, "saves": 2, "corners": 3, "fouls": 1}, "away": {"shots": 6, "saves": 3, "corners": 5, "fouls": 2}}
        self.cards: list[dict[str, Any]] = []
        self.shootout_kicks: list[dict[str, Any]] = []
        self.first_kicker: str | None = None
        self.commands: list[tuple[str, Any, Any, str]] = []

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "period": "SHOOTOUT" if self.first_kicker or self.shootout_kicks else "1st",
            "soccer": {
                "home": dict(self.stats["home"]),
                "away": dict(self.stats["away"]),
                "shootout": {
                    "first_kicker": self.first_kicker,
                    "next_team": self._next_kicker(),
                    "round": len(self.shootout_kicks) // 2 + 1,
                    "home_made": sum(1 for k in self.shootout_kicks if k["team"] == "home" and k["made"]),
                    "away_made": sum(1 for k in self.shootout_kicks if k["team"] == "away" and k["made"]),
                },
            },
        }

    def _next_kicker(self) -> str | None:
        if self.first_kicker is None:
            return None
        if not self.shootout_kicks:
            return self.first_kicker
        last = self.shootout_kicks[-1]["team"]
        return "away" if last == "home" else "home"

    def command(self, name: str, args: Any, expected_revision: Any, *, source: str = "operator") -> dict[str, Any]:
        self.commands.append((name, args, expected_revision, source))
        if expected_revision is not None and expected_revision != self.revision:
            return {"accepted": False, "error": {"code": "STALE_REVISION", "message": "stale"}}
        if name == "add_stat":
            team, stat, step = args["team"], args["stat"], args["step"]
            self.stats[team][stat] = max(0, self.stats[team][stat] + step)
        elif name == "add_card":
            self.cards.append({"team": args["team"], "kind": args["kind"], "player": args.get("player")})
        elif name == "shootout_kick":
            team = args["team"]
            next_team = self._next_kicker()
            if next_team is not None and team != next_team:
                return {"accepted": False, "error": {"code": "INVALID_SHOOTOUT_TEAM", "message": "not this team's kick"}}
            self.shootout_kicks.append({"team": team, "made": args["made"], "kicker": args.get("kicker")})
        elif name == "set_shootout_first_kicker":
            self.first_kicker = args["team"]
        else:
            return {"accepted": False, "error": {"code": "INVALID_COMMAND", "message": f"unsupported: {name}"}}
        self.revision += 1
        return {"accepted": True, "error": None, "view": self.get_snapshot(), "source": source}


class SoccerFieldAssistantBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.operator = FakeSoccerOperator()
        self.bridge = SoccerFieldAssistantBridge(self.operator)

    def test_get_snapshot_delegates_to_operator(self) -> None:
        self.assertEqual(self.bridge.get_snapshot(), self.operator.get_snapshot())

    def test_preview_never_changes_revision(self) -> None:
        before = self.operator.revision
        result = self.bridge.preview_assist({"kind": "stat", "team": "home", "stat": "shots", "step": 1})
        self.assertTrue(result["ok"])
        self.assertEqual(result["label"], "CONFIRM → HOME SHOT #5")
        self.assertEqual(self.operator.revision, before)
        self.assertEqual(self.operator.commands, [])

    def test_preview_of_a_forbidden_kind_is_refused_with_a_clear_error(self) -> None:
        result = self.bridge.preview_assist({"kind": "add_goal", "team": "home"})
        self.assertFalse(result["ok"])
        self.assertIsNone(result["label"])
        self.assertIsNone(result["resulting"])
        self.assertIn("add_goal", result["error"])
        self.assertEqual(self.operator.commands, [])

    def test_finalize_submits_exactly_one_command_tagged_field_assistant(self) -> None:
        action = {"kind": "stat", "team": "away", "stat": "corners", "step": 1}
        result = self.bridge.finalize_assist(action, 0)
        self.assertTrue(result["accepted"])
        self.assertEqual(len(self.operator.commands), 1)
        name, args, expected_revision, source = self.operator.commands[0]
        self.assertEqual(name, "add_stat")
        self.assertEqual(args, {"team": "away", "stat": "corners", "step": 1})
        self.assertEqual(expected_revision, 0)
        self.assertEqual(source, "field-assistant")
        self.assertEqual(self.operator.stats["away"]["corners"], 6)

    def test_finalize_of_a_forbidden_kind_never_reaches_the_operator(self) -> None:
        for forbidden in (
            {"kind": "add_goal", "team": "home"},
            {"kind": "set_score", "team": "home", "value": 4},
            {"kind": "game_clock_start"},
            {"kind": "period_forward"},
            {"kind": "undo"},
        ):
            with self.subTest(action=forbidden):
                result = self.bridge.finalize_assist(forbidden, 0)
                self.assertFalse(result["accepted"])
                self.assertEqual(result["error"]["code"], "ASSIST_ACTION_NOT_ALLOWED")
        self.assertEqual(self.operator.commands, [])

    def test_a_stale_revision_is_refused_and_one_more_confirm_finishes(self) -> None:
        action = {"kind": "stat", "team": "home", "stat": "shots", "step": 1}
        stale = self.bridge.finalize_assist(action, self.operator.revision + 1)
        self.assertFalse(stale["accepted"])
        self.assertEqual(stale["error"]["code"], "STALE_REVISION")
        self.assertEqual(self.operator.stats["home"]["shots"], 4)

        retry = self.bridge.finalize_assist(action, self.operator.revision)
        self.assertTrue(retry["accepted"])
        self.assertEqual(self.operator.stats["home"]["shots"], 5)

    def test_card_finalize_carries_the_player_number(self) -> None:
        action = {"kind": "card", "team": "away", "card": "yellow", "player_number": 10}
        result = self.bridge.finalize_assist(action, 0)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.operator.cards, [{"team": "away", "kind": "yellow", "player": 10}])

    def test_shootout_kick_is_only_accepted_for_the_next_team(self) -> None:
        self.bridge.finalize_assist({"kind": "first_kicker", "team": "home"}, self.operator.revision)
        # HOME kicks first; AWAY trying to kick next is refused.
        wrong_team = self.bridge.finalize_assist(
            {"kind": "shootout_kick", "team": "away", "made": True, "kicker_number": None},
            self.operator.revision,
        )
        self.assertFalse(wrong_team["accepted"])
        self.assertEqual(wrong_team["error"]["code"], "INVALID_SHOOTOUT_TEAM")

        right_team = self.bridge.finalize_assist(
            {"kind": "shootout_kick", "team": "home", "made": True, "kicker_number": 9},
            self.operator.revision,
        )
        self.assertTrue(right_team["accepted"])
        self.assertEqual(self.operator.shootout_kicks, [{"team": "home", "made": True, "kicker": 9}])

        # After HOME's kick, AWAY is next; HOME kicking again is refused.
        home_again = self.bridge.finalize_assist(
            {"kind": "shootout_kick", "team": "home", "made": True, "kicker_number": None},
            self.operator.revision,
        )
        self.assertFalse(home_again["accepted"])
        self.assertEqual(home_again["error"]["code"], "INVALID_SHOOTOUT_TEAM")

    def test_first_kicker_finalize(self) -> None:
        result = self.bridge.finalize_assist({"kind": "first_kicker", "team": "away"}, self.operator.revision)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.operator.first_kicker, "away")


if __name__ == "__main__":
    unittest.main()
