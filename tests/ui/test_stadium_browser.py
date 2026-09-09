"""Exercise the stadium preset with real payloads, offline rendering and editing."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from scoreboard.domain.state import BallSpot, ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.presentation.layout import preset_descriptors, validate_layout
from tests.ui.browser_support import run_browser


class StadiumBrowserTests(unittest.TestCase):
    def test_readability_lifecycle_cutscene_restore_and_editable_preset(self):
        from scoreboard.presentation.cutscenes import build_program, builtin_pack

        layout = next(p['layout'] for p in preset_descriptors() if p['id'] == 'stadium')
        game = GameState(lifecycle='IN_PROGRESS', quarter='4th', home_name='TIGERS',
                         away_name='EAGLES', home_score=28, away_score=17,
                         game_clock=ClockValue(562, False, 720),
                         play_clock=ClockValue(25, False, 40), play_clock_cleared=False,
                         down=3, distance=4, possession='home', ball_on=BallSpot('away', 35))
        games = [spectator_view_model(game)]
        for score in (0, 99, 100, 199):
            games.append(spectator_view_model(replace(
                game, home_name='W' * 24, away_name='W' * 24,
                home_score=score, away_score=score, distance=0,
                game_clock=ClockValue(720, True, 720),
                game_status='TIMEOUT', status_clock=ClockValue(60, True, 300),
                status_clock_cleared=False)))
        games.append(spectator_view_model(replace(game, possession='away',
            game_clock=ClockValue(59.9, False, 720),
            play_clock=ClockValue(0, False, 40))))
        games.append(spectator_view_model(replace(game, play_clock_cleared=True,
                                                 down=None, distance=None, ball_on=None)))
        events = [spectator_view_model(GameState())]
        events += [spectator_view_model(replace(game, quarter='HALF', lifecycle='HALFTIME',
                    home_name='W' * 24, away_name='W' * 24, home_score=199, away_score=199,
                    game_clock=ClockValue(s, False, 900)))
                   for s in (900, 181, 180, 0)]
        with tempfile.TemporaryDirectory(prefix='stadium-editor-') as folder:
            layouts = PresentationLayouts(resolve_paths(Path(folder)).ensure())
            payload = {'layout': layout, 'games': games, 'events': events,
                       'state': layouts.state(), 'valid': layouts.preview(layout)}
            # The same program the host sends; the browser cancels it early
            # and verifies restoration to the chosen screen, not the default.
            broadcast = next(p['layout'] for p in preset_descriptors() if p['id'] == 'broadcast')
            payload['cutscene'] = build_program(play_id=700, event='touchdown',
                pack=builtin_pack('touchdown'), spectator_view=games[0], layout=broadcast)
            result = run_browser('stadium.cjs', payload)
            self.assertEqual(result['cases'], 60)
            draft = result['savedDraft']
            self.assertTrue(validate_layout(draft).ok)
            self.assertEqual(draft['widgets'], layout['widgets'])
            self.assertEqual(draft['screens'], layout['screens'])
            saved = layouts.save('Tigers Stadium', draft)
            self.assertTrue(saved['ok'], saved)
            reopened = PresentationLayouts(resolve_paths(Path(folder)))
            self.assertEqual(reopened.current_layout(), validate_layout({**draft, 'name': 'Tigers Stadium'}).layout)
