"""Real renderer/editor verification for the image-inspired Grid preset."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.presentation.layout import default_layout, preset_descriptors, validate_layout
from tests.ui.browser_support import run_browser


class GridBrowserTests(unittest.TestCase):
    def test_readouts_viewports_format_edits_save_and_reopen(self):
        presets = {p['id']: p['layout'] for p in preset_descriptors()}
        state = GameState(lifecycle='IN_PROGRESS', quarter='3rd', home_score=21, away_score=14,
                          game_clock=ClockValue(522, False, 720),
                          play_clock=ClockValue(25, False, 40), play_clock_cleared=False,
                          down=2, distance=7, ball_on=BallSpot('away',35), home_timeouts=2)
        states = [state]
        for count in range(4):
            states.append(replace(state, home_name='W'*24, away_name='W'*24,
                home_score=(0,99,100,199)[count], away_score=(199,100,99,0)[count],
                quarter=('1st','2nd','3rd','4th')[count], down=count+1, distance=0,
                home_timeouts=count, away_timeouts=3-count, possession='home',
                game_status='TIMEOUT', status_clock=ClockValue(60, True, 300),
                status_clock_cleared=False, game_clock=ClockValue(720, True, 720)))
        states += [replace(state, quarter='OT', distance=99, ball_on=BallSpot('home',50),
                           play_clock=ClockValue(0,False,40)),
                   replace(state, quarter='FINAL', down=None, distance=None, ball_on=None,
                           play_clock_cleared=True)]
        # The game clock at its full 12:00, stopped -- the state the board is
        # in before the clock has ever started, where the too-large fit was
        # visible (bug 2: fit against Graduate's fallback face raced the
        # lazily-loaded web font and the stale, oversized fit stuck).
        clock_start = replace(state, game_clock=ClockValue(720, False, 720))
        with tempfile.TemporaryDirectory() as folder:
            paths = resolve_paths(Path(folder)).ensure()
            library = PresentationLayouts(paths)
            result = run_browser('grid.cjs', {
                'layout': presets['grid'], 'classic': presets['classic'],
                'models': [spectator_view_model(s) for s in states],
                'clock_start': spectator_view_model(clock_start),
                'pregame': spectator_view_model(GameState(game_clock=ClockValue(900, False, 1800))),
                'halftime': spectator_view_model(replace(state, quarter='HALF', lifecycle='HALFTIME',
                    game_clock=ClockValue(181, False, 900))),
                'state': library.state(), 'valid': library.preview(presets['grid']),
            })
            self.assertEqual(result['cases'],35)
            draft = result['savedDraft']
            self.assertTrue(validate_layout(draft).ok)
            self.assertEqual(draft['widgets'],presets['grid']['widgets'])
            # Applying a game preset still leaves both other screens intact.
            self.assertEqual(draft['screens'],default_layout()['screens'])
            self.assertTrue(library.save('Scoreboard Grid',draft)['ok'])
            self.assertEqual(PresentationLayouts(paths).current_layout(),
                             validate_layout({**draft,'name':'Scoreboard Grid'}).layout)
