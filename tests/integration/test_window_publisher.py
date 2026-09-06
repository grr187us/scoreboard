"""``WindowPublisher`` in isolation (C4): bounded, latest-wins window delivery.

No real window and no real wall-clock time. Every wait on the background
delivery thread is a ``threading.Event`` with a bounded timeout so a bug here
fails fast instead of hanging the suite; stall/recovery timing is driven by an
injected monotonic the test advances by hand, never real ``time.sleep``.
"""

from __future__ import annotations

import threading
import time
import unittest

from scoreboard.host.publisher import WindowPublisher

#: Every ``Event.wait`` uses this. It is far longer than any of these tests
#: should ever need, and only bounds a genuine failure (a thread that never
#: wakes) rather than gating normal, fast passing behaviour.
WAIT_TIMEOUT = 2.0


class FakeMonotonic:
    """A monotonic source advanced only by the test, never real time."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class PublisherTestCase(unittest.TestCase):
    """Stops whatever publisher the test started, even after a failure."""

    def setUp(self) -> None:
        self.publisher: WindowPublisher | None = None

    def tearDown(self) -> None:
        if self.publisher is not None:
            self.publisher.stop(timeout=1.0)

    def make(self, deliver, **kwargs) -> WindowPublisher:
        self.publisher = WindowPublisher(deliver, **kwargs)
        return self.publisher


class InlineDeliveryTests(PublisherTestCase):
    """Before ``start()``, every existing host test's synchronous world holds."""

    def test_offer_delivers_inline_before_start(self) -> None:
        calls: list[tuple[str, dict]] = []
        publisher = self.make(lambda name, view: calls.append((name, view)))

        publisher.offer("operator", {"revision": 1})

        self.assertEqual(calls, [("operator", {"revision": 1})])
        self.assertFalse(publisher.started)
        self.assertIsNone(publisher.in_flight)

    def test_a_raising_deliver_does_not_escape_offer_inline(self) -> None:
        def deliver(name: str, view: dict) -> None:
            raise RuntimeError("boom")

        publisher = self.make(deliver)

        publisher.offer("operator", {})  # must not raise


class LatestWinsTests(PublisherTestCase):
    def test_only_the_latest_offer_is_delivered_after_a_block_releases(self) -> None:
        delivered: list[dict] = []
        first_started = threading.Event()
        release_first = threading.Event()
        second_delivered = threading.Event()

        def deliver(name: str, view: dict) -> None:
            delivered.append(view)
            if len(delivered) == 1:
                first_started.set()
                self.assertTrue(
                    release_first.wait(timeout=WAIT_TIMEOUT),
                    "test never released the blocked delivery",
                )
            else:
                second_delivered.set()

        publisher = self.make(deliver)
        publisher.start()

        publisher.offer("operator", {"n": 1})
        self.assertTrue(first_started.wait(timeout=WAIT_TIMEOUT), "first delivery never started")

        # Two more offers land while the first delivery is still blocked; only
        # the last of them should ever reach ``deliver``.
        publisher.offer("operator", {"n": 2})
        publisher.offer("operator", {"n": 3})
        release_first.set()

        self.assertTrue(second_delivered.wait(timeout=WAIT_TIMEOUT), "the third view was never delivered")
        self.assertEqual(delivered, [{"n": 1}, {"n": 3}])


class StallAndRecoveryTests(PublisherTestCase):
    def test_stall_and_recovered_each_fire_once(self) -> None:
        monotonic = FakeMonotonic(100.0)
        stalls: list[tuple[str, float]] = []
        recoveries: list[tuple[str, float]] = []
        started = threading.Event()
        release = threading.Event()
        recovered = threading.Event()

        def deliver(name: str, view: dict) -> None:
            started.set()
            self.assertTrue(release.wait(timeout=WAIT_TIMEOUT), "test never released the delivery")

        def on_recovered(name: str, elapsed: float) -> None:
            recoveries.append((name, elapsed))
            recovered.set()

        publisher = self.make(
            deliver,
            on_stall=lambda name, elapsed: stalls.append((name, elapsed)),
            on_recovered=on_recovered,
            stall_after=2.0,
            monotonic=monotonic,
        )
        publisher.start()

        publisher.offer("spectator", {})
        self.assertTrue(started.wait(timeout=WAIT_TIMEOUT), "delivery never started")

        # Under two seconds elapsed (by the fake clock): no stall yet, even
        # though offer() is what drives the check.
        publisher.offer("operator", {})
        self.assertEqual(stalls, [])

        monotonic.advance(2.5)
        publisher.offer("operator", {})  # the 10x/s tick would call this too

        self.assertEqual(stalls, [("spectator", 2.5)])

        # A further offer before recovery must not report the stall twice.
        publisher.offer("operator", {})
        self.assertEqual(stalls, [("spectator", 2.5)])

        release.set()
        self.assertTrue(recovered.wait(timeout=WAIT_TIMEOUT), "recovery was never reported")
        self.assertEqual(recoveries, [("spectator", 2.5)])

    def test_no_recovery_is_reported_when_nothing_ever_stalled(self) -> None:
        monotonic = FakeMonotonic(0.0)
        recoveries: list[tuple[str, float]] = []
        delivered = threading.Event()

        def deliver(name: str, view: dict) -> None:
            delivered.set()

        publisher = self.make(
            deliver,
            on_recovered=lambda name, elapsed: recoveries.append((name, elapsed)),
            stall_after=2.0,
            monotonic=monotonic,
        )
        publisher.start()

        publisher.offer("operator", {})

        self.assertTrue(delivered.wait(timeout=WAIT_TIMEOUT))
        self.assertEqual(recoveries, [])


class StopTests(PublisherTestCase):
    def test_stop_returns_within_its_timeout_against_a_stuck_delivery(self) -> None:
        started = threading.Event()
        never_released = threading.Event()  # deliberately never set

        def deliver(name: str, view: dict) -> None:
            started.set()
            never_released.wait(timeout=3.0)  # simulates a genuinely stalled evaluate_js

        publisher = self.make(deliver)
        publisher.start()
        publisher.offer("operator", {})
        self.assertTrue(started.wait(timeout=WAIT_TIMEOUT), "delivery never started")

        began = time.monotonic()
        publisher.stop(timeout=0.2)
        elapsed = time.monotonic() - began

        self.assertLess(elapsed, 1.0, "stop() waited far longer than its own timeout")
        self.assertFalse(publisher.started)

    def test_stop_before_start_is_a_harmless_no_op(self) -> None:
        publisher = self.make(lambda name, view: None)

        publisher.stop(timeout=0.1)  # must not raise

        self.assertFalse(publisher.started)


class ThreadSurvivalTests(PublisherTestCase):
    def test_a_raising_deliver_does_not_kill_the_delivery_thread(self) -> None:
        calls: list[dict] = []
        first_done = threading.Event()
        second_done = threading.Event()

        def deliver(name: str, view: dict) -> None:
            calls.append(view)
            if len(calls) == 1:
                first_done.set()
                raise RuntimeError("a window that cannot render must not end the thread")
            second_done.set()

        publisher = self.make(deliver)
        publisher.start()

        publisher.offer("operator", {"n": 1})
        self.assertTrue(first_done.wait(timeout=WAIT_TIMEOUT), "the first delivery never ran")

        publisher.offer("operator", {"n": 2})
        self.assertTrue(
            second_done.wait(timeout=WAIT_TIMEOUT),
            "the delivery thread died after the raising delivery",
        )
        self.assertEqual(calls, [{"n": 1}, {"n": 2}])


if __name__ == "__main__":
    unittest.main()
