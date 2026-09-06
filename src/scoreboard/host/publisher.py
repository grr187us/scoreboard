"""Bounded, latest-wins delivery of view models to webview windows (C4).

``ScoreboardApplication`` builds a formatted view model ten times a second and
after every accepted command; ``WindowHost`` is where that view model finally
reaches a real window through pywebview's ``evaluate_js``. The installed
WebView2 backend implements ``evaluate_js`` as ``Invoke(...)`` followed by an
unbounded ``Semaphore(0).acquire()`` (``edgechromium.py``): if the UI thread
ever stalls, that call blocks forever, and there is no non-blocking primitive
underneath it to fall back to.

Before this module existed, that blocking call ran directly inside
``ScoreboardApplication._publish``, which ran under the same lock every score,
clock, and quarter command needed. One stuck window could therefore freeze the
whole board. The fix is not to make ``evaluate_js`` non-blocking -- it cannot
be, from here -- but to move the wait to the one place a stall can only ever
block *presentation*, never a command: a dedicated delivery thread that the
tick and the bridge merely hand a view model to.

Design
------

* :meth:`WindowPublisher.offer` never blocks and never raises. Before
  :meth:`WindowPublisher.start` is called it delivers inline (synchronously),
  which keeps every existing host test -- built around a fake window whose
  ``evaluate_js`` just records a script -- exactly as deterministic as before
  this module existed.
* Once started, ``offer`` stores the latest view per window name and wakes one
  background thread. A newer offer for a window that has not been delivered
  yet simply replaces the old one: the operator only ever needs the current
  state on screen, never a queue of everything that happened while a window
  was slow.
* The thread delivers in a fixed, sensible order -- operator, then spectator,
  then the optional Field Assistant, then anything else -- catching every
  exception from the injected ``deliver`` callable so a bug in one window's
  push can never stop the thread from trying the next one.
* A delivery running longer than ``stall_after`` is reported once through
  ``on_stall``; when it finally completes, ``on_recovered`` is called once.
  Both are advisory (diagnostics only) and never affect delivery itself.
* :meth:`WindowPublisher.stop` never blocks past its timeout, even if the
  thread is stuck inside a genuinely stalled ``evaluate_js``: Python cannot
  forcibly stop a thread, so a stuck delivery is simply abandoned and the
  thread -- a daemon -- is left to finish or die with the process.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Final

#: How long a single delivery may run before it is worth telling the operator
#: about through diagnostics. This is advisory only -- it never cancels or
#: times out the delivery itself, which is not possible through pywebview.
PUBLISH_STALL_SECONDS: Final[float] = 2.0

#: The order the delivery thread drains window slots in when more than one is
#: waiting. Anything else offered (a name outside this tuple) is drained last,
#: in no particular order, which is fine: nothing today offers a fourth name.
_WINDOW_ORDER: Final[tuple[str, ...]] = ("operator", "spectator", "field_assistant")

#: How often the delivery thread wakes on its own even with no offer, purely
#: as a safety net -- every real wakeup is driven by ``offer`` setting the
#: wake event, so this bounds only how quickly a missed wake is noticed.
_POLL_SECONDS: Final[float] = 0.2


class WindowPublisher:
    """Latest-wins, one-thread delivery of view models to webview windows."""

    def __init__(
        self,
        deliver: Callable[[str, dict[str, Any]], None],
        *,
        on_stall: Callable[[str, float], None] | None = None,
        on_recovered: Callable[[str, float], None] | None = None,
        stall_after: float = PUBLISH_STALL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._deliver_one = deliver
        self._on_stall = on_stall
        self._on_recovered = on_recovered
        self._stall_after = stall_after
        self._monotonic = monotonic
        self._state_lock = threading.Lock()
        self._latest: dict[str, dict[str, Any]] = {}
        self._wake = threading.Event()
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None
        self._in_flight: tuple[str, float] | None = None
        self._stall_reported = False

    # --- The public contract -------------------------------------------------

    def offer(self, window_name: str, view: dict[str, Any]) -> None:
        """Hand off one view for delivery. Never blocks; never raises."""

        try:
            if self._thread is None:
                # Not started: every existing host test built around a fake,
                # synchronously-recording window relies on this staying inline.
                self._deliver_safely(window_name, view)
                return
            with self._state_lock:
                self._latest[window_name] = view
            self._wake.set()
            self._check_stall()
        except Exception:  # noqa: BLE001 - "never raises" is the whole contract
            pass

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_flag.clear()
        thread = threading.Thread(target=self._run, name="scoreboard-publish", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the thread to stop and wait briefly. Never raises.

        If the thread is stuck inside a genuinely stalled delivery this
        returns anyway once ``timeout`` elapses -- Python has no way to force
        a thread to abandon a blocking call -- and the (daemon) thread is left
        to finish on its own or die with the process.
        """

        self._stop_flag.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is None:
            return
        try:
            thread.join(timeout=timeout)
        except Exception:  # noqa: BLE001 - stop() must never raise
            pass

    @property
    def started(self) -> bool:
        return self._thread is not None

    @property
    def in_flight(self) -> tuple[str, float] | None:
        with self._state_lock:
            return self._in_flight

    # --- The delivery thread ---------------------------------------------------

    def _run(self) -> None:
        while True:
            self._wake.wait(timeout=_POLL_SECONDS)
            self._wake.clear()
            self._drain()
            if self._stop_flag.is_set() and not self._has_pending():
                return

    def _has_pending(self) -> bool:
        with self._state_lock:
            return bool(self._latest)

    def _drain(self) -> None:
        while True:
            picked = self._take_next()
            if picked is None:
                return
            name, view = picked
            self._deliver_and_report(name, view)

    def _take_next(self) -> tuple[str, dict[str, Any]] | None:
        with self._state_lock:
            for name in _WINDOW_ORDER:
                if name in self._latest:
                    return name, self._latest.pop(name)
            for name in tuple(self._latest):
                return name, self._latest.pop(name)
            return None

    def _deliver_and_report(self, name: str, view: dict[str, Any]) -> None:
        started_at = self._monotonic()
        with self._state_lock:
            self._in_flight = (name, started_at)
            self._stall_reported = False
        self._deliver_safely(name, view)
        with self._state_lock:
            self._in_flight = None
            stall_reported = self._stall_reported
        if stall_reported and self._on_recovered is not None:
            elapsed = self._monotonic() - started_at
            self._call_hook(self._on_recovered, name, elapsed)

    def _deliver_safely(self, name: str, view: dict[str, Any]) -> None:
        try:
            self._deliver_one(name, view)
        except Exception:  # noqa: BLE001 - the thread must never die from this
            pass

    # --- Stall detection, driven by the caller of offer() -----------------------

    def _check_stall(self) -> None:
        with self._state_lock:
            in_flight = self._in_flight
            already_reported = self._stall_reported
        if in_flight is None or already_reported:
            return
        name, started_at = in_flight
        elapsed = self._monotonic() - started_at
        if elapsed < self._stall_after:
            return
        with self._state_lock:
            if self._in_flight != in_flight:
                return  # it finished in the meantime; nothing to report
            self._stall_reported = True
        self._call_hook(self._on_stall, name, elapsed)

    @staticmethod
    def _call_hook(
        hook: Callable[[str, float], None] | None, name: str, elapsed: float
    ) -> None:
        if hook is None:
            return
        try:
            hook(name, elapsed)
        except Exception:  # noqa: BLE001 - a diagnostics hook must not break delivery
            pass


__all__ = ["PUBLISH_STALL_SECONDS", "WindowPublisher"]
