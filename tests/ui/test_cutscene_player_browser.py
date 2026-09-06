"""Drive the spectator page's cutscene player in an offline Edge page.

The player is the one piece of the cutscene feature that has to be exactly
right on game night: whatever the animation does, the board must come back.
``cutscene_player.cjs`` therefore spends most of its assertions on the ways a
cutscene can *end* -- its own timer, the host's ``endCutscene``, a replacing
cutscene, a media file that will not open, a malformed program -- and checks
after every one of them that ``#canvas`` carries the operator's layout again
and ``#cutscene-stage`` is hidden and empty.

It also pins the two shapes v2 added: the claw intro's strike (a paw with two
motion-trail ghosts, four gouges, debris, and exactly one flash -- one, because
nothing on this wall may strobe), and a ``penalty`` program whose intro is
``none``, which must put the bar and the scene up on the very first frame
rather than waiting through a full-canvas moment that will never come. v3
adds the same first-frame check for ``make_some_noise`` (the 5 s crowd prompt
also has no intro) and pins the registry's six ids across the three scene
files in load order.

Same Playwright/Edge setup as ``test_spectator_browser.py``: the page is
loaded from ``file://`` with a stub ``window.pywebview.api`` built from a real
:func:`spectator_view_model` snapshot, and ``tests/ui/browser_support.py``
raises with setup instructions rather than failing obscurely when Node or
Playwright is missing.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from tests.ui.browser_support import run_browser


class CutscenePlayerBrowserTests(unittest.TestCase):
    def test_timeline_replace_fallback_and_restore(self) -> None:
        snapshot = spectator_view_model(GameState(
            lifecycle="IN_PROGRESS", quarter="3rd", home_name="TIGERS", away_name="EAGLES",
            home_score=14, away_score=7, game_clock=ClockValue(400.0, True, 720.0),
            play_clock=ClockValue(25.0, False, 40.0), play_clock_cleared=False,
            down=1, distance=10, possession="home", ball_on=BallSpot("away", 35),
            home_timeouts=3, away_timeouts=2, revision=42))

        result = run_browser("cutscene_player.cjs", {"snapshot": snapshot})

        self.assertEqual(result["checks"], [
            "idle baseline",
            "intro mounts full canvas",
            "override applied and scene mounted",
            "natural end restores",
            "early end restores",
            "missing media falls back to the builtin",
            "a second cutscene replaces the first",
            "malformed program ignored",
            "a layout push during a cutscene lands on restore",
            "a penalty plays with no intro",
            "make some noise plays with no intro",
            "no controls",
        ])

    def test_the_player_and_scenes_reach_no_network_and_no_command(self) -> None:
        # The browser run proves behaviour; this proves the two things a
        # behavioural test cannot see, on the same files it just exercised.
        root = Path(__file__).resolve().parents[2] / "src/scoreboard/views/spectator"
        for name in ("cutscene.js", "cutscenes/builtin.js", "cutscenes/tigers.js",
                     "cutscenes/crowd.js"):
            source = (root / name).read_text(encoding="utf-8")
            for forbidden in ("fetch(", "XMLHttpRequest", "api.command", "http://", "https://"):
                self.assertNotIn(forbidden, source, f"{forbidden!r} found in {name}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
