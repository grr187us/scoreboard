"""Soccer's button-box table: mirrors ``host/hotkeys.py`` (spec section 4.5).

Soccer has one running match clock and no play clock, so only the two
game-clock rows of football's ``HOTKEY_TABLE`` apply -- F21 (rocker on,
``game_clock_start``) and F22 (rocker off, ``game_clock_stop``). F15-F20 are
not registered for a soccer session: nothing in this module touches
``host/hotkeys.py`` or ``HOTKEY_TABLE`` itself, and the firmware and its pin
map are unchanged.

The two rows are found by their command name rather than by table index, so a
reorder of football's ``HOTKEY_TABLE`` cannot silently change which button the
soccer table registers.
"""

from __future__ import annotations

from typing import Final

from scoreboard.host.hotkeys import HOTKEY_TABLE, HotkeyBinding

_GAME_CLOCK_COMMANDS: Final[tuple[str, str]] = ("game_clock_start", "game_clock_stop")


def _find(command: str) -> HotkeyBinding:
    for binding in HOTKEY_TABLE:
        if binding.command == command:
            return binding
    raise LookupError(f"HOTKEY_TABLE has no {command!r} row; soccer's table cannot be built.")


#: F21 start / F22 stop, taken from football's table by command name. Nothing
#: else is registered for a soccer session (spec 4.5).
SOCCER_HOTKEY_TABLE: Final[tuple[HotkeyBinding, ...]] = tuple(
    _find(command) for command in _GAME_CLOCK_COMMANDS
)

__all__ = ["SOCCER_HOTKEY_TABLE"]
