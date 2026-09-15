"""Drive the shared layout editor (``views/layout/*``, unchanged) against a
real soccer ``layout_state()`` payload, offline in Edge (spec section 5.3,
D-owned): a soccer session must show only soccer widgets and build its
preview board with the soccer registry, never football's.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.presentation import soccer_layout as sl
from tests.ui.browser_support import run_browser


def _sample_soccer_snapshot() -> dict:
    """A hand-built soccer operator/spectator-shaped snapshot (spec 3.3);
    real once ``soccer_bridge.soccer_spectator_view_model`` lands (agent B).
    """

    return {
        "revision": 12,
        "teams": {"home": {"name": "EAGLES", "score": 1}, "away": {"name": "TIGERS", "score": 0}},
        "period": "1st", "period_display": "1st Half", "period_display_short": "1ST",
        "lifecycle": "IN_PROGRESS",
        "clocks": {"game": {"display": "31:07", "status": "RUNNING", "running": True,
                             "seconds": 1867, "maximum_seconds": 2400, "full_display": "31:07",
                             "label": "GAME CLOCK"}},
        "soccer": {
            "home": {"shots_display": "S 4", "saves_display": "SV 2", "corners_display": "COR 3",
                     "fouls_display": "F 1", "cards": {"yellow_display": "Y 1", "red_display": ""}},
            "away": {"shots_display": "S 6", "saves_display": "SV 3", "corners_display": "COR 5",
                     "fouls_display": "F 2", "cards": {"yellow_display": "", "red_display": ""}},
            "shootout": {"home_display": "", "away_display": ""},
        },
        "status": {"display": "", "clock_display": ""},
        "board": {"hidden_widgets": [], "hidden_element_prefixes": list(sl.hidden_element_prefixes())},
    }


class SoccerLayoutEditorBrowserTests(unittest.TestCase):
    def test_editor_shows_only_soccer_widgets_and_builds_the_soccer_board(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scoreboard-soccer-editor-") as directory:
            paths = resolve_paths(Path(directory)).ensure()
            layouts = PresentationLayouts(paths, layout_module=sl)

            state = layouts.state()
            valid = layouts.preview(layouts.current_layout())
            draft = json.loads(json.dumps(layouts.current_layout()))

            payload = {
                "state": state,
                "snapshot": _sample_soccer_snapshot(),
                "validPreview": valid,
                "clamped": layouts.clamp(draft),
                "resetWidget": layouts.reset_widget("period", draft, "game"),
                "saved": layouts.save("Default", layouts.current_layout()),
            }

        result = run_browser("soccer_editor.cjs", payload)

        self.assertEqual(result["checks"], [
            "soccer widget list only",
            "soccer widget selectable",
            "preview board kind is soccer after a screen switch",
            "preview board draws soccer widgets only",
            "no unexpected page scroll",
        ])

    def test_a_soccer_session_never_writes_footballs_layouts_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scoreboard-soccer-editor-paths-") as directory:
            root_paths = resolve_paths(Path(directory)).ensure()
            soccer_paths = root_paths.for_sport("soccer")
            soccer_paths.ensure()
            layouts = PresentationLayouts(soccer_paths, layout_module=sl)
            layouts.save("Soccer save", layouts.current_layout())

            self.assertTrue(soccer_paths.layouts.exists())
            self.assertFalse(root_paths.layouts.exists())


if __name__ == "__main__":
    unittest.main()
