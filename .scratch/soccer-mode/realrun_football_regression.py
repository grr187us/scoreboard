"""Football regression on the REAL pywebview runtime after the soccer seams.

Proves the frozen football path still opens its own operator window through
the (now profile-aware) WindowHost, that the page drives commands, that the
crowd bar and the armed two-step scoring still behave, and that a football
session never creates a ``soccer/`` folder. Development evidence, not part
of the suite. Run from the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\soccer-mode\\realrun_football_regression.py
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
from scoreboard.host.hotkeys import HOTKEY_TABLE  # noqa: E402
from scoreboard.infrastructure.diagnostics import NullDiagnostics  # noqa: E402
from scoreboard.infrastructure.paths import resolve_paths  # noqa: E402

RESULTS: list[tuple[bool, str, object]] = []
OUT = Path(__file__).resolve().parent / "evidence" / "football"


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


def drive(host: WindowHost, data_dir: Path) -> None:
    operator = host.operator_window
    check(wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30),
          "football operator page loaded (home-arm present)")
    app = host.application

    def js(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return app.service.state

    def visible(selector: str) -> bool:
        return js("(function(){var e=document.querySelector('%s');return !!e && !e.hidden && e.getClientRects().length>0;})()" % selector)

    def click(selector: str):
        js("document.querySelector('%s').click()" % selector.replace("'", "\\'"))

    time.sleep(1.0)
    check(app.profile.sport == "football" and app.profile.operator_view == "operator",
          "football application carries the football profile", app.profile)
    check(app.profile.hotkey_table is HOTKEY_TABLE, "football profile uses HOTKEY_TABLE")
    check(js("document.title") and "SOCCER" not in str(js("document.title")).upper(),
          "football operator title has no soccer wording", js("document.title"))
    check(js("!!document.getElementById('home-timeout') && !!document.getElementById('crowd-flag')"),
          "football-only controls (TIMEOUT, FLAG) present")

    bridge = app.bridge
    for team, name in (("home", "Tigers"), ("away", "Eagles")):
        bridge.command("set_team_name", {"team": team, "name": name, "confirmed": True}, app.service.revision)
    bridge.command("set_quarter", {"label": "1st", "confirmed": True}, app.service.revision)
    check(wait_for(lambda: js("document.getElementById('home-name').textContent") in ("Tigers", "TIGERS"), 5)
          or wait_for(lambda: "Tigers" in str(js("document.body.textContent")), 5),
          "push shows the home team name on the page")
    time.sleep(0.8)

    # crowd bar: FLAG raise then clear
    check(not visible("#crowd-clear") and not visible("#crowd-countdown"), "idle crowd bar has no CLEAR/countdown")
    click("#crowd-flag")
    check(wait_for(lambda: state().game_status == "FLAG", 5), "FLAG raised from the page", state().game_status)
    time.sleep(0.5)
    check(visible("#crowd-clear") and not visible("#crowd-countdown"), "FLAG shows CLEAR only")
    capture_hwnd(window_hwnd(operator), OUT / "football-1-flag.png")
    click("#crowd-clear")
    check(wait_for(lambda: state().game_status is None, 5), "CLEAR clears the message")
    time.sleep(0.5)

    # armed two-step scoring, then Undo through Python
    click("#home-arm")
    time.sleep(0.4)
    check(visible("#home-armed"), "SCORE > arms the home panel")
    click('#home-armed [data-command="add_score"][data-points="6"]')
    check(wait_for(lambda: state().home_score == 6, 5), "+6 applied -> home 6", state().home_score)
    time.sleep(0.5)
    check(not visible("#home-armed"), "panel disarms after the score")
    capture_hwnd(window_hwnd(operator), OUT / "football-2-scored.png")
    bridge.command("undo", {"confirmed": True}, app.service.revision)
    check(wait_for(lambda: state().home_score == 0, 5), "undo restores home 0", state().home_score)

    # game clock from the page (settle after the Python-side undo: page-revision race)
    time.sleep(0.8)
    click("#game-start")
    check(wait_for(lambda: state().game_clock.running, 5), "START runs the game clock")
    time.sleep(0.8)
    click("#game-stop")
    check(wait_for(lambda: not state().game_clock.running, 5), "STOP stops the game clock")

    check(not (data_dir / "soccer").exists(), "no soccer/ folder created by a football session")
    check((data_dir / "scoreboard.db").exists(), "football database at the data root")
    time.sleep(0.3)
    operator.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scoreboard-football-realrun-") as directory:
        data_dir = Path(directory)
        application = ScoreboardApplication(resolve_paths(data_dir), diagnostics=NullDiagnostics())
        host = WindowHost(application)
        threading.Timer(3.0, lambda: drive(host, data_dir)).start()
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
