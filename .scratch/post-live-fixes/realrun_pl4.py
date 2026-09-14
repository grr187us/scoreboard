"""PL-4 evidence: FINAL hides both clocks on every preset in the REAL pywebview
spectator (practice) window, pushed by the live host, while the operator
window keeps showing the clock.

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl4.py
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
from scoreboard.presentation.layout import preset_descriptors  # noqa: E402

RESULTS: list[tuple[bool, str, object]] = []
OUT = Path(__file__).resolve().parent / "evidence"
CLOCKS = ["game_clock_label", "game_clock_value", "play_clock_label", "play_clock_value"]


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


def drive(host: WindowHost) -> None:
    operator = host.operator_window
    wait_for(lambda: operator.evaluate_js("!!document.getElementById('home-arm')"), 30)

    def op(expression: str):
        return operator.evaluate_js(expression)

    bridge = host.application.bridge

    def cmd(name, args=None):
        result = bridge.command(name, args or {}, host.application.service.revision)
        assert result["accepted"], result["error"]
        return result

    time.sleep(1.0)
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    host.open_test_window()
    wait_for(lambda: host.test_window is not None, 5)
    board = host.test_window
    wait_for(lambda: board.evaluate_js("!!document.querySelector('[data-widget=\"quarter\"]')"), 30)
    time.sleep(0.8)

    def sp(expression: str):
        return board.evaluate_js(expression)

    def clocks():
        return json.loads(sp("JSON.stringify((function(){var o={};" + json.dumps(CLOCKS) + ".forEach(function(id){var e=document.querySelector('[data-widget=\"'+id+'\"]');o[id]=e?{hidden:e.hidden,hasValue:e.dataset.hasValue,layoutVisible:e.dataset.layoutVisible}:null;});"
                                "o.quarter=document.querySelector('[data-widget=\"quarter\"] .widget-text').textContent;"
                                "o.elements=Array.from(document.querySelectorAll('[data-element]')).filter(function(n){return /^(game|play)_clock_/.test(n.getAttribute('data-element'));}).map(function(n){return [n.getAttribute('data-element'), n.hidden];});return o;})())"))

    cmd("set_quarter", {"label": "4th", "confirmed": True})
    cmd("play_clock_preset", {"seconds": 40})
    cmd("game_clock_correct", {"seconds": 83})
    for preset in preset_descriptors():
        saved = host.application.layouts.save(f"PL4 {preset['name']}"[:24], preset["layout"])
        check(saved.get("saved", False) or saved.get("validation", {}).get("ok", True), f"[{preset['id']}] preset applied through the layout library", saved.get("message"))
        time.sleep(0.8)
        before = clocks()
        visible_ids = [i for i in CLOCKS if before[i]["layoutVisible"] == "1"]
        check(all(before[i]["hasValue"] == "1" for i in CLOCKS) and all(not before[i]["hidden"] for i in visible_ids),
              f"[{preset['id']}] 4th quarter: the clocks the preset shows are on the wall", before)
        cmd("set_quarter", {"label": "FINAL", "confirmed": True})
        check(wait_for(lambda: clocks()["quarter"] == "FINAL", 5), f"[{preset['id']}] FINAL reached the wall", clocks()["quarter"])
        time.sleep(0.4)
        after = clocks()
        check(all(after[i]["hidden"] and after[i]["hasValue"] == "0" for i in CLOCKS),
              f"[{preset['id']}] FINAL: no clock digits and no clock captions", after)
        check(all(hidden for _, hidden in after["elements"]),
              f"[{preset['id']}] FINAL: {len(after['elements'])} clock-framing element(s) hidden too", after["elements"])
        check(op("document.getElementById('game-display').textContent") == "1:23"
              and op("document.getElementById('play-display').textContent") == "40",
              f"[{preset['id']}] operator page still shows 1:23 and 40 on FINAL",
              (op("document.getElementById('game-display').textContent"), op("document.getElementById('play-display').textContent")))
        capture_hwnd(window_hwnd(board), OUT / f"pl4-realrun-{preset['id']}-final.png")
        cmd("set_quarter", {"label": "4th", "confirmed": True})
        check(wait_for(lambda: clocks()["quarter"] != "FINAL", 5), f"[{preset['id']}] back to the 4th")
        time.sleep(0.4)
        restored = clocks()
        check(all(restored[i]["hasValue"] == "1" for i in CLOCKS) and all(not restored[i]["hidden"] for i in visible_ids)
              and all(not hidden for _, hidden in restored["elements"]),
              f"[{preset['id']}] leaving FINAL restores the clocks and frames", restored)

    # End Game alone (lifecycle FINAL, quarter label unchanged) hides them too.
    cmd("end_game")
    check(wait_for(lambda: all(clocks()[i]["hidden"] for i in CLOCKS), 5), "End Game (lifecycle FINAL) hides the clocks as well")
    capture_hwnd(window_hwnd(operator), OUT / "pl4-realrun-operator-final.png")

    time.sleep(0.3)
    board.destroy()
    time.sleep(0.2)
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
