"""Drive the REAL pywebview windows and prove the Broadcast Welcome screens there.

Development evidence, not part of the suite. The browser suite
(tests/ui/test_event_screens_browser.py) runs the same HTML/CSS/JS in Chromium
against a stub bridge; this runs it where it ships -- WebView2 windows created by
pywebview with the real ``js_api`` attached -- which is the only place the
pywebview call path (``get_motion``, ``window.applyMotion`` pushes, the editor's
``set_motion``) is exercised.

Run from the repository root:
    set PYTHONIOENCODING=utf-8
    .\\.venv\\Scripts\\python.exe .scratch\\event-screens\\realrun_event_screens.py

It opens the real operator window, the practice spectator window and the layout
editor, runs the checks from a worker thread (every ``evaluate_js`` blocks on the
WebView2 UI thread, so nothing here may run on it), prints PASS/FAIL lines, and
closes itself. No fullscreen window is opened.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from scoreboard.host.app import ScoreboardApplication, WindowHost
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


BOARD_ANIMS = (
    "(function(){var root=document.getElementById('event-board');"
    "return document.getAnimations().filter(function(a){var t=a.effect&&a.effect.target;"
    "return t&&root.contains(t)&&a.playState==='running';}).length;})()"
)

SWEEP_TIME = (
    "(function(){var el=document.querySelector('#event-board [data-element=\"light_sweep\"]');"
    "if(!el)return null;var a=el.getAnimations();return a.length?a[0].currentTime:null;})()"
)


def drive(host: WindowHost) -> None:
    app = host.application
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('open-teams')"), 30)
    time.sleep(1.0)
    revision_at_start = app.service.revision

    # --- 1. Practice spectator window on the default layout: pregame welcome
    host.open_test_window()
    practice = host.test_window
    ok = wait_for(lambda: practice.evaluate_js(
        "!!document.querySelector('#event-board [data-element=\"ticker\"]')"), 25)
    check(ok, "practice window shows the pregame board with the ticker element")

    def js(expression: str, window=None):
        return (window or practice).evaluate_js(expression)

    time.sleep(1.5)
    check(js("document.getElementById('event-board').dataset.screen") == "pregame",
          "event board is on the pregame screen")
    check(js("document.getElementById('event-board').hidden") is False, "event board is visible")
    check(js("document.querySelector('#event-board [data-element=\"light_sweep\"]').dataset.anim") == "sweep",
          "light sweep carries data-anim=sweep")
    check(js("document.querySelector('#event-board [data-element=\"ticker\"]').dataset.tickerMode") == "scroll",
          "ticker scrolls while motion is on")
    check(js("document.querySelector('#event-board [data-element=\"crest\"] img').getAttribute('src')")
          == "../shared/img/tigers-crest.png", "crest image points at the bundled asset")
    check(js("document.fonts.check(\"700 40px 'Barlow Condensed'\")"),
          "Barlow Condensed is loaded from the bundle")
    check(js("document.fonts.check('40px Graduate')"), "Graduate is loaded from the bundle")
    check(js("document.querySelector('#event-board [data-widget=\"home_score\"]').hidden") is True,
          "scores are hidden before kickoff")
    check(js("document.querySelectorAll('#event-board [data-widget=\"event_clock\"] .clock-colon').length") == 1,
          "the countdown colon is its own span")
    running = js(BOARD_ANIMS)
    check(isinstance(running, (int, float)) and running > 0, "animations are running on the board", running)
    first = js(SWEEP_TIME)
    time.sleep(1.2)
    second = js(SWEEP_TIME)
    check(first is not None and second is not None and second > first,
          "the sweep animation keeps advancing across snapshot ticks", (first, second))
    check(js("document.documentElement.scrollWidth === innerWidth && "
             "document.documentElement.scrollHeight === innerHeight"), "the practice window never scrolls")

    # --- 2. Motion off through the layouts host object (what the editor calls)
    result = app.layouts.set_motion(False)
    check(result.get("ok") is True and result.get("motion") is False, "set_motion(False) is accepted")
    ok = wait_for(lambda: js("document.getElementById('canvas').dataset.motion") == "off", 5)
    check(ok, "the practice window received applyMotion(false)")
    time.sleep(0.6)
    check(js(BOARD_ANIMS) == 0, "no animation is running with motion off", js(BOARD_ANIMS))
    check(js("document.querySelector('#event-board [data-element=\"ticker\"]').dataset.tickerMode") == "static",
          "the ticker becomes one static line")
    ticker_text = js("document.querySelector('#event-board [data-element=\"ticker\"]').textContent")
    check(isinstance(ticker_text, str) and "WELCOME TO TIGER STADIUM" in ticker_text and "•" in ticker_text,
          "the static ticker still carries every announcement", ticker_text[:80] if ticker_text else ticker_text)
    config = json.loads(host.application.paths.config.read_text(encoding="utf-8"))
    check(config.get("presentation", {}).get("motion") is False, "config.json records presentation.motion=false")
    check(app.service.revision == revision_at_start, "motion switch advanced no revision")

    result = app.layouts.set_motion(True)
    check(result.get("ok") is True and result.get("motion") is True, "set_motion(True) is accepted")
    ok = wait_for(lambda: js("document.getElementById('canvas').dataset.motion") != "off", 5)
    check(ok, "the practice window received applyMotion(true)")
    time.sleep(0.6)
    check(js(BOARD_ANIMS) > 0, "animations resume", js(BOARD_ANIMS))
    check(js("document.querySelector('#event-board [data-element=\"ticker\"]').dataset.tickerMode") == "scroll",
          "the ticker scrolls again")
    check(app.layouts.set_motion("yes").get("ok") is False, "a non-boolean is refused")

    # --- 3. Halftime through the real command path
    outcome = app.bridge.command("set_quarter", {"label": "HALF", "confirmed": True}, app.service.revision)
    check(outcome.get("accepted") is True, "set_quarter HALF accepted", outcome.get("error") or outcome.get("message"))
    ok = wait_for(lambda: js("document.getElementById('event-board').dataset.screen") == "halftime", 10)
    check(ok, "event board switched to the halftime screen")
    time.sleep(1.5)
    check(js("document.querySelector('#event-board [data-widget=\"event_phase\"]').textContent") == "HALFTIME",
          "phase label reads HALFTIME")
    check(js("document.querySelector('#event-board [data-widget=\"home_score\"]').hidden") is False,
          "scores show at halftime")
    check(js("document.querySelector('#event-board [data-widget=\"warmup\"]').hidden") is False,
          "warm-up line shows at halftime")
    check(js("document.querySelector('#event-board [data-element=\"ticker\"]').dataset.tickerMode") == "scroll",
          "halftime ticker scrolls")
    check(js(BOARD_ANIMS) > 0, "halftime animations run", js(BOARD_ANIMS))
    # Every glyph inside the 4 % inset and inside its own box (ticker excluded).
    problems = js(
        "(function(){var c=document.getElementById('canvas').getBoundingClientRect();var out=[];"
        "document.querySelectorAll('#event-board [data-widget], #event-board .element-text').forEach(function(el){"
        "if(el.hidden||!el.getClientRects().length)return;if(el.closest('.element-ticker'))return;"
        "var an=el.dataset.anim;if(an==='sweep'||an==='drift'||an==='scroll_x')return;"
        "var s=el.querySelector('.widget-text');if(!s||!s.textContent.trim())return;"
        "var r=document.createRange();r.selectNodeContents(s);var b=r.getBoundingClientRect();"
        "if(b.left<c.left+c.width*.04-1||b.right>c.right-c.width*.04+1||b.top<c.top+c.height*.04-1||"
        "b.bottom>c.bottom-c.height*.04+1)out.push((el.dataset.widget||el.dataset.element)+': outside safe area');"
        "});return out;})()")
    check(problems == [], "halftime glyphs stay inside the safe area", problems)

    # --- 4. The layout editor's Motion toggle drives the wall
    host.open_layout_editor()
    editor = host.layout_window
    ok = wait_for(lambda: js("!!document.getElementById('motion-toggle')", editor), 25)
    check(ok, "layout editor opened with the Motion toggle")
    time.sleep(1.5)
    check(js("document.getElementById('motion-toggle').getAttribute('aria-pressed')", editor) == "true",
          "toggle reflects motion on")
    js("document.getElementById('motion-toggle').click()", editor)
    ok = wait_for(lambda: js("document.getElementById('canvas').dataset.motion") == "off", 8)
    check(ok, "clicking the editor toggle pauses the practice window")
    check(js("document.getElementById('canvas').dataset.motion", editor) == "off",
          "the editor preview paused too")
    js("document.getElementById('motion-toggle').click()", editor)
    ok = wait_for(lambda: js("document.getElementById('canvas').dataset.motion") != "off", 8)
    check(ok, "clicking again resumes the practice window")
    check(app.service.revision == revision_at_start + 1,
          "only the quarter change advanced the revision", (revision_at_start, app.service.revision))
    check(js("!!document.querySelector('[data-action=\"add_ticker\"]')", editor), "editor offers Add ticker")

    time.sleep(0.5)
    try:
        editor.destroy()
    except Exception:  # noqa: BLE001
        pass
    try:
        practice.destroy()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.5)
    operator.destroy()


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
