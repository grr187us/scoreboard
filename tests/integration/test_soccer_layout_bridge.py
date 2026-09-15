"""``PresentationLayouts(paths, layout_module=soccer_layout)`` serves the
soccer widget registry and saves to the given paths' ``layouts.json`` --
football's own ``PresentationLayouts(paths)`` (no ``layout_module`` kwarg)
stays byte-identical (spec section 2.3, D-owned seam).

Deliberately does not import anything under ``scoreboard.host.app`` --
that module is owned by another agent and may be mid-edit; this test only
needs ``infrastructure.layouts``/``host.layout_bridge``/``presentation``.
"""
from __future__ import annotations

import json
import unittest

from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure import layouts as layouts_infra
from scoreboard.presentation import layout as football_layout
from scoreboard.presentation import soccer_layout

from tests.integration.support import TemporaryDataDirectoryTest


class SoccerPresentationLayoutsTests(TemporaryDataDirectoryTest):
    def make_soccer_layouts(self) -> PresentationLayouts:
        return PresentationLayouts(self.paths, layout_module=soccer_layout)

    def test_state_serves_the_soccer_registry_not_footballs(self):
        layouts = self.make_soccer_layouts()
        state = layouts.state()
        self.assertEqual(state["layout"]["name"], "Default")
        self.assertEqual(
            {w["id"] for w in state["widgets"]}, set(soccer_layout.SOCCER_WIDGET_IDS)
        )
        self.assertEqual([s["id"] for s in state["screens"]], ["game", "pregame", "halftime"])
        self.assertEqual(state["screens"][0]["kind"], "soccer")
        preset_ids = {p["id"] for p in state["presets"]}
        self.assertEqual(preset_ids, {"grid", "broadcast", "classic"})
        self.assertNotIn("quarter", {w["id"] for w in state["widgets"]})

    def test_saving_writes_to_the_given_paths_layouts_json_in_soccers_own_shape(self):
        layouts = self.make_soccer_layouts()
        draft = json.loads(json.dumps(layouts.current_layout()))
        draft["widgets"]["home_score"]["color"] = "#123456"
        result = layouts.save("My board", draft)
        self.assertTrue(result["ok"], result["errors"] if not result["ok"] else result)

        self.assertTrue(self.paths.layouts.exists())
        on_disk = json.loads(self.paths.layouts.read_text(encoding="utf-8"))
        self.assertIn("My board", on_disk["layouts"])
        saved_widgets = on_disk["layouts"]["My board"]["widgets"]
        self.assertEqual(set(saved_widgets), set(soccer_layout.SOCCER_WIDGET_IDS))
        self.assertEqual(saved_widgets["home_score"]["color"], "#123456")

    def test_a_football_widget_id_is_rejected_as_unknown(self):
        layouts = self.make_soccer_layouts()
        draft = json.loads(json.dumps(layouts.current_layout()))
        draft["widgets"]["quarter"] = {"id": "quarter", "visible": True}
        preview = layouts.preview(draft)
        self.assertTrue(preview["ok"], preview)
        self.assertNotIn("quarter", preview["layout"]["widgets"])
        self.assertTrue(any(w["code"] == "UNKNOWN_WIDGET" for w in preview["warnings"]))

    def test_reset_widget_and_clamp_use_the_soccer_schema(self):
        layouts = self.make_soccer_layouts()
        draft = json.loads(json.dumps(layouts.current_layout()))
        # A hidden widget: clamping it out of range never risks an OVERLAP
        # error, since overlap is only checked among visible widgets.
        draft["widgets"]["home_shots"]["x"] = 0.999
        clamped = layouts.clamp(draft)
        self.assertTrue(clamped["ok"], clamped["errors"] if not clamped["ok"] else clamped)
        self.assertLessEqual(clamped["layout"]["widgets"]["home_shots"]["x"], 1.0)
        reset = layouts.reset_widget("home_shots", draft)
        self.assertTrue(reset["ok"], reset)
        self.assertEqual(
            reset["layout"]["widgets"]["home_shots"]["x"], soccer_layout.default_soccer_widget("home_shots")["x"]
        )

    def test_pregame_and_halftime_editing_still_uses_footballs_own_event_registry(self):
        layouts = self.make_soccer_layouts()
        draft = json.loads(json.dumps(layouts.current_layout()))
        draft["screens"]["pregame"]["widgets"]["event_title"]["color"] = "#ABCDEF"
        result = layouts.save("Pregame edit", draft)
        self.assertTrue(result["ok"], result)
        self.assertEqual(
            layouts.current_layout()["screens"]["pregame"]["widgets"]["event_title"]["color"], "#ABCDEF"
        )


class FootballPresentationLayoutsUnchangedTests(TemporaryDataDirectoryTest):
    """The existing football call sites take no ``layout_module`` kwarg at
    all and must behave exactly as before this seam was added.
    """

    def test_no_kwarg_still_serves_footballs_own_registry(self):
        layouts = PresentationLayouts(self.paths)
        state = layouts.state()
        self.assertEqual({w["id"] for w in state["widgets"]}, set(football_layout.WIDGET_IDS))
        self.assertEqual(state["layout"], football_layout.default_layout())

    def test_football_and_soccer_layouts_write_to_independent_paths(self):
        football = PresentationLayouts(self.paths)
        soccer_paths = self.paths.for_sport("soccer")
        soccer_paths.ensure()
        soccer = PresentationLayouts(soccer_paths, layout_module=soccer_layout)

        football.save("F", json.loads(json.dumps(football.current_layout())))
        soccer.save("S", json.loads(json.dumps(soccer.current_layout())))

        self.assertNotEqual(self.paths.layouts, soccer_paths.layouts)
        football_on_disk = json.loads(self.paths.layouts.read_text(encoding="utf-8"))
        soccer_on_disk = json.loads(soccer_paths.layouts.read_text(encoding="utf-8"))
        self.assertIn("F", football_on_disk["layouts"])
        self.assertIn("S", soccer_on_disk["layouts"])
        self.assertNotIn("F", soccer_on_disk["layouts"])
        self.assertNotIn("S", football_on_disk["layouts"])

    def test_read_library_with_no_schema_kwarg_is_unchanged(self):
        library = layouts_infra.read_library(self.paths)
        self.assertEqual(library.active_layout(), football_layout.default_layout())


if __name__ == "__main__":
    unittest.main()
