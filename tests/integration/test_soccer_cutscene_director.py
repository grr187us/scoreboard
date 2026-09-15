"""``SoccerCutsceneDirector``/``SoccerCutscenesBridge``: playback state and
its host wiring. Mirrors ``tests/integration/test_cutscene_director.py``
(football; frozen) plus the ``team`` argument :meth:`trigger` requires (spec
section 7, owner choice F: a GOAL is never nobody's) and the same
director/tick lock-ordering rule football's director keeps.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.host.soccer_cutscenes import SoccerCutsceneDirector, SoccerCutsceneLink, SoccerCutscenesBridge
from scoreboard.infrastructure import soccer_cutscene_packs as cutscene_packs
from scoreboard.infrastructure.diagnostics import Diagnostics

from tests.integration.support import FakeMonotonic, TemporaryDataDirectoryTest

JSON_TYPES = (str, int, float, bool, type(None), list, dict)


class FakeTimerHandle:
    def __init__(self, delay_seconds: float, callback) -> None:
        self.delay_seconds = delay_seconds
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[FakeTimerHandle] = []

    def __call__(self, delay_seconds: float, callback) -> FakeTimerHandle:
        handle = FakeTimerHandle(delay_seconds, callback)
        self.calls.append(handle)
        return handle


class RecordingLink(SoccerCutsceneLink):
    def __init__(self) -> None:
        self.published: list[dict] = []
        self.ended: list[int] = []
        self.raise_on_publish: Exception | None = None
        self.raise_on_end: Exception | None = None

    def open_window(self):
        return {"message": "opened"}

    def publish(self, program):
        if self.raise_on_publish is not None:
            raise self.raise_on_publish
        self.published.append(program)

    def end(self, play_id):
        if self.raise_on_end is not None:
            raise self.raise_on_end
        self.ended.append(play_id)


class SoccerCutsceneDirectorTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.soccer_paths = self.paths.for_sport("soccer")

    def make_director(self, **kwargs) -> tuple[SoccerCutsceneDirector, FakeMonotonic, FakeScheduler, RecordingLink]:
        monotonic = FakeMonotonic()
        scheduler = FakeScheduler()
        link = RecordingLink()
        view = kwargs.pop(
            "view",
            {"teams": {"home": {"name": "Eagles", "score": 1}, "away": {"name": "Hawks", "score": 0}}},
        )
        director = SoccerCutsceneDirector(
            self.soccer_paths,
            monotonic=monotonic,
            schedule=scheduler,
            read_spectator_view=lambda: view,
            **kwargs,
        )
        director.link = link
        return director, monotonic, scheduler, link

    def make_diagnostics(self) -> Diagnostics:
        diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(diagnostics.close)
        return diagnostics

    def log_text(self) -> str:
        return self.paths.log_file.read_text(encoding="utf-8")


class TriggerTests(SoccerCutsceneDirectorTestCase):
    def test_goal_home_publishes_the_home_teams_name_and_schedules_seven_seconds(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()

        result = director.trigger("goal", "home")

        self.assertTrue(result["ok"])
        self.assertEqual(result["play_id"], 1)
        program = link.published[0]
        self.assertEqual(program["event"], "goal")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["duration_ms"], 7000)
        self.assertEqual(program["texts"]["team_name"], "Eagles")
        self.assertEqual(scheduler.calls[0].delay_seconds, 7.0)

    def test_goal_away_publishes_the_away_teams_name(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()

        result = director.trigger("goal", "away")

        self.assertTrue(result["ok"])
        self.assertEqual(link.published[0]["team"], "away")
        self.assertEqual(link.published[0]["texts"]["team_name"], "Hawks")

    def test_status_counts_down(self) -> None:
        director, monotonic, _scheduler, _link = self.make_director()
        director.trigger("goal", "home")

        monotonic.advance(3.0)
        status = director.status()

        self.assertEqual(status["remaining_ms"], 4000)
        self.assertEqual(status["team"], "home")

    def test_invalid_event_is_rejected_without_changing_state(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()

        result = director.trigger("own_goal", "home")

        self.assertFalse(result["ok"])
        self.assertIsNone(director.status())
        self.assertEqual(link.published, [])
        self.assertEqual(scheduler.calls, [])

    def test_an_invalid_team_is_rejected_without_changing_state(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()

        result = director.trigger("goal", "referee")

        self.assertFalse(result["ok"])
        self.assertIsNone(director.status())
        self.assertEqual(link.published, [])
        self.assertEqual(scheduler.calls, [])

    def test_trigger_requires_both_arguments(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        with self.assertRaises(TypeError):
            director.trigger("goal")  # type: ignore[call-arg]

    def test_a_missing_view_still_triggers_with_an_empty_team_name(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director(view={})

        result = director.trigger("goal", "home")

        self.assertTrue(result["ok"])
        self.assertEqual(link.published[0]["texts"]["team_name"], "")

    def test_diagnostics_note_the_scoring_team(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, _scheduler, _link = self.make_director(diagnostics=diagnostics)

        director.trigger("goal", "away")
        diagnostics.flush()

        self.assertIn("CUTSCENE_STARTED", self.log_text())
        self.assertIn("team=away", self.log_text())


class ReplaceAndExpireTests(SoccerCutsceneDirectorTestCase):
    def test_replace_on_collision_cancels_the_old_timer(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()
        director.trigger("goal", "home")

        result = director.trigger("goal", "away")

        self.assertTrue(result["ok"])
        self.assertEqual(result["play_id"], 2)
        self.assertTrue(scheduler.calls[0].cancelled)
        self.assertEqual(link.ended, [])

    def test_expire_ends_exactly_once(self) -> None:
        director, monotonic, scheduler, link = self.make_director()
        director.trigger("goal", "home")

        monotonic.advance(7.0)
        scheduler.calls[0].callback()

        self.assertEqual(link.ended, [1])
        self.assertIsNone(director.status())

    def test_a_stale_timer_from_a_replaced_play_never_fires_end(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()
        director.trigger("goal", "home")
        director.trigger("goal", "away")

        scheduler.calls[0].callback()

        self.assertEqual(link.ended, [])
        self.assertEqual(director.status()["play_id"], 2)


class CancelTests(SoccerCutsceneDirectorTestCase):
    def test_cancel_ends_and_clears(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()
        director.trigger("goal", "home")

        result = director.cancel()

        self.assertTrue(result["ok"])
        self.assertEqual(link.ended, [1])
        self.assertTrue(scheduler.calls[0].cancelled)
        self.assertIsNone(director.status())

    def test_cancel_with_nothing_playing_reports_ok_false(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()

        result = director.cancel()

        self.assertFalse(result["ok"])
        self.assertEqual(link.ended, [])


class FailureContainmentTests(SoccerCutsceneDirectorTestCase):
    def test_a_raising_publish_is_contained_and_still_plays(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        link.raise_on_publish = RuntimeError("boom")

        result = director.trigger("goal", "home")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertIsNotNone(director.status())
        self.assertEqual(len(scheduler.calls), 1)
        self.assertIn("UNHANDLED_ERROR", self.log_text())

    def test_a_broken_spectator_view_reader_never_breaks_a_trigger(self) -> None:
        def broken_view():
            raise RuntimeError("no view for you")

        director, _monotonic, _scheduler, link = self.make_director()
        director._read_spectator_view = broken_view  # noqa: SLF001

        result = director.trigger("goal", "home")

        self.assertTrue(result["ok"])
        self.assertEqual(link.published[0]["texts"]["team_name"], "")

    def test_a_raising_board_layout_reader_still_triggers(self) -> None:
        def broken_board_layout():
            raise RuntimeError("no board for you")

        diagnostics = self.make_diagnostics()
        director, _monotonic, _scheduler, link = self.make_director(
            diagnostics=diagnostics, read_board_layout=broken_board_layout,
        )

        result = director.trigger("goal", "home")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertIn("UNHANDLED_ERROR", self.log_text())
        self.assertIn("soccer_cutscene_board_layout", self.log_text())


class LockOrderingTests(SoccerCutsceneDirectorTestCase):
    """Mirrors football's own lock-ordering test: the director must never
    call into the bridge while holding its lock, because the 10 Hz tick
    holds the command lock when it calls ``status()`` to fill every
    operator view -- reading the spectator view under this object's own
    lock would order the two locks both ways.
    """

    def test_the_spectator_view_is_read_with_the_director_lock_free(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()
        seen: list[bool] = []

        def view_that_probes_the_lock():
            free = director._lock.acquire(blocking=False)  # noqa: SLF001
            if free:
                director._lock.release()  # noqa: SLF001
            seen.append(free)
            return {"teams": {"home": {"name": "Eagles"}, "away": {"name": "Hawks"}}}

        director._read_spectator_view = view_that_probes_the_lock  # noqa: SLF001

        result = director.trigger("goal", "home")

        self.assertTrue(result["ok"])
        self.assertEqual(seen, [True])
        self.assertEqual(link.published[0]["texts"]["team_name"], "Eagles")

    def test_a_tick_style_status_read_can_happen_mid_trigger_without_deadlock(self) -> None:
        # A fake spectator-view reader that itself calls status() -- standing
        # in for the 10 Hz tick reaching in from the other side -- must
        # return immediately rather than block on the director's own lock.
        director, _monotonic, _scheduler, _link = self.make_director()
        statuses: list = []

        def view_that_reads_status():
            statuses.append(director.status())
            return {"teams": {"home": {"name": "Eagles"}, "away": {"name": "Hawks"}}}

        director._read_spectator_view = view_that_reads_status  # noqa: SLF001

        self.assertTrue(director.trigger("goal", "away")["ok"])
        self.assertEqual(statuses, [None])


class SelectPackRescanAndAutoTriggerTests(SoccerCutsceneDirectorTestCase):
    def test_select_pack_persists_and_is_reflected_in_state(self) -> None:
        folder = self.soccer_paths.cutscenes / "roar"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "name": "Roar", "event": "goal", "scene": {"type": "builtin", "id": "goal"}}),
            encoding="utf-8",
        )
        director, _monotonic, _scheduler, _link = self.make_director()
        director.rescan()

        result = director.select_pack("goal", "roar")

        self.assertTrue(result["ok"])
        goal_event = next(e for e in result["events"] if e["id"] == "goal")
        self.assertEqual(goal_event["selected_pack_id"], "roar")
        self.assertEqual(cutscene_packs.read_selection(self.soccer_paths).get("goal"), "roar")

    def test_select_pack_rejects_an_unknown_event(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        result = director.select_pack("own_goal", "anything")

        self.assertFalse(result["ok"])

    def test_state_reports_auto_trigger_default_on(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        self.assertEqual(director.state()["auto_trigger"], {"goal": True})
        self.assertTrue(director.auto_trigger_enabled("goal"))

    def test_set_auto_trigger_persists_and_is_read_back(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        result = director.set_auto_trigger("goal", False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["auto_trigger"], {"goal": False})
        self.assertFalse(director.auto_trigger_enabled("goal"))
        # A fresh director reading the same paths sees the persisted value.
        again, _m, _s, _l = self.make_director()
        self.assertFalse(again.auto_trigger_enabled("goal"))

    def test_set_auto_trigger_rejects_an_unknown_event(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        result = director.set_auto_trigger("own_goal", False)

        self.assertFalse(result["ok"])

    def test_an_unknown_events_auto_trigger_defaults_true_rather_than_raising(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        self.assertTrue(director.auto_trigger_enabled("own_goal"))


class BridgeTests(SoccerCutsceneDirectorTestCase):
    class _FakeOperator:
        def get_snapshot(self):
            return {"teams": {"home": {"name": "Eagles"}}}

    def test_bridge_forwards_every_call_to_the_director(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()
        bridge = SoccerCutscenesBridge(director, self._FakeOperator())

        self.assertEqual(bridge.get_snapshot(), {"teams": {"home": {"name": "Eagles"}}})
        self.assertEqual(bridge.state()["folder"], str(self.soccer_paths.cutscenes))
        result = bridge.trigger("goal", "home")
        self.assertTrue(result["ok"])
        self.assertTrue(bridge.cancel()["ok"])
        self.assertIn("message", bridge.rescan())
        self.assertFalse(bridge.select_pack("own_goal", "x")["ok"])
        self.assertTrue(bridge.set_auto_trigger("goal", False)["ok"])

    def test_the_bridge_exposes_no_command_endpoint(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()
        bridge = SoccerCutscenesBridge(director, self._FakeOperator())

        self.assertFalse(hasattr(bridge, "command"))


class JsonBoundaryTests(SoccerCutsceneDirectorTestCase):
    def _assert_json_only(self, value, path="payload") -> None:
        self.assertIsInstance(value, JSON_TYPES, f"{path} is {type(value)!r}")
        if isinstance(value, dict):
            for key, item in value.items():
                self.assertIsInstance(key, str, f"{path} key {key!r}")
                self._assert_json_only(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self._assert_json_only(item, f"{path}[{index}]")

    def test_state_and_trigger_results_are_json_compatible(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        self._assert_json_only(director.state())
        result = director.trigger("goal", "home")
        self._assert_json_only(result)
        self._assert_json_only(director.status())
        self._assert_json_only(director.current_program())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
