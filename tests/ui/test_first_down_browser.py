"""First-down artwork exercised through real Python programs and the player."""
from dataclasses import replace
import unittest

from scoreboard.domain.state import ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.presentation.cutscenes import build_program, builtin_pack
from scoreboard.presentation.layout import preset_descriptors
from tests.ui.browser_support import run_browser


class FirstDownBrowserTests(unittest.TestCase):
    def test_material_scene_timeline_readability_and_recovery(self):
        layouts = {p['id']: p['layout'] for p in preset_descriptors()}
        state = GameState(lifecycle='IN_PROGRESS', quarter='2nd', home_name='TIGERS',
                          away_name='EAGLES', home_score=14, away_score=7,
                          game_clock=ClockValue(522, True, 720), revision=42)
        view = spectator_view_model(state)
        program = build_program(play_id=1, event='first_down', pack=builtin_pack('first_down'),
                                spectator_view=view, layout=layouts['broadcast'],
                                board_layout=layouts['grid'])
        self.assertEqual(program['duration_ms'], 5000)
        result = run_browser('first_down.cjs', {
            'program': program, 'layout': layouts['grid'], 'view': view,
            'nextView': spectator_view_model(replace(state, game_clock=ClockValue(519, True, 720))),
        })
        self.assertEqual(result['cases'], 4)
        self.assertEqual(result['errors'], [])


if __name__ == '__main__':
    unittest.main()
