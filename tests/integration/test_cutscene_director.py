"""``CutsceneDirector``/``CutscenesBridge``: playback state and its host wiring.

Mirrors ``test_layout_bridge.py``/``test_team_presets.py``'s style: a
cutscene action is a host concern exactly like a layout edit or a saved
team, with an injectable clock, an injectable scheduler in place of a real
``threading.Timer``, and a recording ``CutsceneLink`` standing in for
:class:`~scoreboard.host.app.WindowHost`. Diagnostics assertions use a real
:class:`~scoreboard.infrastructure.diagnostics.Diagnostics` and grep the log
text, the way ``test_team_presets.py`` does.
"""

from __future__ import annotations

import json
import unittest

from scoreboard.domain.commands import CommandType
from scoreboard.host.cutscenes import CutsceneDirector, CutsceneLink, CutscenesBridge
from scoreboard.infrastructure import cutscene_packs
from scoreboard.infrastructure.diagnostics import Diagnostics
from scoreboard.presentation import layout as layout_module

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
    """Records every ``schedule`` call instead of starting a real timer."""

    def __init__(self) -> None:
        self.calls: list[FakeTimerHandle] = []

    def __call__(self, delay_seconds: float, callback) -> FakeTimerHandle:
        handle = FakeTimerHandle(delay_seconds, callback)
        self.calls.append(handle)
        return handle


class RecordingLink(CutsceneLink):
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


class CutsceneDirectorTestCase(TemporaryDataDirectoryTest):
    def make_director(self, **kwargs) -> tuple[CutsceneDirector, FakeMonotonic, FakeScheduler, RecordingLink]:
        monotonic = FakeMonotonic()
        scheduler = FakeScheduler()
        link = RecordingLink()
        view = kwargs.pop(
            "view",
            {
                "teams": {"home": {"name": "Tigers", "score": 14}, "away": {"name": "Hawks", "score": 7}},
                "football": {"possession": "home"},
            },
        )
        director = CutsceneDirector(
            self.paths,
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


class TriggerTests(CutsceneDirectorTestCase):
    def test_first_down_countdown_and_timer_share_the_five_second_program(self) -> None:
        director, monotonic, scheduler, link = self.make_director()
        result = director.trigger("first_down")
        self.assertTrue(result["ok"])
        self.assertEqual(link.published[0]["duration_ms"], 5000)
        self.assertEqual(scheduler.calls[0].delay_seconds, 5.0)
        monotonic.advance(3.0)
        self.assertEqual(director.status()["remaining_display"], "2.0s")

    def test_trigger_publishes_one_program_with_the_right_shape_and_schedules_the_delay(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()

        result = director.trigger("touchdown")

        self.assertTrue(result["ok"])
        self.assertEqual(result["play_id"], 1)
        self.assertEqual(result["message"], "Playing Touchdown (10 s).")
        self.assertEqual(len(link.published), 1)
        program = link.published[0]
        self.assertEqual(program["play_id"], 1)
        self.assertEqual(program["event"], "touchdown")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["duration_ms"], 10000)
        self.assertEqual(len(scheduler.calls), 1)
        self.assertEqual(scheduler.calls[0].delay_seconds, 10.0)

    def test_trigger_uses_the_broadcast_bar_preset_by_default(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()

        director.trigger("touchdown")

        broadcast = next(p["layout"] for p in layout_module.preset_descriptors() if p["id"] == "broadcast")
        self.assertEqual(link.published[0]["layout"]["screens"], broadcast["screens"])
        self.assertEqual(link.published[0]["layout"]["name"], "Cutscene")

    def test_trigger_accepts_an_injected_tiny_layout(self) -> None:
        tiny_layout = {"schema_version": 3, "name": "Tiny", "widgets": {}, "screens": {}}
        director, _monotonic, _scheduler, link = self.make_director(read_layout=lambda: tiny_layout)

        director.trigger("touchdown")

        self.assertEqual(link.published[0]["layout"]["widgets"], {})
        self.assertEqual(link.published[0]["layout"]["name"], "Cutscene")

    def test_status_counts_down_and_remaining_display_clamps_at_zero(self) -> None:
        director, monotonic, _scheduler, _link = self.make_director()
        director.trigger("touchdown")

        monotonic.advance(4.0)
        status = director.status()
        self.assertEqual(status["elapsed_ms"], 4000)
        self.assertEqual(status["remaining_ms"], 6000)
        self.assertEqual(status["remaining_display"], "6.0s")

        monotonic.advance(20.0)
        status_over = director.status()
        self.assertEqual(status_over["remaining_ms"], 0)
        self.assertEqual(status_over["remaining_display"], "0.0s")

    def test_status_is_none_when_idle(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        self.assertIsNone(director.status())

    def test_invalid_event_is_rejected_without_changing_state(self) -> None:
        director, _monotonic, scheduler, link = self.make_director()

        result = director.trigger("field_goal")

        self.assertFalse(result["ok"])
        self.assertIsNone(director.status())
        self.assertEqual(link.published, [])
        self.assertEqual(scheduler.calls, [])

    def test_trigger_takes_no_team_argument(self) -> None:
        # Home/away is not a choice any more: the event decides. A caller
        # that still passes a team must fail loudly, not be quietly ignored.
        director, _monotonic, scheduler, link = self.make_director()

        with self.assertRaises(TypeError):
            director.trigger("touchdown", "away")  # type: ignore[call-arg]

        self.assertIsNone(director.status())
        self.assertEqual(link.published, [])
        self.assertEqual(scheduler.calls, [])

    def test_tigers_copy_replaces_home_even_when_the_visitors_have_possession(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director(
            view={
                "teams": {"home": {"name": "HOME", "score": 0}, "away": {"name": "Hawks", "score": 7}},
                "football": {"possession": "away"},
            }
        )

        self.assertTrue(director.trigger("first_down")["ok"])

        self.assertEqual(link.published[0]["team"], "home")
        self.assertEqual(link.published[0]["texts"]["team_name"], "Tigers")
        self.assertEqual(link.published[0]["texts"]["subline"], "TIGERS")

    def test_a_penalty_plays_for_nobody_and_notes_a_null_team(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)

        result = director.trigger("penalty")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Playing Penalty (7 s).")
        program = link.published[0]
        self.assertIsNone(program["team"])
        self.assertEqual(program["texts"]["subline"], "PENALTY")
        self.assertEqual(program["intro"], {"id": "none", "duration_ms": 0})
        self.assertEqual(scheduler.calls[0].delay_seconds, 7.0)
        self.assertIsNone(director.status()["team"])
        self.assertIn("CUTSCENE_STARTED", self.log_text())
        self.assertIn("cutscene_event=penalty", self.log_text())

    def test_a_turnover_is_the_tigers_taking_the_ball_with_the_immediate_impact(self) -> None:
        # Cutscenes v3 (.scratch/cutscenes-v3/spec.md 2.1): a takeaway is a
        # home-team event with no separate intro and a 5 s run.
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)

        result = director.trigger("turnover")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Playing Turnover (5 s).")
        program = link.published[0]
        self.assertEqual(program["event"], "turnover")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["label"], "Turnover")
        self.assertEqual(program["duration_ms"], 5000)
        self.assertEqual(program["intro"], {"id": "none", "duration_ms": 0})
        self.assertEqual(program["texts"]["subline"], "TIGER'S BALL")
        self.assertEqual(scheduler.calls[0].delay_seconds, 5.0)
        self.assertEqual(director.status()["team"], "home")
        self.assertIn("cutscene_event=turnover", self.log_text())

    def test_make_some_noise_is_a_five_second_home_prompt_with_no_intro(self) -> None:
        # v3 2.1: at 5 s a 1.6 s claw would eat a third of the scene, and a
        # crowd prompt wants to be on the wall now -- so `intro` is `none`.
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)

        result = director.trigger("make_some_noise")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "Playing Make some noise (5 s).")
        program = link.published[0]
        self.assertEqual(program["event"], "make_some_noise")
        self.assertEqual(program["team"], "home")
        self.assertEqual(program["label"], "Make some noise")
        self.assertEqual(program["duration_ms"], 5000)
        self.assertEqual(program["intro"], {"id": "none", "duration_ms": 0})
        self.assertEqual(program["texts"]["subline"], "TIGERS FANS")
        self.assertEqual(scheduler.calls[0].delay_seconds, 5.0)
        self.assertEqual(director.status()["team"], "home")
        self.assertIn("cutscene_event=make_some_noise", self.log_text())


class BoardLayoutStyleTests(CutsceneDirectorTestCase):
    """Bug 1: with ``read_board_layout`` wired, every event's program keeps
    the operator's active look while still morphing into the Broadcast bar's
    geometry (the one fix in :func:`~scoreboard.presentation.cutscenes.
    build_program` covers all five events, since every trigger goes through
    it).
    """

    def _board_layout(self) -> dict:
        grid = next(
            preset["layout"] for preset in layout_module.preset_descriptors() if preset["id"] == "grid"
        )
        return grid

    def test_every_event_publishes_the_boards_colour_for_shared_widgets(self) -> None:
        from scoreboard.presentation.cutscenes import CUTSCENE_EVENTS

        board_layout = self._board_layout()
        director, _monotonic, _scheduler, link = self.make_director(
            read_board_layout=lambda: board_layout,
        )
        grid_color = board_layout["widgets"]["home_score"]["color"]
        broadcast_default = next(
            p["layout"] for p in layout_module.preset_descriptors() if p["id"] == "broadcast"
        )["widgets"]["home_score"]["color"]
        # The two presets disagree on colour -- otherwise this test would
        # pass even with the bug still present.
        self.assertNotEqual(grid_color, broadcast_default)

        for index, event in enumerate(CUTSCENE_EVENTS, start=1):
            with self.subTest(event=event):
                director.trigger(event)
                published_layout = link.published[index - 1]["layout"]
                self.assertEqual(published_layout["widgets"]["home_score"]["color"], grid_color)
                self.assertEqual(published_layout["widgets"]["away_score"]["color"], grid_color)
                self.assertTrue(published_layout["widgets"]["home_score"]["fit_text"])
                # The geometry stays the Broadcast bar's, not the Grid's.
                broadcast = next(
                    p["layout"] for p in layout_module.preset_descriptors() if p["id"] == "broadcast"
                )
                self.assertEqual(
                    published_layout["widgets"]["home_score"]["x"],
                    broadcast["widgets"]["home_score"]["x"],
                )


class ExpireTests(CutsceneDirectorTestCase):
    def test_expire_ends_exactly_once(self) -> None:
        diagnostics = self.make_diagnostics()
        director, monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        director.trigger("touchdown")
        diagnostics.flush()

        monotonic.advance(10.0)
        scheduler.calls[0].callback()
        diagnostics.flush()

        self.assertEqual(link.ended, [1])
        self.assertIsNone(director.status())
        self.assertIn("CUTSCENE_ENDED", self.log_text())

    def test_a_stale_timer_firing_late_is_ignored(self) -> None:
        director, monotonic, scheduler, link = self.make_director()
        director.trigger("touchdown")
        monotonic.advance(10.0)
        scheduler.calls[0].callback()
        self.assertEqual(link.ended, [1])

        # The (already-fired) timer callback runs again -- must not double-end.
        scheduler.calls[0].callback()

        self.assertEqual(link.ended, [1])

    def test_a_stale_timer_from_a_replaced_play_never_fires_end(self) -> None:
        director, monotonic, scheduler, link = self.make_director()
        director.trigger("touchdown")
        director.trigger("first_down")  # replaces play_id 1 with play_id 2

        # The stale timer for the replaced play_id somehow still calls back
        # (e.g. a race the cancel() call did not win) -- it must be a no-op.
        scheduler.calls[0].callback()

        self.assertEqual(link.ended, [])
        self.assertIsNotNone(director.status())
        self.assertEqual(director.status()["play_id"], 2)


class ReplaceTests(CutsceneDirectorTestCase):
    def test_replace_on_collision_cancels_the_old_timer_and_notes_replaced(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        director.trigger("touchdown")

        result = director.trigger("first_down")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(result["play_id"], 2)
        self.assertTrue(scheduler.calls[0].cancelled)
        self.assertIn("CUTSCENE_REPLACED", self.log_text())
        self.assertIn("play_id=1", self.log_text())
        # Never calls end() for the replaced play.
        self.assertEqual(link.ended, [])

    def test_replace_publishes_the_new_program_only(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()
        director.trigger("touchdown")

        director.trigger("first_down")

        self.assertEqual(len(link.published), 2)
        self.assertEqual(link.published[1]["event"], "first_down")


class CancelTests(CutsceneDirectorTestCase):
    def test_cancel_ends_and_clears(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        director.trigger("touchdown")

        result = director.cancel()
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertEqual(link.ended, [1])
        self.assertTrue(scheduler.calls[0].cancelled)
        self.assertIsNone(director.status())
        self.assertIn("CUTSCENE_CANCELLED", self.log_text())

    def test_cancel_with_nothing_playing_reports_ok_false(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()

        result = director.cancel()

        self.assertFalse(result["ok"])
        self.assertEqual(link.ended, [])


class FailureContainmentTests(CutsceneDirectorTestCase):
    def test_a_raising_publish_is_contained_and_logged_and_still_plays(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        link.raise_on_publish = RuntimeError("boom")

        result = director.trigger("touchdown")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertIsNotNone(director.status())
        self.assertEqual(len(scheduler.calls), 1)
        self.assertIn("UNHANDLED_ERROR", self.log_text())
        self.assertIn("cutscene_publish", self.log_text())

    def test_a_raising_end_is_contained_and_logged_on_cancel(self) -> None:
        diagnostics = self.make_diagnostics()
        director, _monotonic, _scheduler, link = self.make_director(diagnostics=diagnostics)
        director.trigger("touchdown")
        link.raise_on_end = RuntimeError("boom")

        result = director.cancel()
        diagnostics.flush()

        self.assertTrue(result["ok"])
        self.assertIn("UNHANDLED_ERROR", self.log_text())
        self.assertIn("cutscene_end", self.log_text())

    def test_a_raising_end_is_contained_and_logged_on_expire(self) -> None:
        diagnostics = self.make_diagnostics()
        director, monotonic, scheduler, link = self.make_director(diagnostics=diagnostics)
        director.trigger("touchdown")
        link.raise_on_end = RuntimeError("boom")

        monotonic.advance(10.0)
        scheduler.calls[0].callback()
        diagnostics.flush()

        self.assertIsNone(director.status())
        self.assertIn("UNHANDLED_ERROR", self.log_text())

    def test_a_broken_spectator_view_reader_never_breaks_a_trigger(self) -> None:
        def broken_view():
            raise RuntimeError("no view for you")

        director, _monotonic, _scheduler, link = self.make_director()
        director._read_spectator_view = broken_view  # noqa: SLF001 - directly exercising the fallback

        result = director.trigger("touchdown")

        self.assertTrue(result["ok"])
        self.assertEqual(link.published[0]["texts"]["team_name"], "Tigers")

    def test_a_raising_board_layout_reader_still_triggers_and_notes_a_diagnostic(self) -> None:
        def broken_board_layout():
            raise RuntimeError("no board for you")

        diagnostics = self.make_diagnostics()
        director, _monotonic, _scheduler, link = self.make_director(
            diagnostics=diagnostics, read_board_layout=broken_board_layout,
        )

        result = director.trigger("touchdown")
        diagnostics.flush()

        self.assertTrue(result["ok"])
        broadcast = next(p["layout"] for p in layout_module.preset_descriptors() if p["id"] == "broadcast")
        # Falls back to the Broadcast bar's own look for this play, exactly
        # as if no reader had been wired.
        self.assertEqual(
            link.published[0]["layout"]["widgets"]["home_score"]["color"],
            broadcast["widgets"]["home_score"]["color"],
        )
        self.assertIn("UNHANDLED_ERROR", self.log_text())
        self.assertIn("cutscene_board_layout", self.log_text())


class LockOrderingTests(CutsceneDirectorTestCase):
    """The director must never call into the bridge while holding its lock.

    The 10 Hz tick holds the command lock when it calls ``status()`` to fill
    every operator view; a trigger reads the spectator view through that
    same bridge lock. If the read happened under the director's lock, the
    two locks would be taken in both orders and one collision between a
    trigger and a tick would hang both windows for the rest of the game.
    """

    def test_the_spectator_view_is_read_with_the_director_lock_free(self) -> None:
        director, _monotonic, _scheduler, link = self.make_director()
        seen: list[bool] = []

        def view_that_probes_the_lock():
            # A non-blocking acquire succeeds only if trigger() is not
            # holding the lock while it reads the view. The tick's status()
            # call is what would otherwise be waiting on the far side.
            free = director._lock.acquire(blocking=False)  # noqa: SLF001
            if free:
                director._lock.release()  # noqa: SLF001
            seen.append(free)
            return {"teams": {"home": {"name": "Tigers", "score": 0},
                              "away": {"name": "Hawks", "score": 0}},
                    "football": {"possession": "home"}}

        director._read_spectator_view = view_that_probes_the_lock  # noqa: SLF001

        result = director.trigger("first_down")

        self.assertTrue(result["ok"])
        self.assertEqual(seen, [True])
        self.assertEqual(link.published[0]["texts"]["team_name"], "Tigers")

    def test_status_can_be_read_while_a_view_reader_is_mid_read(self) -> None:
        # The same property from the tick's side: status() taken from inside
        # the view read must return rather than wait on trigger().
        director, _monotonic, _scheduler, _link = self.make_director()
        statuses: list = []

        def view_that_reads_status():
            statuses.append(director.status())
            return {"teams": {"home": {"name": "Tigers", "score": 0},
                              "away": {"name": "Hawks", "score": 0}},
                    "football": {"possession": "home"}}

        director._read_spectator_view = view_that_reads_status  # noqa: SLF001

        self.assertTrue(director.trigger("touchdown")["ok"])
        self.assertEqual(statuses, [None])


class SelectPackAndRescanTests(CutsceneDirectorTestCase):
    def test_select_pack_persists_and_is_reflected_in_state(self) -> None:
        folder = self.paths.cutscenes / "roar"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "name": "Roar", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}}
            ),
            encoding="utf-8",
        )
        director, _monotonic, _scheduler, _link = self.make_director()
        director.rescan()

        result = director.select_pack("touchdown", "roar")

        self.assertTrue(result["ok"])
        touchdown_event = next(e for e in result["events"] if e["id"] == "touchdown")
        self.assertEqual(touchdown_event["selected_pack_id"], "roar")
        self.assertFalse(touchdown_event["fell_back"])
        self.assertEqual(
            cutscene_packs.read_selection(self.paths).get("touchdown"), "roar"
        )

    def test_select_pack_rejects_an_unknown_event(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()

        result = director.select_pack("field_goal", "anything")

        self.assertFalse(result["ok"])

    def test_rescan_sees_a_newly_dropped_folder(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()
        state_before = director.state()
        self.assertEqual(len(state_before["packs"]), 5)  # the five built-ins only (v3)

        folder = self.paths.cutscenes / "roar"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "name": "Roar", "event": "touchdown", "scene": {"type": "builtin", "id": "touchdown"}}
            ),
            encoding="utf-8",
        )

        result = director.rescan()

        self.assertEqual(len(result["packs"]), 6)
        self.assertIn("roar", [p["id"] for p in result["packs"]])


class SelectionFellBackDiagnosticsTests(CutsceneDirectorTestCase):
    def test_a_selection_naming_a_missing_pack_notes_fell_back_once_per_reload(self) -> None:
        cutscene_packs.write_selection(self.paths, {"touchdown": "nonexistent"})
        diagnostics = self.make_diagnostics()

        CutsceneDirector(self.paths, diagnostics=diagnostics)
        diagnostics.flush()

        self.assertIn("CUTSCENE_SELECTION_FELL_BACK", self.log_text())

    def test_a_rejected_pack_notes_pack_rejected(self) -> None:
        folder = self.paths.cutscenes / "broken"
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text("not json", encoding="utf-8")
        diagnostics = self.make_diagnostics()

        CutsceneDirector(self.paths, diagnostics=diagnostics)
        diagnostics.flush()

        self.assertIn("CUTSCENE_PACK_REJECTED", self.log_text())
        self.assertIn("pack_id=broken", self.log_text())


class BridgeTests(CutsceneDirectorTestCase):
    class _FakeOperator:
        def get_snapshot(self):
            return {"teams": {"home": {"name": "Tigers"}}}

    def test_bridge_forwards_every_call_to_the_director(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()
        bridge = CutscenesBridge(director, self._FakeOperator())

        self.assertEqual(bridge.get_snapshot(), {"teams": {"home": {"name": "Tigers"}}})
        self.assertEqual(bridge.state()["folder"], str(self.paths.cutscenes))
        result = bridge.trigger("touchdown")
        self.assertTrue(result["ok"])
        self.assertTrue(bridge.cancel()["ok"])
        self.assertIn("message", bridge.rescan())
        self.assertFalse(bridge.select_pack("field_goal", "x")["ok"])

    def test_the_bridge_exposes_no_command_endpoint_and_no_command_type_name(self) -> None:
        director, _monotonic, _scheduler, _link = self.make_director()
        bridge = CutscenesBridge(director, self._FakeOperator())

        self.assertFalse(hasattr(bridge, "command"))
        command_values = {member.value for member in CommandType}
        for name in dir(bridge):
            if name.startswith("_"):
                continue
            self.assertNotIn(name, command_values, f"{name!r} matches a CommandType value")


class JsonBoundaryTests(CutsceneDirectorTestCase):
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
        result = director.trigger("touchdown")
        self._assert_json_only(result)
        self._assert_json_only(director.status())
        self._assert_json_only(director.current_program())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
