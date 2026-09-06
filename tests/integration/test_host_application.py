"""The host now owns the service, persistence, and both windows.

These tests drive :class:`~scoreboard.host.app.ScoreboardApplication` without
opening a window, which is the point of separating it from ``WindowHost``.
"""

from __future__ import annotations

import json
import threading
import unittest

from scoreboard.host.app import (
    REFRESH_INTERVAL_SECONDS,
    RecoveryChoiceRequired,
    ScoreboardApplication,
    view_url,
)
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.persistence import (
    InstanceAlreadyRunning,
    read_action_history,
    read_stored_game,
)

from tests.integration.support import TemporaryDataDirectoryTest


class ApplicationTestCase(TemporaryDataDirectoryTest):
    def make_application(self, **kwargs) -> ScoreboardApplication:
        kwargs.setdefault("diagnostics", NullDiagnostics())
        kwargs.setdefault("monotonic_clock", self.monotonic)
        application = ScoreboardApplication(self.paths, **kwargs)
        self.addCleanup(application.shutdown)
        return application


class StartupTests(ApplicationTestCase):
    """One process owns the lock, the game, and its storage."""

    def test_a_new_game_starts_saved_and_stopped(self) -> None:
        application = self.make_application()

        bridge = application.start_new()
        view = bridge.get_snapshot()

        self.assertEqual(view["revision"], 0)
        self.assertEqual(view["teams"]["home"]["score"], 0)
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertTrue(view["health"]["persistence"]["saved"])
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 0)

    def test_the_bridge_shares_one_service_and_one_store(self) -> None:
        application = self.make_application()
        bridge = application.start_new()

        bridge.command("add_score", {"team": "home", "points": 6}, 0)

        self.assertIs(bridge.service, application.service)
        self.assertEqual(application.service.state.home_score, 6)
        self.assertEqual(read_stored_game(self.paths.database).state.home_score, 6)

    def test_a_second_instance_is_refused_before_it_touches_the_database(self) -> None:
        application = self.make_application(acquire_lock=True)
        application.start_new()

        with self.assertRaises(InstanceAlreadyRunning):
            ScoreboardApplication(
                self.paths, diagnostics=NullDiagnostics(), acquire_lock=True
            )

        self.assertEqual(application.service.state.home_score, 0)


class RecoveryChoiceTests(ApplicationTestCase):
    """P-005: nothing is resumed or replaced without an explicit choice."""

    def saved_game(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("add_score", {"team": "home", "points": 6}, 0)
        bridge.command("game_clock_start", {}, 1)
        self.monotonic.advance(20.0)
        application.tick()
        application.shutdown()

    def test_a_recoverable_game_is_reported_but_not_started(self) -> None:
        self.saved_game()
        application = self.make_application()

        self.assertTrue(application.can_resume)
        self.assertIsNone(application.service)
        self.assertIsNone(application.bridge)
        payload = application.recovery_payload()
        json.dumps(payload)
        self.assertIn("Resume recovered game", payload["choices"])

    def test_resuming_restores_the_game_with_clocks_stopped(self) -> None:
        self.saved_game()
        application = self.make_application()

        bridge = application.resume()
        view = bridge.get_snapshot()

        self.assertEqual(view["teams"]["home"]["score"], 6)
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertEqual(view["clocks"]["game"]["status"], "STOPPED")
        self.assertEqual(view["clocks"]["game"]["display"], "29:40")

    def test_starting_new_after_a_crash_archives_rather_than_deletes(self) -> None:
        self.saved_game()
        application = self.make_application()

        bridge = application.start_new()

        self.assertEqual(bridge.get_snapshot()["teams"]["home"]["score"], 0)
        commands = [row["command"] for row in read_action_history(self.paths.database)]
        self.assertIn("add_score", commands)

    def test_the_window_host_refuses_to_guess(self) -> None:
        from scoreboard.host.app import WindowHost

        self.saved_game()
        application = self.make_application()
        host = WindowHost(application, initial_display_index=0)

        with self.assertRaises(RecoveryChoiceRequired) as raised:
            host.run(startup_choice=None)

        self.assertTrue(raised.exception.report.can_resume)
        self.assertIsNone(application.service)


class RefreshTests(ApplicationTestCase):
    """The refresh loop displays and checkpoints; it never commands."""

    def test_refresh_cadence_can_present_each_tenth(self) -> None:
        self.assertEqual(REFRESH_INTERVAL_SECONDS, 0.1)

    def test_a_worker_refresh_can_checkpoint_the_shared_store(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start", {}, 0)
        self.monotonic.advance(1.0)
        errors: list[BaseException] = []

        def refresh() -> None:
            try:
                application.tick()
            except BaseException as exc:  # pragma: no cover - assertion below
                errors.append(exc)

        worker = threading.Thread(target=refresh)
        worker.start()
        worker.join()

        self.assertEqual(errors, [])
        self.assertTrue(bridge.get_snapshot()["health"]["persistence"]["saved"])
        stored = read_stored_game(self.paths.database)
        self.assertIsNotNone(stored)
        self.assertAlmostEqual(stored.state.game_clock.seconds, 1799.0, places=6)

    def test_a_tick_publishes_to_both_windows(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        published: list[tuple[str, dict]] = []
        application.set_publisher(lambda name, view: published.append((name, view)))
        bridge.command("game_clock_start", {}, 0)

        published.clear()  # Accepted Start already published immediately.
        self.monotonic.advance(3.0)
        application.tick()

        names = [name for name, _ in published]
        self.assertEqual(names, ["operator", "spectator"])
        operator_view = published[0][1]
        spectator_view = published[1][1]
        self.assertEqual(operator_view["clocks"]["game"]["display"], "29:57")
        self.assertEqual(spectator_view["clocks"]["game"]["display"], "29:57")
        self.assertIn("health", operator_view)
        self.assertNotIn("health", spectator_view)

    def test_a_spectator_push_failure_marks_the_display_and_keeps_the_clock(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start", {}, 0)

        def failing_push(name: str, view: dict) -> None:
            if name == "spectator":
                raise RuntimeError("the display stopped responding")

        application.set_publisher(failing_push)
        self.monotonic.advance(2.0)
        application.tick()

        # R-002: the engine survives a spectator that cannot render.
        self.assertTrue(application.service.state.game_clock.running)
        view = bridge.get_snapshot()
        self.assertTrue(view["clocks"]["game"]["running"])
        self.assertFalse(view["health"]["display"]["open"])
        self.assertIn("stopped responding", view["health"]["display"]["detail"])

    def test_a_tick_before_a_game_starts_is_harmless(self) -> None:
        application = self.make_application()

        self.assertIsNone(application.tick())


class ShutdownTests(ApplicationTestCase):
    """W-004: a clean shutdown saves and releases everything it owns."""

    def test_shutdown_saves_the_final_state_and_releases_the_lock(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("add_score", {"team": "home", "points": 6}, 0)
        bridge.command("game_clock_start", {}, 1)
        self.monotonic.advance(9.0)

        application.shutdown()

        stored = read_stored_game(self.paths.database)
        self.assertEqual(stored.checkpoint_kind, "SHUTDOWN")
        self.assertAlmostEqual(stored.state.game_clock.seconds, 1791.0, places=6)
        # The lock is free again, so the next launch is not blocked.
        second = ScoreboardApplication(
            self.paths, diagnostics=NullDiagnostics(), acquire_lock=True
        )
        self.addCleanup(second.shutdown)
        self.assertTrue(second.can_resume)


class BundledAssetTests(unittest.TestCase):
    """R-001: every page asset is bundled, none is fetched from a network."""

    def test_each_window_loads_a_bundled_local_page(self) -> None:
        for name in ("operator", "spectator"):
            with self.subTest(window=name):
                url = view_url(name)
                self.assertTrue(url.startswith("file:///"))
                self.assertTrue(url.endswith(f"{name}/index.html"))

    def test_no_page_references_a_remote_asset(self) -> None:
        from tests.integration.test_bridge import OPERATOR_HTML, SPECTATOR_HTML

        for page in (OPERATOR_HTML, SPECTATOR_HTML):
            with self.subTest(page=page[:40]):
                self.assertNotIn("http://", page)
                self.assertNotIn("https://", page)
                self.assertNotIn("//cdn", page)


if __name__ == "__main__":
    unittest.main()
