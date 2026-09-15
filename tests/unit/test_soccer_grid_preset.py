"""Mirrors ``tests/unit/test_grid_preset.py`` for the soccer "Soccer Grid"
preset (spec section 5.2, D-owned): geometry, palette, fonts, and the
elements that decorate it.
"""
from __future__ import annotations

import unittest

from scoreboard.presentation import soccer_layout as sl


class SoccerGridPresetTests(unittest.TestCase):
    def setUp(self):
        presets = {p["id"]: p["layout"] for p in sl.soccer_preset_descriptors()}
        self.grid = presets["grid"]

    def test_preset_is_named_soccer_grid_and_validates_without_repairs(self):
        self.assertEqual(self.grid["name"], "Soccer Grid")
        result = sl.validate_soccer_layout(self.grid)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, ())

    def test_uses_the_owners_scoreboard_grid_palette(self):
        self.assertEqual(self.grid["background"]["color"], "#030A12")
        self.assertEqual(self.grid["widgets"]["game_clock_value"]["color"], "#F5AE08")
        self.assertEqual(self.grid["widgets"]["home_yellow"]["color"], "#FFD500")
        self.assertEqual(self.grid["widgets"]["home_red"]["color"], "#FF4B4B")

    def test_uses_bahnschrift_condensed_labels_and_varsity_digits(self):
        self.assertEqual(self.grid["widgets"]["home_name"]["font_family"], "bahnschrift_condensed")
        self.assertEqual(self.grid["widgets"]["home_score"]["font_family"], "varsity")
        self.assertEqual(self.grid["widgets"]["game_clock_value"]["font_family"], "varsity")
        self.assertEqual(self.grid["widgets"]["period"]["font_family"], "varsity")

    def test_names_scores_clock_and_period_shrink_to_fit(self):
        for widget_id in ("home_name", "away_name", "home_score", "away_score", "game_clock_value", "period"):
            self.assertTrue(self.grid["widgets"][widget_id]["fit_text"], widget_id)
        for widget_id in ("home_shots", "status_message"):
            self.assertFalse(self.grid["widgets"][widget_id]["fit_text"], widget_id)

    def test_game_clock_label_starts_hidden_the_operator_may_turn_it_on(self):
        self.assertFalse(self.grid["widgets"]["game_clock_label"]["visible"])

    def test_sixteen_widgets_start_hidden_by_default(self):
        hidden = [wid for wid, w in self.grid["widgets"].items() if not w["visible"]]
        # game_clock_label + 8 stats + 4 cards + 2 shootout = 15, plus nothing
        # else -- the always-visible set is exactly the other 8.
        self.assertEqual(len(hidden), 15)
        visible = [wid for wid, w in self.grid["widgets"].items() if w["visible"]]
        self.assertEqual(
            set(visible),
            {"home_name", "away_name", "home_score", "away_score",
             "game_clock_value", "period", "status_message", "status_clock"},
        )

    def test_home_and_away_stat_and_card_widgets_are_mirrored(self):
        for left, right in (
            ("home_shots", "away_shots"), ("home_saves", "away_saves"),
            ("home_corners", "away_corners"), ("home_fouls", "away_fouls"),
            ("home_yellow", "away_yellow"), ("home_red", "away_red"),
        ):
            home = self.grid["widgets"][left]
            away = self.grid["widgets"][right]
            self.assertAlmostEqual(home["x"] + home["width"] + away["x"], 1.0, places=6)
            self.assertEqual(home["y"], away["y"])
            self.assertEqual(home["width"], away["width"])
            self.assertEqual(home["height"], away["height"])

    def test_elements_include_the_header_team_panels_and_the_gold_period_frame(self):
        ids = {element["id"] for element in self.grid["elements"]}
        for expected in ("title", "home_panel", "home_banner", "away_panel", "away_banner", "period_panel"):
            self.assertIn(expected, ids)
        title = [e for e in self.grid["elements"] if e["id"] == "title"][0]
        self.assertEqual(title["text"], "HIGH SCHOOL SOCCER")
        period_panel = [e for e in self.grid["elements"] if e["id"] == "period_panel"][0]
        self.assertEqual(period_panel["border_color"], "#E9A51A")

    def test_pregame_and_halftime_are_grid_style_and_still_footballs_event_registry(self):
        from scoreboard.presentation import layout as football_layout

        for screen_id in ("pregame", "halftime"):
            screen = self.grid["screens"][screen_id]
            self.assertEqual(set(screen["widgets"]), set(football_layout.EVENT_WIDGET_IDS))
            self.assertEqual(screen["background"]["color"], "#030A12")

    def test_broadcast_and_classic_presets_also_validate_clean(self):
        presets = {p["id"]: p["layout"] for p in sl.soccer_preset_descriptors()}
        for preset_id in ("broadcast", "classic"):
            result = sl.validate_soccer_layout(presets[preset_id])
            self.assertTrue(result.ok, (preset_id, result.errors))
            self.assertEqual(result.warnings, (), preset_id)


if __name__ == "__main__":
    unittest.main()
