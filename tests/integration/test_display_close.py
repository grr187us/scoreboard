"""Closing the spectator display on purpose, and nothing else (D-005).

Owner request 5: the wall can be put away from the display window itself (Esc
or a corner button) and from the operator's Display drawer. These tests hold
the line that makes that safe -- closing a monitor is something about this
laptop, not something that happened in the football game, so it advances no
revision, writes no history row, and stops no clock (D-005, R-002).

They reuse ``test_display_selection``'s fakes: injected screens and a
``webview.create_window`` replacement, so a window is opened and destroyed
without a second monitor or a WebView2 process.
"""

from __future__ import annotations

from scoreboard.host.app import CLOSED_BY_OPERATOR_DETAIL
from scoreboard.host.bridge import SpectatorBridge
from scoreboard.infrastructure.persistence import read_action_history

from tests.integration.test_display_selection import (
    WALL,
    DisplayHostTestCase,
)


class CloseSpectatorTests(DisplayHostTestCase):
    """'The display window can be put away and brought back in one click.'"""

    def open_wall(self, host):
        """Open the spectator window on the saved wall and return it."""

        self.save_wall(host)
        host.reopen_spectator()
        self.assertEqual(len(self.created), 1)
        return self.created[0]

    def test_closing_destroys_the_window_and_says_it_was_on_purpose(self) -> None:
        host = self.make_host()
        window = self.open_wall(host)

        host.close_spectator()

        self.assertTrue(window.destroyed)
        self.assertIsNone(host.spectator_window)
        health = self.display_health()
        self.assertFalse(health["open"])
        self.assertEqual(health["label"], "DISPLAY CLOSED")
        self.assertTrue(health["can_reopen"])
        self.assertFalse(health["needs_selection"])
        self.assertEqual(health["detail"], CLOSED_BY_OPERATOR_DETAIL)

    def test_closing_the_display_changes_nothing_in_the_game(self) -> None:
        host = self.make_host()
        self.open_wall(host)
        self.bridge.command("add_score", {"team": "home", "points": 6}, 0)
        self.bridge.command("game_clock_start", {}, 1)
        revision = self.bridge.get_snapshot()["revision"]
        rows = len(read_action_history(self.paths.database))

        host.close_spectator()
        self.monotonic.advance(5.0)
        view = self.bridge.get_snapshot()

        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["display"], "29:55")
        self.assertEqual(view["revision"], revision)
        self.assertEqual(view["teams"]["home"]["score"], 6)
        self.assertEqual(len(read_action_history(self.paths.database)), rows)

    def test_the_late_closed_event_from_that_window_is_a_no_op(self) -> None:
        """The window's own ``closed`` callback must not overwrite the wording."""

        host = self.make_host()
        window = self.open_wall(host)

        host.close_spectator()
        for handler in window.events.closed.handlers:
            handler(window)

        self.assertEqual(self.display_health()["detail"], CLOSED_BY_OPERATOR_DETAIL)
        self.assertIsNone(host.spectator_window)

    def test_a_deliberate_close_is_told_apart_from_a_crash(self) -> None:
        """The generic wording is what an unexpected close still produces."""

        host = self.make_host()
        window = self.open_wall(host)

        for handler in window.events.closed.handlers:
            handler(window)

        self.assertNotEqual(self.display_health()["detail"], CLOSED_BY_OPERATOR_DETAIL)

    def test_reopening_afterwards_returns_to_the_saved_display(self) -> None:
        host = self.make_host()
        self.open_wall(host)

        host.close_spectator()
        host.reopen_spectator()

        self.assertEqual(len(self.created), 2)
        self.assertIs(self.created[1].screen, WALL)
        self.assertTrue(self.display_health()["open"])

    def test_closing_with_no_window_open_reports_plainly(self) -> None:
        host = self.make_host()
        before = self.display_health()

        result = host.close_spectator()

        self.assertEqual(self.created, [])
        self.assertIn("no display window is open", result["message"])
        self.assertEqual(self.display_health(), before)


class SpectatorSelfCloseTests(DisplayHostTestCase):
    """'The wall closes its own window and can reach nothing else.'"""

    def spectator_bridge(self, host) -> SpectatorBridge:
        self.save_wall(host)
        host.reopen_spectator()
        return self.created[0].kwargs["js_api"]

    def test_the_display_window_can_close_itself(self) -> None:
        host = self.make_host()
        api = self.spectator_bridge(host)

        result = api.close_display()

        self.assertTrue(result["closed"])
        self.assertTrue(self.created[0].destroyed)
        self.assertEqual(self.display_health()["detail"], CLOSED_BY_OPERATOR_DETAIL)

    def test_the_spectator_bridge_still_changes_no_game_state(self) -> None:
        host = self.make_host()
        api = self.spectator_bridge(host)
        self.bridge.command("game_clock_start", {}, 0)
        revision = self.bridge.get_snapshot()["revision"]

        api.close_display()
        self.monotonic.advance(3.0)

        self.assertEqual(self.bridge.get_snapshot()["revision"], revision)
        self.assertTrue(self.bridge.get_snapshot()["clocks"]["game"]["running"])
        self.assertFalse(hasattr(api, "command"))

    def test_a_bridge_built_without_a_close_hook_answers_plainly(self) -> None:
        api = SpectatorBridge(lambda: {"revision": 0})

        result = api.close_display()

        self.assertFalse(result["closed"])
        self.assertEqual(
            result["message"], "This display cannot close itself in this build."
        )

    def test_the_practice_window_closes_only_itself(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()
        host.open_test_window()
        spectator, test_window = self.created[0], self.created[1]

        test_window.kwargs["js_api"].close_display()

        self.assertTrue(test_window.destroyed)
        self.assertIsNone(host.test_window)
        self.assertFalse(spectator.destroyed)
        # The practice window has no display-health role at all.
        self.assertTrue(self.display_health()["open"])


class OperatorCloseDisplayTests(DisplayHostTestCase):
    """'Close Display in the drawer is a host action like Reopen Display.'"""

    def test_it_returns_the_displays_payload_so_the_drawer_re_renders(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()

        payload = self.bridge.close_display()

        self.assertIn("displays", payload)
        self.assertIn("saved", payload)
        self.assertIn("match", payload)
        self.assertEqual(payload["status"]["label"], "DISPLAY CLOSED")
        self.assertEqual(payload["status"]["detail"], CLOSED_BY_OPERATOR_DETAIL)
        self.assertTrue(payload["status"]["can_reopen"])
        self.assertFalse(payload["view"]["health"]["display"]["open"])

    def test_it_advances_no_revision_and_writes_no_history_row(self) -> None:
        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()
        self.bridge.command("add_score", {"team": "away", "points": 3}, 0)
        revision = self.bridge.get_snapshot()["revision"]
        rows = len(read_action_history(self.paths.database))

        self.bridge.close_display()

        self.assertEqual(self.bridge.get_snapshot()["revision"], revision)
        self.assertEqual(len(read_action_history(self.paths.database)), rows)

    def test_a_failing_close_is_contained_and_reported(self) -> None:
        """A display must never stop the game, not even while going away."""

        host = self.make_host()
        self.save_wall(host)
        host.reopen_spectator()

        def boom() -> dict[str, str]:
            raise RuntimeError("the window is wedged")

        self.application.display.close = boom  # type: ignore[method-assign]
        payload = self.bridge.close_display()

        self.assertFalse(payload["status"]["open"])
        self.assertIn("could not be closed", payload["status"]["detail"])
        self.assertEqual(payload["view"]["revision"], 0)
