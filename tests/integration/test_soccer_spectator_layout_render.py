"""Soccer's spectator/layout render contract (spec section 5.1/3.3, D-owned).

The Python<->JS literal mirror itself is covered by
``tests/unit/test_soccer_layout_schema.py``'s ``BoardJsSoccerMirrorTests``;
this file checks the board-rendering *behaviour* football's
``test_spectator_layout_render.py`` checks: the FINAL-hidden-widgets
contract, every ``SOCCER_WIDGET_FIELDS`` path resolving in a plausible
soccer spectator view model (built by hand here, since ``soccer_bridge``'s
real view model is agent B's deliverable -- see the report for the exact
contract it must honour), and that soccer's pre-game/halftime screens really
do bind to football's own event fields, unchanged.
"""
from __future__ import annotations

import unittest

from scoreboard.presentation import layout as football_layout
from scoreboard.presentation import soccer_layout as sl


def _sample_soccer_view_model(*, lifecycle="IN_PROGRESS", period="1st") -> dict:
    """A hand-built soccer spectator view model following spec section 3.3's
    dotted paths -- every field ``SOCCER_WIDGET_FIELDS`` names must resolve
    against a model shaped exactly like this.
    """

    return {
        "teams": {
            "home": {"name": "EAGLES", "score": 1},
            "away": {"name": "TIGERS", "score": 0},
        },
        "period": period,
        "period_display": "1st Half",
        "period_display_short": "1ST",
        "lifecycle": lifecycle,
        "clocks": {
            "game": {
                "display": "31:07", "status": "RUNNING", "running": True,
                "seconds": 1867, "maximum_seconds": 2400, "full_display": "31:07", "label": "GAME CLOCK",
            },
        },
        "soccer": {
            "home": {
                "shots_display": "S 4", "saves_display": "SV 2",
                "corners_display": "COR 3", "fouls_display": "F 1",
                "cards": {"yellow_display": "Y 1", "red_display": ""},
            },
            "away": {
                "shots_display": "S 6", "saves_display": "SV 3",
                "corners_display": "COR 5", "fouls_display": "F 2",
                "cards": {"yellow_display": "", "red_display": ""},
            },
            "shootout": {"home_display": "", "away_display": ""},
        },
        "status": {"display": "", "clock_display": ""},
        "board": {
            "hidden_widgets": list(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS) if lifecycle == "FINAL" else [],
            "hidden_element_prefixes": list(sl.hidden_element_prefixes()),
        },
    }


class FinalHiddenWidgetsContractTests(unittest.TestCase):
    def test_the_hidden_list_is_only_the_game_clock(self):
        self.assertEqual(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS, ("game_clock_label", "game_clock_value"))
        self.assertTrue(set(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS).issubset(sl.SOCCER_WIDGET_IDS))

    def test_period_is_never_in_the_hidden_list(self):
        # Period keeps reading "FINAL"/"SHOOTOUT" on the wall even when the
        # clock digits are hidden.
        self.assertNotIn("period", sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS)


class WidgetFieldsResolveInASampleViewModelTests(unittest.TestCase):
    def test_every_non_static_field_resolves_to_a_non_none_value(self):
        model = _sample_soccer_view_model()
        for widget_id, field in sl.SOCCER_WIDGET_FIELDS.items():
            if field is None:
                continue
            value = football_layout._resolve_path(model, field)
            self.assertIsNotNone(value, f"{widget_id}: {field!r} resolved to None")

    def test_final_hides_only_the_clock_widgets_in_the_sample_model(self):
        final_model = _sample_soccer_view_model(lifecycle="FINAL", period="FINAL")
        self.assertEqual(final_model["board"]["hidden_widgets"], ["game_clock_label", "game_clock_value"])

    def test_supported_widget_ids_matches_the_sample_model(self):
        model = _sample_soccer_view_model()
        supported = sl.supported_widget_ids(model)
        # home_red/away_yellow/away_red/shootout_* are blank in this sample
        # (optional -- hidden rather than drawn empty), everything else has a
        # value.
        self.assertIn("home_yellow", supported)
        self.assertNotIn("home_red", supported)
        self.assertNotIn("shootout_home", supported)
        self.assertIn("home_shots", supported)


class EventScreensReuseFootballsFieldsUnchangedTests(unittest.TestCase):
    def test_pregame_and_halftime_widgets_bind_to_footballs_own_event_fields(self):
        layout = sl.default_soccer_layout()
        for screen_id in ("pregame", "halftime"):
            for widget_id in layout["screens"][screen_id]["widgets"]:
                self.assertIn(widget_id, football_layout.EVENT_WIDGET_FIELDS)

    def test_soccer_screen_descriptors_event_widgets_have_footballs_field_paths(self):
        descriptors = {d["id"]: d for d in sl.soccer_screen_descriptors()}
        pregame_fields = {w["id"]: w["field"] for w in descriptors["pregame"]["widgets"]}
        self.assertEqual(pregame_fields, football_layout.EVENT_WIDGET_FIELDS)


if __name__ == "__main__":
    unittest.main()
