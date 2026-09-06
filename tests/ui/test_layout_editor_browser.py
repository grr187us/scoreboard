"""Drive the layout editor in an offline Edge page against real Python payloads.

The stub bridge in ``layout_editor.cjs`` returns dictionaries produced here by
the real :class:`~scoreboard.host.layout_bridge.PresentationLayouts`, so the
page is tested against the shapes it will actually be handed rather than
against fixtures that could drift from the bridge.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from tests.ui.browser_support import run_browser


class LayoutEditorBrowserTests(unittest.TestCase):
    def test_selection_editing_validation_and_saving(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scoreboard-layout-editor-") as directory:
            paths = resolve_paths(Path(directory)).ensure()
            layouts = PresentationLayouts(paths)

            state = layouts.state()
            valid = layouts.preview(layouts.current_layout())

            # The one case the page must treat as unsaveable: a widget pushed
            # past the bottom safe-area edge.
            invalid_draft = json.loads(json.dumps(layouts.current_layout()))
            invalid_draft["widgets"]["ball_on"]["y"] = 0.930
            invalid = layouts.preview(invalid_draft)
            self.assertFalse(invalid["ok"], "the fixture must actually be invalid")

            snapshot = spectator_view_model(GameState(
                lifecycle="IN_PROGRESS", quarter="4th", home_name="EAGLES",
                away_name="TIGERS", home_score=21, away_score=17,
                play_clock=ClockValue(40, False, 40), play_clock_cleared=False,
                down=4, distance=0, possession="home", ball_on=BallSpot("away", 35),
                home_timeouts=3, away_timeouts=2, revision=42))

            payload = {
                "state": state,
                "snapshot": snapshot,
                "validPreview": valid,
                "invalidPreview": invalid,
                "clamped": layouts.clamp(invalid_draft),
                "resetWidget": layouts.reset_widget("ball_on", invalid_draft, "game"),
                "saved": layouts.save("Default", layouts.current_layout()),
            }

        result = run_browser("layout_editor.cjs", payload)

        self.assertEqual(result["checks"], [
            "widget list", "property panel", "numeric move", "visibility toggle",
            "preview selection", "validation blocks save", "validation clears",
            "issue selects widget", "reset widget", "reset widget names the screen",
            "save as",
            "drag to move", "safe area is a hard boundary", "resize by handle",
            "nudge by key and button", "arrows leave fields alone",
            "history back and forward", "add text element", "add box", "align",
            "multi-select drag", "delete element",
            "switch to pre-game", "apply a pre-game preset",
            "add text on the pre-game screen", "switch back to the game screen",
            "save after editing another screen",
            "no page scroll", "no game command",
        ])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
