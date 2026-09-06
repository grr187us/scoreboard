"""Cutscenes through the operator bridge (spec section 5.1, 5.4).

Cutscenes are a host concern exactly like the presentation layout and saved
teams (spec section 1, mirrored by ``test_team_bridge.py``): the three host
actions this bridge exposes -- ``open_cutscenes``, ``trigger_cutscene``,
``cancel_cutscene`` -- advance no revision, submit no command, and write no
action-history row. What they add to every operator view is the countdown
badge (``cutscenes.available``/``.playing``), computed once by
``CutsceneDirector.status()`` and merely copied here, the same "compute once,
copy everywhere" rule the rest of this bridge follows for every displayed
clock string.

A recording scheduler stands in for ``threading.Timer`` (mirroring
``test_cutscene_director.py``), so nothing in this file starts a real timer
or sleeps.
"""

from __future__ import annotations

import unittest
from typing import Any, Callable

from scoreboard.application.recovery import start_new_game
from scoreboard.host.bridge import ScoreboardBridge
from scoreboard.host.cutscenes import CutsceneDirector
from scoreboard.infrastructure.persistence import GameStore, read_action_history

from tests.integration.support import TemporaryDataDirectoryTest


class _FakeTimerHandle:
    def __init__(self, delay_seconds: float, callback: Callable[[], None]) -> None:
        self.delay_seconds = delay_seconds
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _FakeScheduler:
    """Records every ``schedule`` call instead of starting a real timer."""

    def __init__(self) -> None:
        self.calls: list[_FakeTimerHandle] = []

    def __call__(self, delay_seconds: float, callback: Callable[[], None]) -> _FakeTimerHandle:
        handle = _FakeTimerHandle(delay_seconds, callback)
        self.calls.append(handle)
        return handle


class CutsceneBridgeTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service = start_new_game(monotonic_clock=self.monotonic)
        self.store = GameStore.open(self.paths)
        self.addCleanup(self.store.close)
        self.store.begin_session(self.service.state)
        self.scheduler = _FakeScheduler()
        self.director = CutsceneDirector(
            self.paths,
            monotonic=self.monotonic,
            schedule=self.scheduler,
            read_spectator_view=lambda: {
                "teams": {
                    "home": {"name": "Tigers", "score": 0},
                    "away": {"name": "Hawks", "score": 0},
                },
                "football": {"possession": "home"},
            },
        )
        self.published: list[dict] = []
        self.bridge = ScoreboardBridge(
            self.service, self.store, cutscenes=self.director, on_accepted=self.published.append
        )

    def send(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.bridge.command(name, args or {}, self.service.revision)


class ViewBadgeTests(CutsceneBridgeTestCase):
    def test_every_view_carries_available_true_and_playing_none_when_idle(self) -> None:
        operator = self.bridge.get_snapshot()

        self.assertEqual(operator["cutscenes"], {"available": True, "playing": None})

    def test_a_command_result_view_carries_the_badge_too(self) -> None:
        result = self.send("game_clock_start")

        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["view"]["cutscenes"], {"available": True, "playing": None})

    def test_the_playing_badge_reflects_a_triggered_cutscene(self) -> None:
        self.bridge.trigger_cutscene("touchdown")

        view = self.bridge.get_snapshot()

        self.assertIsNotNone(view["cutscenes"]["playing"])
        self.assertEqual(view["cutscenes"]["playing"]["event"], "touchdown")

    def test_the_spectator_view_carries_no_cutscenes_badge(self) -> None:
        # The countdown badge is an operator/Cutscenes-window concern; the
        # spectator plays the program itself and reads it through
        # `get_cutscene()` on the SpectatorBridge, never this badge.
        spectator = self.bridge.spectator_snapshot()

        self.assertNotIn("cutscenes", spectator)


class TriggerAndCancelHostActionTests(CutsceneBridgeTestCase):
    def test_trigger_cutscene_advances_no_revision_and_writes_no_history_row(self) -> None:
        before_revision = self.service.revision
        before_rows = len(read_action_history(self.paths.database))

        result = self.bridge.trigger_cutscene("touchdown")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["message"], "Playing Touchdown (10 s).")
        self.assertEqual(self.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_rows)
        # A host action, not a command: nothing here goes through the hook
        # command()/finalize_field_action() use to publish an accepted view.
        self.assertEqual(self.published, [])
        self.assertEqual(len(self.scheduler.calls), 1)

    def test_trigger_cutscene_leaves_a_running_clock_running(self) -> None:
        self.send("game_clock_start")
        self.assertTrue(self.service.game_clock.value.running)

        self.bridge.trigger_cutscene("touchdown")

        self.assertTrue(self.service.game_clock.value.running)

    def test_cancel_cutscene_advances_no_revision_and_writes_no_history_row(self) -> None:
        self.bridge.trigger_cutscene("touchdown")
        before_revision = self.service.revision
        before_rows = len(read_action_history(self.paths.database))

        result = self.bridge.cancel_cutscene()

        self.assertTrue(result["ok"], result)
        self.assertIsNone(result["view"]["cutscenes"]["playing"])
        self.assertEqual(self.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_rows)
        self.assertEqual(self.published, [])

    def test_cancel_with_nothing_playing_reports_plainly(self) -> None:
        result = self.bridge.cancel_cutscene()

        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "No cutscene is playing.")

    def test_an_invalid_event_is_rejected_without_changing_the_badge(self) -> None:
        result = self.bridge.trigger_cutscene("field_goal")

        self.assertFalse(result["ok"])
        self.assertIsNone(result["view"]["cutscenes"]["playing"])
        self.assertEqual(self.scheduler.calls, [])


class OffCommandLockTests(CutsceneBridgeTestCase):
    """C4 for cutscenes: the director's publish reaches a window's
    ``evaluate_js``, so the bridge must call the director *outside* the
    command lock. A stalled wall must never hold up the next score command.

    The probe runs on a second thread because the bridge lock is an RLock:
    from the calling thread a non-blocking acquire always succeeds, so only
    another thread can tell whether the lock is actually free.
    """

    def _lock_free_seen_from_another_thread(self) -> bool:
        import threading

        seen: list[bool] = []

        def probe() -> None:
            free = self.bridge._lock.acquire(blocking=False)  # noqa: SLF001
            if free:
                self.bridge._lock.release()  # noqa: SLF001
            seen.append(free)

        worker = threading.Thread(target=probe)
        worker.start()
        worker.join(timeout=2.0)
        return bool(seen) and seen[0]

    def test_trigger_cutscene_publishes_with_the_command_lock_free(self) -> None:
        observed: list[bool] = []
        self.director.link.publish = lambda program: observed.append(  # type: ignore[method-assign]
            self._lock_free_seen_from_another_thread()
        )

        result = self.bridge.trigger_cutscene("touchdown", "home")

        self.assertTrue(result["ok"])
        self.assertEqual(observed, [True])
        self.assertIn("cutscenes", result["view"])

    def test_cancel_cutscene_ends_with_the_command_lock_free(self) -> None:
        self.bridge.trigger_cutscene("touchdown", "home")
        observed: list[bool] = []
        self.director.link.end = lambda play_id: observed.append(  # type: ignore[method-assign]
            self._lock_free_seen_from_another_thread()
        )

        result = self.bridge.cancel_cutscene()

        self.assertTrue(result["ok"])
        self.assertEqual(observed, [True])


class UnavailableWithoutADirectorTests(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service = start_new_game(monotonic_clock=self.monotonic)
        self.store = GameStore.open(self.paths)
        self.addCleanup(self.store.close)
        self.store.begin_session(self.service.state)
        self.bridge = ScoreboardBridge(self.service, self.store)

    def test_the_view_reports_unavailable(self) -> None:
        view = self.bridge.get_snapshot()

        self.assertEqual(view["cutscenes"], {"available": False, "playing": None})

    def test_trigger_and_cancel_answer_plainly_and_change_nothing(self) -> None:
        before_revision = self.service.revision

        trigger_result = self.bridge.trigger_cutscene("touchdown")
        self.assertFalse(trigger_result["ok"])
        self.assertEqual(trigger_result["message"], "Cutscenes are unavailable.")

        cancel_result = self.bridge.cancel_cutscene()
        self.assertFalse(cancel_result["ok"])
        self.assertEqual(cancel_result["message"], "Cutscenes are unavailable.")

        self.assertEqual(self.service.revision, before_revision)


class OpenCutscenesTests(CutsceneBridgeTestCase):
    def test_without_an_opener_it_answers_plainly(self) -> None:
        result = self.bridge.open_cutscenes()

        self.assertEqual(result, {"message": "The Cutscenes window is unavailable."})

    def test_with_an_opener_it_forwards_and_a_raising_opener_is_contained(self) -> None:
        self.bridge.set_cutscenes_opener(lambda: {"message": "opened"})
        self.assertEqual(self.bridge.open_cutscenes(), {"message": "opened"})

        def explode() -> dict[str, str]:
            raise RuntimeError("boom")

        self.bridge.set_cutscenes_opener(explode)

        result = self.bridge.open_cutscenes()

        self.assertIn("could not be opened", result["message"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
