"""Drive the REAL pywebview operator window and prove F3 and I4 there.

Development evidence, not part of the suite. A browser check runs the same
HTML/CSS/JS in Chromium; this runs it where it actually ships -- a WebView2
window created by pywebview, with the real `js_api` bridge attached -- which
is the only place the pywebview call path itself is exercised.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe .scratch\\f3-i4\\realrun_f3i4.py

It opens a real window, runs the checks from a worker thread (every
`evaluate_js` blocks on the WebView2 UI thread, so nothing here may run on
it), prints PASS/FAIL lines, and closes itself.
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

import webview

from scoreboard.host.app import ScoreboardApplication, WindowHost
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths

RESULTS: list[tuple[bool, str, object]] = []


def check(ok: bool, label: str, detail: object = "") -> None:
    RESULTS.append((bool(ok), label, detail))


def drive(host: WindowHost) -> None:
    window = host.operator_window
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if window.evaluate_js("!!document.getElementById('crowd-status')"):
                break
        except Exception:  # noqa: BLE001 - the window is still starting
            pass
        time.sleep(0.2)

    def js(expression: str):
        return window.evaluate_js(expression)

    def view() -> dict:
        return json.loads(js("JSON.stringify(window.pywebview.api.get_snapshot ? null : null)") or "null") or \
            host.application.bridge.get_snapshot()

    # --- The row is really on screen in WebView2, at the shipped window size
    check(js("!!document.querySelector('.crowd-bar')"), "crowd row exists in the real window")
    check(js("document.documentElement.scrollHeight === document.documentElement.clientHeight"),
          "no vertical overflow in the real window",
          js("document.documentElement.scrollHeight + ' vs ' + document.documentElement.clientHeight"))
    check(js("document.documentElement.scrollWidth === document.documentElement.clientWidth"),
          "no horizontal overflow in the real window")
    check(js("Array.from(document.querySelectorAll('.crowd-bar button'))"
             ".every(b => b.getBoundingClientRect().height >= 36)"),
          "every crowd button meets its 36px floor")
    check(js("document.getElementById('reopen-display').getBoundingClientRect().height === 44"),
          "C5's 44px Reopen Display is untouched")

    # --- F3 through the real bridge: click, do not synthesise
    before = host.application.bridge.get_snapshot()["revision"]
    js("document.getElementById('crowd-timeout').click()")
    time.sleep(1.2)
    after = host.application.bridge.get_snapshot()
    check(after["status"]["label"] == "TIMEOUT", "clicking TIMEOUT raised the message",
          after["status"]["label"])
    check(after["status"]["clock"]["running"], "and started its countdown",
          after["status"]["clock_display"])
    check(after["revision"] - before == 1, "in exactly one revision",
          after["revision"] - before)
    check(js("document.getElementById('crowd-status').textContent") == "TIMEOUT",
          "the operator chip shows it")

    # --- I4 through the real bridge
    js("document.querySelector('[data-command=\"add_score\"][data-team=\"home\"][data-points=\"6\"]').click()")
    time.sleep(1.0)
    js("document.querySelector('[data-command=\"add_score\"][data-team=\"away\"][data-points=\"3\"]').click()")
    time.sleep(1.0)
    stacked = host.application.bridge.get_snapshot()
    check(stacked["undo_depth"] == 2, "two scores stack two undo entries", stacked["undo_depth"])
    check([e["label"] for e in stacked["undo_history"]] ==
          ["AWAY score 0 → 3", "HOME score 0 → 6"],
          "the history is newest first",
          [e["label"] for e in stacked["undo_history"]])

    js("document.getElementById('last-action-button').click()")
    time.sleep(0.4)
    check(js("!document.getElementById('history-drawer').hidden"),
          "the LAST strip opens the history drawer")
    check(js("document.querySelectorAll('#history-list li').length") == 2,
          "the drawer lists both entries")
    check("next Undo" in (js("document.querySelector('#history-list li').textContent") or ""),
          "and marks which one Undo reverses next")

    js("document.querySelector('#history-drawer [data-command=\"undo\"]').click()")
    time.sleep(1.0)
    js("document.querySelector('#history-drawer [data-command=\"undo\"]').click()")
    time.sleep(1.0)
    final = host.application.bridge.get_snapshot()
    check(final["teams"]["home"]["score"] == 0 and final["teams"]["away"]["score"] == 0,
          "two Undos walked both scores back",
          f'{final["teams"]["home"]["score"]}-{final["teams"]["away"]["score"]}')
    check(final["status"]["label"] == "TIMEOUT",
          "and the crowd message was never spent by Undo", final["status"]["label"])
    check(final["can_undo"] is False, "the stack is now empty")

    time.sleep(0.5)
    window.destroy()


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
        # A Windows console is cp1252; the history labels carry a real arrow.
        print(line.encode("ascii", "backslashreplace").decode("ascii"))
        failures += 0 if ok else 1
    print(f"\n{len(RESULTS) - failures}/{len(RESULTS)} checks passed in the real pywebview runtime")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
