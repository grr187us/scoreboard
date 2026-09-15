"""Soccer Field Assistant window-opening contract.

Mirrors ``tests/integration/test_field_assistant_window.py``: an optional
helper window is opened at 1180x720 (min 1024x600, per
``.scratch/soccer-mode/spec.md`` section 6, matching football's own Field
Assistant size) with ``SoccerFieldAssistantBridge`` as its ``js_api``, reads
the live bridge, and a helper failure/close never disturbs the game.

**Note for the integrator / agent B**: at the time this file was written,
``src/scoreboard/host/soccer_app.py`` (``SoccerApplication``) and
``src/scoreboard/host/soccer_bridge.py`` (``SoccerBridge``) did not exist yet
(IMPLEMENTERS.md assigns both to agent B), so there is no
``WindowHost``-equivalent ``open_field_assistant`` to drive the way
``test_field_assistant_window.py`` drives ``host.app.WindowHost``. This file
instead proves the same contract one layer down, against a pywebview-shaped
fake and ``SoccerFieldAssistantBridge`` directly: the window is created with
the right URL/size/js_api, closing/replacing it does not touch game state,
and a push failure only destroys the helper window. When
``host/soccer_app.py`` lands with its own
``open_soccer_field_assistant``/``field_assistant_window`` pair (mirroring
``WindowHost.open_field_assistant``/``field_assistant_window`` in
``host/app.py``), a follow-up test should drive that method directly instead
of the local ``_open_soccer_field_assistant`` helper below -- the assertions
themselves (URL, size, js_api type, snapshot revision, isolation) should not
need to change.
"""

from __future__ import annotations

import unittest
from typing import Any

from scoreboard.host.soccer_field_assistant import SoccerFieldAssistantBridge

from tests.integration.test_soccer_field_assistant import FakeSoccerOperator

# Per spec section 6's wireframe header ("1180x720, min 1024x600") -- the
# same size football's Field Assistant window uses (host/app.py
# ``open_field_assistant``). Whichever module ends up creating the real
# soccer window should use these same numbers.
SOCCER_FIELD_ASSISTANT_URL = "soccer_field_assistant"
SOCCER_FIELD_ASSISTANT_SIZE = (1180, 720)
SOCCER_FIELD_ASSISTANT_MIN_SIZE = (1024, 600)


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


class _FakeWebviewModule:
    """A minimal stand-in for ``webview.create_window``."""

    def __init__(self) -> None:
        self.windows: list[_Window] = []

    def create_window(self, title: str, **kwargs: Any) -> _Window:
        window = _Window(title=title, **kwargs)
        self.windows.append(window)
        return window


class _SoccerFieldAssistantHost:
    """A tiny stand-in for the eventual ``host/soccer_app.py`` opener.

    Mirrors ``WindowHost.open_field_assistant``/``_field_assistant_closed``
    (``host/app.py``) exactly, but against the fake webview module above
    instead of the real ``webview`` package, and against
    ``SoccerFieldAssistantBridge`` instead of football's
    ``FieldAssistantBridge``.
    """

    def __init__(self, webview_module: _FakeWebviewModule, operator: FakeSoccerOperator) -> None:
        self._webview = webview_module
        self._operator = operator
        self.field_assistant_window: _Window | None = None

    def open_field_assistant(self) -> dict[str, str]:
        previous, self.field_assistant_window = self.field_assistant_window, None
        if previous is not None:
            previous.destroy()
        window = self._webview.create_window(
            "Field Assistant",
            url=SOCCER_FIELD_ASSISTANT_URL,
            js_api=SoccerFieldAssistantBridge(self._operator),
            width=SOCCER_FIELD_ASSISTANT_SIZE[0],
            height=SOCCER_FIELD_ASSISTANT_SIZE[1],
            min_size=SOCCER_FIELD_ASSISTANT_MIN_SIZE,
        )
        window.events.closed += self._closed
        self.field_assistant_window = window
        return {"message": "Field Assistant opened with the latest field status."}

    def _closed(self, window: _Window) -> None:
        if self.field_assistant_window is window:
            self.field_assistant_window = None

    def push(self, view: dict[str, Any]) -> None:
        window = self.field_assistant_window
        if window is None or not window.events.loaded.is_set():
            return
        try:
            window.evaluate_js(f"window.applyView && window.applyView({view!r})")
        except Exception:  # noqa: BLE001 - mirrors host/app.py's containment
            if self.field_assistant_window is window:
                self.field_assistant_window = None
            window.destroy()


class SoccerFieldAssistantWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.webview = _FakeWebviewModule()
        self.operator = FakeSoccerOperator()
        self.host = _SoccerFieldAssistantHost(self.webview, self.operator)

    def test_open_is_sized_like_footballs_helper_and_reads_the_live_bridge(self) -> None:
        revision = self.operator.get_snapshot()["revision"]
        result = self.host.open_field_assistant()

        self.assertIn("opened", result["message"].lower())
        window = self.host.field_assistant_window
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kwargs["url"], SOCCER_FIELD_ASSISTANT_URL)
        self.assertEqual((window.kwargs["width"], window.kwargs["height"]), SOCCER_FIELD_ASSISTANT_SIZE)
        self.assertEqual(window.kwargs["min_size"], SOCCER_FIELD_ASSISTANT_MIN_SIZE)
        self.assertIsInstance(window.kwargs["js_api"], SoccerFieldAssistantBridge)
        self.assertEqual(window.kwargs["js_api"].get_snapshot()["revision"], revision)

    def test_close_and_reopen_are_isolated_and_reopening_sees_latest_state(self) -> None:
        self.host.open_field_assistant()
        first = self.host.field_assistant_window
        assert first is not None
        self.operator.command("add_stat", {"team": "home", "stat": "shots", "step": 1}, 0, source="operator")
        for handler in first.events.closed.handlers:
            handler(first)
        self.assertIsNone(self.host.field_assistant_window)

        self.host.open_field_assistant()
        second = self.host.field_assistant_window
        assert second is not None
        self.assertEqual(second.kwargs["js_api"].get_snapshot()["soccer"]["home"]["shots"], 5)

    def test_a_push_failure_destroys_only_the_helper(self) -> None:
        self.host.open_field_assistant()
        helper = self.host.field_assistant_window
        assert helper is not None
        helper.fail_push = True

        self.host.push(self.operator.get_snapshot())

        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.field_assistant_window)
        # The game itself is untouched: the operator can still take commands.
        result = self.operator.command("add_stat", {"team": "away", "stat": "fouls", "step": 1}, self.operator.revision, source="operator")
        self.assertTrue(result["accepted"])


if __name__ == "__main__":
    unittest.main()
