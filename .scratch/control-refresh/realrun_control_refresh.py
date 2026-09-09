"""Drive the REAL pywebview windows and prove the control refresh there.

Development evidence, not part of the suite. The browser suites run the same
HTML/CSS/JS in Chromium against a stub bridge; this runs it where it ships --
WebView2 windows created by pywebview with the real ``js_api`` attached --
which is the only place the pywebview call path itself is exercised.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe .scratch\\control-refresh\\realrun_control_refresh.py

It opens the real operator window (and, briefly, a fullscreen spectator window
on this machine's primary display to prove Esc closes it), runs the checks from
a worker thread (every ``evaluate_js`` blocks on the WebView2 UI thread, so
nothing here may run on it), prints PASS/FAIL lines, and closes itself.
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from scoreboard.host.app import CLOSED_BY_OPERATOR_DETAIL, ScoreboardApplication, WindowHost
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths

RESULTS: list[tuple[bool, str, object]] = []


def check(ok: bool, label: str, detail: object = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def wait_for(predicate, seconds: float = 10.0, step: float = 0.2) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001 - a window that is still starting
            pass
        time.sleep(step)
    return False


def drive(host: WindowHost) -> None:
    window = host.operator_window
    wait_for(lambda: window.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def js(expression: str):
        return window.evaluate_js(expression)

    def snap() -> dict:
        return host.application.bridge.get_snapshot()

    # --- 1. Fresh game: the Teams prompt opened by itself; the board says so
    time.sleep(1.0)
    check(js("!document.getElementById('teams-drawer').hidden"),
          "Teams drawer opened by itself on a fresh game")
    check(js("document.getElementById('teams-prompt').textContent") ==
          "Choose the HOME and AWAY teams before kickoff.",
          "the prompt carries Python's sentence", js("document.getElementById('teams-prompt').textContent"))
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)
    check(js("document.getElementById('teams-drawer').hidden"), "Escape dismisses it (soft prompt)")
    check(js("!document.getElementById('home-pending').hidden && "
             "document.getElementById('home-pending').textContent.trim() === 'NOT CHOSEN'"),
          "HOME panel shows NOT CHOSEN")
    check(js("document.getElementById('open-teams').classList.contains('is-attention')"),
          "Teams button draws attention while pending")
    check(js("document.documentElement.scrollHeight === document.documentElement.clientHeight && "
             "document.documentElement.scrollWidth === document.documentElement.clientWidth"),
          "no overflow in the real window (U-001)",
          js("document.documentElement.scrollHeight + 'x' + document.documentElement.scrollWidth + ' vs ' + "
             "document.documentElement.clientHeight + 'x' + document.documentElement.clientWidth"))

    # --- 2. No exposed score buttons; the tool bar carries no command
    check(js("Array.from(document.querySelectorAll('[data-command=\"add_score\"]'))"
             ".filter(b => !b.closest('#corrections')).every(b => b.hidden || b.closest('[hidden]'))"),
          "every board add_score control is hidden while nothing is armed")
    check(js("document.querySelectorAll('.tools [data-command]').length") == 0,
          "the tool bar holds no data-command")

    # --- 3. Two-step scoring through the real bridge
    before = snap()["revision"]
    js("document.getElementById('home-arm').click()")
    time.sleep(0.3)
    check(snap()["revision"] == before, "arming sends nothing")
    check(js("document.querySelector('.team.is-armed') !== null"), "HOME panel shows it is armed")
    check(js("!document.querySelector('[data-command=\"add_score\"][data-team=\"home\"][data-points=\"6\"]:not(#corrections *)').closest('[hidden]')"),
          "the +6 button is reachable while armed")
    js("document.querySelector('.team [data-command=\"add_score\"][data-team=\"home\"][data-points=\"6\"]').click()")
    time.sleep(1.0)
    after = snap()
    check(after["teams"]["home"]["score"] == 6 and after["revision"] == before + 1,
          "+6 applied in one revision", after["teams"]["home"]["score"])
    check(js("document.querySelector('.team.is-armed') === null"), "and the panel disarmed itself")

    # --- 4. Auto-disarm
    js("document.getElementById('away-arm').click()")
    time.sleep(0.3)
    check(js("document.querySelector('.team.is-armed') !== null"), "AWAY armed")
    time.sleep(8.8)
    check(js("document.querySelector('.team.is-armed') === null"), "AWAY disarmed by itself after 8 s")
    check(snap()["teams"]["away"]["score"] == 0, "and no score moved")

    # --- 5. Undo confirms and names what it reverses
    rev = snap()["revision"]
    js("document.getElementById('undo').click()")
    time.sleep(0.4)
    check(js("!document.getElementById('confirm-dialog').hidden"), "Undo opens a dialog")
    change = js("document.getElementById('confirm-change').textContent") or ""
    check(change.startswith("Reverses: ") and "HOME" in change, "the dialog says what it reverses", change)
    check(snap()["revision"] == rev, "nothing changed yet")
    js("document.getElementById('confirm-cancel').click()")
    time.sleep(0.3)
    check(snap()["teams"]["home"]["score"] == 6, "Cancel changed nothing")
    js("document.getElementById('undo').click()")
    time.sleep(0.3)
    js("document.getElementById('confirm-accept').click()")
    time.sleep(1.0)
    check(snap()["teams"]["home"]["score"] == 0, "Confirm undid the +6")

    # --- 6. Quick timeout: charge only
    st = snap()
    js("document.getElementById('home-timeout').click()")
    time.sleep(1.0)
    st2 = snap()
    check(st2["football"]["timeouts"]["home"] == 2, "HOME TIMEOUT charged one timeout",
          st2["football"]["timeouts"]["home"])
    check(st2["status"]["label"] == st["status"]["label"] and not st2["status"]["active"],
          "and raised no crowd message")
    check(st2["clocks"]["game"]["running"] == st["clocks"]["game"]["running"], "and touched no clock")
    check(js("document.getElementById('home-timeout').textContent").strip().endswith("2") or
          "2" in js("document.getElementById('home-timeout').textContent"),
          "the button shows the new count", js("document.getElementById('home-timeout').textContent"))

    # --- 7. Game drawer: the three dangerous commands live there
    js("document.getElementById('open-game').click()")
    time.sleep(0.3)
    check(js("!document.getElementById('game-drawer').hidden"), "Game drawer opens")
    check(sorted(js("Array.from(document.querySelectorAll('#game-drawer [data-command]')).map(b=>b.dataset.command)")) ==
          ["end_game", "game_clock_reset", "new_game"], "it holds exactly the three dangerous commands")
    rev = snap()["revision"]
    js("document.querySelector('#game-drawer [data-command=\"new_game\"]').click()")
    time.sleep(0.8)
    check(js("!document.getElementById('confirm-dialog').hidden"), "New Game asks first")
    check(snap()["revision"] == rev, "and changed nothing")
    js("document.getElementById('confirm-accept').click()")
    time.sleep(1.0)
    fresh = snap()
    check(fresh["football"]["timeouts"]["home"] == 3 and fresh["revision"] > rev, "New Game replaced the board")
    check(js("!document.getElementById('teams-drawer').hidden"), "and the Teams drawer opened by itself again")
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # --- 8. Kickoff confirmation names the unchosen teams
    js("document.querySelector('[data-command=\"quarter_forward\"]').click()")
    time.sleep(0.8)
    detail = js("document.getElementById('confirm-detail').textContent") or ""
    check(detail.startswith("Choose the HOME and AWAY teams before kickoff."),
          "kickoff confirmation names the unchosen teams", detail[:80])
    js("document.getElementById('confirm-cancel').click()")
    time.sleep(0.3)

    # --- 9. Corrections still has the plus and minus buttons
    check(js("document.querySelectorAll('#corrections [data-command=\"add_score\"]').length") == 8 and
          js("document.querySelectorAll('#corrections [data-command=\"correct_score\"]').length") == 8,
          "Corrections offers +N and -N for both teams")

    # --- 10. Closing the spectator window from the window itself
    displays = host.available_displays()
    if displays:
        host.select_display(displays[0].key)
        spectator = host.spectator_window
        ok = wait_for(lambda: spectator.evaluate_js("!!document.getElementById('close-display')"), 20)
        check(ok, "spectator window opened on a real display with the close control present")
        health = snap()["health"]["display"]
        check(health["open"], "health strip says DISPLAY OPEN", health["label"])
        check(js("!document.getElementById('close-display').hidden"),
              "operator Display drawer offers Close Display while open")
        spectator.evaluate_js("document.dispatchEvent(new MouseEvent('mousemove',{bubbles:true}))")
        time.sleep(0.3)
        check(spectator.evaluate_js("!document.getElementById('close-display').hidden"),
              "pointer movement reveals the close button on the wall")
        spectator.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
        closed = wait_for(lambda: host.spectator_window is None, 10)
        check(closed, "Esc on the spectator window closed it")
        time.sleep(0.8)
        health = snap()["health"]["display"]
        check(not health["open"] and health["can_reopen"] and not health["needs_selection"],
              "health strip: DISPLAY CLOSED, one-click reopen", health)
        check(health["detail"] == CLOSED_BY_OPERATOR_DETAIL, "with the pinned detail", health["detail"])
        check(snap()["revision"] == fresh["revision"], "closing moved no revision")
        # Reopen from the strip, then close from the operator's Display drawer.
        js("document.getElementById('reopen-display').click()")
        reopened = wait_for(lambda: host.spectator_window is not None, 10)
        check(reopened, "Reopen Display put it back")
        time.sleep(1.5)
        js("document.getElementById('open-display').click()")
        time.sleep(0.5)
        js("document.getElementById('close-display').click()")
        closed2 = wait_for(lambda: host.spectator_window is None, 10)
        check(closed2, "Close Display in the operator drawer closed it")
        time.sleep(0.5)
        check(not snap()["health"]["display"]["open"], "and the strip agrees")
    else:
        check(False, "no display reported; spectator close not exercised")

    # --- 11. Practice window closes with Esc too
    host.open_test_window()
    test_window = host.test_window
    wait_for(lambda: test_window.evaluate_js("!!document.getElementById('close-display')"), 20)
    test_window.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    check(wait_for(lambda: host.test_window is None, 10), "Esc closes the practice window")

    time.sleep(0.5)
    window.destroy()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="scoreboard-realrun-") as directory:
        application = ScoreboardApplication(resolve_paths(Path(directory)),
                                            diagnostics=NullDiagnostics())
        host = WindowHost(application)
        threading.Timer(3.0, lambda: drive(host)).start()
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
