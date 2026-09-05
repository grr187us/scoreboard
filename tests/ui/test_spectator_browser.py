"""Render real Python view models in an offline Edge page at measured viewports."""
from dataclasses import replace
from pathlib import Path
import unittest

from scoreboard.domain.state import ClockValue, GameState
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
        result = run_browser('spectator.cjs', {'games': games, 'events': events,
                             'pregame': spectator_view_model(GameState()), 'zero': zero, 'blank': blank,
                             'runningGame': running_game, 'runningPlay': running_play})
        self.assertEqual(result['cases'], 36)

    def test_renderer_contains_no_authoritative_computation_or_controls(self):
        root = Path(__file__).resolve().parents[2] / 'src/scoreboard/views'
        script = (root / 'spectator/spectator.js').read_text()
        for forbidden in ('Math.', 'toFixed', 'parseInt', 'parseFloat', 'setInterval',
                          '.seconds', 'revision++', 'api.command'):
            self.assertNotIn(forbidden, script)
        html = (root / 'spectator/index.html').read_text()
        for forbidden in ('<button', '<input', '<dialog', 'data-command', 'data-action'):
            self.assertNotIn(forbidden, html)
