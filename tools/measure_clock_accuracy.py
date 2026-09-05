"""Measure the game clock against an independent reference (R-005).

Every automated clock test uses an injected fake clock, which proves the
arithmetic but never lets a real second pass. This script does the opposite: it
runs the real ``GameClock`` for a real twelve minutes and compares it to
``time.perf_counter``, which is a different system counter from the
``time.monotonic`` the engine reads.

Two numbers matter, and they answer different questions:

* the error at the end of a continuous run says whether remaining time drifts;
* the drift across several hundred stop/start cycles says whether pausing and
  resuming loses or gains the sub-second remainder.

The worst *sampled* error is reported too, but it is dominated by the gap
between reading the reference and reading the engine inside one sample, so read
it as a ceiling rather than as drift.

Run it from the repository root on the machine you want to characterise::

    .\\.venv\\Scripts\\python.exe tools\\measure_clock_accuracy.py

It takes twelve minutes, prints JSON, and writes nothing. A result from this
script is evidence about *that host*: R-005 asks for the production laptop,
under the real refresh loop and a real WebView2 window.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scoreboard.domain.clocks import GameClock  # noqa: E402
from scoreboard.domain.state import ClockValue  # noqa: E402

DURATION = 12 * 60.0
TOLERANCE = 0.25
PAUSE_RESUME_CYCLES = 400


def continuous_run() -> tuple[int, float, float]:
    """Run one full quarter without stopping, sampling four times a second."""

    clock = GameClock(value=ClockValue(DURATION))
    reference_start = time.perf_counter()
    clock = clock.start()
    worst = 0.0
    samples = 0

    while True:
        elapsed = time.perf_counter() - reference_start
        if elapsed >= DURATION - 0.5:
            break
        worst = max(worst, abs(clock.remaining_at() - (DURATION - elapsed)))
        samples += 1
        time.sleep(0.25)

    elapsed = time.perf_counter() - reference_start
    final = abs(clock.remaining_at() - (DURATION - elapsed))
    return samples, max(worst, final), final


def pause_resume_drift() -> float:
    """Stop and start repeatedly, counting only the time the clock was running."""

    clock = GameClock(value=ClockValue(DURATION))
    clock = clock.start()
    reference_running = 0.0

    for _ in range(PAUSE_RESUME_CYCLES + 1):
        started = time.perf_counter()
        time.sleep(0.005)
        clock = clock.stop()
        reference_running += time.perf_counter() - started
        time.sleep(0.002)  # Paused: the reference must not advance either.
        clock = clock.start()

    clock = clock.stop()
    return abs((DURATION - clock.remaining_at()) - reference_running)


def main() -> int:
    samples, worst, final = continuous_run()
    drift = pause_resume_drift()
    print(
        json.dumps(
            {
                "duration_seconds": DURATION,
                "samples": samples,
                "worst_absolute_error_seconds": round(worst, 6),
                "final_absolute_error_seconds": round(final, 6),
                "pause_resume_cycles": PAUSE_RESUME_CYCLES + 1,
                "pause_resume_drift_seconds": round(drift, 6),
                "tolerance_seconds": TOLERANCE,
                "within_tolerance": worst <= TOLERANCE and drift <= TOLERANCE,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
