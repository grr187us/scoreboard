"""Global button-box hook: Win32 ``RegisterHotKey`` for F15-F22 (PL-1).

The Pro Micro button box is a plain USB keyboard, so Windows delivers its
keystrokes to whichever window has focus. Until September 14, 2026 the only
listener was the operator page's ``document`` keydown handler
(``views/operator/keyboard.js``), which meant the rocker and the play-clock
buttons went dead whenever Cutscenes, the Field Assistant, the layout editor,
or any other program was in front. This module registers the eight keys with
the operating system instead: a daemon thread calls ``RegisterHotKey`` for
each (``MOD_NOREPEAT``, so a held button fires once), runs a ``GetMessage``
loop, and on ``WM_HOTKEY`` dispatches the same command the page would have
sent, tagged ``source: "button-box"``. Windows swallows a registered hotkey,
so the page never sees it and nothing can fire twice; a key that could not be
registered (another program owns it) is reported and keeps working through
the page listener while the operator window is focused.

Only ``ctypes`` is used (the stadium laptop is offline; no new dependency).
Everything Win32 goes through an injectable ``user32`` so the dispatch table
and the loop are unit-tested against a fake without registering anything.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any, Callable, Final

#: The source tag on every command the hook submits (recorded in history).
BUTTON_BOX_SOURCE: Final[str] = "button-box"

WM_HOTKEY: Final[int] = 0x0312
WM_QUIT: Final[int] = 0x0012
#: RegisterHotKey modifier: a held key fires WM_HOTKEY once, not repeatedly.
MOD_NOREPEAT: Final[int] = 0x4000
#: Hotkey ids are per-thread; keep them well clear of anything else.
HOTKEY_ID_BASE: Final[int] = 0x5B00


@dataclass(frozen=True, slots=True)
class HotkeyBinding:
    """One box button: the key it types, its VK code, and the command it means."""

    key: str
    vk: int
    command: str
    args: dict[str, Any] = field(default_factory=dict)
    action: str = ""


#: The box mapping (hardware/scoreboard_button_box, September 10, 2026 pin
#: map). This must equal the F-key rows of ``views/operator/keyboard.js``;
#: ``tests/integration/test_button_box_hook.py`` holds that contract.
HOTKEY_TABLE: Final[tuple[HotkeyBinding, ...]] = (
    HotkeyBinding("F15", 0x7E, "play_clock_preset_start", {"seconds": 25}, "Load play clock 25 and start (Quick 25)"),
    HotkeyBinding("F16", 0x7F, "play_clock_preset_start", {"seconds": 40}, "Load play clock 40 and start (Quick 40)"),
    HotkeyBinding("F17", 0x80, "play_clock_preset", {"seconds": 40}, "Load play clock 40 (stopped)"),
    HotkeyBinding("F18", 0x81, "play_clock_preset", {"seconds": 25}, "Load play clock 25 (stopped)"),
    HotkeyBinding("F19", 0x82, "play_clock_clear", {}, "Clear play clock"),
    HotkeyBinding("F20", 0x83, "play_clock_start", {}, "Start play clock"),
    HotkeyBinding("F21", 0x84, "game_clock_start", {}, "Start game clock (rocker on)"),
    HotkeyBinding("F22", 0x85, "game_clock_stop", {}, "Stop game clock (rocker off)"),
)


def hotkey_id(index: int) -> int:
    """The per-thread hotkey id registered for table row ``index``."""

    return HOTKEY_ID_BASE + index


def command_for(vk: int, table: tuple[HotkeyBinding, ...] = HOTKEY_TABLE) -> HotkeyBinding | None:
    """The binding a virtual-key code means, or ``None`` when it is not a box key."""

    for binding in table:
        if binding.vk == vk:
            return binding
    return None


@dataclass(frozen=True, slots=True)
class HookStatus:
    """What the hook managed to register; shown on the operator health strip."""

    #: The message loop is running and at least one key is registered.
    active: bool
    registered: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    #: Why nothing is registered at all (not Windows, hook never started, ...).
    error: str | None = None

    @property
    def fallback(self) -> bool:
        """True when at least one key still relies on the focused-window page listener."""

        return bool(self.failed) or not self.active

    def as_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "registered": list(self.registered),
            "failed": list(self.failed),
            "fallback": self.fallback,
            "error": self.error,
        }


class ButtonBoxHook:
    """Own the registration thread; dispatch each ``WM_HOTKEY`` as one command.

    ``dispatch(binding)`` is the only game-facing call and runs on the hook
    thread; the host wires it to the operator bridge's ``command`` (which has
    its own lock), never to the service directly. Every failure is reported
    through ``diagnostics`` and ``on_status``; nothing here raises into the
    message loop.
    """

    def __init__(
        self,
        dispatch: Callable[[HotkeyBinding], Any],
        *,
        user32: Any = None,
        current_thread_id: Callable[[], int] | None = None,
        diagnostics: Any = None,
        on_status: Callable[[HookStatus], None] | None = None,
        table: tuple[HotkeyBinding, ...] = HOTKEY_TABLE,
    ) -> None:
        self._dispatch = dispatch
        self._user32 = user32
        self._current_thread_id = current_thread_id
        self._diagnostics = diagnostics
        self._on_status = on_status
        self._table = table
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._status = HookStatus(active=False, error="not started")
        self._lock = threading.Lock()

    # --- lifecycle -----------------------------------------------------------

    @property
    def status(self) -> HookStatus:
        with self._lock:
            return self._status

    def start(self, timeout: float = 5.0) -> HookStatus:
        """Register the keys on a daemon thread and return what happened.

        Blocks (bounded) until registration has been attempted, so the caller
        can log and show the outcome at once. Safe to call once; a second call
        returns the current status.
        """

        if self._thread is not None:
            return self.status
        if self._user32 is None:
            if sys.platform != "win32":
                self._set_status(HookStatus(active=False, error="not Windows: no global hook"))
                return self.status
            self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        if self._current_thread_id is None:
            self._current_thread_id = (
                ctypes.windll.kernel32.GetCurrentThreadId  # type: ignore[attr-defined]
                if sys.platform == "win32" else threading.get_ident
            )
        self._thread = threading.Thread(target=self._run, name="button-box-hook", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.status

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the loop to quit (it unregisters on the way out) and wait for it."""

        thread, thread_id = self._thread, self._thread_id
        if thread is None or not thread.is_alive():
            return
        if thread_id is not None and self._user32 is not None:
            try:
                self._user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception as exc:  # noqa: BLE001 - reported, never raised at shutdown
                self._report_error("button_box_stop", exc)
        thread.join(timeout)

    # --- the hook thread -------------------------------------------------------

    def _run(self) -> None:
        user32 = self._user32
        registered: list[str] = []
        failed: list[str] = []
        ids: dict[int, HotkeyBinding] = {}
        try:
            self._thread_id = int(self._current_thread_id()) if self._current_thread_id else None
            for index, binding in enumerate(self._table):
                identifier = hotkey_id(index)
                ok = user32.RegisterHotKey(None, identifier, MOD_NOREPEAT, binding.vk)
                if ok:
                    registered.append(binding.key)
                    ids[identifier] = binding
                else:
                    failed.append(binding.key)
            status = HookStatus(
                active=bool(registered),
                registered=tuple(registered),
                failed=tuple(failed),
                error=None if registered else "no key could be registered",
            )
            self._set_status(status)
            self._note("BUTTON_BOX_HOOK_STARTED", registered=registered, failed=failed)
        except Exception as exc:  # noqa: BLE001 - a broken hook must not take the app down
            self._set_status(HookStatus(active=False, error=f"hook failed to start: {exc}"))
            self._report_error("button_box_start", exc)
            self._ready.set()
            return
        finally:
            self._ready.set()

        message = wintypes.MSG()
        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == 0 or result == -1:
                    break
                if int(message.message) == WM_HOTKEY:
                    binding = ids.get(int(message.wParam))
                    if binding is None:
                        continue
                    try:
                        self._dispatch(binding)
                    except Exception as exc:  # noqa: BLE001 - one bad press never stops the loop
                        self._report_error("button_box_dispatch", exc, key=binding.key)
        finally:
            for identifier in ids:
                try:
                    user32.UnregisterHotKey(None, identifier)
                except Exception as exc:  # noqa: BLE001
                    self._report_error("button_box_unregister", exc)
            self._set_status(HookStatus(active=False, registered=(), failed=tuple(failed), error="stopped"))
            self._note("BUTTON_BOX_HOOK_STOPPED", registered=registered)

    # --- reporting ---------------------------------------------------------------

    def _set_status(self, status: HookStatus) -> None:
        with self._lock:
            self._status = status
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception as exc:  # noqa: BLE001
                self._report_error("button_box_status", exc)

    def _note(self, event: str, **fields: Any) -> None:
        if self._diagnostics is not None and hasattr(self._diagnostics, "note"):
            try:
                self._diagnostics.note(event, **fields)
            except Exception:  # noqa: BLE001 - logging must never matter here
                pass

    def _report_error(self, context: str, error: BaseException, **fields: Any) -> None:
        if self._diagnostics is not None and hasattr(self._diagnostics, "unhandled_error"):
            try:
                self._diagnostics.unhandled_error(context=context, error=error, **fields)
            except Exception:  # noqa: BLE001
                pass


__all__ = [
    "BUTTON_BOX_SOURCE",
    "HOTKEY_TABLE",
    "MOD_NOREPEAT",
    "WM_HOTKEY",
    "WM_QUIT",
    "ButtonBoxHook",
    "HookStatus",
    "HotkeyBinding",
    "command_for",
    "hotkey_id",
]
