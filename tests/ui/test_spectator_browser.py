"""Render real Python view models in an offline Edge page at measured viewports.

The board is drawn as independently positioned widgets (Task: presentation
layout editor), so these checks assert three separate things: that every
widget's *text* stays inside its own box and inside the layout's safe area at
every supported viewport, that a layout the host pushes actually moves the
widgets it names, and that a malformed layout leaves the previous good one on
screen. The default layout is the one Python owns; `board.js` only mirrors it,
and `tests/integration/test_spectator_layout_render.py` holds that contract.
"""
from dataclasses import replace
from pathlib import Path
import unittest

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from tests.ui.browser_support import run_browser


class SpectatorBrowserTests(unittest.TestCase):
    def test_viewport_values_phases_initial_snapshot_and_render_failure(self):
        play = GameState(lifecycle='IN_PROGRESS', quarter='4th', home_name='W' * 24,
                         away_name='W' * 24, play_clock=ClockValue(40, False, 40),
                         play_clock_cleared=False, revision=71)
        games = [spectator_view_model(replace(play, home_score=s, away_score=s))
                 for s in (0, 99, 100, 199)]
        events = [spectator_view_model(replace(play, lifecycle='HALFTIME', event_phase='HALFTIME',
                    event_countdown=ClockValue(s, False, 1800))) for s in (900, 181, 180, 0)]
        zero = spectator_view_model(replace(play, play_clock=ClockValue(0, False, 40)))
        blank = spectator_view_model(replace(play, play_clock=ClockValue(0, False, 40), play_clock_cleared=True))
        running_game = spectator_view_model(replace(play, game_clock=ClockValue(700, True, 720)))
        running_play = spectator_view_model(replace(play, play_clock=ClockValue(25, True, 40),
                                                     play_clock_cleared=False))
        # Every optional football field present at once, so a test can turn one
        # off and prove only that widget disappears.
        populated = spectator_view_model(replace(
            play, home_score=21, away_score=17, down=4, distance=0, possession='home',
            ball_on=BallSpot('away', 35), home_timeouts=3, away_timeouts=2))
        result = run_browser('spectator.cjs', {'games': games, 'events': events,
                             'pregame': spectator_view_model(GameState()), 'zero': zero, 'blank': blank,
                             'runningGame': running_game, 'runningPlay': running_play,
                             'populated': populated})
        self.assertEqual(result['cases'], 36)

    def test_renderer_contains_no_authoritative_computation_or_controls(self):
        root = Path(__file__).resolve().parents[2] / 'src/scoreboard/views'
        for name in ('spectator/spectator.js', 'shared/board.js'):
            script = (root / name).read_text(encoding='utf-8')
            for forbidden in ('Math.', 'toFixed', 'parseInt', 'parseFloat', 'setInterval',
                              '.seconds', 'revision++', 'api.command'):
                self.assertNotIn(forbidden, script, f'{name} must not derive a displayed value')
        html = (root / 'spectator/index.html').read_text(encoding='utf-8')
        for forbidden in ('<button', '<input', '<dialog', 'data-command', 'data-action'):
            self.assertNotIn(forbidden, html)
