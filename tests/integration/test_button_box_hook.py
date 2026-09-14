"""PL-1: the global button-box hook is the single source of the box mapping.

Three contracts: the hook's dispatch table equals the F-key rows of the
operator page's ``keyboard.js`` (those rows stay as the focused-window
fallback for a key another program owns; Windows swallows a registered
hotkey, so they can never double fire); a ``button-box`` command goes through
the bridge airlock like any control and is recorded with that source; and the
host reports the hook's status on every operator view so a failed
registration is visible, never silent.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest import mock

from scoreboard.host.app import WindowHost
from scoreboard.host.bridge import BUTTON_BOX_SOURCE, build_command
from scoreboard.host.hotkeys import HOTKEY_TABLE, HookStatus
from scoreboard.infrastructure.persistence import read_action_history

from tests.integration.test_host_application import ApplicationTestCase

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


def _page_fkey_rows() -> list[tuple[str, str, dict]]:
    source = (VIEWS / "operator" / "keyboard.js").read_text(encoding="utf-8")
    rows = []
    for match in re.finditer(
        r"\{key: '(f\d\d)', label: '(F\d\d)', action: '([^']*)', command: '([a-z_]+)'(?:, args: \{seconds: (\d+)\})?\}",
        source,
    ):
        key, label, action, command, seconds = match.groups()
        rows.append((label, command, {"seconds": int(seconds)} if seconds else {}, action))
    return rows


class MappingContractTests(unittest.TestCase):
    def test_the_hook_table_equals_the_pages_fkey_rows(self) -> None:
        page = _page_fkey_rows()
        self.assertEqual(len(page), 8, page)
        self.assertEqual(
            [(b.key, b.command, b.args, b.action) for b in HOTKEY_TABLE],
            page,
        )

    def test_the_vk_codes_are_the_windows_function_keys(self) -> None:
        # VK_F15 is 0x7E; each later key is the next code.
        self.assertEqual([b.vk for b in HOTKEY_TABLE], list(range(0x7E, 0x86)))
        self.assertEqual([b.vk - 0x7E + 15 for b in HOTKEY_TABLE], [int(b.key[1:]) for b in HOTKEY_TABLE])


class ButtonBoxSourceTests(ApplicationTestCase):
    def test_a_button_box_command_passes_the_airlock_and_is_recorded_with_its_source(self) -> None:
        app = self.make_application()
        bridge = app.start_new()
        for binding in HOTKEY_TABLE:
            with self.subTest(key=binding.key):
                built = build_command(binding.command, {**binding.args, "source": BUTTON_BOX_SOURCE})
                self.assertFalse(hasattr(built, "code"), getattr(built, "message", None))
        bridge.command("set_quarter", {"label": "1st", "confirmed": True}, None)
        result = bridge.command("game_clock_start", {"source": BUTTON_BOX_SOURCE}, None)
        self.assertTrue(result["accepted"], result["error"])
        self.assertTrue(app.service.state.game_clock.running)
        rows = read_action_history(self.paths.database)
        self.assertEqual((rows[-1]["command"], rows[-1]["source"]), ("game_clock_start", "button-box"))
        # The rocker is absolute: a second "on" is a harmless no-op (the domain
        # ignores a redundant start), never a toggle, so the switch position
        # and the clock cannot diverge.
        again = bridge.command("game_clock_start", {"source": BUTTON_BOX_SOURCE}, None)
        self.assertTrue(again["accepted"], again["error"])
        self.assertTrue(app.service.state.game_clock.running)
        off = bridge.command("game_clock_stop", {"source": BUTTON_BOX_SOURCE}, None)
        self.assertTrue(off["accepted"], off["error"])
        self.assertFalse(app.service.state.game_clock.running)

    def test_the_hook_status_rides_on_every_operator_view(self) -> None:
        app = self.make_application()
        bridge = app.start_new()
        self.assertIsNone(bridge.get_snapshot()["button_box"])
        bridge.set_button_box_status(HookStatus(active=True, registered=("F15",), failed=("F16",)).as_dict())
        view = bridge.get_snapshot()["button_box"]
        self.assertEqual(view, {"active": True, "registered": ["F15"], "failed": ["F16"], "fallback": True, "error": None})
        pushed = bridge.command("add_score", {"team": "home", "points": 3}, None)["view"]["button_box"]
        self.assertEqual(pushed["failed"], ["F16"])


class HostWiringTests(ApplicationTestCase):
    """The host starts the hook after the operator window loads, wires its
    dispatch to the bridge with the button-box source, publishes its status,
    and stops it when the operator window closes."""

    def test_operator_loaded_starts_the_hook_and_closing_stops_it(self) -> None:
        app = self.make_application()
        app.start_new()
        host = WindowHost(app, read_screens=lambda: [])
        started: list = []

        class FakeHook:
            def __init__(self, dispatch, *, diagnostics=None, on_status=None):
                self.dispatch = dispatch
                self.on_status = on_status
                self.stopped = False
                started.append(self)

            def start(self, timeout=5.0):
                status = HookStatus(active=True, registered=tuple(b.key for b in HOTKEY_TABLE))
                self.on_status(status)
                return status

            def stop(self, timeout=2.0):
                self.stopped = True

        with mock.patch("scoreboard.host.app.ButtonBoxHook", FakeHook), \
                mock.patch.object(host, "open_spectator", lambda *a, **k: None), \
                mock.patch.object(host._publisher, "start", lambda: None), \
                mock.patch.object(app, "start_refresh", lambda: None):
            host._operator_loaded()
        self.assertEqual(len(started), 1)
        hook = started[0]
        self.assertEqual(app.bridge.get_snapshot()["button_box"]["registered"], [b.key for b in HOTKEY_TABLE])
        # The dispatch is the page's command with the button-box source.
        app.bridge.command("set_quarter", {"label": "1st", "confirmed": True}, None)
        hook.dispatch(HOTKEY_TABLE[6])  # F21: rocker on
        self.assertTrue(app.service.state.game_clock.running)
        rows = read_action_history(self.paths.database)
        self.assertEqual((rows[-1]["command"], rows[-1]["source"]), ("game_clock_start", "button-box"))
        with mock.patch.object(host._publisher, "stop", lambda: None), \
                mock.patch.object(app, "stop_refresh", lambda: None):
            host._operator_closing()
        self.assertTrue(hook.stopped)

    def test_the_cutscenes_window_is_no_longer_always_on_top(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "host" / "app.py").read_text(encoding="utf-8")
        cutscenes = source.split("def open_cutscenes", 1)[1].split("def _cutscenes_closed", 1)[0]
        self.assertNotIn("on_top=True", cutscenes)


if __name__ == "__main__":
    unittest.main()
