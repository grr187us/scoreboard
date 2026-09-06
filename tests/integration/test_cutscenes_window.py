"""Cutscenes window host lifecycle contract (spec section 5.3, 5.4).

These use pywebview-shaped fakes: no native window is claimed as evidence.
They prove the host containment policy for the Cutscenes window and the
publish/end path to the spectator and practice windows -- exactly the same
policy ``test_field_assistant_window.py`` proves for the Field Assistant: an
optional surface can disappear or fail without reaching clocks, persistence,
the primary operator, or the spectator (R-002). A cutscene push failure is
decoration only: it must never destroy the spectator or the practice window,
unlike a real ``applyView`` push failure, which does.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from scoreboard.host.app import ScoreboardApplication, WindowHost, view_url
from scoreboard.host.bridge import SpectatorBridge
from scoreboard.host.cutscenes import CutscenesBridge
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths

from tests.integration.support import TemporaryDataDirectoryTest


class _Event:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "_Event":
        self.handlers.append(handler)
        return self

    def is_set(self) -> bool:
        return True


class _Events:
    def __init__(self) -> None:
        self.closed = _Event()
        self.closing = _Event()
        self.loaded = _Event()


class _Window:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # ``webview.create_window`` takes its title positionally; every other
        # argument the host passes is a keyword.
        self.title = args[0] if args else kwargs.get("title")
        self.kwargs = kwargs
        self.events = _Events()
        self.destroyed = False
        self.scripts: list[str] = []
        self.fail_push = False

    def destroy(self) -> None:
        self.destroyed = True

    def evaluate_js(self, script: str) -> None:
        if self.fail_push:
            raise RuntimeError("helper renderer stopped")
        self.scripts.append(script)


class CutscenesWindowTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.windows: list[_Window] = []
        patcher = mock.patch(
            "scoreboard.host.app.webview.create_window", side_effect=self._create
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.application = ScoreboardApplication(
            self.paths,
            diagnostics=NullDiagnostics(),
            monotonic_clock=self.monotonic,
            acquire_lock=False,
        )
        self.addCleanup(self.application.shutdown)
        self.host = WindowHost(self.application, read_screens=lambda: [])
        self.bridge = self.application.start_new()
        self.bridge.set_cutscenes_opener(self.host.open_cutscenes)

    def _create(self, *args: Any, **kwargs: Any) -> _Window:
        window = _Window(*args, **kwargs)
        self.windows.append(window)
        return window

    def make_diagnostics(self) -> Diagnostics:
        diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(diagnostics.close)
        self.application.diagnostics = diagnostics
        return diagnostics

    def log_text(self) -> str:
        return self.paths.log_file.read_text(encoding="utf-8")


class CutscenesWindowLifecycleTests(CutscenesWindowTestCase):
    def test_open_is_deliberate_similarly_sized_and_reads_the_live_bridge(self) -> None:
        result = self.host.open_cutscenes()

        self.assertIn("opened", result["message"].lower())
        window = self.host.cutscenes_window
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.title, "Cutscenes")
        self.assertEqual(window.kwargs["url"], view_url("cutscenes"))
        self.assertEqual((window.kwargs["width"], window.kwargs["height"]), (520, 640))
        self.assertEqual(window.kwargs["min_size"], (420, 520))
        self.assertTrue(window.kwargs["on_top"])
        self.assertIsInstance(window.kwargs["js_api"], CutscenesBridge)

    def test_close_and_reopen_are_isolated_and_reopening_sees_a_live_bridge(self) -> None:
        self.host.open_cutscenes()
        first = self.host.cutscenes_window
        assert first is not None
        for handler in first.events.closed.handlers:
            handler(first)
        self.assertIsNone(self.host.cutscenes_window)

        self.host.open_cutscenes()
        second = self.host.cutscenes_window
        assert second is not None
        self.assertIsNot(second, first)
        self.assertIsInstance(second.kwargs["js_api"], CutscenesBridge)

    def test_reopen_replaces_and_destroys_the_previous(self) -> None:
        self.host.open_cutscenes()
        first = self.host.cutscenes_window
        assert first is not None

        self.host.open_cutscenes()

        self.assertTrue(first.destroyed)
        second = self.host.cutscenes_window
        assert second is not None
        self.assertIsNot(second, first)

    def test_deliver_cutscenes_pushes_apply_view(self) -> None:
        self.host.open_cutscenes()
        window = self.host.cutscenes_window
        assert window is not None

        self.host._deliver(  # noqa: SLF001 - the delivery boundary itself
            "cutscenes", {"teams": {}, "cutscenes": {"available": True, "playing": None}}
        )

        self.assertEqual(len(window.scripts), 1)
        self.assertIn("window.applyView", window.scripts[0])

    def test_a_failing_push_destroys_only_the_helper(self) -> None:
        self.host.open_cutscenes()
        helper = self.host.cutscenes_window
        assert helper is not None
        helper.fail_push = True

        self.bridge.command("game_clock_start", {}, 0)

        self.assertTrue(self.application.service.game_clock.value.running)
        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.cutscenes_window)
        self.assertTrue(self.bridge.get_snapshot()["health"]["persistence"]["saved"])

    def test_operator_shutdown_destroys_the_cutscenes_window(self) -> None:
        self.host.open_cutscenes()
        helper = self.host.cutscenes_window
        assert helper is not None
        self.host._operator_closing()

        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.cutscenes_window)

    def test_opening_before_a_game_exists_reports_plainly(self) -> None:
        bare_paths = resolve_paths(self.temporary_root / "bare")
        bare_paths.ensure()
        bare_application = ScoreboardApplication(
            bare_paths, diagnostics=NullDiagnostics(), monotonic_clock=self.monotonic, acquire_lock=False
        )
        self.addCleanup(bare_application.shutdown)
        bare_host = WindowHost(bare_application, read_screens=lambda: [])

        result = bare_host.open_cutscenes()

        self.assertIn("start", result["message"].lower())
        self.assertIsNone(bare_host.cutscenes_window)


class CutscenePublishTests(CutscenesWindowTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.spectator = _Window()
        self.test_window_fake = _Window()
        self.layout_window = _Window()
        self.host.spectator_window = self.spectator  # type: ignore[assignment]
        self.host.test_window = self.test_window_fake  # type: ignore[assignment]
        self.host.layout_window = self.layout_window  # type: ignore[assignment]

    def test_publish_cutscene_reaches_spectator_and_test_window_but_not_the_editor(self) -> None:
        program = {"play_id": 1, "event": "touchdown"}

        self.host.publish_cutscene(program)

        self.assertEqual(len(self.spectator.scripts), 1)
        self.assertIn("window.applyCutscene", self.spectator.scripts[0])
        self.assertEqual(len(self.test_window_fake.scripts), 1)
        self.assertIn("window.applyCutscene", self.test_window_fake.scripts[0])
        self.assertEqual(self.layout_window.scripts, [])

    def test_end_cutscene_reaches_spectator_and_test_window_but_not_the_editor(self) -> None:
        self.host.end_cutscene(7)

        self.assertEqual(len(self.spectator.scripts), 1)
        self.assertIn("window.endCutscene", self.spectator.scripts[0])
        self.assertIn("7", self.spectator.scripts[0])
        self.assertEqual(len(self.test_window_fake.scripts), 1)
        self.assertIn("window.endCutscene", self.test_window_fake.scripts[0])
        self.assertEqual(self.layout_window.scripts, [])

    def test_a_publish_failure_is_logged_and_the_spectator_is_not_destroyed(self) -> None:
        self.make_diagnostics()
        self.spectator.fail_push = True

        self.host.publish_cutscene({"play_id": 1, "event": "touchdown"})
        self.application.diagnostics.flush()

        log_text = self.log_text()
        self.assertIn("UNHANDLED_ERROR", log_text)
        self.assertIn("spectator_cutscene_push", log_text)
        self.assertFalse(self.spectator.destroyed)
        self.assertIs(self.host.spectator_window, self.spectator)
        # The practice window and the game itself are unaffected by a
        # spectator failure (a cutscene push failure is decoration only).
        self.assertEqual(len(self.test_window_fake.scripts), 1)

    def test_an_end_failure_is_logged_and_the_spectator_is_not_destroyed(self) -> None:
        self.make_diagnostics()
        self.spectator.fail_push = True

        self.host.end_cutscene(3)
        self.application.diagnostics.flush()

        log_text = self.log_text()
        self.assertIn("UNHANDLED_ERROR", log_text)
        self.assertIn("spectator_cutscene_end", log_text)
        self.assertFalse(self.spectator.destroyed)


class CutsceneLinkWiringTests(CutscenesWindowTestCase):
    def test_the_directors_link_is_wired_to_the_host_methods(self) -> None:
        # open_window: calling the link opens the real Cutscenes window.
        self.application.cutscenes.link.open_window()
        self.assertIsNotNone(self.host.cutscenes_window)

        # publish/end: calling the link reaches the spectator/test windows,
        # exactly as calling host.publish_cutscene/end_cutscene directly would.
        spectator = _Window()
        self.host.spectator_window = spectator  # type: ignore[assignment]

        self.application.cutscenes.link.publish({"play_id": 1, "event": "touchdown"})
        self.assertEqual(len(spectator.scripts), 1)
        self.assertIn("window.applyCutscene", spectator.scripts[0])

        self.application.cutscenes.link.end(1)
        self.assertEqual(len(spectator.scripts), 2)
        self.assertIn("window.endCutscene", spectator.scripts[1])

    def test_the_cutscenes_active_predicate_follows_the_window(self) -> None:
        self.assertFalse(self.application._cutscenes_active())  # noqa: SLF001

        self.host.open_cutscenes()

        self.assertTrue(self.application._cutscenes_active())  # noqa: SLF001


class SpectatorGetCutsceneTests(CutscenesWindowTestCase):
    def test_get_cutscene_on_the_spectator_bridge_returns_the_current_program(self) -> None:
        self.host.open_test_window()
        window = self.host.test_window
        assert window is not None
        spectator_bridge: SpectatorBridge = window.kwargs["js_api"]

        self.assertIsNone(spectator_bridge.get_cutscene())

        result = self.bridge.trigger_cutscene("touchdown")
        self.assertTrue(result["ok"], result)

        program = spectator_bridge.get_cutscene()
        self.assertIsNotNone(program)
        assert program is not None
        self.assertEqual(program["event"], "touchdown")
        self.assertIn("elapsed_ms", program)

        cancelled = self.bridge.cancel_cutscene()
        self.assertTrue(cancelled["ok"], cancelled)
        self.assertIsNone(spectator_bridge.get_cutscene())

    def test_a_bridge_with_no_reader_answers_none(self) -> None:
        bridge = SpectatorBridge(lambda: {})

        self.assertIsNone(bridge.get_cutscene())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
