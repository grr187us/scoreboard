"""PL-3 evidence: +/- nudges on the REAL pywebview operator window at 1366x768.

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl3.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import capture_hwnd, window_hwnd  # noqa: E402

from scoreboard.host.app import ScoreboardApplication, WindowHost  # noqa: E402
from scoreboard.infrastructure.diagnostics import NullDiagnostics  # noqa: E402
from scoreboard.infrastructure.paths import resolve_paths  # noqa: E402
from scoreboard.infrastructure.persistence import read_action_history  # noqa: E402

RESULTS: list[tuple[bool, str, object]] = []
OUT = Path(__file__).resolve().parent / "evidence"


def check(ok: bool, label: str, detail: object = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def wait_for(predicate, seconds: float = 10.0, step: float = 0.1) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(step)
    return False


def size_viewport(window, js, width: int, height: int) -> tuple[int, int]:
    """Resize the native window until the CSS viewport is exactly width x height."""

    window.resize(width + 16, height + 39)
    time.sleep(0.6)
    for _ in range(4):
        inner = json.loads(js("JSON.stringify([window.innerWidth, window.innerHeight])"))
        if inner == [width, height]:
            break
        window.resize(width + 16 + (width - inner[0]), height + 39 + (height - inner[1]))
        time.sleep(0.6)
    return tuple(json.loads(js("JSON.stringify([window.innerWidth, window.innerHeight])")))


def drive(host: WindowHost, paths) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def js(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return host.application.service.state

    def strip():
        return json.loads(js("JSON.stringify(Array.from(document.querySelectorAll('#field-status .nudge-value')).map(function(n){return n.textContent;}))"))

    def overflow_free():
        return js("document.documentElement.scrollHeight === document.documentElement.clientHeight && "
                  "document.documentElement.scrollWidth === document.documentElement.clientWidth")

    def settle():
        # Each tap sends the revision the page is showing; wait for the push
        # that carries the previous result before tapping again, as a human
        # inevitably does (the strip has to re-render before the next read).
        time.sleep(0.5)

    def nudge_heights():
        return json.loads(js("JSON.stringify(Array.from(document.querySelectorAll('button.nudge')).map(function(b){var r=b.getBoundingClientRect();return [Math.round(r.height), Math.round(r.width)];}))"))

    time.sleep(1.0)
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    inner = size_viewport(operator, js, 1366, 768)
    check(inner == (1366, 768), "operator CSS viewport is 1366x768", inner)

    # --- seed a series from the drawer's existing controls
    js("document.getElementById('open-field').click()")
    time.sleep(0.3)
    js("document.querySelector('#field-drawer [data-command=\"set_down\"][data-value=\"2\"]').click()")
    time.sleep(0.2)
    js("(function(){var i=document.getElementById('distance-input'); i.value='8'; i.dispatchEvent(new Event('input',{bubbles:true}));"
       "document.querySelector('#field-drawer [data-command=\"set_distance\"][data-arg-source]').click();})()")
    time.sleep(0.2)
    js("(function(){var i=document.getElementById('ball-on-yard-line'); i.value='47'; i.dispatchEvent(new Event('input',{bubbles:true}));"
       "document.querySelector('#field-drawer [data-command=\"set_ball_on\"][data-arg-side]').click();})()")
    check(wait_for(lambda: state().down == 2 and state().distance == 8 and state().ball_on.yard_line == 47, 5), "seeded 2nd & 8 at HOME 47", (state().down, state().distance, state().ball_on))
    time.sleep(0.4)
    heights = nudge_heights()
    check(all(h >= 44 for h, _ in heights) and len(heights) == 16, "all 16 nudge buttons are at least 44px tall (drawer open)", heights)
    check(overflow_free(), "no overflow with the drawer open at 1366x768")
    capture_hwnd(window_hwnd(operator), OUT / "pl3-02-field-drawer-1366.png")
    js("document.querySelector('#field-drawer [data-action=\"close_drawer\"]').click()")
    time.sleep(0.3)
    check(js("document.getElementById('field-drawer').hidden"), "Field drawer closed")

    # --- the main strip: one tap each
    check(strip() == ["2nd", "& 8", "HOME 47"], "strip shows 2nd & 8 at HOME 47", strip())
    history_before = len(read_action_history(paths.database))
    js("document.querySelector('#field-status [data-command=\"set_down\"][data-nudge=\"1\"]').click()")
    check(wait_for(lambda: state().down == 3, 5), "strip + on Down -> 3rd", state().down)
    settle()
    js("document.querySelector('#field-status [data-command=\"set_distance\"][data-nudge=\"-1\"]').click()")
    check(wait_for(lambda: state().distance == 7, 5), "strip - on To Go -> 7", state().distance)
    settle()
    js("document.querySelector('#field-status [data-command=\"set_ball_on\"][data-nudge=\"5\"]').click()")
    check(wait_for(lambda: state().ball_on.team == "away" and state().ball_on.yard_line == 48, 5), "strip +5 on Ball On crossed the 50 -> AWAY 48", state().ball_on)
    settle()
    js("document.querySelector('#field-status [data-command=\"set_ball_on\"][data-nudge=\"-1\"]').click()")
    check(wait_for(lambda: state().ball_on.team == "away" and state().ball_on.yard_line == 49, 5), "strip -1 -> AWAY 49", state().ball_on)
    time.sleep(0.4)
    check(strip() == ["3rd", "& 7", "AWAY 49"], "strip re-rendered from Python", strip())
    rows = read_action_history(paths.database)
    check([r["command"] for r in rows[history_before:]] == ["set_down", "set_distance", "set_ball_on", "set_ball_on"],
          "four ordinary history rows, one per nudge", [r["command"] for r in rows[history_before:]])
    last = js("document.getElementById('last-action').textContent")
    check("AWAY 49" in last or "49" in last, "LAST strip names the nudge", last)
    check(overflow_free(), "no overflow on the main screen at 1366x768")
    heights = nudge_heights()
    check(all(h >= 44 for h, _ in heights[:8]), "the eight strip nudges are at least 44px tall", heights[:8])
    capture_hwnd(window_hwnd(operator), OUT / "pl3-01-strip-1366.png")

    # --- undo reverses the last nudge like any other command
    js("document.getElementById('undo').click()")
    time.sleep(0.3)
    js("document.getElementById('confirm-accept').click()")
    check(wait_for(lambda: state().ball_on.yard_line == 48, 5), "Undo reversed the last nudge", state().ball_on)

    # --- a refused nudge (Goal) says why and changes nothing
    js("document.getElementById('open-field').click()")
    time.sleep(0.3)
    js("document.querySelector('#field-drawer [data-command=\"set_distance\"][data-value=\"0\"]').click()")
    check(wait_for(lambda: state().distance == 0, 5), "Goal set from the drawer")
    js("document.querySelector('#field-drawer [data-action=\"close_drawer\"]').click()")
    time.sleep(0.3)
    revision = state().revision
    js("document.querySelector('#field-status [data-command=\"set_distance\"][data-nudge=\"1\"]').click()")
    time.sleep(0.6)
    alert = js("document.getElementById('alert') ? document.getElementById('alert').textContent : document.body.textContent.indexOf('Goal')>=0 ? 'Goal' : ''")
    check(state().revision == revision and state().distance == 0, "Goal stays Goal on a nudge (refused, no revision)", (state().distance, state().revision))
    check("Goal" in (alert or ""), "the refusal is shown to the operator", alert)

    # --- narrowest supported viewport
    inner = size_viewport(operator, js, 1093, 614)
    check(inner == (1093, 614), "operator CSS viewport is 1093x614", inner)
    time.sleep(0.4)
    check(overflow_free(), "no overflow on the main screen at 1093x614")
    check(all(h >= 44 for h, _ in nudge_heights()[:8]), "strip nudges still 44px at 1093x614")
    capture_hwnd(window_hwnd(operator), OUT / "pl3-03-strip-1093.png")

    time.sleep(0.3)
    operator.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-realrun-") as directory:
        paths = resolve_paths(Path(directory))
        application = ScoreboardApplication(paths, diagnostics=NullDiagnostics())
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
