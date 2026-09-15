"""A whole soccer game on the REAL pywebview runtime, through the sport picker.

Sport picker -> SOCCER -> operator window (soccer page) -> pregame -> 1st half
(goal from the page with the GOAL cutscene, a yellow card with a number, stat
nudges, WEATHER crowd word with its countdown) -> halftime -> 2nd half ->
shootout from the page -> FINISH SHOOTOUT -> FINAL; the Field Assistant window
records a stat; the layout editor opens on the soccer registry; football's
files at the data root are never created. Screenshots go to
``.scratch/soccer-mode/evidence/soccer/``. Development evidence, not part of
the suite. Run from the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\soccer-mode\\realrun_soccer.py
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

from scoreboard.host.sport_picker import SportPickerHost  # noqa: E402
from scoreboard.infrastructure.paths import resolve_paths  # noqa: E402
from scoreboard.infrastructure.persistence import read_action_history  # noqa: E402

RESULTS: list[tuple[bool, str, object]] = []
OUT = Path(__file__).resolve().parent / "evidence" / "soccer"


PROGRESS = Path(__file__).resolve().parent / "evidence" / "soccer" / "progress.log"


def check(ok: bool, label: str, detail: object = "") -> None:
    RESULTS.append((bool(ok), label, detail))
    with PROGRESS.open("a", encoding="utf-8") as handle:
        handle.write(("PASS " if ok else "FAIL ") + label + chr(10))


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


def drive(picker: SportPickerHost, data_dir: Path) -> None:
    try:
        _drive(picker, data_dir)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check, never a hung loop
        import traceback
        check(False, "harness raised", traceback.format_exc())
    finally:
        host = picker.host
        for name in ("field_assistant_window", "layout_window", "cutscenes_window", "operator_window"):
            window = getattr(host, name, None) if host is not None else None
            if window is not None:
                try:
                    window.destroy()
                except Exception:  # noqa: BLE001
                    pass
        if picker._picker_window is not None:
            try:
                picker._picker_window.destroy()
            except Exception:  # noqa: BLE001
                pass


def _drive(picker: SportPickerHost, data_dir: Path) -> None:
    # --- 1. the sport picker, chosen from its own page
    window = picker._picker_window
    check(wait_for(lambda: window.evaluate_js("!!document.getElementById('soccer')"), 30),
          "sport picker page loaded")
    capture_hwnd(window_hwnd(window), OUT / "00-picker.png")
    window.evaluate_js("document.getElementById('soccer').click()")
    check(wait_for(lambda: picker.host is not None and picker.host.operator_window is not None, 20),
          "choosing SOCCER built the soccer application and its operator window")
    host = picker.host
    app = host.application
    operator = host.operator_window
    check(app.profile.sport == "soccer" and app.profile.operator_view == "soccer_operator",
          "soccer profile in use", (app.profile.sport, app.profile.operator_view))
    check(wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm') && !!document.getElementById('crowd-weather')"), 30),
          "soccer operator page loaded (home-arm, crowd-weather present)")
    check(json.loads((data_dir / "config.json").read_text(encoding="utf-8")).get("sport", {}).get("last") == "soccer",
          "last sport remembered in the root config.json")

    def js(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return app.service.state

    def visible(selector: str) -> bool:
        return js("(function(){var e=document.querySelector('%s');return !!e && !e.hidden && e.getClientRects().length>0;})()" % selector)

    def click(selector: str):
        js("document.querySelector('%s').click()" % selector.replace("'", "\\'"))

    def overflow_free():
        return js("document.documentElement.scrollHeight === document.documentElement.clientHeight && "
                  "document.documentElement.scrollWidth === document.documentElement.clientWidth")

    def shot(name: str):
        capture_hwnd(window_hwnd(operator), OUT / name)

    def settle(seconds: float = 0.8):
        time.sleep(seconds)

    time.sleep(1.0)
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    bridge = app.bridge
    check(not visible("#home-timeout") and js("!document.getElementById('crowd-flag') && !document.getElementById('play-display')"),
          "no football controls on the soccer page")
    check(overflow_free(), "no page scroll on the soccer operator page (idle)")

    # --- 2. teams (shared library), pregame countdown
    bridge.save_team({"name": "Tigers", "short_name": "TMSA", "primary": "#2B07DF", "secondary": "#AA0909"})
    bridge.save_team({"name": "Eagles", "short_name": "Grace", "primary": "#28D425", "secondary": "#CB9625"})
    for team, name in (("home", "Tigers"), ("away", "Eagles")):
        bridge.command("set_team_name", {"team": team, "name": name, "confirmed": True}, app.service.revision)
    check(wait_for(lambda: js("document.getElementById('home-identity-stripe').textContent") == "TMSA", 5),
          "home stripe shows TMSA after the push")
    check((data_dir / "teams.json").exists() and not (data_dir / "scoreboard.db").exists()
          and (data_dir / "soccer" / "scoreboard.db").exists(),
          "teams.json shared at the root; the game database only under soccer/")
    check(state().period == "PRE" and state().lifecycle == "PRE_GAME", "new soccer game starts in PRE", state().period)
    settle()
    shot("01-pregame.png")

    # rules for a short evening: no overtime, shootout on (playoff style)
    saved = bridge.save_rules({**bridge.rules()["rules"], "overtime_periods": 0, "shootout_enabled": True})
    check(saved.get("ok", False), "rules saved (no OT, shootout on)", saved.get("message"))
    settle()

    # --- 3. first half from the page: period forward (confirmed), START
    click('[data-command="period_forward"]')
    settle(0.5)
    check(visible("#confirm-dialog"), "period forward asks for confirmation (pregame time discarded)")
    click("#confirm-accept")
    check(wait_for(lambda: state().period == "1st", 5), "period is 1st", state().period)
    settle()
    click("#game-start")
    check(wait_for(lambda: state().game_clock.running, 5), "START runs the game clock from the page")
    settle()

    # goal: SCORE > then GOAL (two-step), auto GOAL cutscene
    click("#home-arm")
    settle(0.4)
    check(visible("#home-goal-armed"), "SCORE > arms the home panel")
    shot("02-armed.png")
    click('#home-goal-armed [data-command="add_goal"][data-team="home"]')
    check(wait_for(lambda: state().home_score == 1, 5), "GOAL -> home 1", state().home_score)
    check(wait_for(lambda: not state().game_clock.running, 5), "stop_clock_on_goal stopped the clock")
    check(wait_for(lambda: (app.cutscenes.state() or {}).get("active") or (app.cutscenes.state() or {}).get("playing"), 5)
          or bool(app.cutscenes.state()), "GOAL cutscene triggered automatically", app.cutscenes.state())
    settle(1.0)
    if host.spectator_window is not None:
        capture_hwnd(window_hwnd(host.spectator_window), OUT / "03-spectator-goal.png")
    settle(0.5)
    check(not visible("#home-goal-armed"), "panel disarmed after the goal")
    click("#game-start")
    check(wait_for(lambda: state().game_clock.running, 5), "clock restarted after the goal")
    settle()

    # yellow card with a number from the page
    click("#away-yellow")
    settle(0.4)
    check(visible("#away-card-armed"), "YELLOW arms the card entry")
    js("var n=document.getElementById('away-card-number'); n.value='10'; n.dispatchEvent(new Event('input',{bubbles:true}));")
    settle(0.3)
    click("#away-card-confirm-yellow")
    check(wait_for(lambda: state().away_yellow == 1 and state().cards[-1].player_number == 10, 5),
          "AWAY yellow #10 recorded with period and clock", state().cards)
    settle()
    check("AWAY yellow #10" in str(js("document.getElementById('last-action').textContent")), "LAST strip names the card",
          js("document.getElementById('last-action').textContent"))

    # stat nudges from the page
    click('[data-command="add_stat"][data-team="home"][data-stat="shots"][data-step="1"]')
    check(wait_for(lambda: state().home_shots == 1, 5), "home shots +1 from the page")
    settle()
    click('[data-command="add_stat"][data-team="away"][data-stat="corners"][data-step="1"]')
    check(wait_for(lambda: state().away_corners == 1, 5), "away corners +1 from the page")
    settle()

    # crowd bar: WEATHER raises the word and its countdown; CLEAR hides both
    check(not visible("#crowd-clear") and not visible("#crowd-countdown"), "idle crowd bar has no CLEAR/countdown")
    click("#crowd-weather")
    check(wait_for(lambda: state().game_status == "WEATHER" and state().status_clock.running, 5),
          "WEATHER raised with its countdown running", state().game_status)
    settle()
    check(visible("#crowd-clear") and visible("#crowd-countdown") and visible("#crowd-start") and visible("#crowd-stop"),
          "WEATHER shows CLEAR and the countdown with START/STOP")
    check(overflow_free(), "no page scroll with the countdown up")
    shot("04-weather.png")
    click("#crowd-clear")
    check(wait_for(lambda: state().game_status is None, 5), "CLEAR clears WEATHER")
    settle()
    check(not visible("#crowd-clear") and not visible("#crowd-countdown"), "crowd bar back to idle")

    # undo the last stat through the page (confirmed)
    click("#undo")
    settle(0.5)
    check(visible("#confirm-dialog"), "Undo asks for confirmation")
    click("#confirm-accept")
    check(wait_for(lambda: state().away_corners == 0, 5), "Undo reversed the corner")
    settle()

    # --- 4. halftime, second half
    click("#game-stop")
    check(wait_for(lambda: not state().game_clock.running, 5), "STOP stops the clock")
    settle()
    click('[data-command="period_forward"]')
    settle(0.5)
    if visible("#confirm-dialog"):
        click("#confirm-accept")
    check(wait_for(lambda: state().period == "HALF" and state().lifecycle == "HALFTIME", 5), "HALF loaded", state().period)
    settle()
    if host.spectator_window is not None:
        capture_hwnd(window_hwnd(host.spectator_window), OUT / "05-spectator-halftime.png")
    shot("05-halftime.png")
    click('[data-command="period_forward"]')
    settle(0.5)
    if visible("#confirm-dialog"):
        click("#confirm-accept")
    check(wait_for(lambda: state().period == "2nd", 5), "2nd loaded", state().period)
    settle()

    # --- 5. the Field Assistant records a stat
    result = bridge.open_field_assistant()
    check(wait_for(lambda: host.field_assistant_window is not None, 10), "Field Assistant window opened", result)
    fa = host.field_assistant_window
    check(wait_for(lambda: fa.evaluate_js("!!document.getElementById('confirm')"), 20), "Field Assistant page loaded")
    settle(1.0)
    fa.evaluate_js("document.querySelector('[data-action=\"stat\"][data-team=\"home\"][data-stat=\"saves\"]').click()")
    settle(0.5)
    fa.evaluate_js("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().home_saves == 1, 5), "Field Assistant recorded HOME save", state().home_saves)
    check(fa.evaluate_js("!document.querySelector('[data-command=\"add_goal\"], #game-start, #home-arm')"),
          "Field Assistant has no goal or clock control")
    capture_hwnd(window_hwnd(fa), OUT / "06-field-assistant.png")
    fa.destroy()
    settle()

    # --- 6. shootout from the page
    bridge.command("set_period", {"label": "SHOOTOUT", "confirmed": True}, app.service.revision)
    check(wait_for(lambda: state().period == "SHOOTOUT", 5), "SHOOTOUT period", state().period)
    settle()
    check(visible("#shootout-block") and not visible("#clock-block"), "shootout panel replaces the clock block")
    check(overflow_free(), "no page scroll in the shootout")
    click('#shootout-first-kicker-row [data-command="set_shootout_first_kicker"][data-team="home"]')
    check(wait_for(lambda: state().shootout_first_kicker == "home", 5), "HOME kicks first")
    settle()
    sequence = [("home", "made"), ("away", "missed"), ("home", "made"), ("away", "made"),
                ("home", "made"), ("away", "missed"), ("home", "made")]
    for team, outcome in sequence:
        n = len(state().shootout_kicks)
        click(f"#shootout-{team}-{outcome}")
        check(wait_for(lambda: len(state().shootout_kicks) == n + 1, 5), f"kick {n + 1}: {team} {outcome}")
        settle(0.7)
    view = bridge.get_snapshot()["soccer"]["shootout"]
    check(view["decided"] and view["derived_winner"] == "home", "shootout decided for HOME (4-1)", view["tally_display"])
    check(js("!document.getElementById('finish-shootout').disabled"), "FINISH SHOOTOUT enabled once decided")
    shot("07-shootout.png")
    click("#finish-shootout")
    settle(0.5)
    check(visible("#confirm-dialog"), "FINISH SHOOTOUT asks for confirmation")
    click("#confirm-accept")
    check(wait_for(lambda: state().period == "FINAL" and state().home_score == 2, 5),
          "FINAL with one goal credited to the shootout winner (2-0)", (state().period, state().home_score, state().away_score))
    settle()
    hidden = bridge.spectator_snapshot()["board"]["hidden_widgets"]
    check(hidden == ["game_clock_label", "game_clock_value"], "FINAL hides the clock widgets on the wall", hidden)
    shot("08-final.png")
    if host.spectator_window is not None:
        capture_hwnd(window_hwnd(host.spectator_window), OUT / "08-spectator-final.png")

    # --- 7. layout editor opens on the soccer registry
    bridge.open_layout_editor()
    check(wait_for(lambda: host.layout_window is not None, 10), "layout editor window opened")
    editor = host.layout_window
    check(wait_for(lambda: editor.evaluate_js("!!document.querySelector('#game-board [data-widget=\"home_shots\"]')"), 20),
          "editor board shows soccer widgets on first paint")
    check(editor.evaluate_js("!document.querySelector('#game-board [data-widget=\"play_clock_value\"], #game-board [data-widget=\"down\"]')"),
          "editor board shows no football widgets")
    settle(1.0)
    capture_hwnd(window_hwnd(editor), OUT / "09-editor.png")
    editor.destroy()

    # --- 8. history rows carry the sources
    rows = read_action_history(app.paths.database)
    sources = {row.get("source") for row in rows}
    check("field-assistant" in sources and any(s and s.startswith("operator") for s in sources),
          "history rows carry operator and field-assistant sources", sorted(s for s in sources if s))
    check(not (data_dir / "scoreboard.db").exists() and not (data_dir / "layouts.json").exists(),
          "a soccer session wrote no football files at the root")
    time.sleep(0.3)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text("", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="scoreboard-soccer-realrun-") as directory:
        data_dir = Path(directory)
        picker = SportPickerHost(resolve_paths(data_dir))
        threading.Timer(3.0, lambda: drive(picker, data_dir)).start()
        picker.run()

    failures = 0
    for ok, label, detail in RESULTS:
        line = ("PASS  " if ok else "FAIL  ") + label + (f"   [{detail}]" if detail != "" else "")
        print(line.encode("ascii", "backslashreplace").decode("ascii"))
        failures += 0 if ok else 1
    print(f"\n{len(RESULTS) - failures}/{len(RESULTS)} checks passed in the real pywebview runtime")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
