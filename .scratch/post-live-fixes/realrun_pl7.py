"""PL-7 evidence: swap sides in the 2nd quarter from the REAL pywebview Field
Assistant (press-again confirm) and from the operator Field drawer; the
end-zone labels mirror and the ball stays on its yard line.

Development evidence, not part of the suite (September 14, 2026). Run from
the repository root with PYTHONIOENCODING=utf-8:
    .\\.venv\\Scripts\\python.exe .scratch\\post-live-fixes\\realrun_pl7.py
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

    bridge = host.application.bridge

    def cmd(name, args=None):
        result = bridge.command(name, args or {}, host.application.service.revision)
        assert result["accepted"], result["error"]
        time.sleep(0.5)
        return result

    time.sleep(1.0)
    op("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}))")
    op("document.getElementById('open-field-assistant').click()")
    wait_for(lambda: host.field_assistant_window is not None, 10)
    helper = host.field_assistant_window
    wait_for(lambda: helper.evaluate_js("!!document.getElementById('confirm') && !!window.pywebview"), 30)
    time.sleep(1.0)

    def fa(expression: str):
        return helper.evaluate_js(expression)

    def fa_state():
        return json.loads(fa("JSON.stringify({left:document.getElementById('endzone-left').textContent,"
                             "right:document.getElementById('endzone-right').textContent,"
                             "ball:document.getElementById('ball').dataset.absolute,"
                             "ballLeft:document.getElementById('ball').style.left,"
                             "ltg:document.getElementById('line-to-gain').style.left,"
                             "ltgHidden:document.getElementById('line-to-gain').hidden,"
                             "swapHidden:document.getElementById('swap-sides').hidden,"
                             "swapLabel:document.getElementById('swap-sides').textContent,"
                             "swapArmed:document.getElementById('swap-sides').getAttribute('aria-pressed'),"
                             "direction:document.getElementById('direction').textContent,"
                             "notice:document.getElementById('notice').textContent,"
                             "down:document.getElementById('current-down').textContent,"
                             "spot:document.getElementById('current-spot').textContent})"))

    # --- before a direction is saved the swap control is not offered
    check(fa_state()["swapHidden"], "Swap sides hidden until a direction is saved")
    swap_refused = bridge.command("set_assistant_direction", {"swap": True}, state().revision)
    check(not swap_refused["accepted"] and "No direction is saved yet" in swap_refused["error"]["message"],
          "a drawer swap before any direction is refused with a sentence", swap_refused["error"])

    # --- opening series from the assistant, HOME scores to the RIGHT
    fa("document.querySelector('[data-direction=\"1\"]').click()")
    time.sleep(0.3)
    fa("(function(){var t=document.getElementById('spot-team');t.value='home';t.dispatchEvent(new Event('change'));"
       "var y=document.getElementById('spot-yard');y.value='25';y.dispatchEvent(new Event('change'));})()")
    fa("document.querySelector('[data-action=\"start_series\"][data-team=\"home\"]').click()")
    check(wait_for(lambda: not fa("document.getElementById('confirm').disabled"), 5), "series previewed")
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().assistant_first_quarter_home_direction == 1 and state().down == 1, 5), "direction +1 saved with the opening series")
    time.sleep(0.5)
    fa("document.querySelector('[data-action=\"normal_play\"]').click()")
    fa("document.getElementById('nudge-right-5').click()")
    check(wait_for(lambda: not fa("document.getElementById('confirm').disabled"), 5), "a play to HOME 30 previewed")
    fa("document.getElementById('confirm').click()")
    check(wait_for(lambda: state().ball_on.yard_line == 30 and state().down == 2, 5), "2nd & 5 at HOME 30 committed", (state().down, state().distance, state().ball_on))
    time.sleep(0.5)

    # --- 2nd quarter: HOME goal drawn on the right; then swap from the assistant
    cmd("set_quarter", {"label": "2nd", "confirmed": True})
    before = fa_state()
    check(before["right"].startswith("HOME") and before["left"].startswith("AWAY"), "2nd quarter: HOME goal drawn on the RIGHT", (before["left"], before["right"]))
    check(not before["swapHidden"] and before["swapArmed"] == "false", "Swap sides offered, unarmed", before)
    revision = state().revision
    fa("document.getElementById('swap-sides').click()")
    time.sleep(0.3)
    armed = fa_state()
    check(armed["swapArmed"] == "true" and "PRESS AGAIN" in armed["swapLabel"] and state().revision == revision,
          "first press arms and sends nothing", (armed["swapLabel"], state().revision))
    capture_hwnd(window_hwnd(helper), OUT / "pl7-01-assistant-swap-armed-2nd.png")
    fa("document.getElementById('swap-sides').click()")
    check(wait_for(lambda: state().assistant_first_quarter_home_direction == -1, 5), "second press swapped the saved direction to -1")
    time.sleep(0.6)
    after = fa_state()
    check(after["left"].startswith("HOME") and after["right"].startswith("AWAY"), "end-zone labels mirrored: HOME goal now on the LEFT", (after["left"], after["right"]))
    check(after["ball"] == before["ball"] == "30", "draft ball still on HOME 30", (before["ball"], after["ball"]))
    check(after["ballLeft"] != before["ballLeft"], "...drawn on the mirrored side", (before["ballLeft"], after["ballLeft"]))
    check(after["down"] == before["down"] == "2nd & 5" and after["spot"] == before["spot"] == "HOME 30", "down, distance, ball on unchanged", (after["down"], after["spot"]))
    check(state().assistant_line_to_gain == 35 and not after["ltgHidden"] and after["ltg"] != before["ltg"], "line to gain still 35, drawn mirrored", (state().assistant_line_to_gain, before["ltg"], after["ltg"]))
    check(state().ball_on.yard_line == 30 and state().down == 2 and state().distance == 5, "Python field state untouched by the swap", (state().ball_on, state().down, state().distance))
    check(after["swapArmed"] == "false" and "Sides swapped" in after["notice"], "button disarmed and the notice says what happened", after["notice"])
    rows = read_action_history(paths.database)
    check(rows[-1]["command"] == "set_assistant_direction" and rows[-1]["source"] == "field-assistant", "history row: set_assistant_direction from field-assistant", (rows[-1]["command"], rows[-1]["source"]))
    last = op("document.getElementById('last-action').textContent")
    check("Sides" in last and "right" in last and "left" in last, "operator LAST strip names the swap", last)
    capture_hwnd(window_hwnd(helper), OUT / "pl7-02-assistant-after-swap-2nd.png")

    # --- Undo from the operator window reverses it
    op("document.getElementById('undo').click()")
    time.sleep(0.3)
    op("document.getElementById('confirm-accept').click()")
    check(wait_for(lambda: state().assistant_first_quarter_home_direction == 1, 5), "Undo restored direction +1")
    time.sleep(0.6)
    undone = fa_state()
    check(undone["right"].startswith("HOME") and undone["ball"] == "30", "assistant mirrored back, ball still HOME 30", (undone["left"], undone["right"], undone["ball"]))

    # --- the operator Field drawer swaps too (local confirm)
    op("document.getElementById('open-field').click()")
    time.sleep(0.3)
    op("document.querySelector('#field-drawer [data-command=\"set_assistant_direction\"]').click()")
    time.sleep(0.3)
    check(not op("document.getElementById('confirm-dialog').hidden"), "drawer swap asks first")
    op("document.getElementById('confirm-accept').click()")
    check(wait_for(lambda: state().assistant_first_quarter_home_direction == -1, 5), "drawer swap flipped the direction")
    time.sleep(0.6)
    drawer = fa_state()
    check(drawer["left"].startswith("HOME") and drawer["ball"] == "30", "assistant picked the drawer swap up without a reload", (drawer["left"], drawer["ball"]))
    capture_hwnd(window_hwnd(operator), OUT / "pl7-03-operator-field-drawer-swap.png")
    op("document.querySelector('#field-drawer [data-action=\"close_drawer\"]').click()")

    # --- pressing the saved side again does nothing; the other side arms a swap
    revision = state().revision
    fa("document.getElementById('swap-sides').click()")  # arm
    time.sleep(0.2)
    fa("document.getElementById('swap-sides').click()")  # fire -> +1
    check(wait_for(lambda: state().assistant_first_quarter_home_direction == 1, 5), "swap back to +1 from the assistant")
    time.sleep(0.5)
    revision = state().revision
    fa("document.querySelector('[data-open=\"manual\"]').click()")  # any panel; direction panel is not shown once saved
    time.sleep(0.2)
    fa("document.querySelector('[data-back]') && document.querySelector('[data-panel=\"manual\"] [data-back]').click()")
    time.sleep(0.2)
    check(state().revision == revision, "no stray direction command from panel navigation")

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
