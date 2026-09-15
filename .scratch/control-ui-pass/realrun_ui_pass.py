"""September 14, 2026 UI pass evidence on the REAL pywebview operator window.

Nudges under the game clock, crowd CLEAR/countdown only when needed (yellow /
green / red), legible identity stripe. Development evidence, not part of the
suite. Run from the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\control-ui-pass\\realrun_ui_pass.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".scratch" / "post-live-fixes"))
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
        except Exception:  # noqa: BLE001
            pass
        time.sleep(step)
    return False


def size_viewport(window, js, width: int, height: int) -> tuple[int, int]:
    window.resize(width + 16, height + 39)
    time.sleep(0.6)
    for _ in range(4):
        inner = json.loads(js("JSON.stringify([window.innerWidth, window.innerHeight])"))
        if inner == [width, height]:
            break
        window.resize(width + 16 + (width - inner[0]), height + 39 + (height - inner[1]))
        time.sleep(0.6)
    return tuple(json.loads(js("JSON.stringify([window.innerWidth, window.innerHeight])")))


def drive(host: WindowHost) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)
    app = host.application

    def js(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return app.service.state

    def visible(selector: str) -> bool:
        return js("(function(){var e=document.querySelector('%s');return !!e && !e.hidden && e.getClientRects().length>0;})()" % selector)

    def overflow_free():
        return js("document.documentElement.scrollHeight === document.documentElement.clientHeight && "
                  "document.documentElement.scrollWidth === document.documentElement.clientWidth")

    def click(selector: str):
        js("document.querySelector('%s').click()" % selector.replace("'", "\\'"))

    def columns():
        return json.loads(js(
            "JSON.stringify(Array.from(document.querySelectorAll('.clock-block')).map(function(b){"
            "return Math.round(Math.max.apply(null, Array.from(b.querySelectorAll('button, p, .nudge-value')).map(function(e){return e.getBoundingClientRect().bottom;})));}))"))

    time.sleep(1.0)
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")

    # --- the owner's two saved teams, applied from Python, then let the push land
    bridge = app.bridge
    bridge.save_team({"name": "Tigers", "short_name": "TMSA", "primary": "#2B07DF", "secondary": "#AA0909"})
    bridge.save_team({"name": "Eagles", "short_name": "Grace", "primary": "#28D425", "secondary": "#CB9625"})
    for team, name in (("home", "Tigers"), ("away", "Eagles")):
        bridge.command("set_team_name", {"team": team, "name": name, "confirmed": True}, app.service.revision)
    bridge.command("set_quarter", {"label": "1st", "confirmed": True}, app.service.revision)
    bridge.command("set_possession", {"team": "home"}, app.service.revision)
    bridge.command("set_down", {"value": 3}, app.service.revision)
    bridge.command("set_distance", {"value": 7}, app.service.revision)
    bridge.command("set_ball_on", {"nudge": -15}, app.service.revision)
    check(wait_for(lambda: js("document.getElementById('home-identity-stripe').textContent") == "TMSA", 5),
          "home stripe shows TMSA after the push")
    time.sleep(0.8)  # page-revision settle before the first page click

    # --- 3. identity stripe legible
    stripes = json.loads(js(
        "JSON.stringify(['home','away'].map(function(s){var e=document.getElementById(s+'-identity-stripe');var c=getComputedStyle(e);"
        "return [e.textContent, c.backgroundColor, c.color, c.fontSize, Math.round(e.getBoundingClientRect().height), e.scrollWidth>e.clientWidth];}))"))
    check(stripes[0] == ["TMSA", "rgb(43, 7, 223)", "rgb(255, 255, 255)", "17px", 26, False], "TMSA: white 17px on the dark blue, not clipped", stripes[0])
    check(stripes[1] == ["Grace", "rgb(40, 212, 37)", "rgb(18, 22, 28)", "17px", 26, False], "Grace: dark 17px on the bright green, not clipped", stripes[1])

    for width, height in ((1366, 768), (1093, 614)):
        inner = size_viewport(operator, js, width, height)
        check(inner == (width, height), f"operator CSS viewport is {width}x{height}", inner)
        time.sleep(0.4)
        tag = f"{width}x{height}"

        # --- 1. nudges live under the game clock, not in the quarter bar
        check(js("!!document.querySelector('.clocks .clock-block:first-child #field-status')"), f"{tag}: nudge strip is inside the game clock column")
        check(js("document.querySelectorAll('.quarter-bar [data-nudge]').length === 0"), f"{tag}: no nudges left in the quarter bar")
        values = json.loads(js("JSON.stringify(Array.from(document.querySelectorAll('#field-status .nudge-value')).map(function(n){return n.textContent;}))"))
        check(values == ["3rd", "& 7", "Tigers 35"], f"{tag}: strip shows 3rd & 7, Tigers 35", values)
        game_bottom, play_bottom = columns()
        check(abs(game_bottom - play_bottom) <= 1, f"{tag}: game column ends level with the play column", (game_bottom, play_bottom))
        heights = json.loads(js("JSON.stringify(Array.from(document.querySelectorAll('#field-status button.nudge')).map(function(b){return Math.round(b.getBoundingClientRect().height);}))"))
        check(len(heights) == 8 and min(heights) >= 44, f"{tag}: eight strip nudges, all 44px tall", heights)
        check(overflow_free(), f"{tag}: no page scroll (idle)")

        # --- 2. crowd bar: nothing floating when idle
        check(not visible("#crowd-clear") and not visible("#crowd-countdown"), f"{tag}: idle bar has no CLEAR and no countdown")
        board_idle = js("Math.round(document.querySelector('.board').getBoundingClientRect().height)")
        capture_hwnd(window_hwnd(operator), OUT / f"ui-{width}-1-idle.png")

        click("#crowd-flag")
        check(wait_for(lambda: state().game_status == "FLAG", 5), f"{tag}: FLAG raised", state().game_status)
        time.sleep(0.5)
        check(visible("#crowd-clear") and not visible("#crowd-countdown"), f"{tag}: FLAG shows CLEAR only")
        capture_hwnd(window_hwnd(operator), OUT / f"ui-{width}-2-flag.png")

        click("#crowd-timeout")
        check(wait_for(lambda: state().game_status == "TIMEOUT" and state().status_clock.running, 5), f"{tag}: TIMEOUT raised and its countdown running")
        time.sleep(0.7)
        check(visible("#crowd-clear") and visible("#crowd-countdown") and visible("#crowd-start") and visible("#crowd-stop"),
              f"{tag}: TIMEOUT shows CLEAR and the countdown with START/STOP")
        colours = json.loads(js("JSON.stringify(['crowd-clear','crowd-start','crowd-stop'].map(function(i){return getComputedStyle(document.getElementById(i)).backgroundColor;}))"))
        check(colours == ["rgb(255, 200, 69)", "rgb(46, 158, 106)", "rgb(196, 61, 61)"], f"{tag}: CLEAR yellow, START green, STOP red", colours)
        check(js("document.getElementById('crowd-start').classList.contains('is-current')"), f"{tag}: running countdown dims START")
        board_timeout = js("Math.round(document.querySelector('.board').getBoundingClientRect().height)")
        check(board_timeout == board_idle, f"{tag}: raising TIMEOUT does not change the board height", (board_idle, board_timeout))
        check(overflow_free(), f"{tag}: no page scroll (TIMEOUT)")
        capture_hwnd(window_hwnd(operator), OUT / f"ui-{width}-3-timeout.png")

        click("#crowd-stop")
        check(wait_for(lambda: not state().status_clock.running, 5), f"{tag}: STOP stops the countdown")
        time.sleep(0.5)
        check(visible("#crowd-countdown"), f"{tag}: stopped countdown stays on screen until CLEAR")
        click("#crowd-clear")
        check(wait_for(lambda: state().game_status is None, 5), f"{tag}: CLEAR clears the message")
        time.sleep(0.6)
        check(not visible("#crowd-clear") and not visible("#crowd-countdown"), f"{tag}: after CLEAR both are hidden again")

    # --- a strip nudge reaches Python from its new home
    click('#field-status [data-command="set_down"][data-nudge="-1"]')
    check(wait_for(lambda: state().down == 2, 5), "strip - on DOWN -> 2nd", state().down)
    time.sleep(0.5)
    click('#field-status [data-command="set_ball_on"][data-nudge="5"]')
    check(wait_for(lambda: state().ball_on is not None and state().ball_on.yard_line == 40, 5), "strip +5 on BALL ON -> 40", state().ball_on)

    time.sleep(0.3)
    operator.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-realrun-") as directory:
        application = ScoreboardApplication(resolve_paths(Path(directory)), diagnostics=NullDiagnostics())
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
