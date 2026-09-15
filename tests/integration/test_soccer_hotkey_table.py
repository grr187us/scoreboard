"""Soccer's button-box table: only F21 (start) and F22 (stop) (spec 4.5).

Mirrors ``tests/integration/test_button_box_hook.py``'s table-shape checks,
but for ``host/soccer_hotkeys.SOCCER_HOTKEY_TABLE``. ``host/hotkeys.py`` and
``HOTKEY_TABLE`` itself are never imported for edit here -- only read -- so a
regression in this file can never mean football's table changed.
"""

from __future__ import annotations

import unittest

from scoreboard.host.hotkeys import HOTKEY_TABLE
from scoreboard.host.soccer_hotkeys import SOCCER_HOTKEY_TABLE


class SoccerHotkeyTableTests(unittest.TestCase):
    def test_exactly_two_rows(self) -> None:
        self.assertEqual(len(SOCCER_HOTKEY_TABLE), 2)

    def test_rows_are_game_clock_start_and_stop(self) -> None:
        commands = [binding.command for binding in SOCCER_HOTKEY_TABLE]
        self.assertEqual(commands, ["game_clock_start", "game_clock_stop"])

    def test_keys_are_f21_and_f22(self) -> None:
        keys = [binding.key for binding in SOCCER_HOTKEY_TABLE]
        self.assertEqual(keys, ["F21", "F22"])

    def test_rows_are_the_same_objects_football_registers(self) -> None:
        """Found by command name, not index -- a reorder of HOTKEY_TABLE must
        not silently change which button the soccer table registers."""

        by_command = {binding.command: binding for binding in HOTKEY_TABLE}
        self.assertEqual(SOCCER_HOTKEY_TABLE[0], by_command["game_clock_start"])
        self.assertEqual(SOCCER_HOTKEY_TABLE[1], by_command["game_clock_stop"])

    def test_no_play_clock_or_rocker_arguments(self) -> None:
        for binding in SOCCER_HOTKEY_TABLE:
            self.assertEqual(binding.args, {})

    def test_football_table_is_untouched(self) -> None:
        """This module never edits hotkeys.py; the table it imports still has
        its original eight rows in their original order."""

        self.assertEqual(len(HOTKEY_TABLE), 8)
        self.assertEqual(HOTKEY_TABLE[6].command, "game_clock_start")
        self.assertEqual(HOTKEY_TABLE[7].command, "game_clock_stop")


if __name__ == "__main__":
    unittest.main()
