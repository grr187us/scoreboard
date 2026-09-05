"""Field Assistant host lifecycle contract (FA-25 through FA-27).

These use pywebview-shaped fakes: no native window is claimed as evidence.
They prove the host containment policy -- an optional helper can disappear or
fail without reaching clocks, persistence, the primary operator, or spectator.
"""

from __future__ import annotations

from typing import Any
from unittest import mock

from scoreboard.host.app import ScoreboardApplication, WindowHost, view_url
from scoreboard.host.bridge import FieldAssistantBridge
from scoreboard.infrastructure.diagnostics import NullDiagnostics

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
    def __init__(self, **kwargs: Any) -> None:
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


class FieldAssistantWindowTests(TemporaryDataDirectoryTest):
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
        self.bridge.set_field_assistant_opener(self.host.open_field_assistant)

    def _create(self, *args: Any, **kwargs: Any) -> _Window:
        window = _Window(**kwargs)
        self.windows.append(window)
        return window

    def test_open_is_deliberate_similarly_sized_and_reads_the_live_bridge(self) -> None:
        revision = self.bridge.get_snapshot()["revision"]
        result = self.host.open_field_assistant()

        self.assertIn("opened", result["message"].lower())
        window = self.host.field_assistant_window
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kwargs["url"], view_url("field_assistant"))
        self.assertEqual((window.kwargs["width"], window.kwargs["height"]), (1180, 720))
        self.assertEqual(window.kwargs["min_size"], (1024, 600))
        self.assertIsInstance(window.kwargs["js_api"], FieldAssistantBridge)
        self.assertEqual(window.kwargs["js_api"].get_snapshot()["revision"], revision)

    def test_close_and_reopen_are_isolated_and_reopening_sees_latest_snapshot(self) -> None:
        self.host.open_field_assistant()
        first = self.host.field_assistant_window
        assert first is not None
        self.bridge.command("add_score", {"team": "home", "points": 6}, 0)
        for handler in first.events.closed.handlers:
            handler(first)
        self.assertIsNone(self.host.field_assistant_window)

        self.host.open_field_assistant()
        second = self.host.field_assistant_window
        assert second is not None
        self.assertEqual(second.kwargs["js_api"].get_snapshot()["teams"]["home"]["score"], 6)
        self.assertFalse(self.application.service is None)

    def test_helper_push_failure_destroys_only_the_helper(self) -> None:
        self.host.open_field_assistant()
        helper = self.host.field_assistant_window
        assert helper is not None
        helper.fail_push = True
        self.bridge.command("game_clock_start", {}, 0)

        self.assertTrue(self.application.service.game_clock.value.running)
        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.field_assistant_window)
        self.assertTrue(self.bridge.get_snapshot()["health"]["persistence"]["saved"])

    def test_operator_shutdown_destroys_the_helper(self) -> None:
        self.host.open_field_assistant()
        helper = self.host.field_assistant_window
        assert helper is not None
        self.host._operator_closing()

        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.field_assistant_window)

