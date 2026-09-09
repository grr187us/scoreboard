"""The presentation layout is a host concern and can never reach the game.

Editing where a widget is drawn is the same class of action as choosing a
display or a data folder (see ``tests/integration/test_display_selection.py``
and ``test_data_folder.py``): it advances no revision, writes nothing to the
game database, records no action-history row, and leaves a running clock
running. These tests exist to make that structural rather than assumed.
"""

from __future__ import annotations

import json
import types
import unittest

from scoreboard.domain.commands import CommandType
from scoreboard.host.bridge import SpectatorBridge
from scoreboard.host.layout_bridge import (
    LayoutEditorBridge,
    LayoutLink,
    PresentationLayouts,
)
from scoreboard.infrastructure import config
from scoreboard.infrastructure.persistence import read_action_history
from scoreboard.presentation import layout as layout_module

from tests.integration.test_host_application import ApplicationTestCase

JSON_TYPES = (str, int, float, bool, type(None), list, dict)


def moved(layout: dict, widget_id: str, **changes) -> dict:
    """A copy of ``layout`` with one widget's properties replaced."""

    document = json.loads(json.dumps(layout))
    document["widgets"][widget_id].update(changes)
    return document


class LayoutTestCase(ApplicationTestCase):
    def make_layouts(self, **kwargs) -> PresentationLayouts:
        return PresentationLayouts(self.paths, **kwargs)

    def assert_json_only(self, payload) -> None:
        """No domain object may cross this boundary (ARCHITECTURE.md section 8)."""

        def walk(value, path="payload"):
            self.assertIsInstance(value, JSON_TYPES, f"{path} is {type(value)!r}")
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertIsInstance(key, str, f"{path} key {key!r}")
                    walk(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")

        walk(payload)
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)


class LayoutCannotTouchTheGameTests(LayoutTestCase):
    """The headline guarantee: presentation editing is not a game mutation."""

    def test_saving_selecting_and_resetting_change_no_authoritative_value(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("set_quarter", {"label": "2nd", "confirmed": True})
        bridge.command("add_score", {"team": "home", "points": 6})
        bridge.command("set_down", {"value": 3})
        bridge.command("set_distance", {"value": 7})
        bridge.command("timeout_used", {"team": "away"})
        bridge.command("game_clock_start")
        self.monotonic.advance(12.0)

        before_state = application.service.materialized_state()
        before_revision = application.service.revision
        before_history = len(read_action_history(self.paths.database))

        layouts = self.make_layouts()
        saved = layouts.save("Default", moved(layouts.current_layout(), "home_name", x=0.05))
        self.assertTrue(saved["ok"], saved)
        layouts.save("Night", moved(layouts.current_layout(), "quarter", color="#FFAA00"))
        layouts.select("Night")
        layouts.rename("Night", "Evening")
        layouts.save("Extra", layouts.current_layout())
        layouts.duplicate("Extra", "Extra copy")
        layouts.reset()
        layouts.state()
        layouts.preview(layouts.current_layout())

        self.monotonic.advance(3.0)
        after_state = application.service.materialized_state()

        self.assertEqual(application.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_history)
        for field in ("home_score", "away_score", "quarter", "lifecycle", "down",
                      "distance", "possession", "home_timeouts", "away_timeouts"):
            self.assertEqual(getattr(after_state, field), getattr(before_state, field), field)
        self.assertEqual(after_state.ball_on, before_state.ball_on)
        # The clock kept running across every layout operation, and consumed
        # exactly the simulated time rather than being disturbed by one.
        self.assertTrue(after_state.game_clock.running)
        self.assertAlmostEqual(
            before_state.game_clock.seconds - after_state.game_clock.seconds, 3.0, places=6
        )

    def test_no_layout_operation_writes_a_command_to_the_durable_history(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("add_score", {"team": "away", "points": 3})
        layouts = self.make_layouts()
        layouts.save("Default", moved(layouts.current_layout(), "quarter", x=0.06))
        layouts.save("Night", layouts.current_layout())
        layouts.rename("Night", "Evening")
        layouts.duplicate("Evening", "Evening copy")
        layouts.reset()

        commands = {row["command"] for row in read_action_history(self.paths.database)}
        self.assertNotIn("layout", " ".join(commands))
        for name in commands:
            # Every recorded row is a real game command or a system event; none
            # of them can have come from the layout editor.
            self.assertNotIn("layout_", name)
        self.assertTrue(commands.issubset(
            {command.value for command in CommandType}
            | {"session_started", "session_resumed", "session_shutdown",
               "game_clock_expired", "play_clock_expired",
               "play_clock_cleared_on_game_clock_stop"}
        ), commands)

    def test_the_editor_bridge_exposes_no_way_to_change_the_game(self) -> None:
        layouts = self.make_layouts()
        editor = LayoutEditorBridge(layouts, lambda: {})
        self.assertFalse(hasattr(editor, "command"))
        for command in CommandType:
            self.assertFalse(
                hasattr(editor, command.value),
                f"the editor bridge must not expose {command.value}",
            )
        public = {name for name in dir(editor) if not name.startswith("_")}
        self.assertEqual(public, {
            "get_snapshot", "layout_state", "preview_layout", "clamp_layout",
            "reset_widget", "save_layout", "select_layout", "delete_layout",
            "rename_layout", "duplicate_layout", "reset_layout",
            # The motion switch (event-screens spec section 2.9): a host
            # preference, deliberately not named like any CommandType.
            "set_motion",
        })

    def test_opening_the_editor_is_a_host_action(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start")
        self.monotonic.advance(5.0)
        revision = application.service.revision
        history = len(read_action_history(self.paths.database))

        opened = bridge.open_layout_editor()

        self.assertIsInstance(opened, dict)
        self.assertIn("message", opened)
        self.assertEqual(application.service.revision, revision)
        self.assertEqual(len(read_action_history(self.paths.database)), history)
        self.assertTrue(application.service.materialized_state().game_clock.running)

    def test_a_bare_link_reports_plainly_instead_of_raising(self) -> None:
        # The default LayoutLink opens nothing. A window-free host must say so
        # rather than throw into a button an operator pressed mid-game.
        message = LayoutLink().open_editor()
        self.assertIsInstance(message, dict)
        self.assertIsInstance(message["message"], str)
        self.assertTrue(message["message"])


class RenameAndDuplicateTests(LayoutTestCase):
    """Renaming and duplicating are host actions, exactly like save/select/delete."""

    def make_counting_link(self) -> tuple[LayoutLink, list[dict]]:
        link = LayoutLink()
        published: list[dict] = []
        link.publish = lambda layout: published.append(layout)  # type: ignore[method-assign]
        return link, published

    def test_rename_and_duplicate_advance_no_revision_and_write_no_history_row(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start")
        self.monotonic.advance(6.0)

        layouts = self.make_layouts()
        layouts.save("Night", moved(layouts.current_layout(), "quarter", color="#FFAA00"))

        before_state = application.service.materialized_state()
        before_revision = application.service.revision
        before_history = len(read_action_history(self.paths.database))

        renamed = layouts.rename("Night", "Evening")
        self.assertTrue(renamed["ok"], renamed)
        duplicated = layouts.duplicate("Evening", "Evening copy")
        self.assertTrue(duplicated["ok"], duplicated)
        # Refusals must be just as inert as successes.
        layouts.rename("Nowhere", "Somewhere")
        layouts.duplicate("Nowhere", "Somewhere")
        layouts.rename("Default", "Renamed default")

        self.monotonic.advance(4.0)
        after_state = application.service.materialized_state()

        self.assertEqual(application.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_history)
        self.assertTrue(after_state.game_clock.running)
        self.assertAlmostEqual(
            before_state.game_clock.seconds - after_state.game_clock.seconds, 4.0, places=6
        )

    def test_rename_publishes_exactly_once_on_success_and_never_on_refusal(self) -> None:
        link, published = self.make_counting_link()
        layouts = self.make_layouts(link=link)
        layouts.save("Night", layouts.current_layout())
        published.clear()

        ok = layouts.rename("Night", "Evening")
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(len(published), 1)

        refused = layouts.rename("Nowhere", "Somewhere Else")
        self.assertFalse(refused["ok"])
        self.assertEqual(len(published), 1)

        refused = layouts.rename("Default", "New Default Name")
        self.assertFalse(refused["ok"])
        self.assertEqual(len(published), 1)

        refused = layouts.rename("Evening", "Default")
        self.assertFalse(refused["ok"])
        self.assertEqual(len(published), 1)

    def test_duplicate_publishes_exactly_once_on_success_and_never_on_refusal(self) -> None:
        link, published = self.make_counting_link()
        layouts = self.make_layouts(link=link)
        layouts.save("Night", layouts.current_layout())
        published.clear()

        ok = layouts.duplicate("Night", "Night copy")
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(len(published), 1)
        self.assertEqual(layouts.state()["active"], "Night copy")

        refused = layouts.duplicate("Nowhere", "Somewhere Else")
        self.assertFalse(refused["ok"])
        self.assertEqual(len(published), 1)

        refused = layouts.duplicate("Night", "Night copy")  # already exists
        self.assertFalse(refused["ok"])
        self.assertEqual(len(published), 1)

    def test_renaming_the_active_layout_keeps_it_active(self) -> None:
        layouts = self.make_layouts()
        layouts.save("Night", layouts.current_layout())
        layouts.select("Night")

        result = layouts.rename("Night", "Evening")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["active"], "Evening")

    def test_duplicating_makes_the_copy_active(self) -> None:
        layouts = self.make_layouts()
        layouts.save("Night", layouts.current_layout())
        layouts.select("Default")

        result = layouts.duplicate("Night", "Night copy")

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["active"], "Night copy")


class MotionSwitchTests(LayoutTestCase):
    """The animation kill switch (event-screens spec section 2.9) is a host
    preference in ``config.json``, exactly like the display: it advances no
    revision, writes no history row, and is pushed to the boards through the
    link -- never through a command.
    """

    def test_set_motion_advances_no_revision_and_writes_no_history_row(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("add_score", {"team": "home", "points": 7})
        bridge.command("game_clock_start")
        self.monotonic.advance(5.0)
        before_state = application.service.materialized_state()
        before_revision = application.service.revision
        before_history = len(read_action_history(self.paths.database))

        layouts = self.make_layouts()
        self.assertTrue(layouts.motion_enabled(), "motion is on until an operator turns it off")
        off = layouts.set_motion(False)
        on = layouts.set_motion(True)
        refused = layouts.set_motion("off")

        self.monotonic.advance(2.0)
        after_state = application.service.materialized_state()
        self.assertEqual(application.service.revision, before_revision)
        self.assertEqual(len(read_action_history(self.paths.database)), before_history)
        self.assertEqual(after_state.home_score, before_state.home_score)
        self.assertTrue(after_state.game_clock.running)
        self.assertTrue(off["ok"])
        self.assertFalse(off["motion"])
        self.assertEqual(off["message"], "Motion is off.")
        self.assertTrue(on["ok"])
        self.assertTrue(on["motion"])
        self.assertEqual(on["message"], "Motion is on.")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["message"], "Motion must be on or off.")
        self.assertTrue(refused["motion"], "a refused answer changes nothing")
        for payload in (off, on, refused):
            self.assertIn("layout", payload, "set_motion answers with the full layout state")

    def test_the_preference_round_trips_through_config_json(self) -> None:
        layouts = self.make_layouts()
        self.assertTrue(layouts.set_motion(False)["ok"])

        self.assertEqual(config.read_section(self.paths, config.PRESENTATION_SECTION), {"motion": False})
        self.assertFalse(config.read_motion(self.paths))
        self.assertFalse(self.make_layouts().motion_enabled(), "a fresh host reads the stored switch")
        self.assertFalse(self.make_layouts().state()["motion"])

        layouts.set_motion(True)
        self.assertEqual(config.read_section(self.paths, config.PRESENTATION_SECTION), {"motion": True})
        self.assertTrue(config.read_motion(self.paths))

    def test_a_non_bool_writes_nothing_and_an_unreadable_section_means_on(self) -> None:
        layouts = self.make_layouts()
        for bad in ("off", 0, None, [False]):
            with self.subTest(value=bad):
                self.assertFalse(layouts.set_motion(bad)["ok"])
                self.assertIsNone(config.read_section(self.paths, config.PRESENTATION_SECTION))
        for broken in ({"motion": "no"}, {"motion": 0}, "off", 3, {}):
            with self.subTest(section=broken):
                config.write_section(self.paths, config.PRESENTATION_SECTION, broken)
                self.assertTrue(config.read_motion(self.paths))
                self.assertTrue(self.make_layouts().motion_enabled())
        config.write_section(self.paths, config.PRESENTATION_SECTION, {"motion": False, "future_key": 1})
        config.write_motion(self.paths, True)
        self.assertEqual(config.read_section(self.paths, config.PRESENTATION_SECTION),
                         {"motion": True, "future_key": 1}, "other presentation keys survive")

    def test_set_motion_publishes_the_switch_through_the_link_and_survives_a_failure(self) -> None:
        pushed: list[bool] = []
        link = LayoutLink()
        link.publish_motion = pushed.append  # type: ignore[method-assign]
        layouts = self.make_layouts(link=link)
        layouts.set_motion(False)
        layouts.set_motion("nonsense")
        layouts.set_motion(True)
        self.assertEqual(pushed, [False, True])

        def explode(enabled: bool) -> None:
            raise RuntimeError("window gone")

        link.publish_motion = explode  # type: ignore[method-assign]
        result = layouts.set_motion(False)
        self.assertTrue(result["ok"], "a publish failure never fails the switch (R-002)")
        self.assertFalse(config.read_motion(self.paths))

    def test_the_spectator_bridge_reads_the_switch_read_only(self) -> None:
        layouts = self.make_layouts()
        spectator = SpectatorBridge(lambda: {}, layouts.current_layout, read_motion=layouts.motion_enabled)
        self.assertTrue(spectator.get_motion())
        layouts.set_motion(False)
        self.assertFalse(spectator.get_motion())
        self.assertFalse(hasattr(spectator, "set_motion"))
        self.assertTrue(SpectatorBridge(lambda: {}).get_motion(), "no reader means motion on")

    def test_every_motion_payload_is_json_compatible(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        layouts = self.make_layouts()
        editor = LayoutEditorBridge(layouts, bridge.spectator_snapshot)
        self.assert_json_only(editor.set_motion(False))
        self.assert_json_only(editor.set_motion(True))
        self.assert_json_only(editor.set_motion("no"))
        self.assert_json_only(editor.layout_state())
        self.assertIn("motion", editor.layout_state())
        self.assert_json_only(SpectatorBridge(bridge.spectator_snapshot, layouts.current_layout,
                                              read_motion=layouts.motion_enabled).get_motion())


class LayoutPayloadTests(LayoutTestCase):
    def test_every_payload_is_json_compatible(self) -> None:
        application = self.make_application()
        bridge = application.start_new()
        layouts = self.make_layouts()
        editor = LayoutEditorBridge(layouts, bridge.spectator_snapshot)

        self.assert_json_only(bridge.presentation_layout())
        self.assert_json_only(editor.layout_state())
        self.assert_json_only(editor.get_snapshot())
        self.assert_json_only(editor.preview_layout(layouts.current_layout()))
        self.assert_json_only(editor.save_layout("Default", layouts.current_layout()))
        self.assert_json_only(editor.clamp_layout(layouts.current_layout()))
        self.assert_json_only(editor.reset_widget("quarter", layouts.current_layout()))
        self.assert_json_only(editor.save_layout("Night", layouts.current_layout()))
        self.assert_json_only(editor.rename_layout("Night", "Evening"))
        self.assert_json_only(editor.duplicate_layout("Evening", "Evening copy"))
        self.assert_json_only(editor.reset_layout())
        # A rejection payload has to survive the boundary too.
        self.assert_json_only(editor.save_layout("Default", {"nonsense": True}))
        self.assert_json_only(editor.rename_layout("Nowhere", "Somewhere"))
        self.assert_json_only(editor.duplicate_layout("Nowhere", "Somewhere"))
        self.assert_json_only(editor.rename_layout("Default", "New Name"))
        self.assert_json_only(SpectatorBridge(bridge.spectator_snapshot,
                                              layouts.current_layout).get_layout())

    def test_the_spectator_bridge_serves_the_active_layout_read_only(self) -> None:
        layouts = self.make_layouts()
        layouts.save("Default", moved(layouts.current_layout(), "home_score", x=0.07))
        spectator = SpectatorBridge(lambda: {}, layouts.current_layout)

        self.assertAlmostEqual(spectator.get_layout()["widgets"]["home_score"]["x"], 0.07)
        self.assertFalse(hasattr(spectator, "command"))
        self.assertFalse(hasattr(spectator, "save_layout"))

    def test_a_spectator_bridge_without_a_reader_still_serves_the_default(self) -> None:
        spectator = SpectatorBridge(lambda: {})
        self.assertEqual(spectator.get_layout(), layout_module.default_layout())


class InvalidLayoutTests(LayoutTestCase):
    def test_an_invalid_save_is_refused_and_the_stored_layout_survives(self) -> None:
        layouts = self.make_layouts()
        good = moved(layouts.current_layout(), "quarter", x=0.08)
        self.assertTrue(layouts.save("Default", good)["ok"])
        stored = self.paths.layouts.read_bytes()

        # Pushed past the bottom edge of the safe area.
        bad = moved(layouts.current_layout(), "ball_on", y=0.930)
        result = layouts.save("Default", bad)

        self.assertFalse(result["ok"])
        codes = {issue["code"] for issue in result["errors"]}
        self.assertIn("OUTSIDE_SAFE_AREA", codes)
        messages = " ".join(issue["message"] for issue in result["errors"])
        # The operator is told which widget, by its human name, not its id.
        self.assertIn(layout_module.WIDGET_LABELS["ball_on"], messages)
        self.assertEqual(self.paths.layouts.read_bytes(), stored)
        self.assertAlmostEqual(layouts.current_layout()["widgets"]["quarter"]["x"], 0.08)

    def test_a_malformed_file_still_yields_a_usable_board_and_a_working_host(self) -> None:
        self.paths.layouts.write_text("{ this is not JSON", encoding="utf-8")

        layouts = self.make_layouts()
        state = layouts.state()

        self.assertTrue(state["fell_back"])
        self.assertEqual(layouts.current_layout(), layout_module.default_layout())
        # And the application still starts, ticks, and keeps a clock running.
        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start")
        self.monotonic.advance(2.0)
        view = application.tick()
        self.assertIsNotNone(view)
        self.assertTrue(view["clocks"]["game"]["running"])

    def test_a_publish_failure_does_not_fail_the_save_or_reach_the_game(self) -> None:
        """R-002: an optional display concern must not stop core operation."""

        application = self.make_application()
        bridge = application.start_new()
        bridge.command("game_clock_start")
        self.monotonic.advance(4.0)
        revision = application.service.revision

        link = LayoutLink()
        published: list[str] = []

        def explode(_layout):
            published.append("attempted")
            raise RuntimeError("injected layout publish failure")

        link.publish = explode  # type: ignore[method-assign]
        layouts = self.make_layouts(link=link)

        result = layouts.save("Default", moved(layouts.current_layout(), "quarter", x=0.09))

        self.assertTrue(result["ok"], result)
        self.assertEqual(published, ["attempted"])
        self.assertAlmostEqual(layouts.current_layout()["widgets"]["quarter"]["x"], 0.09)
        self.assertEqual(application.service.revision, revision)
        self.assertTrue(application.service.materialized_state().game_clock.running)


class IndependentPositioningTests(LayoutTestCase):
    """A label and its value are separate widgets, and stay separate on disk."""

    def round_trip(self, changes: dict[str, dict]) -> dict:
        """Move only the named widgets, and prove the move survives a reload.

        Every other widget is hidden first, so the assertion is about the two
        coordinates surviving independently rather than about whether the
        chosen destinations happen to collide with the rest of the board --
        overlap has its own tests in ``tests/unit/test_layout_schema.py``.
        """

        layouts = self.make_layouts()
        document = layouts.current_layout()
        for widget_id in layout_module.WIDGET_IDS:
            if widget_id not in changes:
                document = moved(document, widget_id, visible=False)
        for widget_id, properties in changes.items():
            document = moved(document, widget_id, **properties)
        result = layouts.save("Default", document)
        self.assertTrue(result["ok"], result.get("errors"))
        # A completely fresh reader, as a restart would produce.
        return PresentationLayouts(self.paths).current_layout()

    def test_the_play_clock_label_and_value_move_independently(self) -> None:
        reloaded = self.round_trip({
            "play_clock_label": {"x": 0.100, "y": 0.120},
            "play_clock_value": {"x": 0.700, "y": 0.300},
        })
        self.assertAlmostEqual(reloaded["widgets"]["play_clock_label"]["x"], 0.100)
        self.assertAlmostEqual(reloaded["widgets"]["play_clock_label"]["y"], 0.120)
        self.assertAlmostEqual(reloaded["widgets"]["play_clock_value"]["x"], 0.700)
        self.assertAlmostEqual(reloaded["widgets"]["play_clock_value"]["y"], 0.300)

    def test_the_game_clock_label_and_value_move_independently(self) -> None:
        reloaded = self.round_trip({
            "game_clock_label": {"x": 0.050, "y": 0.200, "visible": True},
            "game_clock_value": {"x": 0.300, "y": 0.600, "width": 0.300},
        })
        self.assertAlmostEqual(reloaded["widgets"]["game_clock_label"]["x"], 0.050)
        self.assertTrue(reloaded["widgets"]["game_clock_label"]["visible"])
        self.assertAlmostEqual(reloaded["widgets"]["game_clock_value"]["x"], 0.300)

    def test_team_names_move_independently_of_each_other_and_their_scores(self) -> None:
        reloaded = self.round_trip({
            "home_name": {"x": 0.050, "y": 0.050},
            "away_name": {"x": 0.560, "y": 0.250},
            "home_score": {"x": 0.100, "y": 0.400},
        })
        self.assertAlmostEqual(reloaded["widgets"]["home_name"]["y"], 0.050)
        self.assertAlmostEqual(reloaded["widgets"]["away_name"]["x"], 0.560)
        self.assertAlmostEqual(reloaded["widgets"]["away_name"]["y"], 0.250)
        self.assertAlmostEqual(reloaded["widgets"]["home_score"]["y"], 0.400)

    def test_reset_returns_the_built_in_default(self) -> None:
        layouts = self.make_layouts()
        customised = layouts.save(
            "Default", moved(layouts.current_layout(), "quarter", x=0.06, color="#112233"))
        self.assertTrue(customised["ok"], customised.get("errors"))
        self.assertAlmostEqual(layouts.current_layout()["widgets"]["quarter"]["x"], 0.06)

        layouts.reset()

        self.assertEqual(layouts.current_layout(), layout_module.default_layout())
        self.assertEqual(PresentationLayouts(self.paths).current_layout(),
                         layout_module.default_layout())

    def test_reset_widget_restores_only_that_widget(self) -> None:
        layouts = self.make_layouts()
        document = moved(layouts.current_layout(), "quarter", x=0.06)
        document = moved(document, "ball_on", x=0.460, color="#010203")
        result = layouts.reset_widget("quarter", document)

        default = layout_module.default_layout()
        self.assertEqual(result["layout"]["widgets"]["quarter"], default["widgets"]["quarter"])
        self.assertAlmostEqual(result["layout"]["widgets"]["ball_on"]["x"], 0.460)
        self.assertEqual(result["layout"]["widgets"]["ball_on"]["color"], "#010203")


class ScreensStateTests(LayoutTestCase):
    """``state()`` carries the per-screen descriptors and presets the editor's
    Game / Pre-game / Halftime switcher needs (presentation-screens spec
    section 4)."""

    def test_state_exposes_screen_descriptors_for_every_screen(self) -> None:
        layouts = self.make_layouts()

        state = layouts.state()

        self.assertIn("screens", state)
        screen_ids = [descriptor["id"] for descriptor in state["screens"]]
        self.assertEqual(screen_ids, list(layout_module.SCREEN_IDS))
        for descriptor in state["screens"]:
            self.assertEqual(descriptor["label"], layout_module.SCREEN_LABELS[descriptor["id"]])
            self.assertEqual(descriptor["kind"], layout_module.SCREEN_KINDS[descriptor["id"]])

        event_descriptors = {
            descriptor["id"]: descriptor for descriptor in state["screens"]
            if descriptor["id"] in layout_module.EVENT_SCREEN_IDS
        }
        self.assertEqual(set(event_descriptors), set(layout_module.EVENT_SCREEN_IDS))
        for descriptor in event_descriptors.values():
            widget_ids = {widget["id"] for widget in descriptor["widgets"]}
            self.assertEqual(widget_ids, set(layout_module.EVENT_WIDGET_IDS))
            self.assertEqual(descriptor["widget_groups"], list(layout_module.EVENT_WIDGET_GROUP_ORDER))

    def test_state_exposes_screen_presets_keyed_by_event_screen(self) -> None:
        layouts = self.make_layouts()

        state = layouts.state()

        self.assertIn("screen_presets", state)
        self.assertEqual(set(state["screen_presets"]), set(layout_module.EVENT_SCREEN_IDS))
        for screen_id, presets in state["screen_presets"].items():
            self.assertTrue(presets)
            ids = [preset["id"] for preset in presets]
            self.assertEqual(len(ids), len(set(ids)), "screen preset ids must be unique")
            for preset in presets:
                self.assertEqual(set(preset), {"id", "name", "description", "screen"})
                self.assertTrue(preset["id"].startswith(f"{screen_id}_"))
                self.assertIsInstance(preset["screen"], dict)

    def test_screens_and_screen_presets_survive_the_json_boundary(self) -> None:
        layouts = self.make_layouts()
        self.assert_json_only(layouts.state()["screens"])
        self.assert_json_only(layouts.state()["screen_presets"])


class ResetWidgetScreenTests(LayoutTestCase):
    """``reset_widget`` takes an optional ``screen`` and forwards it through
    both the host object and the editor's ``js_api`` (presentation-screens
    spec section 4)."""

    def test_reset_widget_defaults_to_the_game_screen(self) -> None:
        layouts = self.make_layouts()
        document = moved(layouts.current_layout(), "quarter", x=0.06)

        result = layouts.reset_widget("quarter", document)

        default = layout_module.default_layout()
        self.assertEqual(result["layout"]["widgets"]["quarter"], default["widgets"]["quarter"])

    def test_reset_widget_can_target_an_event_screen(self) -> None:
        layouts = self.make_layouts()
        document = json.loads(json.dumps(layouts.current_layout()))
        document["screens"]["halftime"]["widgets"]["event_title"]["x"] = 0.01

        result = layouts.reset_widget("event_title", document, "halftime")

        expected = layout_module.default_screen_widget("halftime", "event_title")
        self.assertEqual(
            result["layout"]["screens"]["halftime"]["widgets"]["event_title"], expected
        )
        # The other event screen is untouched by a reset scoped to halftime.
        self.assertAlmostEqual(
            result["layout"]["screens"]["pregame"]["widgets"]["event_title"]["x"],
            layout_module.default_screen_widget("pregame", "event_title")["x"],
        )

    def test_the_editor_bridge_forwards_the_screen_argument(self) -> None:
        layouts = self.make_layouts()
        editor = LayoutEditorBridge(layouts, lambda: {})
        document = json.loads(json.dumps(layouts.current_layout()))
        document["screens"]["pregame"]["widgets"]["warmup"]["x"] = 0.02

        result = editor.reset_widget("warmup", document, "pregame")

        expected = layout_module.default_screen_widget("pregame", "warmup")
        self.assertEqual(result["layout"]["screens"]["pregame"]["widgets"]["warmup"], expected)

    def test_an_unknown_screen_leaves_the_layout_unchanged(self) -> None:
        layouts = self.make_layouts()
        document = layouts.current_layout()

        result = layouts.reset_widget("quarter", document, "nonexistent")

        self.assertEqual(result["layout"], layout_module.validate_layout(document).layout)


class OperatorSurfaceTests(unittest.TestCase):
    """The editor is reachable, and only from the drawer (U-001)."""

    def setUp(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views" / "operator"
        self.html = (root / "index.html").read_text(encoding="utf-8")
        self.script = (root / "operator.js").read_text(encoding="utf-8")

    def test_the_advanced_drawer_offers_the_editor_without_a_game_command(self) -> None:
        self.assertIn('data-action="open_layout_editor"', self.html)
        self.assertIn("if (action === 'open_layout_editor')", self.script)
        self.assertIn("api.open_layout_editor()", self.script)
        # It sits in the Advanced drawer, which overlays and scrolls inside
        # itself, so no always-visible control moved (U-001).
        advanced = self.html.split('id="advanced-drawer"', 1)[1]
        self.assertIn('data-action="open_layout_editor"', advanced.split("</div>\n  </div>", 1)[0])

    def test_the_control_is_not_a_command_and_says_what_it_cannot_do(self) -> None:
        button = [line for line in self.html.splitlines()
                  if 'data-action="open_layout_editor"' in line]
        self.assertEqual(len(button), 1)
        self.assertNotIn("data-command", button[0])
        self.assertIn("never changes", self.html.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
