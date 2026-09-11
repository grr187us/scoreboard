"""Defensive impact through the actual Python program and spectator player."""
from dataclasses import replace
import unittest
from scoreboard.domain.state import ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.presentation.cutscenes import build_program, builtin_pack
from scoreboard.presentation.layout import preset_descriptors
from tests.ui.browser_support import run_browser

class TurnoverBrowserTests(unittest.TestCase):
    def test_impact_readability_and_recovery(self):
        layouts = {p['id']: p['layout'] for p in preset_descriptors()}
        state = GameState(lifecycle='IN_PROGRESS', quarter='2nd', home_score=14,
                          game_clock=ClockValue(522, True, 720), revision=42)
        view = spectator_view_model(state)
        program = build_program(play_id=1, event='turnover', pack=builtin_pack('turnover'),
                                spectator_view=view, layout=layouts['broadcast'], board_layout=layouts['grid'])
        self.assertEqual(program['duration_ms'], 5000)
        self.assertEqual(program['intro'], {'id':'none', 'duration_ms':0})
        result = run_browser('turnover.cjs', dict(program=program, layout=layouts['grid'], view=view,
            nextView=spectator_view_model(replace(state, game_clock=ClockValue(519, True, 720)))))
        self.assertEqual(result['cases'], 5)
        self.assertEqual(result['errors'], [])
