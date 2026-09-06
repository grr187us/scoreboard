"""Task 7 bridge and operator-interface contract tests.

These assert behaviour at the bridge boundary rather than by driving a browser:
a browser test would prove that one build of WebView2 dispatched a click, while
these prove that every control reaches the right command, that nothing changes
before Apply, and that no domain object escapes into JavaScript.

The one requirement that cannot be checked here is U-001, the 1366x768 visual
fit at 100% and 125% scaling. That is recorded as a manual observation with
evidence, not claimed from an automated pass.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from scoreboard.domain.commands import CommandType
from scoreboard.host.bridge import (
    OPERATOR_MOUSE_SOURCE,
    DisplayLink,
    FieldAssistantBridge,
    ScoreboardBridge,
    SpectatorBridge,
    build_command,
)
from scoreboard.infrastructure.persistence import decode, read_action_history

from tests.integration.support import FailingConnection, TemporaryDataDirectoryTest

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
OPERATOR_HTML = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")
OPERATOR_JS = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
SPECTATOR_HTML = (VIEWS / "spectator" / "index.html").read_text(encoding="utf-8")


#: One representative payload per command, exactly as a control sends it.
COMMAND_PAYLOADS: dict[str, dict] = {
    "set_team_name": {"team": "home", "name": "Tigers"},
    "add_score": {"team": "home", "points": 6},
    "correct_score": {"team": "home", "points": 1},
    "set_score": {"team": "home", "value": 21},
    "undo": {},
    "quarter_forward": {},
    "quarter_back": {},
    "set_quarter": {"label": "2nd"},
    "new_game": {"confirmed": True},
    "end_game": {},
    "game_clock_start": {},
    "game_clock_stop": {},
    "game_clock_reset": {},
    "game_clock_correct": {"seconds": 300.0},
    "play_clock_preset": {"seconds": 40},
    "play_clock_preset_start": {"seconds": 40},
    "play_clock_start": {},
    "play_clock_stop": {},
    "play_clock_clear": {},
    "play_clock_reset": {},
    "play_clock_correct": {"seconds": 12.0},
    "event_countdown_select": {"label": "HALFTIME"},
    "event_countdown_start": {},
    "event_countdown_stop": {},
    "event_countdown_reset": {},
    "event_countdown_correct": {"seconds": 120.0},
    "set_down": {"value": 2},
    "set_distance": {"value": 8},
    "set_possession": {"team": "home"},
    "set_ball_on": {"team": "away", "value": 35},
    "timeout_used": {"team": "home"},
    "timeout_correct": {"team": "home", "points": -1},
    "set_timeouts": {"team": "away", "value": 1},
}

#: A few commands need the board to be somewhere first: there is nothing to
#: undo, subtract, or step back from on a brand new game.
COMMAND_PRELUDES: dict[str, list[tuple[str, dict]]] = {
    "undo": [("add_score", {"team": "home", "points": 6})],
    "correct_score": [("add_score", {"team": "home", "points": 6})],
    "quarter_back": [("quarter_forward", {})],
}


class BridgeTestCase(TemporaryDataDirectoryTest):
    """A bridge over a real service and store, with no window anywhere."""

    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.display = DisplayLink()
        self.bridge = ScoreboardBridge(self.service, self.store, display=self.display)

    def send(self, name, args=None, expected_revision="current"):
        if expected_revision == "current":
            expected_revision = self.service.revision
        return self.bridge.command(name, args or {}, expected_revision)


class MousePathTests(BridgeTestCase):
    """K-001: every command is reachable, and every control has a command."""

    def test_every_command_has_a_control_in_the_operator_page(self) -> None:
        controls = set(re.findall(r'data-command="([a-z_]+)"', OPERATOR_HTML))
        # set_quarter's buttons are built from the view model's quarter labels,
        # so the page carries it as a rendered control rather than a literal.
        controls.update(re.findall(r"'data-command', '([a-z_]+)'", OPERATOR_JS))

        # The composite Field Assistant command deliberately has no generic
        # operator ``data-command`` control: only its separate bridge can
        # submit it, preventing an accidental sequence of manual set_* calls.
        missing = {
            command.value for command in CommandType
            if command is not CommandType.FINALIZE_FIELD_ACTION
        } - controls
        self.assertEqual(missing, set(), f"no mouse control for: {sorted(missing)}")

    def test_no_control_names_a_command_that_does_not_exist(self) -> None:
        controls = set(re.findall(r'data-command="([a-z_]+)"', OPERATOR_HTML))
        known = {command.value for command in CommandType}

        self.assertEqual(controls - known, set())

    def test_preset_start_buttons_are_distinct_and_reach_the_atomic_command(self) -> None:
        for seconds in (25, 40):
            with self.subTest(seconds=seconds):
                control = (
                    f'class="preset preset-start" data-command="play_clock_preset_start" '
                    f'data-seconds="{seconds}"'
                )
                self.assertIn(control, OPERATOR_HTML)

                result = self.send("play_clock_preset_start", {"seconds": seconds})
                self.assertTrue(result["accepted"], result["error"])
                self.assertTrue(result["view"]["clocks"]["play"]["running"])
                self.assertEqual(result["view"]["clocks"]["play"]["seconds"], seconds)

    def test_every_command_reaches_the_service_through_the_bridge(self) -> None:
        for command in CommandType:
            if command is CommandType.FINALIZE_FIELD_ACTION:
                continue
            with self.subTest(command=command.value):
                # Each command runs against a fresh game so an earlier one
                # cannot make a later one impossible.
                service, store = self.started_session()
                bridge = ScoreboardBridge(service, store)
                for name, args in COMMAND_PRELUDES.get(command.value, []):
                    bridge.command(name, args, service.revision)
                before = service.revision

                result = bridge.command(
                    command.value, COMMAND_PAYLOADS[command.value], before
                )

                self.assertTrue(result["accepted"], result["error"])
                self.assertEqual(result["view"]["revision"], before + 1)

    def test_a_command_is_recorded_with_the_operator_mouse_source(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})

        row = read_action_history(self.paths.database)[-1]

        self.assertEqual(row["source"], OPERATOR_MOUSE_SOURCE)
        self.assertEqual(decode(row["new_value"]), 6)

    def test_the_test_window_control_is_reachable_without_becoming_a_command(self) -> None:
        self.assertIn('data-action="open_advanced"', OPERATOR_HTML)
        self.assertIn('data-action="open_test_window"', OPERATOR_HTML)
        self.assertIn("api.open_test_window()", OPERATOR_JS)
        self.assertNotIn("open_test_window", {command.value for command in CommandType})

    def test_field_assistant_is_a_separate_explicit_window_control(self) -> None:
        self.assertIn('data-action="open_field_assistant"', OPERATOR_HTML)
        self.assertIn("api.open_field_assistant()", OPERATOR_JS)
        self.assertNotIn('data-command="finalize_field_action"', OPERATOR_HTML)


class FieldAssistantBridgeTests(BridgeTestCase):
    """FA-19/20/25: the helper owns a draft, not game mutations."""

    def set_live_quarter(self) -> None:
        accepted = self.send("set_quarter", {"label": "1st", "confirmed": True})
        self.assertTrue(accepted["accepted"], accepted["error"])

    def start_action(self) -> dict:
        return {
            "kind": "start_series",
            "payload": {
                "offense": "home",
                "ball_absolute": 25,
                "first_quarter_home_direction": 1,
            },
        }

    def test_preview_is_read_only_and_finalization_is_one_composite_source(self) -> None:
        self.set_live_quarter()
        assistant = FieldAssistantBridge(self.bridge)
        revision = self.service.revision

        preview = assistant.preview_field_action(self.start_action())
        self.assertTrue(preview["accepted"], preview["error"])
        self.assertEqual(self.service.revision, revision)
        self.assertEqual(preview["preview"]["down"], 1)

        committed = assistant.finalize_field_action(self.start_action(), revision)
        self.assertTrue(committed["accepted"], committed["error"])
        self.assertEqual(self.service.revision, revision + 1)
        rows = read_action_history(self.paths.database)
        self.assertEqual(rows[-1]["command"], "finalize_field_action")
        self.assertEqual(rows[-1]["source"], "field-assistant")
        self.assertEqual(committed["view"]["football"]["down"], 1)

    def test_stale_draft_is_refused_and_manual_controls_remain_available(self) -> None:
        self.set_live_quarter()
        assistant = FieldAssistantBridge(self.bridge)
        base = assistant.get_snapshot()["revision"]
        self.send("set_down", {"value": 2})

        stale = assistant.finalize_field_action(self.start_action(), base)
        self.assertFalse(stale["accepted"])
        self.assertEqual(stale["error"]["code"], "STALE_REVISION")
        # FA-20: The pre-existing manual path remains usable and is not
        # silently overwritten by the rejected draft.
        manual = self.send("set_ball_on", {"team": "away", "value": 35})
        self.assertTrue(manual["accepted"], manual["error"])
        synced = assistant.get_snapshot()
        self.assertEqual(synced["football"]["ball_on"], {"team": "away", "yard_line": 35})

    def test_assistant_block_reports_display_facts_derived_in_python(self) -> None:
        assistant = FieldAssistantBridge(self.bridge)

        # A fresh game has no assistant state at all: the default BallSpot is
        # HOME's own 50, which absolute_from_ball_spot maps to 50.
        fresh = assistant.get_snapshot()["assistant"]
        self.assertEqual(
            fresh,
            {
                "first_quarter_home_direction": None,
                "line_to_gain": None,
                "ball_absolute": 50,
                "home_goal_side": None,
                "offense_direction": None,
            },
        )

        self.set_live_quarter()
        revision = self.service.revision
        committed = assistant.finalize_field_action(self.start_action(), revision)
        self.assertTrue(committed["accepted"], committed["error"])

        live = assistant.get_snapshot()["assistant"]
        self.assertEqual(
            live,
            {
                "first_quarter_home_direction": 1,
                "line_to_gain": 35,
                "ball_absolute": 25,
                "home_goal_side": "left",
                "offense_direction": 1,
            },
        )


class CommandTranslationTests(unittest.TestCase):
    """The airlock: JavaScript cannot invent a mutation."""

    def test_an_unknown_name_never_becomes_a_command(self) -> None:
        error = build_command("drop_tables", {})

        self.assertEqual(error.code, "UNKNOWN_COMMAND")

    def test_an_argument_a_command_does_not_take_is_refused(self) -> None:
        error = build_command("game_clock_start", {"team": "home"})

        self.assertEqual(error.code, "INVALID_ARGUMENTS")
        self.assertIn("team", error.message)

    def test_arguments_of_the_wrong_type_are_refused(self) -> None:
        for name, args in (
            ("add_score", {"team": "home", "points": "six"}),
            ("add_score", {"team": 6, "points": 6}),
            ("set_quarter", {"label": 2}),
            ("game_clock_correct", {"seconds": None}),
        ):
            with self.subTest(args=args):
                self.assertEqual(build_command(name, args).code, "INVALID_ARGUMENTS")

    def test_an_empty_number_field_is_refused_rather_than_becoming_nan(self) -> None:
        error = build_command("set_score", {"team": "home", "value": float("nan")})

        self.assertEqual(error.code, "INVALID_ARGUMENTS")

    def test_a_bad_expected_revision_is_refused(self) -> None:
        error = build_command("undo", {}, "seventeen")

        self.assertEqual(error.code, "INVALID_ARGUMENTS")

    def test_a_well_formed_request_carries_the_mouse_source(self) -> None:
        command = build_command("add_score", {"team": "away", "points": 3}, 4)

        self.assertEqual(command.type, CommandType.ADD_SCORE)
        self.assertEqual(command.source, OPERATOR_MOUSE_SOURCE)
        self.assertEqual(command.expected_revision, 4)
        self.assertFalse(command.confirmed)


class TypingChangesNothingTests(BridgeTestCase):
    """F-016: authoritative state changes only on Apply."""

    def test_the_text_fields_are_drafts_with_no_command_of_their_own(self) -> None:
        inputs = re.findall(r"<input[^>]*>", OPERATOR_HTML)
        self.assertTrue(inputs)

        for element in inputs:
            with self.subTest(element=element[:60]):
                # A field carries no command, so no keystroke has a path to the
                # bridge; the Apply button reads it at click time instead.
                self.assertNotIn("data-command", element)
                self.assertIn('data-draft="true"', element)

    def test_no_input_or_change_listener_exists_in_the_operator_script(self) -> None:
        self.assertNotIn("addEventListener('input'", OPERATOR_JS)
        self.assertNotIn("addEventListener('change'", OPERATOR_JS)
        self.assertNotIn('addEventListener("input"', OPERATOR_JS)
        self.assertNotIn('addEventListener("change"', OPERATOR_JS)

    def test_reading_the_view_repeatedly_changes_no_state(self) -> None:
        before = self.service.revision

        for _ in range(5):
            self.bridge.get_snapshot()

        self.assertEqual(self.service.revision, before)
        self.assertEqual(self.service.state.home_score, 0)

    def test_a_direct_set_only_applies_when_it_is_actually_submitted(self) -> None:
        # A typed value that is never submitted leaves the board untouched.
        self.assertEqual(self.bridge.get_snapshot()["teams"]["home"]["score"], 0)

        result = self.send("set_score", {"team": "home", "value": 21})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["teams"]["home"]["score"], 21)


class ConfirmationTests(BridgeTestCase):
    """F-022, F-023, U-004: confirmation travels on the command."""

    def test_new_game_asks_first_and_changes_nothing(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})
        before = self.service.revision

        result = self.send("new_game", {})

        self.assertFalse(result["accepted"])
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(result["error"]["code"], "CONFIRMATION_REQUIRED")
        self.assertEqual(self.service.revision, before)
        self.assertEqual(result["view"]["teams"]["home"]["score"], 6)

    def test_cancelling_new_game_does_nothing_at_all(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})
        self.send("new_game", {})
        before = self.service.revision

        # Cancel sends no second command; the next read must be unchanged.
        view = self.bridge.get_snapshot()

        self.assertEqual(view["teams"]["home"]["score"], 6)
        self.assertEqual(self.service.revision, before)

    def test_confirming_new_game_resubmits_the_same_command(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})

        result = self.send("new_game", {"confirmed": True})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["teams"]["home"]["score"], 0)
        self.assertEqual(result["view"]["quarter"], "PRE")

    def test_a_quarter_change_while_a_clock_runs_asks_first(self) -> None:
        self.send("game_clock_start")
        before = self.service.revision

        result = self.send("quarter_forward", {})

        self.assertTrue(result["confirmation_required"])
        self.assertIn("will stop", result["error"]["message"])
        self.assertEqual(self.service.revision, before)
        self.assertTrue(result["view"]["clocks"]["game"]["running"])
        self.assertEqual(result["view"]["quarter"], "PRE")

    def test_confirming_the_quarter_change_stops_both_clocks_in_one_step(self) -> None:
        self.send("game_clock_start")
        self.send("quarter_forward", {})

        result = self.send("quarter_forward", {"confirmed": True})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["quarter"], "1st")
        self.assertFalse(result["view"]["clocks"]["game"]["running"])
        self.assertFalse(result["view"]["clocks"]["play"]["running"])

    def test_a_quarter_change_while_stopped_still_needs_confirmation(self) -> None:
        result = self.send("quarter_forward", {})

        self.assertFalse(result["accepted"])
        self.assertTrue(result["confirmation_required"])
        self.assertEqual(result["confirmation"]["accept_label"],
                         "Start 1st quarter — discard remaining pregame time")

    def test_the_page_offers_a_cancel_and_a_confirm(self) -> None:
        self.assertIn('id="confirm-cancel"', OPERATOR_HTML)
        self.assertIn('id="confirm-accept"', OPERATOR_HTML)
        # Cancel is focused first, so a stray Enter is safe (U-004).
        self.assertIn("confirm-cancel').focus()", OPERATOR_JS)

    def test_dangerous_corrections_confirm_locally_before_anything_is_sent(self) -> None:
        confirming = re.findall(
            r'data-command="([a-z_]+)"[^>]*data-confirm="local"', OPERATOR_HTML
        )

        for command in ("set_score", "game_clock_correct", "play_clock_correct",
                        "game_clock_reset", "end_game", "event_countdown_correct"):
            with self.subTest(command=command):
                self.assertIn(command, confirming)


class RejectionTests(BridgeTestCase):
    """U-007: a rejection is visible and leaves the board unchanged."""

    def test_a_rejected_command_returns_a_plain_language_message(self) -> None:
        result = self.send("correct_score", {"team": "home", "points": 6})

        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "SCORE_BELOW_ZERO")
        self.assertIn("cannot be corrected below 0", result["error"]["message"])
        self.assertEqual(result["view"]["teams"]["home"]["score"], 0)

    def test_a_rejection_still_returns_the_authoritative_view(self) -> None:
        self.send("add_score", {"team": "away", "points": 3})

        result = self.send("set_score", {"team": "home", "value": 500})

        self.assertFalse(result["accepted"])
        self.assertEqual(result["view"]["teams"]["away"]["score"], 3)
        self.assertEqual(result["view"]["revision"], self.service.revision)

    def test_the_page_has_somewhere_to_show_a_rejection(self) -> None:
        self.assertIn('id="alert"', OPERATOR_HTML)
        self.assertIn('role="alert"', OPERATOR_HTML)
        self.assertIn("showAlert(result.error.message)", OPERATOR_JS)


class StaleRevisionTests(BridgeTestCase):
    """A control showing an old revision is refused, never applied."""

    def test_a_stale_control_is_rejected(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})
        stale_revision = self.service.revision - 1

        result = self.bridge.command(
            "add_score", {"team": "home", "points": 6}, stale_revision
        )

        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "STALE_REVISION")
        self.assertEqual(result["view"]["teams"]["home"]["score"], 6)

    def test_the_rendered_revision_is_what_the_next_command_sends(self) -> None:
        view = self.bridge.get_snapshot()

        result = self.bridge.command(
            "add_score", {"team": "home", "points": 6}, view["revision"]
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["revision"], view["revision"] + 1)

    def test_the_script_sends_the_rendered_revision(self) -> None:
        self.assertIn("var expected = model ? model.revision : null;", OPERATOR_JS)


class HealthStripTests(BridgeTestCase):
    """U-005: spectator connection, persistence status, and the revision."""

    def test_the_health_strip_reports_all_three(self) -> None:
        health = self.bridge.get_snapshot()["health"]

        self.assertEqual(health["revision"], self.service.revision)
        self.assertIn("open", health["display"])
        self.assertIn("saved", health["persistence"])

    def test_a_write_failure_shows_not_saved_without_stopping_the_game(self) -> None:
        failing = FailingConnection(self.store._connection, fail_execute=True)
        self.store._connection = failing

        result = self.send("add_score", {"team": "home", "points": 6})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["teams"]["home"]["score"], 6)
        persistence = result["view"]["health"]["persistence"]
        self.assertFalse(persistence["saved"])
        self.assertEqual(persistence["label"], "NOT SAVED")
        self.assertIn("memory only", persistence["message"])

    def test_saving_recovers_and_the_strip_says_saved_again(self) -> None:
        failing = FailingConnection(self.store._connection, fail_execute=True)
        self.store._connection = failing
        self.send("add_score", {"team": "home", "points": 6})

        failing.fail_execute = False
        result = self.send("add_score", {"team": "away", "points": 3})

        self.assertTrue(result["view"]["health"]["persistence"]["saved"])
        self.assertEqual(result["view"]["health"]["persistence"]["label"], "SAVED")

    def test_a_closed_display_says_so_and_offers_one_click_reopen(self) -> None:
        view = self.bridge.display_closed()

        display = view["health"]["display"]
        self.assertFalse(display["open"])
        self.assertEqual(display["label"], "DISPLAY CLOSED")
        self.assertTrue(display["can_reopen"])
        self.assertIn('id="reopen-display"', OPERATOR_HTML)

    def test_closing_the_display_stops_no_clock(self) -> None:
        self.send("game_clock_start")

        self.bridge.display_closed()
        self.monotonic.advance(5.0)
        view = self.bridge.get_snapshot()

        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["display"], "29:55")

    def test_reopening_marks_the_display_open_again(self) -> None:
        self.bridge.display_closed()

        self.bridge.display_opened("Display 2")
        view = self.bridge.get_snapshot()

        self.assertTrue(view["health"]["display"]["open"])
        self.assertEqual(view["health"]["display"]["label"], "DISPLAY OPEN")
        self.assertEqual(view["health"]["display"]["target"], "Display 2")

    def test_a_failing_reopen_is_reported_and_the_game_survives(self) -> None:
        def explode():
            raise RuntimeError("no display attached")

        self.display.reopen = explode  # type: ignore[method-assign]
        self.send("game_clock_start")

        view = self.bridge.reopen_display()

        self.assertFalse(view["health"]["display"]["open"])
        self.assertIn("could not be reopened", view["health"]["display"]["detail"])
        self.assertTrue(view["clocks"]["game"]["running"])


class UndoVisibilityTests(BridgeTestCase):
    """U-008: the previous reversible command and Undo are always visible."""

    def test_the_last_action_is_reported_in_plain_language(self) -> None:
        result = self.send("add_score", {"team": "home", "points": 6})

        last = result["view"]["last_action"]
        self.assertEqual(last["label"], "HOME score 0 → 6")
        self.assertTrue(result["view"]["can_undo"])

    def test_nothing_to_undo_is_reported_rather_than_hidden(self) -> None:
        view = self.bridge.get_snapshot()

        self.assertIsNone(view["last_action"])
        self.assertFalse(view["can_undo"])

    def test_undo_reverses_the_previous_command(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})

        result = self.send("undo", {})

        self.assertTrue(result["accepted"])
        self.assertEqual(result["view"]["teams"]["home"]["score"], 0)
        self.assertFalse(result["view"]["can_undo"])

    def test_the_page_shows_both(self) -> None:
        self.assertIn('id="last-action"', OPERATOR_HTML)
        self.assertIn('id="undo"', OPERATOR_HTML)


class RunningStateTests(BridgeTestCase):
    """U-002, U-003: separate Start/Stop with visible state; presets on top."""

    def test_running_and_stopped_are_reported_as_text(self) -> None:
        stopped = self.bridge.get_snapshot()
        self.assertEqual(stopped["clocks"]["game"]["status"], "STOPPED")

        running = self.send("game_clock_start")["view"]
        self.assertEqual(running["clocks"]["game"]["status"], "RUNNING")

    def test_start_and_stop_are_separate_controls(self) -> None:
        self.assertIn('id="game-start" data-command="game_clock_start"', OPERATOR_HTML)
        self.assertIn('id="game-stop" data-command="game_clock_stop"', OPERATOR_HTML)

    def test_the_presets_and_both_score_columns_need_no_menu(self) -> None:
        # Everything below is in the always-visible board, not in a drawer.
        board = OPERATOR_HTML.split('<main class="board"')[1].split("</main>")[0]

        self.assertIn('data-command="play_clock_preset" data-seconds="25"', board)
        self.assertIn('data-command="play_clock_preset" data-seconds="40"', board)
        for team in ("home", "away"):
            for points in (1, 2, 3, 6):
                with self.subTest(team=team, points=points):
                    self.assertIn(
                        f'data-command="add_score" data-team="{team}" data-points="{points}"',
                        board,
                    )

    def test_corrections_are_separated_from_normal_scoring(self) -> None:
        board = OPERATOR_HTML.split('<main class="board"')[1].split("</main>")[0]
        drawer = OPERATOR_HTML.split('id="corrections"')[1]

        self.assertNotIn("correct_score", board)
        self.assertNotIn("set_score", board)
        self.assertIn("correct_score", drawer)
        self.assertIn("set_score", drawer)


class JsonBoundaryTests(BridgeTestCase):
    """No domain object leaks into JavaScript."""

    def assert_json_only(self, payload) -> None:
        encoded = json.dumps(payload, allow_nan=False)
        self.assertEqual(json.loads(encoded), payload)

    def test_the_snapshot_is_json_compatible(self) -> None:
        self.assert_json_only(self.bridge.get_snapshot())

    def test_every_command_result_is_json_compatible(self) -> None:
        for command in CommandType:
            if command is CommandType.FINALIZE_FIELD_ACTION:
                continue
            with self.subTest(command=command.value):
                service, store = self.started_session()
                bridge = ScoreboardBridge(service, store)
                for name, args in COMMAND_PRELUDES.get(command.value, []):
                    bridge.command(name, args, service.revision)
                result = bridge.command(
                    command.value, COMMAND_PAYLOADS[command.value], service.revision
                )
                self.assert_json_only(result)

    def test_a_rejection_payload_is_json_compatible(self) -> None:
        self.assert_json_only(self.send("correct_score", {"team": "home", "points": 6}))
        self.assert_json_only(self.bridge.command("nonsense", {}, None))

    def test_the_payload_contains_no_domain_object(self) -> None:
        def walk(value):
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            else:
                self.assertIsInstance(value, (str, int, float, bool, type(None)))

        walk(self.send("game_clock_start"))
        walk(self.bridge.get_snapshot())

    def test_clock_values_are_formatted_by_python_not_javascript(self) -> None:
        view = self.bridge.get_snapshot()

        self.assertEqual(view["clocks"]["game"]["display"], "30:00")
        self.assertEqual(view["clocks"]["event"]["display"], "30:00")
        self.assertEqual(view["clocks"]["event"]["title"], "KICKOFF IN")
        # The page renders these strings; it does not build them.
        self.assertNotIn("Math.floor", OPERATOR_JS)
        self.assertNotIn("toFixed", OPERATOR_JS)


class FootballStateViewTests(BridgeTestCase):
    """Deferred scoreboard fields: rendered text, JSON safety, and Undo."""

    def test_the_view_model_carries_rendered_football_text(self) -> None:
        self.send("set_team_name", {"team": "away", "name": "Eagles"})
        self.send("set_down", {"value": 3})
        self.send("set_distance", {"value": 7})
        self.send("set_possession", {"team": "away"})
        result = self.send("set_ball_on", {"team": "away", "value": 35})

        view = result["view"]
        self.assertEqual(view["football"]["down_distance_display"], "3rd & 7")
        self.assertEqual(view["football"]["ball_on_display"], "Eagles 35")
        self.assertEqual(view["football"]["possession"], "away")
        self.assertEqual(view["football"]["timeouts"], {"home": 3, "away": 3})

    def test_clearing_down_or_distance_blanks_the_rendered_text(self) -> None:
        self.send("set_down", {"value": 2})
        self.send("set_distance", {"value": 10})

        result = self.send("set_distance", {"value": None})

        self.assertEqual(result["view"]["football"]["down_distance_display"], "")

    def test_set_ball_on_followed_by_undo_stays_json_compatible(self) -> None:
        """Regression: BallSpot must never reach the last-action payload raw.

        set_ball_on is undoable, so immediately after it is accepted the undo
        entry (and therefore ``last_action``) holds the same BallSpot value
        that used to leak past the JSON boundary before the bridge converted
        it to plain text.
        """

        self.send("set_ball_on", {"team": "home", "value": 40})
        result = self.send("set_ball_on", {"team": "away", "value": 22})

        json.dumps(result, allow_nan=False)
        self.assertEqual(result["view"]["last_action"]["field"], "ball_on")
        self.assertIsInstance(result["view"]["last_action"]["old_value"], str)
        self.assertIsInstance(result["view"]["last_action"]["new_value"], str)

        undone = self.send("undo")
        json.dumps(undone, allow_nan=False)
        self.assertEqual(undone["view"]["football"]["ball_on"], {"team": "home", "yard_line": 40})

    def test_timeout_used_is_reachable_and_reported_in_last_action(self) -> None:
        result = self.send("timeout_used", {"team": "home"})

        self.assertTrue(result["accepted"], result["error"])
        self.assertEqual(result["view"]["football"]["timeouts"]["home"], 2)
        self.assertIn("HOME timeouts", result["view"]["last_action"]["label"])

    def test_a_null_value_is_refused_for_any_other_command(self) -> None:
        result = self.send("set_score", {"team": "home", "value": None})

        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENTS")

    def test_possession_cannot_be_cleared_through_an_unrelated_command(self) -> None:
        result = self.send("timeout_used", {"team": None})

        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENTS")


class SpectatorBridgeTests(BridgeTestCase):
    """The spectator surface can read and can do nothing else."""

    def test_it_exposes_no_mutating_method(self) -> None:
        spectator = SpectatorBridge(self.bridge.spectator_snapshot)

        public = {name for name in dir(spectator) if not name.startswith("_")}

        # get_layout was added alongside the presentation layout editor
        # (spec section 6.1); it is read-only in exactly the same way.
        self.assertEqual(public, {"get_snapshot", "get_layout"})

    def test_it_returns_a_complete_json_snapshot(self) -> None:
        self.send("add_score", {"team": "home", "points": 6})
        spectator = SpectatorBridge(self.bridge.spectator_snapshot)

        snapshot = spectator.get_snapshot()

        json.dumps(snapshot, allow_nan=False)
        self.assertEqual(snapshot["teams"]["home"]["score"], 6)
        self.assertEqual(snapshot["clocks"]["game"]["display"], "30:00")

    def test_the_spectator_page_carries_no_control(self) -> None:
        self.assertNotIn("data-command", SPECTATOR_HTML)
        self.assertNotIn("<button", SPECTATOR_HTML)

    def test_a_spectator_rendering_error_is_caught_in_the_page(self) -> None:
        # R-002: the page reports its own failure rather than throwing into
        # the host, which is what would put the state engine at risk.
        script = (VIEWS / "spectator" / "spectator.js").read_text()
        self.assertIn("catch (error)", script)
        self.assertIn("Spectator rendering failed", script)

    def test_warmup_display_is_none_during_pre_game(self) -> None:
        # A fresh game starts in PRE_GAME (presentation-screens spec section
        # 4): the warmup line has nothing to say before halftime exists.
        snapshot = self.bridge.spectator_snapshot()

        self.assertEqual(snapshot["lifecycle"], "PRE_GAME")
        self.assertEqual(snapshot["clocks"]["event"]["phase"], "PREGAME")
        self.assertIsNone(snapshot["clocks"]["event"]["warmup_display"])

    def test_warmup_display_matches_warmup_follows_above_the_threshold(self) -> None:
        # A quarter move now requires confirmation (follow-up 02, PROJECT_
        # ROADMAP.md's failure inventory); confirm it explicitly rather than
        # relying on the bare command the way the pre-existing (currently
        # failing) test_spectator.py lifecycle test does.
        self.send("set_quarter", {"label": "HALF", "confirmed": True})

        snapshot = self.bridge.spectator_snapshot()
        event = snapshot["clocks"]["event"]

        self.assertEqual(snapshot["lifecycle"], "HALFTIME")
        self.assertEqual(event["phase"], "HALFTIME")
        self.assertEqual(event["warmup_follows"], "3:00")
        self.assertEqual(event["warmup_display"], "Warmup follows: 3:00")

        # Once the countdown drops to the warmup threshold, the phase flips
        # to WARMUP and both fields go quiet together.
        self.send("event_countdown_correct", {"seconds": 180})
        event = self.bridge.spectator_snapshot()["clocks"]["event"]
        self.assertEqual(event["phase"], "WARMUP")
        self.assertIsNone(event["warmup_follows"])
        self.assertIsNone(event["warmup_display"])


class TickTests(BridgeTestCase):
    """The refresh loop displays and checkpoints; it never commands."""

    def test_a_tick_checkpoints_without_advancing_the_revision(self) -> None:
        self.send("game_clock_start")
        revision = self.service.revision
        history = len(read_action_history(self.paths.database))

        for _ in range(12):
            self.monotonic.advance(0.25)
            self.bridge.tick()

        self.assertEqual(self.service.revision, revision)
        self.assertEqual(len(read_action_history(self.paths.database)), history)

    def test_a_tick_returns_the_current_formatted_view(self) -> None:
        self.send("game_clock_start")

        self.monotonic.advance(1.5)
        view = self.bridge.tick()

        self.assertEqual(view["clocks"]["game"]["display"], "29:59")
        self.assertTrue(view["clocks"]["game"]["running"])

    def test_a_failing_checkpoint_does_not_stop_the_clock(self) -> None:
        self.send("game_clock_start")
        self.store._connection = FailingConnection(
            self.store._connection, fail_execute=True
        )

        self.monotonic.advance(2.0)
        view = self.bridge.tick()

        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertFalse(view["health"]["persistence"]["saved"])


class ExpirationHistoryTests(BridgeTestCase):
    """F-037, F-046: a clock that runs itself to zero is recorded.

    Expiration is the one clock event with no operator command behind it, so
    without this the history would show a start and then silence.
    """

    def run_to(self, seconds: float, step: float = 0.25) -> None:
        elapsed = 0.0
        while elapsed < seconds:
            self.monotonic.advance(step)
            elapsed += step
            self.bridge.tick()

    def expirations(self) -> list[dict]:
        return [
            row
            for row in read_action_history(self.paths.database)
            if str(row["command"]).endswith("_expired")
        ]

    def test_a_play_clock_that_reaches_zero_is_recorded_once(self) -> None:
        self.send("play_clock_preset", {"seconds": 25})
        self.send("play_clock_start")

        self.run_to(27.0)

        rows = self.expirations()
        self.assertEqual([row["command"] for row in rows], ["play_clock_expired"])
        self.assertEqual(rows[0]["source"], "system")
        self.assertEqual(rows[0]["result"], "ACCEPTED")
        self.assertEqual(decode(rows[0]["new_value"]), {"seconds": 0.0, "running": False})
        self.assertTrue(decode(rows[0]["old_value"])["running"])

    def test_a_game_clock_that_reaches_zero_is_recorded(self) -> None:
        self.send("game_clock_correct", {"seconds": 3.0})
        self.send("game_clock_start")

        self.run_to(5.0)

        self.assertEqual(
            [row["command"] for row in self.expirations()], ["game_clock_expired"]
        )

    def test_game_clock_expiry_clears_a_running_play_clock_durably(self) -> None:
        self.send("game_clock_correct", {"seconds": 2.0})
        self.send("game_clock_start")
        self.send("play_clock_preset", {"seconds": 40})
        self.send("play_clock_start")
        self.bridge.tick()  # Establish the pre-expiry observation.
        revision = self.service.revision

        self.monotonic.advance(1.0)
        self.bridge.tick()
        self.monotonic.advance(1.0)
        view = self.bridge.tick()

        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertFalse(view["clocks"]["play"]["running"])
        self.assertEqual(view["clocks"]["play"]["display"], "—")
        self.assertEqual(self.service.revision, revision)
        commands = [row["command"] for row in read_action_history(self.paths.database)]
        self.assertIn("game_clock_expired", commands)
        self.assertIn("play_clock_cleared_on_game_clock_stop", commands)
        self.assertNotIn("play_clock_expired", commands)
        game_expiry = next(
            row for row in read_action_history(self.paths.database)
            if row["command"] == "game_clock_expired"
        )
        self.assertEqual(decode(game_expiry["old_value"]), {"seconds": 1.0, "running": True})
        auto_clear = next(
            row for row in read_action_history(self.paths.database)
            if row["command"] == "play_clock_cleared_on_game_clock_stop"
        )
        self.assertEqual(auto_clear["source"], "system")
        self.assertEqual(decode(auto_clear["old_value"]), {"seconds": 39.0, "running": True})
        self.assertEqual(decode(auto_clear["new_value"]), {"seconds": 0.0, "running": False})

        self.monotonic.advance(3.0)
        later = self.bridge.tick()
        self.assertFalse(later["clocks"]["play"]["running"])
        self.assertEqual(later["clocks"]["play"]["display"], "—")

    def test_the_revision_is_not_advanced_by_an_expiration(self) -> None:
        self.send("game_clock_correct", {"seconds": 2.0})
        self.send("game_clock_start")
        revision = self.service.revision

        self.run_to(4.0)

        self.assertEqual(self.service.revision, revision)
        self.assertEqual(len(self.expirations()), 1)

    def test_a_running_clock_that_is_stopped_short_of_zero_is_not_an_expiry(self) -> None:
        self.send("game_clock_correct", {"seconds": 5.0})
        self.send("game_clock_start")

        self.run_to(2.0)
        self.send("game_clock_stop")
        self.run_to(4.0)

        self.assertEqual(self.expirations(), [])

    def test_clearing_the_play_clock_at_a_start_is_not_an_expiry(self) -> None:
        """A game-clock Start blanks a running play clock (F-048).

        The play clock reaches zero, but a command put it there and that
        command has its own history row; inventing an expiration as well would
        misreport what happened on the field.
        """

        self.send("play_clock_preset", {"seconds": 25})
        self.send("play_clock_start")
        self.run_to(2.0)

        self.send("game_clock_start")
        self.run_to(2.0)

        self.assertEqual(self.expirations(), [])

    def test_correcting_a_running_clock_to_zero_is_not_double_recorded(self) -> None:
        self.send("game_clock_correct", {"seconds": 30.0})
        self.send("game_clock_start")
        self.run_to(2.0)

        self.send("game_clock_correct", {"seconds": 0.0})
        self.run_to(2.0)

        self.assertEqual(self.expirations(), [])

    def test_an_expired_zero_survives_in_the_stored_state(self) -> None:
        self.send("game_clock_correct", {"seconds": 2.0})
        self.send("game_clock_start")

        self.run_to(4.0)

        view = self.bridge.get_snapshot()
        self.assertEqual(view["clocks"]["game"]["display"], "0.0")
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertTrue(view["health"]["persistence"]["saved"])


if __name__ == "__main__":
    unittest.main()
