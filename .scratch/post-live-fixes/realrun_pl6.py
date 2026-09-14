"""PL-6 evidence: a touchdown and try from the REAL pywebview Field Assistant
with the operator window and a practice board open, then a control-panel +6.

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl6.py
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


def drive(host: WindowHost, paths) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def op(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return host.application.service.state

    def strip():
        return json.loads(op("JSON.stringify({values:Array.from(document.querySelectorAll('#field-status .nudge-value')).map(function(n){return n.textContent;}),"
                             "tryPending:document.querySelector('#field-status .try-pending').textContent,"
                             "tryVisible:getComputedStyle(document.querySelector('#field-status .try-pending')).display!=='none'})"))

    time.sleep(1.0)
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    host.open_test_window()
    wait_for(lambda: host.test_window is not None, 5)
    board = host.test_window
    wait_for(lambda: board.evaluate_js("!!document.querySelector('[data-widget=\"quarter\"]')"), 30)
    op("document.getElementById('open-field-assistant').click()")
    wait_for(lambda: host.field_assistant_window is not None, 10)
    helper = host.field_assistant_window
    wait_for(lambda: helper.evaluate_js("!!document.getElementById('confirm') && !!window.pywebview"), 30)
    time.sleep(1.0)

    def fa(expression: str):
        return helper.evaluate_js(expression)

    def fa_state():
        return json.loads(fa("JSON.stringify({panel:Array.from(document.querySelectorAll('[data-panel]')).filter(function(p){return !p.hidden;}).map(function(p){return p.getAttribute('data-panel');}),"
                             "tryTeam:document.getElementById('try-team-word').textContent,"
                             "penaltyOnScore:!!document.querySelector('[data-panel=\"score\"] [data-open=\"penalty\"]'),"
                             "noSeriesHidden:document.getElementById('penalty-no-series').hidden,"
                             "confirmDisabled:document.getElementById('confirm').disabled,"
                             "confirmLabel:document.getElementById('confirm').textContent,"
                             "notice:document.getElementById('notice').textContent,"
                             "down:document.getElementById('current-down').textContent,"
                             "spot:document.getElementById('current-spot').textContent,"
                             "status:document.getElementById('current-status').textContent})"))

    def board_state():
        return json.loads(board.evaluate_js("JSON.stringify((function(){var o={};['down','distance','ball_on','home_score','away_score'].forEach(function(id){var e=document.querySelector('[data-widget=\"'+id+'\"]');o[id]={hidden:e.hidden,text:e.querySelector('.widget-text').textContent};});return o;})())"))

    bridge = host.application.bridge

    def cmd(name, args=None):
        result = bridge.command(name, args or {}, host.application.service.revision)
        assert result["accepted"], result["error"]
        time.sleep(0.5)
        return result

    # --- a HOME series at the AWAY 6, 1st quarter
    cmd("set_quarter", {"label": "1st", "confirmed": True})
    # Seed the series through the assistant's own bridge entry (the press-by-
    # press opening series is PL-2's evidence); the untouched draft ball then
    # follows the board (PL-2) and the play panel opens.
    seeded = bridge.finalize_field_action(
        {"kind": "start_series", "payload": {"offense": "home", "ball_absolute": 94, "first_quarter_home_direction": 1}},
        state().revision,
    )
    check(seeded["accepted"], "series seeded: HOME 1st & Goal at the AWAY 6", seeded["error"])
    check(wait_for(lambda: state().possession == "home" and state().down == 1 and state().distance == 0, 5), "series committed: 1st & Goal", (state().down, state().distance, state().ball_on))
    check(wait_for(lambda: fa_state()["panel"] == ["play"] and fa_state()["down"] == "1st & Goal", 5), "assistant shows the play panel at 1st & Goal", (fa_state()["panel"], fa_state()["down"]))
    time.sleep(0.6)
    b = board_state()
    check(not b["down"]["hidden"] and not b["ball_on"]["hidden"], "board shows down and ball on before the score", b)
    check(strip()["values"][0] == "1st", "operator strip shows 1st", strip())

    # --- step 1: TOUCHDOWN from the assistant
    fa("document.querySelector('[data-open=\"score\"]').click()")
    time.sleep(0.2)
    fa("document.querySelector('[data-action=\"touchdown\"][data-team=\"home\"]').click()")
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "touchdown previewed", fa_state()["confirmLabel"])
    check("+6" in fa_state()["confirmLabel"] and "clear" in fa_state()["confirmLabel"], "Confirm label says +6 and down & distance clear", fa_state()["confirmLabel"])
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().home_score == 6, 5), "one tap plus Confirm: HOME 6", state().home_score)
    time.sleep(0.7)
    s = fa_state()
    check((state().down, state().distance, state().ball_on, state().possession) == (None, None, None, None), "Python: down, distance, ball on, possession cleared", (state().down, state().distance, state().ball_on, state().possession))
    check(s["panel"] == ["score"] and s["tryTeam"] == "HOME", "TRY panel opened for HOME", (s["panel"], s["tryTeam"]))
    time.sleep(0.8)
    s = fa_state()
    check(s["confirmDisabled"] and s["confirmLabel"] == "CONFIRM",
          "no re-armed touchdown draft after the commit (a second Confirm must not add 6 again)", (s["confirmDisabled"], s["confirmLabel"], s["notice"]))
    check("Touchdown recorded" in s["notice"], "notice leads into the try", s["notice"])
    check(s["penaltyOnScore"], "PENALTY… is on the try screen")
    check(s["down"] == "" and s["spot"] == "—", "assistant readouts blank", (s["down"], s["spot"]))
    b = board_state()
    check(b["down"]["hidden"] and b["distance"]["hidden"] and b["ball_on"]["hidden"] and b["home_score"]["text"] == "6",
          "board: down/distance/ball on widgets hidden, HOME 6", b)
    st = strip()
    check(st["values"] == ["", "", "—"] or st["values"][:2] == ["", ""], "operator strip: down and distance blank", st["values"])
    check(st["tryVisible"] and st["tryPending"].startswith("TRY PENDING"), "operator strip says TRY PENDING · HOME", st["tryPending"])
    capture_hwnd(window_hwnd(helper), OUT / "pl6-01-assistant-try-panel.png")
    capture_hwnd(window_hwnd(operator), OUT / "pl6-02-operator-after-td.png")
    capture_hwnd(window_hwnd(board), OUT / "pl6-03-board-after-td.png")

    # --- PENALTY reachable from the try screen; it explains, and Back returns
    fa("document.querySelector('[data-panel=\"score\"] [data-open=\"penalty\"]').click()")
    time.sleep(0.3)
    s = fa_state()
    check(s["panel"] == ["penalty"] and not s["noSeriesHidden"], "penalty panel opened from the try screen with the no-series note", (s["panel"], s["noSeriesHidden"]))
    time.sleep(0.4)
    check(fa_state()["confirmDisabled"] and "cannot" in fa_state()["confirmLabel"].lower() or fa_state()["confirmDisabled"], "Confirm stays disabled: nothing to enforce yet", (fa_state()["confirmDisabled"], fa("document.getElementById('proposed-status').textContent")))
    capture_hwnd(window_hwnd(helper), OUT / "pl6-04-assistant-penalty-from-try.png")
    fa("document.querySelector('[data-panel=\"penalty\"] [data-back]').click()")
    time.sleep(0.3)
    # Back lands on the top panel (start); SCORE… reopens the try for HOME.
    fa("document.querySelector('[data-panel=\"start\"] [data-open=\"score\"]').click()")
    time.sleep(0.2)
    check(fa_state()["panel"] == ["score"] and fa_state()["tryTeam"] == "HOME", "back on the try screen for HOME")

    # --- the try: KICK +1, then "Set up the kickoff."
    fa("document.querySelector('[data-action=\"try\"][data-points=\"1\"]').click()")
    check(wait_for(lambda: not fa_state()["confirmDisabled"], 5), "KICK +1 previewed", fa_state()["confirmLabel"])
    check("Set up the kickoff" in fa_state()["notice"], "preview notice: Set up the kickoff.", fa_state()["notice"])
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().home_score == 7, 5), "try committed: HOME 7")
    time.sleep(0.6)
    s = fa_state()
    check(s["panel"] == ["start"], "start panel (kickoff) offered after the try", s["panel"])
    check(not strip()["tryVisible"], "TRY PENDING cleared after the try", strip())
    capture_hwnd(window_hwnd(helper), OUT / "pl6-05-assistant-after-try.png")

    # --- step 3: control-panel +6 for AWAY clears the field and hints
    cmd("set_possession", {"team": "away"})
    cmd("set_down", {"value": 2})
    cmd("set_distance", {"value": 3})
    cmd("set_ball_on", {"team": "home", "value": 3})
    check(strip()["values"] == ["2nd", "& 3", "HOME 3"], "control panel seeded 2nd & 3 at HOME 3", strip())
    op("document.getElementById('away-arm').click()")
    time.sleep(0.2)
    op("document.querySelector('.team [data-command=\"add_score\"][data-team=\"away\"][data-points=\"6\"]').click()")
    check(wait_for(lambda: state().away_score == 6, 5), "control panel +6: AWAY 6")
    time.sleep(0.6)
    check((state().down, state().distance, state().ball_on) == (None, None, None), "+6 blanked down, distance, ball on", (state().down, state().distance, state().ball_on))
    st = strip()
    check(st["values"][:2] == ["", ""] and st["tryVisible"] and "TRY PENDING" in st["tryPending"] and "AWAY" in st["tryPending"], "strip blank with TRY PENDING · AWAY", st)
    b = board_state()
    check(b["down"]["hidden"] and b["ball_on"]["hidden"] and b["away_score"]["text"] == "6", "board blank field, AWAY 6", b)
    check(fa_state()["down"] == "" and fa_state()["panel"] == ["start"], "assistant followed the control-panel +6 without a reload", (fa_state()["down"], fa_state()["panel"]))
    capture_hwnd(window_hwnd(operator), OUT / "pl6-06-operator-panel-plus6.png")
    op("document.getElementById('undo').click()")
    time.sleep(0.3)
    op("document.getElementById('confirm-accept').click()")
    check(wait_for(lambda: state().away_score == 0, 5), "Undo took the 6 back")
    time.sleep(0.5)
    check((state().down, state().distance, state().ball_on.yard_line, state().possession) == (2, 3, 3, "away") and not strip()["tryVisible"], "...and restored AWAY 2nd & 3 at HOME 3, hint gone", (state().down, state().distance, state().ball_on, state().possession, strip()))
    rows = [r["command"] for r in read_action_history(paths.database)[-2:]]
    check(rows == ["add_score", "undo"], "history: add_score then undo", rows)

    time.sleep(0.3)
    helper.destroy(); time.sleep(0.2)
    board.destroy(); time.sleep(0.2)
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
