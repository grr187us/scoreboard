"""PL-1 evidence: the global button-box hook in the REAL pywebview app.

Synthetic F15-F22 presses are injected with ``keybd_event`` (the same input
path a USB keyboard takes) while the Field Assistant, Cutscenes, the layout
editor, a practice board, and Notepad have focus, then with the operator
window focused for the double-fire check, a held key, and a stopped hook.
The physical box test is still owed (PL-8 owner action items).

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl1.py
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import capture_hwnd, window_hwnd  # noqa: E402

from scoreboard.host.app import ScoreboardApplication, WindowHost  # noqa: E402
from scoreboard.host.hotkeys import HOTKEY_TABLE  # noqa: E402
from scoreboard.infrastructure.paths import resolve_paths  # noqa: E402
from scoreboard.infrastructure.persistence import read_action_history  # noqa: E402

RESULTS: list[tuple[bool, str, object]] = []
OUT = Path(__file__).resolve().parent / "evidence"
user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002
VK = {b.key: b.vk for b in HOTKEY_TABLE}


def check(ok: bool, label: str, detail: object = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def wait_for(predicate, seconds: float = 5.0, step: float = 0.05) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(step)
    return False


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buffer, 256)
    return buffer.value


def focus(hwnd: int) -> str:
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    return foreground_title()


def press(key: str, hold: float = 0.0) -> None:
    user32.keybd_event(VK[key], 0, 0, 0)
    if hold:
        time.sleep(hold)
    user32.keybd_event(VK[key], 0, KEYEVENTF_KEYUP, 0)


def drive(host: WindowHost, paths) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)
    app = host.application

    def state():
        return app.service.state

    def rows():
        return read_action_history(paths.database)

    time.sleep(1.5)
    operator.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    hook = getattr(host, "_button_box", None)
    check(hook is not None, "the host started the hook after the operator window loaded")
    status = hook.status
    check(status.active and status.registered == tuple(b.key for b in HOTKEY_TABLE) and not status.failed,
          "all eight keys registered with Windows (MOD_NOREPEAT)", status)
    log = paths.log_file.read_text(encoding="utf-8", errors="replace")
    check("BUTTON_BOX_HOOK_STARTED" in log, "hook start is logged")
    check(operator.evaluate_js("document.getElementById('chip-button-box').hidden"), "no warning chip when every key registered")
    app.bridge.command("set_quarter", {"label": "1st", "confirmed": True}, None)
    time.sleep(0.3)

    # --- every box button and both rocker positions with another window focused
    def exercise(label: str, hwnd: int) -> None:
        focused = focus(hwnd)
        before = len(rows())
        press("F21"); check(wait_for(lambda: state().game_clock.running), f"[{label}] F21 rocker on -> game clock running (focus: {focused})")
        press("F22"); check(wait_for(lambda: not state().game_clock.running), f"[{label}] F22 rocker off -> stopped")
        press("F15"); check(wait_for(lambda: state().play_clock.running and 0 < state().play_clock.seconds <= 25), f"[{label}] F15 Quick 25 (25 loaded and running)", state().play_clock)
        press("F19"); check(wait_for(lambda: not state().play_clock.running and state().play_clock_cleared), f"[{label}] F19 clear", state().play_clock)
        press("F16"); check(wait_for(lambda: state().play_clock.running and 25 < state().play_clock.seconds <= 40), f"[{label}] F16 Quick 40 (40 loaded and running)", state().play_clock)
        press("F19"); wait_for(lambda: not state().play_clock.running)
        press("F17"); check(wait_for(lambda: not state().play_clock.running and state().play_clock.seconds == 40), f"[{label}] F17 load 40 stopped", state().play_clock)
        press("F20"); check(wait_for(lambda: state().play_clock.running), f"[{label}] F20 play clock start")
        press("F19"); wait_for(lambda: not state().play_clock.running)
        press("F18"); check(wait_for(lambda: not state().play_clock.running and state().play_clock.seconds == 25), f"[{label}] F18 load 25 stopped", state().play_clock)
        press("F19"); wait_for(lambda: state().play_clock_cleared)
        time.sleep(0.3)
        new_rows = rows()[before:]
        check(len(new_rows) == 11 and all(r["source"] == "button-box" for r in new_rows),
              f"[{label}] 11 presses -> 11 history rows, all source button-box", (len(new_rows), sorted({r["source"] for r in new_rows})))

    host.open_field_assistant()
    wait_for(lambda: host.field_assistant_window is not None and host.field_assistant_window.evaluate_js("!!document.getElementById('confirm')"), 20)
    time.sleep(0.5)
    exercise("Field Assistant focused", window_hwnd(host.field_assistant_window))
    capture_hwnd(window_hwnd(operator), OUT / "pl1-01-operator-after-presses-with-assistant-focused.png")

    host.open_cutscenes()
    wait_for(lambda: host.cutscenes_window is not None and host.cutscenes_window.evaluate_js("!!document.body"), 20)
    time.sleep(0.5)
    exercise("Cutscenes focused", window_hwnd(host.cutscenes_window))

    host.open_layout_editor()
    wait_for(lambda: host.layout_window is not None and host.layout_window.evaluate_js("!!document.body"), 20)
    time.sleep(1.0)
    exercise("Layout editor focused", window_hwnd(host.layout_window))

    notepad = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    hwnd = 0
    for _ in range(20):
        hwnd = user32.FindWindowW("Notepad", None) or user32.FindWindowW(None, "Untitled - Notepad")
        if hwnd:
            break
        time.sleep(0.2)
    if hwnd:
        exercise("Notepad focused", hwnd)
    else:
        check(False, "Notepad window found")
    notepad.kill()

    # --- double-fire check: operator window focused, one row per press
    focused = focus(window_hwnd(operator))
    check("Scoreboard control" in focused, "operator window focused for the double-fire check", focused)
    before = len(rows())
    sequence = ["F21", "F22", "F15", "F19", "F16", "F19", "F17", "F20", "F19", "F18", "F19"]
    for key in sequence:
        press(key)
        time.sleep(0.25)
    time.sleep(0.4)
    new_rows = rows()[before:]
    check(len(new_rows) == len(sequence), f"operator focused: {len(sequence)} presses -> exactly {len(sequence)} rows (no double fire)", [(r["command"], r["source"]) for r in new_rows])
    check(all(r["source"] == "button-box" for r in new_rows), "...all from the hook, none from the page listener (Windows swallowed them)", sorted({r["source"] for r in new_rows}))

    # --- a held rocker fires once
    before = len(rows())
    press("F21", hold=1.5)
    time.sleep(0.4)
    held_rows = rows()[before:]
    check(len(held_rows) == 1 and state().game_clock.running, "a 1.5 s held F21 is one command (MOD_NOREPEAT)", [(r["command"]) for r in held_rows])
    press("F22"); wait_for(lambda: not state().game_clock.running)
    time.sleep(0.4)

    # --- rapid double press: two rows, absolute start/stop never toggles
    before = len(rows())
    press("F21"); press("F21")
    time.sleep(0.4)
    check(state().game_clock.running and len(rows()[before:]) == 2, "two quick F21 presses: still running, two rows (redundant start ignored)", len(rows()[before:]))
    press("F22"); wait_for(lambda: not state().game_clock.running)

    # --- stop: the operator-closing path calls hook.stop() (pinned by
    # tests/integration/test_button_box_hook.py); here it is called the same
    # way before the windows go, so the checks can still read the store.
    for window in (host.field_assistant_window, host.cutscenes_window, host.layout_window):
        if window is not None:
            window.destroy()
    time.sleep(0.5)
    hook.stop()
    time.sleep(0.5)
    check(not hook.status.active and hook.status.error == "stopped", "hook stopped: keys unregistered", hook.status)
    # With the keys unregistered, Windows delivers F21 to the focused window
    # again: the operator page's own listener (the fallback) handles it.
    focused = focus(window_hwnd(operator))
    before_rows = len(rows())
    press("F21")
    time.sleep(0.6)
    fallback_rows = rows()[before_rows:]
    check(len(fallback_rows) == 1 and fallback_rows[0]["source"] == "operator-keyboard" and state().game_clock.running,
          f"after stop, the page listener takes over (fallback row, focus: {focused})", [(r["command"], r["source"]) for r in fallback_rows])
    log = paths.log_file.read_text(encoding="utf-8", errors="replace")
    check("BUTTON_BOX_HOOK_STOPPED" in log, "hook stop is logged")
    operator.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-realrun-") as directory:
        paths = resolve_paths(Path(directory))
        application = ScoreboardApplication(paths)
        host = WindowHost(application)
        threading.Timer(3.0, lambda: drive(host, application.paths)).start()
        host.run(startup_choice="new")

    failures = 0
    for ok, label, detail in RESULTS:
        line = ("PASS  " if ok else "FAIL  ") + label + (f"   [{detail}]" if detail != "" else "")
        print(line.encode("ascii", "backslashreplace").decode("ascii"))
        failures += 0 if ok else 1
    print(f"\n{len(RESULTS) - failures}/{len(RESULTS)} checks passed in the real pywebview runtime")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
