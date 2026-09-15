"""The sport picker, ``--sport``, and ``ScoreboardPaths.for_sport`` (spec 2.3/2.5).

Football's own path (no picker involved) is proven byte-identical here by
building a ``ScoreboardApplication`` two ways -- directly, and through the
picker's ``choose_sport("football")`` -- and comparing the operator view
model produced by each. ``webview.create_window``/``webview.start`` are
mocked throughout: nothing here opens a real window.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scoreboard import __main__ as main_module
from scoreboard.host.app import ScoreboardApplication, WindowHost
from scoreboard.host.sport_picker import (
    SPORTS,
    SportPickerBridge,
    SportPickerHost,
    read_last_sport,
    write_last_sport,
)
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import ScoreboardPaths

from tests.integration.support import TemporaryDataDirectoryTest


class ForSportTests(TemporaryDataDirectoryTest):
    """``ScoreboardPaths.for_sport`` (spec 2.3): a new, additive method only."""

    def test_for_sport_roots_under_a_subdirectory(self) -> None:
        soccer_paths = self.paths.for_sport("soccer")
        self.assertEqual(soccer_paths.root, self.paths.root / "soccer")
        self.assertEqual(soccer_paths.database, self.paths.root / "soccer" / "scoreboard.db")
        self.assertEqual(soccer_paths.lock, self.paths.root / "soccer" / "scoreboard.lock")

    def test_for_sport_leaves_the_root_paths_untouched(self) -> None:
        before = self.paths.database
        self.paths.for_sport("soccer")
        self.assertEqual(self.paths.database, before)

    def test_for_sport_returns_a_scoreboard_paths(self) -> None:
        self.assertIsInstance(self.paths.for_sport("soccer"), ScoreboardPaths)


class SportPickerBridgeTests(TemporaryDataDirectoryTest):
    """Remembering and reporting the last sport (spec 2.5, owner choice A)."""

    def test_no_preference_reads_as_none(self) -> None:
        self.assertIsNone(read_last_sport(self.paths))

    def test_write_then_read_round_trips(self) -> None:
        self.assertTrue(write_last_sport(self.paths, "soccer"))
        self.assertEqual(read_last_sport(self.paths), "soccer")

    def test_bridge_last_sport_reads_through(self) -> None:
        write_last_sport(self.paths, "football")
        bridge = SportPickerBridge(lambda sport: None, lambda: read_last_sport(self.paths))
        self.assertEqual(bridge.last_sport(), "football")

    def test_bridge_choose_sport_calls_through(self) -> None:
        seen: list[str] = []
        bridge = SportPickerBridge(seen.append, lambda: None)
        bridge.choose_sport("soccer")
        self.assertEqual(seen, ["soccer"])

    def test_bridge_refuses_an_unknown_sport(self) -> None:
        bridge = SportPickerBridge(lambda sport: None, lambda: None)
        with self.assertRaises(ValueError):
            bridge.choose_sport("basketball")

    def test_a_garbled_section_reads_as_none(self) -> None:
        from scoreboard.infrastructure import config

        config.write_section(self.paths, "sport", {"last": "basketball"})
        self.assertIsNone(read_last_sport(self.paths))

    def test_sports_tuple(self) -> None:
        self.assertEqual(SPORTS, ("football", "soccer"))


class SportPickerHostFootballTests(TemporaryDataDirectoryTest):
    """Choosing Football through the picker is byte-identical to today's path."""

    def _direct_operator_view(self, paths):
        application = ScoreboardApplication(
            paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic,
        )
        self.addCleanup(application.shutdown)
        bridge = application.start_new()
        return bridge.get_snapshot()

    def test_choose_football_builds_scoreboard_application_on_root_paths(self) -> None:
        picker = SportPickerHost(self.paths)
        with patch("scoreboard.host.sport_picker.webview.create_window") as create:
            create.return_value = MagicMock()
            picker._choose_sport("football")
        self.assertIsNotNone(picker.host)
        self.assertIsInstance(picker.host.application, ScoreboardApplication)
        self.assertEqual(picker.host.application.paths.root, self.paths.root)
        self.addCleanup(picker.host.application.shutdown)

    def test_a_second_choice_is_ignored(self) -> None:
        picker = SportPickerHost(self.paths)
        with patch("scoreboard.host.sport_picker.webview.create_window") as create:
            create.return_value = MagicMock()
            picker._choose_sport("football")
            first = picker.host
            picker._choose_sport("soccer")
        self.assertIs(picker.host, first)
        self.addCleanup(picker.host.application.shutdown)

    def test_choosing_football_remembers_it(self) -> None:
        picker = SportPickerHost(self.paths)
        with patch("scoreboard.host.sport_picker.webview.create_window") as create:
            create.return_value = MagicMock()
            picker._choose_sport("football")
        self.assertEqual(read_last_sport(self.paths), "football")
        self.addCleanup(picker.host.application.shutdown)

    def test_picker_window_is_destroyed_on_choice(self) -> None:
        picker = SportPickerHost(self.paths)
        fake_picker_window = MagicMock()
        picker._picker_window = fake_picker_window
        with patch("scoreboard.host.sport_picker.webview.create_window") as create:
            create.return_value = MagicMock()
            picker._choose_sport("football")
        fake_picker_window.destroy.assert_called_once()
        self.addCleanup(picker.host.application.shutdown)

    def test_operator_view_model_matches_a_direct_application(self) -> None:
        # A separate, fresh root for the direct comparison application: the
        # picker below builds its own ScoreboardApplication on self.paths,
        # and a recoverable game on that same root would make the picker's
        # begin() stop at a recovery-choice screen instead of the operator.
        other_paths = self.paths.__class__(self.temporary_root / "Direct")
        direct_view = self._direct_operator_view(other_paths)

        picker = SportPickerHost(self.paths)
        with patch("scoreboard.host.sport_picker.webview.create_window") as create:
            create.return_value = MagicMock()
            picker._choose_sport("football")
        self.addCleanup(picker.host.application.shutdown)
        # Both applications inspected the same (empty) recovery report and
        # started a new game, so their operator views must be identical
        # except for the two timestamps/paths a second construction disturbs.
        picker_view = picker.host.application.bridge.get_snapshot()
        self.assertEqual(picker_view["teams"], direct_view["teams"])
        self.assertEqual(picker_view["clocks"], direct_view["clocks"])
        self.assertEqual(picker_view["quarter"], direct_view["quarter"])
        self.assertEqual(picker_view["revision"], direct_view["revision"])

    def test_instance_already_running_is_reported_and_picker_stays_open(self) -> None:
        from scoreboard.infrastructure.persistence import InstanceAlreadyRunning

        picker = SportPickerHost(self.paths)
        fake_picker_window = MagicMock()
        picker._picker_window = fake_picker_window
        with patch(
            "scoreboard.host.sport_picker.ScoreboardApplication",
            side_effect=InstanceAlreadyRunning("already running"),
        ), patch("scoreboard.host.sport_picker.preflight.report") as report:
            picker._choose_sport("football")
        report.assert_called_once()
        self.assertIsNone(picker.host)
        fake_picker_window.destroy.assert_not_called()

    def test_auto_close_after_seconds_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            SportPickerHost(self.paths, auto_close_after_seconds=0)


class ParseArgsTests(unittest.TestCase):
    def test_default_sport_is_none(self) -> None:
        args = main_module.parse_args([])
        self.assertIsNone(args.sport)

    def test_sport_football(self) -> None:
        args = main_module.parse_args(["--sport", "football"])
        self.assertEqual(args.sport, "football")

    def test_sport_soccer(self) -> None:
        args = main_module.parse_args(["--sport", "soccer"])
        self.assertEqual(args.sport, "soccer")

    def test_an_unknown_sport_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            main_module.parse_args(["--sport", "basketball"])

    def test_resume_and_new_game_are_still_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            main_module.parse_args(["--resume", "--new-game"])


class MainDispatchTests(unittest.TestCase):
    """``main()``'s three-way sport dispatch, with every application stubbed."""

    def _patched_webview2(self):
        satisfied = MagicMock()
        satisfied.satisfied = True
        return patch("scoreboard.__main__.preflight.check_webview2", return_value=satisfied)

    def test_no_sport_and_no_startup_choice_opens_the_picker(self) -> None:
        picker_instance = MagicMock()
        with self._patched_webview2(), patch(
            "scoreboard.host.sport_picker.SportPickerHost", return_value=picker_instance
        ) as picker_cls:
            result = main_module.main([])
        picker_cls.assert_called_once()
        picker_instance.run.assert_called_once()
        self.assertEqual(result, 0)

    def test_bare_resume_uses_the_football_path_not_the_picker(self) -> None:
        application = MagicMock()
        host = MagicMock()
        with self._patched_webview2(), patch(
            "scoreboard.host.sport_picker.SportPickerHost"
        ) as picker_cls, patch(
            "scoreboard.__main__.ScoreboardApplication", return_value=application
        ), patch("scoreboard.__main__.WindowHost", return_value=host) as host_cls:
            result = main_module.main(["--resume"])
        picker_cls.assert_not_called()
        host_cls.assert_called_once()
        host.run.assert_called_once_with(startup_choice="resume", interactive=True)
        self.assertEqual(result, 0)

    def test_sport_football_uses_the_football_path(self) -> None:
        application = MagicMock()
        host = MagicMock()
        with self._patched_webview2(), patch(
            "scoreboard.host.sport_picker.SportPickerHost"
        ) as picker_cls, patch(
            "scoreboard.__main__.ScoreboardApplication", return_value=application
        ), patch("scoreboard.__main__.WindowHost", return_value=host) as host_cls:
            result = main_module.main(["--sport", "football"])
        picker_cls.assert_not_called()
        host_cls.assert_called_once_with(
            application, initial_display_index=None, auto_close_after_seconds=None
        )
        self.assertEqual(result, 0)

    def test_sport_soccer_builds_soccer_application(self) -> None:
        application = MagicMock()
        host = MagicMock()
        with self._patched_webview2(), patch(
            "scoreboard.host.soccer_app.SoccerApplication", return_value=application
        ) as soccer_cls, patch(
            "scoreboard.__main__.WindowHost", return_value=host
        ) as host_cls:
            result = main_module.main(["--sport", "soccer"])
        soccer_cls.assert_called_once_with()
        host_cls.assert_called_once_with(
            application, initial_display_index=None, auto_close_after_seconds=None
        )
        host.run.assert_called_once_with(startup_choice=None, interactive=True)
        self.assertEqual(result, 0)

    def test_sport_soccer_reports_instance_already_running(self) -> None:
        from scoreboard.infrastructure.persistence import InstanceAlreadyRunning

        with self._patched_webview2(), patch(
            "scoreboard.host.soccer_app.SoccerApplication",
            side_effect=InstanceAlreadyRunning("already running"),
        ), patch("scoreboard.__main__.preflight.report") as report:
            result = main_module.main(["--sport", "soccer"])
        report.assert_called_once()
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
