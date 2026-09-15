"""GOAL cutscene artwork exercised through real Python programs and the
real player (``views/soccer_spectator/cutscene.js`` + ``cutscenes/soccer.js``).

``views/soccer_spectator/index.html`` (agent D's) does not exist yet at the
time this test was written, so it plays the programs against a minimal
test-only page, ``.scratch/soccer-mode/preview/goal/index.html`` -- see that
file's own header comment. It loads the same four files (the two frozen-shape
CSS files and the two JS files) the real spectator page needs; this agent's
final report names the exact tags for agent D to add.
"""
import unittest

from scoreboard.presentation.soccer_cutscenes import build_program, builtin_pack
from tests.ui.browser_support import run_browser


class SoccerGoalBrowserTests(unittest.TestCase):
    def _layout(self) -> dict:
        return {"schema_version": 3, "name": "Broadcast bar", "widgets": {}, "screens": {}}

    def _view(self) -> dict:
        return {
            "teams": {
                "home": {"name": "Eagles", "score": 1, "primary": "#123456"},
                "away": {"name": "Hawks", "score": 0, "primary": "#654321"},
            },
        }

    def test_goal_scene_timeline_readability_and_recovery(self) -> None:
        view = self._view()
        layout = self._layout()
        pack = builtin_pack("goal")

        programs = {
            "home": build_program(
                play_id=1, event="goal", pack=pack, spectator_view=view,
                layout=layout, team="home",
            ),
            "away": build_program(
                play_id=1, event="goal", pack=pack, spectator_view=view,
                layout=layout, team="away",
            ),
        }

        self.assertEqual(programs["home"]["duration_ms"], 7000)
        self.assertEqual(programs["home"]["intro"], {"id": "none", "duration_ms": 0})
        self.assertEqual(programs["home"]["texts"]["team_name"], "Eagles")
        self.assertEqual(programs["away"]["texts"]["team_name"], "Hawks")
        self.assertEqual(programs["home"]["theme"]["home_primary"], "#123456")
        self.assertEqual(programs["away"]["theme"]["away_primary"], "#654321")

        result = run_browser("soccer_goal.cjs", {"programs": programs})

        self.assertEqual(result["errors"], [])
        self.assertEqual(result["cases"], 5)


if __name__ == "__main__":
    unittest.main()
