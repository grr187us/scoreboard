"""Render the real soccer spectator page in an offline Edge page (spec
section 5.1/5.2, D-owned): every optional widget off, then on and populated,
must stay glyph-in-box with no overlap; FINAL must hide the game clock but
nothing else. Screenshots land in ``.scratch/soccer-mode/evidence/spectator/``.

The view models here are hand-built dicts following spec section 3.3's
dotted paths (``scoreboard.host.soccer_bridge.soccer_spectator_view_model``
is agent B's deliverable, not yet built) -- see the report for the exact
``board.hidden_widgets`` contract that function must honour so this test's
expectations keep holding once it exists.
"""
import copy
import json
import unittest

from scoreboard.presentation import soccer_layout as sl
from tests.ui.browser_support import run_browser


def _base_model():
    return {
        "teams": {"home": {"name": "EAGLES", "score": 1}, "away": {"name": "TIGERS", "score": 0}},
        "period": "1st", "period_display": "1st Half", "period_display_short": "1ST",
        "lifecycle": "IN_PROGRESS",
        "clocks": {"game": {"display": "31:07", "status": "RUNNING", "running": True,
                             "seconds": 1867, "maximum_seconds": 2400, "full_display": "31:07",
                             "label": "GAME CLOCK"}},
        "soccer": {
            "home": {"shots_display": "S 4", "saves_display": "SV 2", "corners_display": "COR 3",
                     "fouls_display": "F 1", "cards": {"yellow_display": "", "red_display": ""}},
            "away": {"shots_display": "S 6", "saves_display": "SV 3", "corners_display": "COR 5",
                     "fouls_display": "F 2", "cards": {"yellow_display": "", "red_display": ""}},
            "shootout": {"home_display": "", "away_display": ""},
        },
        "status": {"display": "", "clock_display": ""},
        "board": {"hidden_widgets": [], "hidden_element_prefixes": list(sl.hidden_element_prefixes())},
        "revision": 12,
    }


class SoccerSpectatorBrowserTests(unittest.TestCase):
    def test_optional_widgets_final_and_no_overlap(self):
        optional_off = _base_model()

        optional_on = copy.deepcopy(optional_off)
        optional_on["soccer"]["home"]["cards"]["yellow_display"] = "Y 1"
        optional_on["soccer"]["away"]["cards"]["red_display"] = "R 1"
        optional_on["soccer"]["shootout"] = {"home_display": "● ● ○", "away_display": "● ○"}
        optional_on["status"] = {"display": "WEATHER", "clock_display": "29:58"}

        final = copy.deepcopy(optional_on)
        final["period"] = "FINAL"
        final["period_display"] = "Final"
        final["lifecycle"] = "FINAL"
        final["board"]["hidden_widgets"] = list(sl.SOCCER_FINAL_HIDDEN_WIDGET_IDS)

        all_on_layout = json.loads(json.dumps(sl.default_soccer_layout()))
        for widget_id in (
            "home_shots", "away_shots", "home_saves", "away_saves", "home_corners", "away_corners",
            "home_fouls", "away_fouls", "home_yellow", "away_yellow", "home_red", "away_red",
            "shootout_home", "shootout_away",
        ):
            all_on_layout["widgets"][widget_id]["visible"] = True
        validated = sl.validate_soccer_layout(all_on_layout)
        self.assertTrue(validated.ok, validated.errors)

        result = run_browser("soccer_spectator.cjs", {
            "optionalOff": optional_off, "optionalOn": optional_on, "final": final,
            "allOnLayout": validated.layout,
        })
        self.assertEqual(result["cases"], 4)


if __name__ == "__main__":
    unittest.main()
