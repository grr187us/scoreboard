"""``SoccerApplication`` without a window (spec section 2.2, api_domain.md).

Mirrors ``tests/integration/test_host_application.py``'s style: drives the
application object directly, the way ``WindowHost`` does, so every one of
these proves the same contract football's application keeps -- lock,
recovery, resume/start-new, tick, shutdown -- but scoped entirely under
``<root>/soccer/``.
"""

from __future__ import annotations

import unittest

from scoreboard.host.app import ScoreboardApplication
from scoreboard.host.soccer_app import SOCCER_PROFILE, SoccerApplication
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.persistence import InstanceAlreadyRunning

from tests.integration.support import TemporaryDataDirectoryTest


class SoccerApplicationTestCase(TemporaryDataDirectoryTest):
    def make_application(self, **kwargs) -> SoccerApplication:
        kwargs.setdefault("diagnostics", NullDiagnostics())
        kwargs.setdefault("monotonic_clock", self.monotonic)
        application = SoccerApplication(self.paths, **kwargs)
        self.addCleanup(application.shutdown)
        return application


class LockAndPathsTests(SoccerApplicationTestCase):
    def test_paths_are_rooted_under_soccer(self) -> None:
        application = self.make_application()
        self.assertEqual(application.paths.root, self.paths.root / "soccer")

    def test_lock_file_lives_under_soccer(self) -> None:
        application = self.make_application()
        self.assertEqual(application.paths.lock, self.paths.root / "soccer" / "scoreboard.lock")
        self.assertTrue(application.paths.lock.exists())

    def test_root_paths_is_the_original_root(self) -> None:
        application = self.make_application()
        self.assertEqual(application.root_paths.root, self.paths.root)

    def test_teams_json_stays_at_the_root(self) -> None:
        application = self.make_application()
        self.assertEqual(application.teams._paths.root, self.paths.root)

    def test_a_second_instance_is_refused(self) -> None:
        self.make_application()
        with self.assertRaises(InstanceAlreadyRunning):
            SoccerApplication(self.paths, diagnostics=NullDiagnostics())

    def test_football_can_run_alongside_soccer(self) -> None:
        """Both sports may hold locks at once -- different files (spec 2.5)."""

        soccer_app = self.make_application()
        football_app = ScoreboardApplication(
            self.paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic,
        )
        self.addCleanup(football_app.shutdown)
        self.assertNotEqual(soccer_app.paths.lock, football_app.paths.lock)

    def test_profile_is_the_soccer_profile(self) -> None:
        application = self.make_application()
        self.assertIs(application.profile, SOCCER_PROFILE)
        self.assertEqual(application.profile.sport, "soccer")
        self.assertEqual(application.profile.operator_view, "soccer_operator")


class RecoveryIsolationTests(SoccerApplicationTestCase):
    def test_a_fresh_soccer_root_has_nothing_to_recover(self) -> None:
        application = self.make_application()
        self.assertFalse(application.can_resume)

    def test_a_football_crash_is_never_offered_to_soccer(self) -> None:
        football_app = ScoreboardApplication(
            self.paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic,
        )
        bridge = football_app.start_new()
        bridge.command("add_score", {"team": "home", "points": 6})
        bridge.command("game_clock_start")
        self.monotonic.advance(5)
        football_app.shutdown()

        soccer_app = self.make_application()
        self.assertFalse(soccer_app.can_resume)

    def test_a_soccer_crash_is_never_offered_to_football(self) -> None:
        soccer_app = self.make_application()
        bridge = soccer_app.start_new()
        # Advance a period first so a later add_goal would be legal, mirroring
        # the domain rule that a goal can only be recorded during a live period.
        rev = bridge.get_snapshot()["revision"]
        bridge.command("period_forward", {"confirmed": True}, rev)
        self.monotonic.advance(5)
        soccer_app.shutdown()

        football_app = ScoreboardApplication(
            self.paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic,
        )
        self.addCleanup(football_app.shutdown)
        self.assertFalse(football_app.can_resume)


class LifecycleTests(SoccerApplicationTestCase):
    def test_start_new_begins_a_saved_stopped_game(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        view = bridge.get_snapshot()
        self.assertEqual(view["revision"], 0)
        self.assertEqual(view["teams"]["home"]["score"], 0)
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertTrue(view["health"]["persistence"]["saved"])

    def test_bridge_and_application_share_one_service(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        rev = bridge.get_snapshot()["revision"]
        bridge.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, rev)
        self.assertIs(bridge.service, application.service)
        self.assertEqual(application.service.state.home_shots, 1)

    def test_resume_continues_the_saved_game_with_clocks_stopped(self) -> None:
        first = self.make_application()
        bridge = first.start_new()
        rev = bridge.get_snapshot()["revision"]
        bridge.command("period_forward", {"confirmed": True}, rev)
        rev = bridge.get_snapshot()["revision"]
        bridge.command("game_clock_start", {}, rev)
        self.monotonic.advance(10)
        first.shutdown()

        second = self.make_application()
        self.assertTrue(second.can_resume)
        resumed_bridge = second.resume()
        view = resumed_bridge.get_snapshot()
        self.assertEqual(view["period"], "1st")
        self.assertFalse(view["clocks"]["game"]["running"])

    def test_tick_publishes_operator_and_spectator_views(self) -> None:
        application = self.make_application()
        application.start_new()
        pushed: list[tuple[str, dict]] = []
        application.set_publisher(lambda name, view: pushed.append((name, view)))
        application.tick()
        names = [name for name, _ in pushed]
        self.assertIn("operator", names)
        self.assertIn("spectator", names)

    def test_shutdown_saves_and_releases_the_lock(self) -> None:
        application = self.make_application(acquire_lock=True)
        application.start_new()
        application.shutdown()
        # The lock is released, so a fresh instance can now be built.
        second = SoccerApplication(self.paths, diagnostics=NullDiagnostics())
        second.shutdown()


if __name__ == "__main__":
    unittest.main()
