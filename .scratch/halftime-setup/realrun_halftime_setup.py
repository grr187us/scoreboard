"""Drive the REAL pywebview operator window: halftime on the game clock + Setup.

Development evidence, not part of the suite (September 9, 2026). Mirrors
``.scratch/control-refresh/realrun_control_refresh.py``: the checks run from a
worker thread because every ``evaluate_js`` blocks on the WebView2 UI thread.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe .scratch\\halftime-setup\\realrun_halftime_setup.py
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from scoreboard.host.app import ScoreboardApplication, WindowHost
from scoreboard.infrastructure import config
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


def set_field(js, element_id: str, value) -> None:
    js(f"(function(){{var f=document.getElementById('{element_id}'); f.value='{value}';"
       "f.dispatchEvent(new Event('input',{bubbles:true}));})()")


def drive(host: WindowHost, paths) -> None:
    window = host.operator_window
    wait_for(lambda: window.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def js(expression: str):
        return window.evaluate_js(expression)

    def snap() -> dict:
        return host.application.bridge.get_snapshot()

    time.sleep(1.0)
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # --- 1. The halftime drawer is gone; the clock card is named by Python
    check(js("document.getElementById('event-drawer') === null"), "no Halftime drawer in the real window")
    check(js("document.getElementById('open-event') === null"), "no Halftime tool-bar button")
    check(js("document.querySelector('.clocks h2').textContent") == "KICKOFF COUNTDOWN",
          "clock card reads KICKOFF COUNTDOWN in PRE",
          js("document.querySelector('.clocks h2').textContent"))
    check(js("document.getElementById('game-minutes').max") == "30", "correction field max follows the 30:00 kickoff")
    check(js("document.querySelectorAll('.tools [data-command]').length") == 0, "the tool bar holds no data-command")

    # --- 2. Setup opens and is filled from api.rules()
    js("document.getElementById('open-setup').click()")
    time.sleep(0.5)
    check(js("!document.getElementById('setup-drawer').hidden"), "Setup drawer opens")
    check(js("document.getElementById('rule-halftime-minutes').value") == "15",
          "halftime field filled from Python (15)", js("document.getElementById('rule-halftime-minutes').value"))
    check(js("document.getElementById('rule-timeouts-per-half').value") == "3", "timeouts per half filled (3)")
    check(js("document.getElementById('setup-drawer').querySelectorAll('[data-command]').length") == 0,
          "the Setup drawer holds no data-command")

    # --- 3. Save through the real bridge: no revision, config.json written
    revision = snap()["revision"]
    set_field(js, "rule-halftime-minutes", 10)
    set_field(js, "rule-warmup-minutes", 2)
    set_field(js, "rule-timeout-seconds", 45)
    set_field(js, "rule-timeouts-per-half", 2)
    js("document.querySelector('#setup-drawer [data-action=\"save_rules\"]').click()")
    time.sleep(1.0)
    note = js("document.getElementById('rules-note').textContent") or ""
    check(note.startswith("Rules saved."), "the drawer shows Python's saved sentence", note)
    check(snap()["revision"] == revision, "saving rules advanced no revision")
    stored = json.loads(paths.config.read_text(encoding="utf-8"))
    check(stored.get(config.RULES_SECTION, {}).get("halftime_seconds") == 600,
          "config.json holds the new halftime length", stored.get(config.RULES_SECTION))
    check(host.application.rules.timeout_seconds == 45, "the host's copy of the rules moved too")
    check(js("document.getElementById('crowd-timeout').dataset.seconds") == "45",
          "the crowd TIMEOUT button now carries 45 seconds")
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # --- 4. A refused save changes nothing and says why
    js("document.getElementById('open-setup').click()")
    time.sleep(0.4)
    set_field(js, "rule-quarter-minutes", 0)
    set_field(js, "rule-quarter-seconds", 30)
    js("document.querySelector('#setup-drawer [data-action=\"save_rules\"]').click()")
    time.sleep(0.8)
    refused = js("document.getElementById('rules-note').textContent") or ""
    check("Quarter length" in refused, "a 0:30 quarter is refused with Python's sentence", refused)
    check(host.application.rules.quarter_seconds == 720, "and the quarter length did not move")
    js("document.querySelector('#setup-drawer [data-action=\"restore_default_rules\"]').click()")
    time.sleep(0.3)
    check(js("document.getElementById('rule-quarter-minutes').value") == "12", "Restore defaults refills the fields")
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # --- 5. Halftime runs on the game clock with the saved 10:00
    bridge = host.application.bridge
    bridge.command("set_quarter", {"label": "2nd", "confirmed": True}, snap()["revision"])
    bridge.command("set_quarter", {"label": "HALF", "confirmed": True}, snap()["revision"])
    time.sleep(0.8)
    check(js("document.querySelector('.clocks h2').textContent") == "HALFTIME COUNTDOWN",
          "clock card reads HALFTIME COUNTDOWN in HALF")
    check(js("document.getElementById('game-display').textContent") == "10:00",
          "the card shows the configured 10:00", js("document.getElementById('game-display').textContent"))
    check(js("document.getElementById('game-minutes').max") == "10", "correction field max follows 10:00")
    js("document.getElementById('game-start').click()")
    time.sleep(1.5)
    view = snap()
    check(view["clocks"]["game"]["running"], "the page's START runs the halftime countdown")
    check(view["clocks"]["event"]["title"] == "UNTIL SECOND HALF" and view["clocks"]["event"]["running"],
          "the spectator event block reads the same running clock", view["clocks"]["event"])
    check(view["clocks"]["event"]["warmup_follows"] == "2:00", "warmup line follows the saved 2:00",
          view["clocks"]["event"]["warmup_follows"])
    js("document.getElementById('game-stop').click()")
    time.sleep(0.8)
    check(not snap()["clocks"]["game"]["running"], "STOP stops it")

    # --- 6. Crowd TIMEOUT sends the configured length through the airlock
    js("document.getElementById('crowd-timeout').click()")
    time.sleep(0.8)
    status = snap()["status"]
    check(status["label"] == "TIMEOUT" and status["clock_display"] == "0:45",
          "TIMEOUT raised with a 0:45 countdown", status)

    # --- 7. Second half restores two timeouts a side
    bridge.command("set_quarter", {"label": "3rd", "confirmed": True}, snap()["revision"])
    time.sleep(0.8)
    view = snap()
    check(view["football"]["timeouts"] == {"home": 2, "away": 2}, "3rd loads two timeouts a side", view["football"]["timeouts"])
    check(view["clocks"]["game"]["display"] == "12:00" and js("document.querySelector('.clocks h2').textContent") == "GAME CLOCK",
          "and the card is GAME CLOCK at 12:00 again")
    check(js("document.documentElement.scrollHeight === document.documentElement.clientHeight && "
             "document.documentElement.scrollWidth === document.documentElement.clientWidth"),
          "no overflow in the real window (U-001)")

    time.sleep(0.5)
    window.destroy()


def main() -> int:
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
