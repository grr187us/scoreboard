"""The Broadcast Welcome default screens and the Kickoff Clock / Fifty Yard
Line presets on the real spectator page (event-screens spec section 3.5):
three viewports, motion on and off, real view models, then each layout
round-tripped through PresentationLayouts.save exactly as the stadium test
does. Set SCOREBOARD_CAPTURE_DIR to keep a screenshot per screen, motion
state and viewport width (``<screen>-<motion>-<width>.png``)."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from scoreboard.domain.state import ClockValue, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.presentation.layout import default_layout, screen_preset_descriptors, validate_layout
from tests.ui.browser_support import run_browser

PINNED_PRESETS = ('pregame_kickoff_clock', 'pregame_fifty', 'halftime_kickoff_clock', 'halftime_fifty')


def _event_screen_layouts():
    """The default layout (its pregame and halftime are the welcome screens)
    plus one copy per pinned preset with that screen swapped in."""
    presets = {entry['id']: entry['screen']
               for entries in screen_preset_descriptors().values() for entry in entries}
    screens = [{'id': 'pregame_welcome', 'screen': 'pregame', 'layout': default_layout()},
               {'id': 'halftime_welcome', 'screen': 'halftime', 'layout': default_layout()}]
    for preset_id in PINNED_PRESETS:
        screen_id = preset_id.split('_')[0]
        layout = default_layout()
        layout['screens'][screen_id] = presets[preset_id]
        screens.append({'id': preset_id, 'screen': screen_id, 'layout': layout})
    return screens


class EventScreensBrowserTests(unittest.TestCase):
    def test_welcome_kickoff_and_fifty_at_three_viewports_with_motion_on_and_off(self):
        screens = _event_screen_layouts()
        long_name = 'W' * 24
        # Pregame shows the game clock; the second model also moves it so the
        # persistence check sees a clock text change on the pregame screens.
        pregame = [spectator_view_model(GameState()),
                   spectator_view_model(GameState(home_name=long_name, away_name=long_name,
                                                  game_clock=ClockValue(1799, False, 1800)))]
        halftime = GameState(quarter='HALF', lifecycle='HALFTIME', home_name=long_name,
                             away_name=long_name, home_score=199, away_score=199)
        halftime_models = [spectator_view_model(replace(halftime, game_clock=ClockValue(s, False, 900)))
                           for s in (900, 181, 180, 0)]
        halftime_models.append(spectator_view_model(replace(
            halftime, home_name='TIGERS', away_name='EAGLES', home_score=7, away_score=3,
            game_clock=ClockValue(600, False, 900))))
        # 180 s flips the phase to WARMUP, 0 s reads 0:00 (spec section 3.5).
        self.assertEqual(halftime_models[2]['clocks']['event']['phase'], 'WARMUP')
        self.assertEqual(halftime_models[3]['clocks']['event']['display'], '0:00')

        result = run_browser('event_screens.cjs', {
            'screens': screens, 'models': {'pregame': pregame, 'halftime': halftime_models},
        })
        # 3 pregame screens x 3 viewports x 2 motion states x 2 models
        # + 3 halftime screens x 3 x 2 x 5 models.
        self.assertEqual(result['cases'], 3 * 3 * 2 * 2 + 3 * 3 * 2 * 5)

        with tempfile.TemporaryDirectory(prefix='event-screens-') as folder:
            paths = resolve_paths(Path(folder)).ensure()
            library = PresentationLayouts(paths)
            for entry in screens:
                validation = validate_layout(entry['layout'])
                self.assertTrue(validation.ok, (entry['id'], validation.errors))
                self.assertEqual(validation.warnings, (), entry['id'])
                saved = library.save(entry['id'], entry['layout'])
                self.assertTrue(saved['ok'], (entry['id'], saved))
                reopened = PresentationLayouts(paths)
                self.assertEqual(reopened.current_layout(),
                                 validate_layout({**entry['layout'], 'name': entry['id']}).layout)


if __name__ == '__main__':
    unittest.main()
