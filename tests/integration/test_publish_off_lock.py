"""C4: the command lock is free of publishing, and a broken command fails safe.

Four things are proven here, none of them by sleeping for real time:

* a command submitted while a window push is still blocked completes anyway
  (mirrors the C2 "the open picker does not hold up the game" test in
  ``test_data_folder.py``);
* the ``(revision, seq)`` delivery-ordering guard drops a batch delivered out
  of order rather than repainting a window with stale data;
* ``ScoreboardBridge.command()``'s catch-all turns an unexpected exception
  into a safe ``INTERNAL_ERROR`` rejection with a complete view, a diagnostics
  entry, and an untouched store;
* ``on_accepted`` genuinely runs with the command lock released, not merely
  after the code that built its argument.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from unittest import mock

from scoreboard.host.app import ScoreboardApplication, _PublishBatch
from scoreboard.host.bridge import INTERNAL_ERROR, ScoreboardBridge
from scoreboard.infrastructure.diagnostics import NullDiagnostics

from tests.integration.support import TemporaryDataDirectoryTest

WAIT_TIMEOUT = 2.0

#: The fake blocking publisher's own safety-valve wait -- long enough that a
#: command which actually had to wait behind it is unambiguous (the assertion
#: below requires the command to finish in well under a second), but bounded
#: so a genuine regression fails this test in seconds rather than hanging it.
BLOCKED_PUSH_SAFETY_VALVE_SECONDS = 5.0


class OffLockApplicationTest(TemporaryDataDirectoryTest):
    """A real, window-free application -- exactly what Task 7 built this for."""

    def make_application(self, **kwargs: Any) -> ScoreboardApplication:
        kwargs.setdefault("diagnostics", NullDiagnostics())
        kwargs.setdefault("monotonic_clock", self.monotonic)
        kwargs.setdefault("acquire_lock", False)
        application = ScoreboardApplication(self.paths, **kwargs)
        self.addCleanup(application.shutdown)
        return application


class CommandLockIsFreeDuringPublishTests(OffLockApplicationTest):
    def test_a_command_completes_while_a_window_push_is_still_blocked(self) -> None:
        """A stalled window must never hang the command every control needs.

        The installed publisher blocks the *first* delivery it is ever asked
        to make to the operator window -- standing in for a WebView2 UI thread
        that has stalled inside ``evaluate_js`` (ARCHITECTURE.md §8, C4). A
        second delivery -- the one this command's own acceptance triggers --
        must not need that first one to finish: only the command lock, which
        this test proves is already free by the time the command runs.
        """

        application = self.make_application()
        bridge = application.start_new()

        push_started = threading.Event()
        release_push = threading.Event()
        blocked_once = {"done": False}

        def blocking_push(name: str, view: dict) -> None:
            if name == "operator" and not blocked_once["done"]:
                blocked_once["done"] = True
                push_started.set()
                # A safety valve, not the proof: if the command below ever had
                # to wait behind this, it would still eventually go through
                # once this returns, which would hide the regression as
                # "slow" rather than catch it. The timing assertion below is
                # the actual proof; this bound just keeps a real regression
                # from hanging the suite instead of failing it.
                release_push.wait(timeout=BLOCKED_PUSH_SAFETY_VALVE_SECONDS)

        application.set_publisher(blocking_push)

        tick_done = threading.Event()

        def run_tick() -> None:
            application.tick()
            tick_done.set()

        worker = threading.Thread(target=run_tick)
        worker.start()
        self.assertTrue(
            push_started.wait(timeout=WAIT_TIMEOUT),
            "the tick never reached the blocking window push",
        )

        # The whole point of C4: the command lock must be free right now, even
        # though a delivery from the tick is still blocked mid-push. Measure
        # it: without the fix, this call blocks behind the command lock (held
        # by the stuck tick) until the safety valve above releases it several
        # seconds later, which "passes" on acceptance alone but is exactly the
        # freeze C4 exists to prevent -- so the timing assertion is required,
        # not incidental.
        began = time.monotonic()
        result = bridge.command("game_clock_start", {}, 0)
        elapsed = time.monotonic() - began

        release_push.set()
        worker.join(timeout=WAIT_TIMEOUT)

        self.assertTrue(tick_done.is_set(), "the blocked tick never returned")
        self.assertTrue(result["accepted"], result.get("error"))
        self.assertTrue(application.service.state.game_clock.running)
        self.assertLess(
            elapsed,
            1.0,
            f"command() waited {elapsed:.2f}s behind the blocked window push",
        )


class OrderingGuardTests(OffLockApplicationTest):
    """A batch behind the last one actually delivered must never repaint a window."""

    def make_delivering_application(self) -> tuple[ScoreboardApplication, list[tuple[str, dict]]]:
        application = self.make_application()
        application.start_new()
        pushed: list[tuple[str, dict]] = []
        application.set_publisher(lambda name, view: pushed.append((name, view)))
        return application, pushed

    def test_a_batch_behind_the_last_delivered_key_is_dropped_silently(self) -> None:
        application, pushed = self.make_delivering_application()
        newer = _PublishBatch(2, 0, {"revision": 0, "marker": "newer"}, {"marker": "newer"})
        older = _PublishBatch(1, 0, {"revision": 0, "marker": "older"}, {"marker": "older"})

        application._deliver(newer)
        pushed.clear()
        application._deliver(older)

        self.assertEqual(pushed, [], "a stale (revision, seq) must not reach a window")

    def test_a_lower_revision_is_also_dropped_even_with_a_higher_seq(self) -> None:
        application, pushed = self.make_delivering_application()
        newer = _PublishBatch(1, 5, {"revision": 5, "marker": "newer"}, {"marker": "newer"})
        stale_but_higher_seq = _PublishBatch(
            9, 4, {"revision": 4, "marker": "stale"}, {"marker": "stale"}
        )

        application._deliver(newer)
        pushed.clear()
        application._deliver(stale_but_higher_seq)

        self.assertEqual(pushed, [], "(revision, seq) compares revision first")

    def test_increasing_seq_at_the_same_revision_is_never_dropped(self) -> None:
        """Clock refreshes between commands share a revision but must all land."""

        application, pushed = self.make_delivering_application()
        first = _PublishBatch(1, 3, {"revision": 3, "marker": "a"}, {"marker": "a"})
        second = _PublishBatch(2, 3, {"revision": 3, "marker": "b"}, {"marker": "b"})

        application._deliver(first)
        application._deliver(second)

        names_and_markers = [(name, view["marker"]) for name, view in pushed]
        self.assertIn(("operator", "a"), names_and_markers)
        self.assertIn(("operator", "b"), names_and_markers)


class CommandCatchAllTests(OffLockApplicationTest):
    def test_an_unexpected_exception_returns_a_safe_rejection_and_is_logged(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        status_before = bridge.get_snapshot()["health"]["persistence"]

        with mock.patch.object(
            application.service, "submit", side_effect=RuntimeError("boom")
        ), mock.patch.object(application.diagnostics, "unhandled_error") as unhandled:
            result = bridge.command("game_clock_start", {}, 0)

        self.assertFalse(result["accepted"])
        self.assertFalse(result["confirmation_required"])
        self.assertIsNone(result["event"])
        self.assertIsNone(result["confirmation"])
        self.assertEqual(result["error"]["code"], INTERNAL_ERROR)
        self.assertIn("view", result)
        json.dumps(result["view"])  # a complete, JSON-safe view, not a partial one
        self.assertEqual(result["view"]["revision"], 0)

        unhandled.assert_called_once()
        _, kwargs = unhandled.call_args
        self.assertEqual(kwargs["context"], "command")
        self.assertEqual(kwargs["command"], "game_clock_start")

        # Nothing about the store's status changed: the exception happened
        # before any record_command call could run.
        self.assertEqual(bridge.get_snapshot()["health"]["persistence"], status_before)
        self.assertFalse(application.service.state.game_clock.running)

    def test_finalize_field_action_has_the_same_catch_all(self) -> None:
        application = self.make_application()
        bridge = application.start_new()

        with mock.patch.object(
            application.service, "submit", side_effect=RuntimeError("boom")
        ), mock.patch.object(application.diagnostics, "unhandled_error") as unhandled:
            result = bridge.finalize_field_action(
                {"kind": "normal_play", "payload": {"final_absolute": 30}}, 0
            )

        self.assertFalse(result["accepted"])
        self.assertEqual(result["error"]["code"], INTERNAL_ERROR)
        json.dumps(result["view"])
        unhandled.assert_called_once()
        _, kwargs = unhandled.call_args
        self.assertEqual(kwargs["context"], "finalize_field_action")


class OnAcceptedRunsOutsideTheLockTests(TemporaryDataDirectoryTest):
    def test_on_accepted_sees_the_lock_already_released(self) -> None:
        lock = threading.RLock()
        observed: dict[str, bool] = {}

        def on_accepted(view: dict) -> None:
            # RLock exposes ``_is_owned()`` in CPython; if this method is still
            # inside the bridge's own ``with self._lock:`` block it would be
            # owned by this very thread.
            observed["owned_by_this_thread"] = lock._is_owned()  # type: ignore[attr-defined]

        service, store = self.started_session()
        bridge = ScoreboardBridge(service, store, lock=lock, on_accepted=on_accepted)

        bridge.command("game_clock_start", {}, 0)

        self.assertIn("owned_by_this_thread", observed, "on_accepted was never called")
        self.assertFalse(
            observed["owned_by_this_thread"],
            "on_accepted ran while command() still held the lock",
        )

    def test_a_different_thread_can_take_the_lock_while_on_accepted_runs(self) -> None:
        lock = threading.RLock()
        acquired_elsewhere = threading.Event()

        def on_accepted(view: dict) -> None:
            def probe() -> None:
                if lock.acquire(blocking=False):
                    acquired_elsewhere.set()
                    lock.release()

            worker = threading.Thread(target=probe)
            worker.start()
            worker.join(timeout=WAIT_TIMEOUT)

        service, store = self.started_session()
        bridge = ScoreboardBridge(service, store, lock=lock, on_accepted=on_accepted)

        bridge.command("game_clock_start", {}, 0)

        self.assertTrue(
            acquired_elsewhere.wait(timeout=WAIT_TIMEOUT),
            "a different thread could not take the lock while on_accepted ran",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
