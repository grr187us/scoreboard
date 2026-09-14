"""PL-5 evidence: drive the 4th-quarter clock to 0:00 in the REAL pywebview
operator window and take each branch of the Final / Overtime / Keep 4th prompt.

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl5.py
"""
from __future__ import annotations

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

    def js(expression: str):
        return operator.evaluate_js(expression)

    def state():
        return host.application.service.state

    def prompt_visible():
        return not js("document.getElementById('period-dialog').hidden")

    bridge = host.application.bridge

    def cmd(name, args=None):
        result = bridge.command(name, args or {}, host.application.service.revision)
        assert result["accepted"], result["error"]
        # Let the push carrying this revision reach the page before a page
        # control is clicked, as a human's next press always does.
        time.sleep(0.5)
        return result

    def run_clock_out(seconds: float = 2.0):
        cmd("game_clock_correct", {"seconds": seconds})
        js("document.getElementById('game-start').click()")
        check(wait_for(lambda: state().game_clock.running, 5), "game clock started from the page")

    time.sleep(1.0)
    js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    time.sleep(0.3)

    # --- 1st..3rd: expiry asks nothing
    for quarter in ("1st", "3rd"):
        cmd("set_quarter", {"label": quarter, "confirmed": True})
        run_clock_out(1.0)
        check(wait_for(lambda: js("document.getElementById('game-display').textContent") == "0:00", 6), f"{quarter} clock ran out to 0:00 on the page")
        time.sleep(0.5)
        check(not prompt_visible(), f"no prompt on expiry in the {quarter}")

    # --- 4th: the prompt appears at 0:00 with no other action
    cmd("set_quarter", {"label": "4th", "confirmed": True})
    run_clock_out(2.0)
    check(not prompt_visible(), "no prompt while the 4th-quarter clock is still running")
    check(wait_for(prompt_visible, 8), "the prompt appeared on its own when the 4th hit 0:00")
    check(js("document.getElementById('game-display').textContent") == "0:00", "page shows 0:00")
    check(js("document.getElementById('period-keep').textContent") == "Keep 4th", "Keep button names the 4th", js("document.getElementById('period-keep').textContent"))
    capture_hwnd(window_hwnd(operator), OUT / "pl5-01-prompt-at-zero-4th.png")

    # --- branch 1: Keep 4th (dismiss) -- nothing sent, re-armed by a second expiry
    revision = state().revision
    history = len(read_action_history(paths.database))
    js("document.getElementById('period-keep').click()")
    time.sleep(0.4)
    check(not prompt_visible(), "Keep 4th hid the prompt")
    check(state().revision == revision and len(read_action_history(paths.database)) == history and state().quarter == "4th",
          "Keep 4th sent nothing (revision, history, quarter unchanged)", (state().revision, state().quarter))
    time.sleep(0.6)
    check(not prompt_visible(), "the prompt stays down across pushes for the dismissed expiry")
    run_clock_out(1.0)
    check(wait_for(prompt_visible, 8), "restarting the clock and letting it run out re-armed the prompt")

    # --- branch 2: Overtime
    js("document.getElementById('period-overtime').click()")
    check(wait_for(lambda: state().quarter == "OT", 5), "Overtime set the quarter to OT", state().quarter)
    time.sleep(0.5)
    ot = host.application.service.rules.overtime_seconds
    check(state().game_clock.seconds == ot and not state().game_clock.running, f"OT loaded the configured {ot:.0f} s, stopped", state().game_clock)
    check(not prompt_visible(), "prompt gone after choosing Overtime")
    check(js("document.getElementById('game-display').textContent") == js("document.querySelector('[data-field=\"clocks.game.full_display\"]') ? document.querySelector('[data-field=\"clocks.game.full_display\"]').textContent : document.getElementById('game-display').textContent"),
          "page shows the full OT length")
    capture_hwnd(window_hwnd(operator), OUT / "pl5-02-overtime-loaded.png")

    # --- OT expiry asks again; branch 3: Final
    run_clock_out(1.0)
    check(wait_for(prompt_visible, 8), "the prompt appears again when OT runs out")
    check(js("document.getElementById('period-keep').textContent") == "Keep OT", "Keep button names OT")
    js("document.getElementById('period-final').click()")
    check(wait_for(lambda: state().quarter == "FINAL" and state().lifecycle == "FINAL", 6), "Final set the FINAL label and ended the game", (state().quarter, state().lifecycle))
    time.sleep(0.5)
    check(not prompt_visible(), "prompt gone after choosing Final")
    view = bridge.spectator_snapshot()
    check(view["board"]["hidden_widgets"] == ["game_clock_label", "game_clock_value", "play_clock_label", "play_clock_value"],
          "the board is told to hide both clocks (PL-4)", view["board"])
    rows = [r["command"] for r in read_action_history(paths.database)[-2:]]
    check(rows == ["set_quarter", "end_game"], "history shows set_quarter then end_game", rows)
    capture_hwnd(window_hwnd(operator), OUT / "pl5-03-final-chosen.png")

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
