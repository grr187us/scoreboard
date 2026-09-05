"""Task 10: choosing a display, remembering it, and surviving losing it.

Everything here runs on a host with one physical display. The screen list and
the Windows device names are injected, and ``webview.create_window`` is
replaced, so a second monitor is plugged in by appending to a list and unplugged
by removing from it. That is what makes disconnect and reconnect testable at
all on this machine.

What these tests establish is that the *policy* is right: which display is
chosen, what is remembered, what the operator is told, and -- the part that
matters most on a Friday night -- that none of it can touch the game. What they
cannot establish is that Windows and WebView2 behave as assumed on real
hardware. That is `docs/DISPLAY_CHECKLIST.md`, and it is not claimed here.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from scoreboard.host.app import ScoreboardApplication, WindowHost
from scoreboard.host.displays import (
    MATCH_EXACT,
    MATCH_GEOMETRY,
    MATCH_INDEX,
    MATCH_NAME,
    MATCH_NONE,
    enumerate_displays,
)
from scoreboard.infrastructure import config
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.persistence import read_action_history, read_stored_game

from tests.integration.support import TemporaryDataDirectoryTest


class FakeScreen:
    def __init__(self, x: int, y: int, width: int, height: int, scale: float = 1.0) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.scale = scale


LAPTOP = FakeScreen(0, 0, 1366, 768)
WALL = FakeScreen(1366, 0, 1920, 1080)
LAPTOP_NAME = r"\\.\DISPLAY1"
WALL_NAME = r"\\.\DISPLAY2"


class FakeEvent:
    """Stands in for a pywebview event slot, which is used with ``+=``."""

    def __init__(self, ready: bool = True) -> None:
        self.handlers: list[Any] = []
        self._ready = ready

    def __iadd__(self, handler: Any) -> "FakeEvent":
        self.handlers.append(handler)
        return self

    def is_set(self) -> bool:
        return self._ready


class FakeWindowEvents:
    def __init__(self) -> None:
        self.closed = FakeEvent()
        self.loaded = FakeEvent()


class FakeWindow:
    """A spectator window that records what happened to it."""

    def __init__(self, **kwargs: Any) -> None:
        self.screen = kwargs.get("screen")
        self.kwargs = kwargs
        self.events = FakeWindowEvents()
        self.destroyed = False
        self.pushes: list[str] = []

    def destroy(self) -> None:
        self.destroyed = True

    def evaluate_js(self, script: str) -> None:
        self.pushes.append(script)


class DisplayHostTestCase(TemporaryDataDirectoryTest):
    """A real application and host, with the screens and the windows faked."""

    def setUp(self) -> None:
        super().setUp()
        self.screens: list[FakeScreen] = [LAPTOP, WALL]
        self.names: list[str | None] = [LAPTOP_NAME, WALL_NAME]
        self.now = 500.0
        self.created: list[FakeWindow] = []

        patcher = mock.patch(
            "scoreboard.host.app.webview.create_window", side_effect=self._create_window
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create_window(self, *args: Any, **kwargs: Any) -> FakeWindow:
        window = FakeWindow(**kwargs)
        self.created.append(window)
        return window

    def make_host(self, **kwargs: Any) -> WindowHost:
        application = ScoreboardApplication(
            self.paths,
            diagnostics=NullDiagnostics(),
            monotonic_clock=self.monotonic,
            acquire_lock=False,
        )
        self.addCleanup(application.shutdown)
        kwargs.setdefault("read_screens", lambda: list(self.screens))
        kwargs.setdefault("read_device_names", lambda: list(self.names))
        kwargs.setdefault("monotonic", lambda: self.now)
        host = WindowHost(application, **kwargs)
        self.bridge = application.start_new()
        self.application = application
        return host

    # --- Small helpers -----------------------------------------------------

    def wall_target(self):
        return enumerate_displays(self.screens, self.names)[1]

    def save_wall(self, host: WindowHost) -> None:
        host.remember_display(self.wall_target())

    def unplug_wall(self) -> None:
        self.screens = [LAPTOP]
        self.names = [LAPTOP_NAME]

    def display_health(self) -> dict[str, Any]:
        return self.bridge.get_snapshot()["health"]["display"]


class SavedDisplayTests(DisplayHostTestCase):
    """'A saved display is selected predictably when present.'"""

    def test_the_saved_display_is_opened_and_the_primary_is_not(self) -> None:
        host = self.make_host()
        self.save_wall(host)

        host.reopen_spectator()

        self.assertEqual(len(self.created), 1)
        self.assertIs(self.created[0].screen, WALL)
        self.assertTrue(self.display_health()["open"])
        self.assertIn("1920x1080", host.status)

    def test_a_resolution_change_still_finds_the_same_display(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        # The processor renegotiated HDMI and came back smaller.
        smaller = FakeScreen(1366, 0, 1280, 720)
        self.screens = [LAPTOP, smaller]

        match = host.resolve_target()

        self.assertEqual(match.how, MATCH_NAME)
        host.reopen_spectator()
        self.assertIs(self.created[0].screen, smaller)

    def test_a_renumbered_device_in_the_same_place_is_still_found(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        self.names = [LAPTOP_NAME, r"\\.\DISPLAY5"]

        match = host.resolve_target()

        self.assertEqual(match.how, MATCH_GEOMETRY)
        self.assertIsNotNone(match.target)

    def test_recognising_the_saved_display_refreshes_what_is_stored(self) -> None:
        """Same display, current geometry -- never a different display."""

        host = self.make_host()
        self.save_wall(host)
        self.screens = [LAPTOP, FakeScreen(1366, 0, 1280, 720)]

        host.reopen_spectator()

        saved = host.saved_display()
        self.assertEqual(saved.name, WALL_NAME)  # type: ignore[union-attr]
        self.assertEqual(saved.width, 1280)  # type: ignore[union-attr]

    def test_an_explicit_index_opens_that_display_but_never_re_points_the_save(self) -> None:
        host = self.make_host(initial_display_index=0)
        self.save_wall(host)

        host.reopen_spectator()

        self.assertIs(self.created[0].screen, LAPTOP)
        # The operator asked for this once from a terminal. The remembered
        # display is still the wall.
        self.assertEqual(host.saved_display().name, WALL_NAME)  # type: ignore[union-attr]
        self.assertEqual(host.resolve_target(index=0).how, MATCH_INDEX)

    def test_with_nothing_saved_the_first_non_primary_display_is_used(self) -> None:
        host = self.make_host()

        match = host.resolve_target()

        self.assertEqual(match.how, "default")
        self.assertEqual(match.target.key, self.wall_target().key)  # type: ignore[union-attr]

    def test_a_default_open_does_not_silently_become_the_saved_display(self) -> None:
        host = self.make_host()

        host.reopen_spectator()

        self.assertIs(self.created[0].screen, WALL)
        # Nothing was chosen by a person, so nothing was remembered.
        self.assertIsNone(host.saved_display())


class MissingDisplayTests(DisplayHostTestCase):
    """'A missing display never hides or blocks the operator.'"""

    def test_an_unplugged_saved_display_opens_no_window_at_all(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        self.unplug_wall()

        host.reopen_spectator()

        self.assertEqual(self.created, [])
        health = self.display_health()
        self.assertFalse(health["open"])
        self.assertEqual(health["label"], "DISPLAY NOT FOUND")
        self.assertTrue(health["needs_selection"])
        self.assertIn("DISPLAY NOT FOUND", health["detail"])

    def test_the_operator_keeps_a_complete_usable_view(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        self.unplug_wall()
        self.bridge.command("add_score", {"team": "home", "points": 6}, 0)

        host.reopen_spectator()
        view = self.bridge.get_snapshot()

        self.assertEqual(view["teams"]["home"]["score"], 6)
        self.assertTrue(view["health"]["persistence"]["saved"])
        self.assertEqual(view["health"]["revision"], 1)
        json.dumps(view, allow_nan=False)

    def test_a_missing_display_stops_no_clock(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        self.bridge.command("game_clock_start", {}, 0)
        revision = self.bridge.get_snapshot()["revision"]
        self.unplug_wall()

        host.reopen_spectator()
        self.monotonic.advance(5.0)
        view = self.bridge.get_snapshot()

        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["display"], "11:55")
        self.assertEqual(view["revision"], revision)

    def test_one_display_and_nothing_saved_never_covers_the_operator(self) -> None:
        host = self.make_host()
        self.unplug_wall()

        host.reopen_spectator()

        self.assertEqual(self.created, [])
        self.assertIn("No second display", self.display_health()["detail"])

    def test_the_operator_can_still_deliberately_choose_the_only_screen(self) -> None:
        host = self.make_host()
        self.unplug_wall()
        key = enumerate_displays(self.screens, self.names)[0].key

        host.select_display(key)

        self.assertEqual(len(self.created), 1)
        self.assertIs(self.created[0].screen, LAPTOP)
        self.assertTrue(self.display_health()["open"])
        self.assertEqual(host.saved_display().name, LAPTOP_NAME)  # type: ignore[union-attr]

    def test_choosing_a_display_that_vanished_in_between_is_refused(self) -> None:
        host = self.make_host()
        key = self.wall_target().key
        self.unplug_wall()

        host.select_display(key)

        self.assertEqual(self.created, [])
        self.assertTrue(self.display_health()["needs_selection"])
        self.assertIn("no longer connected", self.display_health()["detail"])

    def test_a_stale_saved_display_never_stops_the_scoreboard_starting(self) -> None:
        """The same trade the data-folder pointer makes: fall back, keep going."""

        damaged = [
            "not json at all",
            json.dumps({"schema_version": 1, "display": {"x": "left"}}),
            json.dumps({"schema_version": 1, "display": None}),
            json.dumps({"schema_version": 99, "display": {"x": 0}}),
            json.dumps(["display"]),
            "",
        ]
        host = self.make_host()
        for payload in damaged:
            with self.subTest(payload[:24]):
                self.paths.config.write_text(payload, encoding="utf-8")

                self.assertIsNone(host.saved_display())
                # And the scoreboard still resolves a display and runs.
                self.assertTrue(host.resolve_target().found)
                self.assertEqual(self.bridge.get_snapshot()["revision"], 0)

    def test_a_config_written_by_a_newer_build_is_read_by_none_and_kept(self) -> None:
        host = self.make_host()
        future = json.dumps({"schema_version": 99, "display": {"x": 1366}})
        self.paths.config.write_text(future, encoding="utf-8")

        self.assertIsNone(host.saved_display())
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), future)


class DisconnectTests(DisplayHostTestCase):
    """'Display close or disconnect does not stop clocks or corrupt state.'"""

    def running_game(self, host: WindowHost) -> None:
        self.save_wall(host)
        host.reopen_spectator()
        self.bridge.command("add_score", {"team": "away", "points": 3}, 0)
        self.bridge.command("game_clock_start", {}, 1)

    def test_the_watch_notices_the_wall_going_away_and_says_so(self) -> None:
        host = self.make_host()
        self.running_game(host)
        self.application.tick()  # the watch's first look: the baseline

        self.unplug_wall()
        self.now += 5.0
        self.application.tick()

        health = self.display_health()
        self.assertFalse(health["open"])
        self.assertTrue(health["needs_selection"])
        self.assertIn("no longer connected", health["detail"])
        self.assertTrue(self.created[0].destroyed)

    def test_a_disconnect_leaves_the_clock_running_and_the_game_intact(self) -> None:
        host = self.make_host()
        self.running_game(host)
        self.application.tick()
        revision = self.bridge.get_snapshot()["revision"]

        self.unplug_wall()
        self.now += 5.0
        self.monotonic.advance(10.0)
        self.application.tick()

        view = self.bridge.get_snapshot()
        # Assert the loss was actually noticed, so the rest of this test cannot
        # pass by simply never detecting anything.
        self.assertTrue(view["health"]["display"]["needs_selection"])
        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["display"], "11:50")
        self.assertEqual(view["revision"], revision)
        self.assertEqual(view["teams"]["away"]["score"], 3)
        self.assertTrue(view["health"]["persistence"]["saved"])
        self.assertEqual(read_stored_game(self.paths.database).state.away_score, 3)

    def test_a_disconnect_writes_no_command_into_the_action_history(self) -> None:
        host = self.make_host()
        self.running_game(host)
        self.application.tick()
        before = len(read_action_history(self.paths.database))

        self.unplug_wall()
        self.now += 5.0
        self.application.tick()

        self.assertTrue(self.display_health()["needs_selection"])
        self.assertEqual(len(read_action_history(self.paths.database)), before)

    def test_the_display_coming_back_is_reported_but_nothing_moves(self) -> None:
        """D-006: reopening after a reconnection is the operator's decision."""

        host = self.make_host()
        self.running_game(host)
        self.application.tick()
        self.unplug_wall()
        self.now += 5.0
        self.application.tick()
        opened_windows = len(self.created)

        self.screens = [LAPTOP, WALL]
        self.names = [LAPTOP_NAME, WALL_NAME]
        self.now += 5.0
        self.application.tick()

        self.assertEqual(len(self.created), opened_windows)  # no window was created
        health = self.display_health()
        self.assertFalse(health["open"])
        self.assertFalse(health["needs_selection"])  # one click will do it now
        self.assertIn("Reopen Display", health["detail"])

    def test_the_operator_reopens_it_afterwards_in_one_click(self) -> None:
        host = self.make_host()
        self.running_game(host)
        self.application.tick()
        self.unplug_wall()
        self.now += 5.0
        self.application.tick()

        self.screens = [LAPTOP, WALL]
        self.names = [LAPTOP_NAME, WALL_NAME]
        self.bridge.reopen_display()

        self.assertTrue(self.display_health()["open"])
        self.assertIs(self.created[-1].screen, WALL)

    def test_a_watch_that_cannot_read_the_screens_does_not_end_the_game(self) -> None:
        def explode() -> list[FakeScreen]:
            raise OSError("the display driver is not answering")

        host = self.make_host(read_screens=explode)
        self.bridge.command("game_clock_start", {}, 0)
        self.monotonic.advance(3.0)

        self.application.tick()
        self.monotonic.advance(2.0)
        view = self.application.tick()

        self.assertIsNotNone(view)
        self.assertTrue(view["clocks"]["game"]["running"])  # type: ignore[index]
        self.assertEqual(view["clocks"]["game"]["display"], "11:55")  # type: ignore[index]

    def test_closing_the_spectator_window_by_hand_keeps_one_click_recovery(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()
        self.bridge.command("game_clock_start", {}, 0)

        host._spectator_closed(self.created[0])

        health = self.display_health()
        self.assertFalse(health["open"])
        self.assertEqual(health["label"], "DISPLAY CLOSED")
        self.assertTrue(health["can_reopen"])
        self.assertFalse(health["needs_selection"])
        self.assertTrue(self.bridge.get_snapshot()["clocks"]["game"]["running"])


class ReopenedViewTests(DisplayHostTestCase):
    """'A reopened view shows the current revision immediately.'"""

    def test_the_new_window_reads_the_current_snapshot_not_a_stale_one(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()

        host._spectator_closed(self.created[0])
        self.bridge.command("add_score", {"team": "home", "points": 6}, 0)
        self.bridge.command("add_score", {"team": "away", "points": 2}, 1)
        host.reopen_spectator()

        snapshot = host._spectator_snapshot()
        self.assertEqual(snapshot["revision"], self.application.service.state.revision)
        self.assertEqual(snapshot["teams"]["home"]["score"], 6)
        self.assertEqual(snapshot["teams"]["away"]["score"], 2)

    def test_a_reopened_view_shows_a_play_clock_that_never_stopped(self) -> None:
        """D-008: this board is the stadium's only play-clock display."""

        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()
        self.bridge.command("play_clock_preset", {"seconds": 40}, 0)
        self.bridge.command("play_clock_start", {}, 1)
        self.monotonic.advance(12.0)

        host._spectator_closed(self.created[0])
        self.monotonic.advance(3.0)
        host.reopen_spectator()

        snapshot = host._spectator_snapshot()
        self.assertTrue(snapshot["clocks"]["play"]["running"])
        self.assertEqual(snapshot["clocks"]["play"]["display"], "25")

    def test_reopening_replaces_the_old_window_rather_than_stacking_them(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()

        host.reopen_spectator()

        self.assertEqual(len(self.created), 2)
        self.assertTrue(self.created[0].destroyed)
        self.assertFalse(self.created[1].destroyed)
        self.assertIs(host.spectator_window, self.created[1])


class TestSpectatorWindowTests(DisplayHostTestCase):
    """The practice preview is independent of production display management."""

    def test_it_is_fixed_size_bordered_live_and_never_reads_display_selection(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        config_before = self.paths.config.read_text(encoding="utf-8")
        health_before = self.display_health()
        revision = self.bridge.get_snapshot()["revision"]
        history_before = len(read_action_history(self.paths.database))

        with mock.patch.object(host, "resolve_target", side_effect=AssertionError):
            payload = self.bridge.open_test_window()

        window = self.created[0]
        self.assertEqual(payload, {"message": "Test spectator window opened."})
        self.assertEqual(window.kwargs["width"], 640)
        self.assertEqual(window.kwargs["height"], 360)
        self.assertFalse(window.kwargs["frameless"])
        self.assertFalse(window.kwargs["resizable"])
        self.assertNotIn("screen", window.kwargs)
        self.assertNotIn("fullscreen", window.kwargs)
        self.assertIs(host.test_window, window)
        self.assertEqual(self.paths.config.read_text(encoding="utf-8"), config_before)
        self.assertEqual(self.display_health(), health_before)
        self.assertEqual(self.bridge.get_snapshot()["revision"], revision)
        self.assertEqual(len(read_action_history(self.paths.database)), history_before)

        # It receives the same spectator snapshot stream as the real board.
        self.bridge.command("add_score", {"team": "home", "points": 6}, revision)
        self.assertEqual(len(window.pushes), 1)
        self.assertIn('"score": 6', window.pushes[0])

    def test_reopening_replaces_the_old_test_window_without_touching_health(self) -> None:
        host = self.make_host()
        health_before = self.display_health()

        self.bridge.open_test_window()
        self.bridge.open_test_window()

        self.assertEqual(len(self.created), 2)
        self.assertTrue(self.created[0].destroyed)
        self.assertFalse(self.created[1].destroyed)
        self.assertIs(host.test_window, self.created[1])
        self.assertEqual(self.display_health(), health_before)

    def test_a_test_window_render_failure_does_not_change_production_health(self) -> None:
        host = self.make_host()
        self.bridge.open_test_window()
        test_window = self.created[0]
        health_before = self.display_health()
        test_window.evaluate_js = mock.Mock(side_effect=RuntimeError("test crashed"))

        host._push("spectator", host._spectator_snapshot())

        self.assertTrue(test_window.destroyed)
        self.assertIsNone(host.test_window)
        self.assertEqual(self.display_health(), health_before)

    def test_closing_or_shutdown_cleans_up_only_the_test_window_lifecycle(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()
        self.bridge.open_test_window()
        production, test_window = self.created
        health_before = self.display_health()

        host._test_window_closed(test_window)

        self.assertIsNone(host.test_window)
        self.assertEqual(self.display_health(), health_before)

        self.bridge.open_test_window()
        replacement = self.created[-1]
        host._operator_closing()

        self.assertTrue(production.destroyed)
        self.assertTrue(replacement.destroyed)
        self.assertIsNone(host.test_window)


class HostActionTests(DisplayHostTestCase):
    """Selecting, listing, and forgetting are host actions, not game commands."""

    def test_selecting_a_display_advances_no_revision_and_stops_no_clock(self) -> None:
        host = self.make_host()
        self.bridge.command("game_clock_start", {}, 0)
        revision = self.bridge.get_snapshot()["revision"]
        before = len(read_action_history(self.paths.database))

        payload = self.bridge.select_display(self.wall_target().key)

        self.monotonic.advance(4.0)
        view = self.bridge.get_snapshot()
        self.assertEqual(view["revision"], revision)
        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["display"], "11:56")
        self.assertEqual(len(read_action_history(self.paths.database)), before)
        self.assertTrue(payload["status"]["open"])

    def test_forgetting_a_display_leaves_the_open_window_alone(self) -> None:
        host = self.make_host()
        self.bridge.select_display(self.wall_target().key)
        self.assertIsNotNone(host.saved_display())

        payload = self.bridge.forget_display()

        self.assertIsNone(host.saved_display())
        self.assertTrue(payload["status"]["open"])
        self.assertFalse(self.created[0].destroyed)
        self.assertIsNone(payload["saved"])

    def test_the_displays_payload_is_json_safe_and_names_the_match(self) -> None:
        host = self.make_host()
        self.save_wall(host)

        payload = self.bridge.displays()

        json.dumps(payload, allow_nan=False)
        self.assertEqual(len(payload["displays"]), 2)
        self.assertEqual(payload["match"]["how"], MATCH_EXACT)
        self.assertEqual(payload["saved"]["name"], WALL_NAME)
        self.assertIn("1920x1080", payload["saved_label"])
        self.assertIn("view", payload)
        self.assertEqual(payload["view"]["revision"], 0)

    def test_the_payload_reports_a_missing_display_rather_than_hiding_it(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        self.unplug_wall()

        payload = self.bridge.displays()

        self.assertEqual(len(payload["displays"]), 1)
        self.assertEqual(payload["match"]["how"], MATCH_NONE)
        self.assertFalse(payload["match"]["found"])
        self.assertIn("DISPLAY NOT FOUND", payload["match"]["message"])

    def test_the_payload_marks_the_display_currently_in_use(self) -> None:
        host = self.make_host()
        self.bridge.select_display(self.wall_target().key)

        payload = self.bridge.displays()

        self.assertEqual(payload["current_key"], self.wall_target().key)

    def test_an_enumeration_failure_is_reported_rather_than_raised(self) -> None:
        def explode() -> dict[str, Any]:
            raise OSError("the display driver is not answering")

        host = self.make_host()
        self.application.display.list_displays = explode  # type: ignore[method-assign]

        payload = self.bridge.displays()

        self.assertIn("could not be read", payload["error"])
        self.assertEqual(payload["displays"], [])
        self.assertEqual(payload["view"]["revision"], 0)

    def test_a_preference_that_cannot_be_written_does_not_stop_the_open(self) -> None:
        host = self.make_host()
        with mock.patch.object(config, "write_section", return_value=False):
            host.select_display(self.wall_target().key)

        self.assertTrue(self.display_health()["open"])
        self.assertIs(self.created[0].screen, WALL)

    def test_every_display_control_is_reachable_from_the_operator_page(self) -> None:
        from tests.integration.test_bridge import OPERATOR_HTML

        self.assertIn('id="display-row"', OPERATOR_HTML)
        self.assertIn('id="display-choices"', OPERATOR_HTML)
        self.assertIn('data-action="forget_display"', OPERATOR_HTML)
        # And the one-click reopen stayed in the health strip, where a lost
        # display has to be recoverable without opening anything (D-005).
        self.assertIn('id="reopen-display"', OPERATOR_HTML)

    def test_display_actions_share_the_one_command_lock(self) -> None:
        """A display action can never read a half-applied command.

        The bridge takes the application's own command lock, which is what
        serialises commands against the refresh tick. Holding it here and then
        calling through the bridge proves both halves: the lock really is
        shared, and it is re-entrant, so a display action taken from the
        operator window cannot deadlock against a tick on the same thread.
        """

        self.make_host()
        self.assertIs(self.bridge._lock, self.application._command_lock)

        with self.application._command_lock:
            payload = self.bridge.displays()

        self.assertEqual(payload["view"]["revision"], 0)
        self.assertEqual(len(payload["displays"]), 2)


class ConfigFileTests(TemporaryDataDirectoryTest):
    """``config.json``: preferences that may never stop the scoreboard."""

    def test_a_section_round_trips(self) -> None:
        self.assertTrue(config.write_section(self.paths, "display", {"x": 1366}))

        self.assertEqual(config.read_section(self.paths, "display"), {"x": 1366})
        self.assertEqual(
            config.read_config(self.paths)["schema_version"],
            config.CONFIG_SCHEMA_VERSION,
        )

    def test_writing_one_section_preserves_the_others(self) -> None:
        config.write_section(self.paths, "display", {"x": 1366})
        config.write_section(self.paths, "shortcuts", {"space": "start"})

        document = config.read_config(self.paths)
        self.assertEqual(document["display"], {"x": 1366})
        self.assertEqual(document["shortcuts"], {"space": "start"})

    def test_writing_none_removes_only_that_section(self) -> None:
        config.write_section(self.paths, "display", {"x": 1366})
        config.write_section(self.paths, "shortcuts", {"space": "start"})

        config.write_section(self.paths, "display", None)

        self.assertIsNone(config.read_section(self.paths, "display"))
        self.assertEqual(config.read_section(self.paths, "shortcuts"), {"space": "start"})

    def test_a_missing_file_is_not_an_error_and_creates_nothing(self) -> None:
        self.assertEqual(config.read_config(self.paths), {})
        self.assertFalse(self.paths.config.exists())

    def test_unreadable_content_reads_as_no_preferences(self) -> None:
        for payload in ("", "{", "[]", '"text"', '{"schema_version": "1"}'):
            with self.subTest(payload):
                self.paths.config.write_text(payload, encoding="utf-8")

                self.assertEqual(config.read_config(self.paths), {})

    def test_an_unwritable_location_is_reported_not_raised(self) -> None:
        with mock.patch("pathlib.Path.write_text", side_effect=OSError("read-only")):
            self.assertFalse(config.write_section(self.paths, "display", {"x": 1}))

    def test_a_failed_write_leaves_the_previous_preference_intact(self) -> None:
        config.write_section(self.paths, "display", {"x": 1366})

        with mock.patch("os.replace", side_effect=OSError("interrupted")):
            self.assertFalse(config.write_section(self.paths, "display", {"x": 9}))

        self.assertEqual(config.read_section(self.paths, "display"), {"x": 1366})
        self.assertFalse(self.paths.config.with_suffix(".json.tmp").exists())
