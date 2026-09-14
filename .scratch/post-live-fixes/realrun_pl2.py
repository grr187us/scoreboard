"""PL-2 evidence: drive the REAL pywebview operator + Field Assistant windows.

Development evidence, not part of the suite (September 14, 2026). Mirrors
``.scratch/halftime-setup/realrun_halftime_setup.py``: checks run from a
worker thread because every ``evaluate_js`` blocks on the WebView2 UI thread.

Run from the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl2.py
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
        except Exception:  # noqa: BLE001 - a window that is still starting
            pass
        time.sleep(step)
    return False


def drive(host: WindowHost) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def op(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return host.application.service.state

    time.sleep(1.0)
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # ---- open the assistant from the operator page's own button
    op("document.getElementById('open-field-assistant').click()")
    wait_for(lambda: host.field_assistant_window is not None, 10)
    helper = host.field_assistant_window
    wait_for(lambda: helper.evaluate_js("!!document.getElementById('confirm') && !!window.pywebview"), 30)
    time.sleep(1.0)

    def fa(expression: str):
        return helper.evaluate_js(expression)

    def fa_json(expression: str):
        return json.loads(fa("JSON.stringify(" + expression + ")"))

    def fa_state():
        return fa_json("({rev:document.getElementById('revision').textContent,"
                       "down:document.getElementById('current-down').textContent,"
                       "spot:document.getElementById('current-spot').textContent,"
                       "ball:document.getElementById('ball').dataset.absolute,"
                       "confirmDisabled:document.getElementById('confirm').disabled,"
                       "confirmLabel:document.getElementById('confirm').textContent,"
                       "conflictHidden:document.getElementById('conflict').hidden,"
                       "notice:document.getElementById('notice').textContent,"
                       "panel:Array.from(document.querySelectorAll('[data-panel]')).filter(function(p){return !p.hidden;}).map(function(p){return p.getAttribute('data-panel');}),"
                       "resyncLabel:document.getElementById('resync').textContent})")

    check(fa("document.getElementById('stale') === null"), "no stale banner element in the real window")
    check(fa_state()["resyncLabel"] == "Discard draft & reload", "Reload button relabelled", fa_state()["resyncLabel"])

    # ---- 1. direction + opening series from the assistant
    fa("document.querySelector('[data-direction=\"1\"]').click()")
    time.sleep(0.3)
    fa("(function(){var t=document.getElementById('spot-team');t.value='home';t.dispatchEvent(new Event('change'));"
       "var y=document.getElementById('spot-yard');y.value='25';y.dispatchEvent(new Event('change'));})()")
    fa("document.querySelector('[data-action=\"start_series\"][data-team=\"home\"]').click()")
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "Confirm enabled after HOME BALL HERE", fa_state())
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().possession == "home" and state().down == 1, 5), "opening series committed", (state().possession, state().down))
    time.sleep(0.5)
    s = fa_state()
    check(s["down"] == "1st & 10" and s["ball"] == "25", "assistant shows 1st & 10 at HOME 25 after commit", s)

    # ---- 2. control-panel change with a press pending: adopted, Confirm never disabled
    fa("document.querySelector('[data-action=\"incomplete_pass\"]').click()")
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "INCOMPLETE PASS previewed (Confirm enabled)", fa_state()["confirmLabel"])
    label_before = fa_state()["confirmLabel"]
    rev_before = fa_state()["rev"]
    op("document.getElementById('open-field').click()")
    time.sleep(0.3)
    op("document.querySelector('#field-drawer [data-command=\"set_down\"][data-value=\"3\"]').click()")
    # Sample the assistant's Confirm button every 50 ms for a second: it must never be disabled.
    disabled_seen = False
    samples = 0
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        st = fa_state()
        samples += 1
        if st["confirmDisabled"]:
            disabled_seen = True
        time.sleep(0.05)
    st = fa_state()
    check(state().down == 3, "control panel set 3rd down", state().down)
    check(st["rev"] != rev_before, "assistant adopted the new revision without a reload", (rev_before, st["rev"]))
    check(st["down"] == "3rd & 10", "assistant readout shows 3rd & 10 from the push", st["down"])
    check(not disabled_seen, f"Confirm was never disabled across {samples} samples", samples)
    check(st["confirmLabel"] != label_before and "4th" in st["confirmLabel"], "Confirm label re-previewed against the new down", (label_before, st["confirmLabel"]))
    check(st["conflictHidden"], "no conflict toast for an ordinary change elsewhere")
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")

    # ---- 3. a touched ball survives an unrelated control-panel change
    fa("document.getElementById('nudge-right-5').click()")
    time.sleep(0.4)
    ball_before = fa_state()["ball"]
    check(ball_before == "30", "nudged the draft ball to HOME 30", ball_before)
    op("document.getElementById('home-arm').click()")
    time.sleep(0.2)
    op("document.querySelector('.team [data-command=\"add_score\"][data-team=\"home\"][data-points=\"6\"]').click()")
    check(wait_for(lambda: state().home_score == 6, 5), "control panel added 6", state().home_score)
    time.sleep(0.5)
    st = fa_state()
    check(st["ball"] == ball_before, "dragged/nudged ball stayed put across the score push", (ball_before, st["ball"]))
    check(not st["confirmDisabled"], "Confirm still enabled after the score", st)
    capture_hwnd(window_hwnd(helper), OUT / "pl2-01-assistant-after-panel-changes.png")
    capture_hwnd(window_hwnd(operator), OUT / "pl2-02-operator-after-panel-changes.png")

    # ---- 4. an untouched ball follows the board
    fa("document.getElementById('resync').click()")
    time.sleep(0.5)
    st = fa_state()
    check(st["ball"] == "25" and st["confirmDisabled"] and "discarded" in st["notice"].lower(), "Discard draft & reload gave the ball back to the board", st)
    op("document.getElementById('open-field').click()")
    time.sleep(0.3)
    op("(function(){var i=document.getElementById('ball-on-yard-line'); i.value='40'; i.dispatchEvent(new Event('input',{bubbles:true}));"
       "document.querySelector('#field-drawer [data-command=\"set_ball_on\"]').click();})()")
    check(wait_for(lambda: state().ball_on is not None and state().ball_on.yard_line == 40, 5), "control panel moved the ball to HOME 40", state().ball_on)
    check(wait_for(lambda: fa_state()["ball"] == "40", 3), "untouched draft ball followed the board to 40 without a reload", fa_state()["ball"])
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")

    # ---- 5. a genuine race: refused once, toast, one more Confirm
    fa("document.getElementById('nudge-right-5').click()")
    time.sleep(0.3)
    fa("document.querySelector('[data-action=\"normal_play\"]').click()")
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "PLAY OVER previewed at HOME 45", fa_state()["confirmLabel"])
    fa_bridge = helper._js_api
    original = fa_bridge.finalize_field_action
    raced = {"done": False}

    def racing_finalize(action, expected_revision=None):
        if not raced["done"]:
            raced["done"] = True
            host.application.bridge.command("set_distance", {"value": 7}, host.application.service.revision)
        return original(action, expected_revision)

    fa_bridge.finalize_field_action = racing_finalize
    rev_before_race = state().revision
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: not fa_state()["conflictHidden"], 5), "conflict toast shown after the refused race", fa_state())
    st = fa_state()
    check(state().distance == 7 and state().down == 3, "the racing control-panel change landed (3rd & 7)", (state().down, state().distance))
    check(st["ball"] == "40" and "HOME 40" in st["confirmLabel"], "the draft ball re-seeded from the board after the refused race", (st["ball"], st["confirmLabel"]))
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "Confirm re-enabled after the race (one more tap)", fa_state()["confirmLabel"])
    capture_hwnd(window_hwnd(helper), OUT / "pl2-03-assistant-conflict-toast.png")
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().revision == rev_before_race + 2, 5), "second Confirm committed the play", state().revision)
    check(state().ball_on.yard_line == 40 and state().revision == rev_before_race + 2, "retried play committed at the re-seeded HOME 40 in one extra tap", (state().down, state().distance, state().ball_on))
    time.sleep(0.5)
    fa_bridge.finalize_field_action = original
    check(wait_for(lambda: fa_state()["conflictHidden"], 7), "conflict toast cleared itself")

    time.sleep(0.3)
    helper.destroy()
    time.sleep(0.3)
    operator.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-realrun-") as directory:
        paths = resolve_paths(Path(directory))
        application = ScoreboardApplication(paths, diagnostics=NullDiagnostics())
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
