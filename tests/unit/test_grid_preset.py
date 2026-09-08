"""Presentation formats stay derived, compatible, validated and persistent."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from scoreboard.domain.formatting import format_distance_value, format_timeout_dots
from scoreboard.domain.state import BallSpot, GameState
from scoreboard.host.bridge import spectator_view_model
from scoreboard.host.layout_bridge import PresentationLayouts
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.presentation.layout import (
    WIDGET_FORMAT_FIELDS, default_layout, preset_descriptors, screen_descriptors,
    validate_layout, widget_descriptors,
)
from tests.integration.test_spectator_layout_render import _extract_js_literal, BOARD_JS


class GridPresetTests(unittest.TestCase):
    def test_preset_validates_without_repairs(self):
        presets = {p['id']: p['layout'] for p in preset_descriptors()}
        grid = presets['grid']
        self.assertEqual(grid['name'], 'Scoreboard Grid')
        result = validate_layout(grid)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.warnings, ())
        for key, expected in {'quarter': 'ordinal', 'down': 'ordinal', 'distance': 'value',
                              'ball_on': 'value', 'home_timeouts': 'dots', 'away_timeouts': 'dots'}.items():
            self.assertEqual(grid['widgets'][key]['display_format'], expected)
        self.assertTrue(all(e['corner_radius'] == 0 for e in grid['elements']))

    def test_a_box_may_be_a_hairline_but_text_and_images_may_not(self):
        from scoreboard.presentation.layout import MIN_BOX_THICKNESS, MIN_WIDGET_HEIGHT, clamp_layout
        doc = default_layout()
        doc['elements'] = [{'id': 'rule', 'type': 'box', 'x': 0.1, 'y': 0.5, 'width': 0.3,
                            'height': MIN_BOX_THICKNESS, 'background': '#2869BC'}]
        result = validate_layout(doc)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.layout['elements'][0]['height'], MIN_BOX_THICKNESS)
        doc['elements'][0]['height'] = MIN_BOX_THICKNESS / 2
        self.assertIn('MIN_DIMENSION', [e.code for e in validate_layout(doc).errors])
        self.assertEqual(clamp_layout(doc)[0]['elements'][0]['height'], MIN_BOX_THICKNESS)
        for element_type in ('text', 'image'):
            doc['elements'] = [{'id': 'thin', 'type': element_type, 'x': 0.1, 'y': 0.5, 'width': 0.3,
                                'height': MIN_WIDGET_HEIGHT / 2, 'text': 'x'}]
            self.assertIn('MIN_DIMENSION', [e.code for e in validate_layout(doc).errors])

    def test_missing_property_keeps_old_wording_on_every_screen(self):
        original = default_layout()
        for screen in [original, *original['screens'].values()]:
            for widget in screen['widgets'].values():
                widget.pop('display_format')
                widget.pop('fit_text')
        result = validate_layout(original)
        self.assertTrue(result.ok)
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.layout, default_layout())

    def test_formats_reject_arbitrary_paths_wrong_widgets_and_bad_types(self):
        for widget, value in [('quarter', 'dots'), ('home_score', 'ordinal'),
                              ('distance', 'teams.home.score'), ('quarter', {}),
                              ('quarter', None), ('quarter', 1)]:
            with self.subTest(widget=widget, value=value):
                doc = default_layout()
                doc['widgets'][widget]['display_format'] = value
                result = validate_layout(doc)
                self.assertFalse(result.ok)
                self.assertIn('DISPLAY_FORMAT', [e.code for e in result.errors])
        doc = default_layout()
        doc['screens']['pregame']['widgets']['home_name']['display_format'] = 'dots'
        self.assertFalse(validate_layout(doc).ok)

    def test_format_bindings_match_renderer_and_editor_metadata(self):
        self.assertEqual(_extract_js_literal(BOARD_JS.read_text(encoding='utf-8'),
                                           'WIDGET_FORMAT_FIELDS'), WIDGET_FORMAT_FIELDS)
        for descriptors in [widget_descriptors(), screen_descriptors()[0]['widgets']]:
            for descriptor in descriptors:
                self.assertEqual([f['id'] for f in descriptor['formats']],
                                 ['default', *WIDGET_FORMAT_FIELDS.get(descriptor['id'], {})])

    def test_text_fitting_is_opt_in_and_boolean_only(self):
        self.assertFalse(default_layout()['widgets']['home_name']['fit_text'])
        for value in ('true', 1, None, []):
            doc = default_layout()
            doc['widgets']['home_name']['fit_text'] = value
            result = validate_layout(doc)
            self.assertFalse(result.ok)
            self.assertIn('FIT_TEXT', [e.code for e in result.errors])

    def test_all_timeout_counts_goal_missing_and_quarter_labels(self):
        for count, text in enumerate(('○ ○ ○', '● ○ ○', '● ● ○', '● ● ●')):
            self.assertEqual(format_timeout_dots(count), text)
            model = spectator_view_model(GameState(home_timeouts=count, away_timeouts=3-count))
            self.assertEqual(model['football']['home_timeouts_dots'], text)
            self.assertEqual(model['football']['away_timeouts_dots'], format_timeout_dots(3-count))
            self.assertEqual(model['football']['home_timeouts_display'], f'TO {count}')
        for invalid in (None, -1, 4, True, '2', 1.5):
            self.assertEqual(format_timeout_dots(invalid), '')
        for distance, expected in [(None, ''), (-1, ''), (0, 'Goal'), (7, '7'), (99, '99')]:
            self.assertEqual(format_distance_value(distance), expected)
        for quarter in ('1st', '2nd', '3rd', '4th', 'OT', 'FINAL'):
            state = GameState(quarter=quarter, down=2, distance=7, ball_on=BallSpot('away',35))
            model = spectator_view_model(state)
            self.assertEqual(model['quarter'], quarter)
            self.assertEqual(model['football']['down_display'], '2nd')
            self.assertEqual(model['football']['distance_value_display'], '7')
            self.assertEqual(model['football']['distance_display'], '& 7')
            self.assertEqual(model['football']['ball_on_value_display'], '35')
            self.assertEqual(model['football']['ball_on_display'], 'AWAY 35')
        missing = spectator_view_model(replace(state, down=None, distance=None, ball_on=None))
        self.assertEqual(missing['football']['down_display'], '')
        self.assertEqual(missing['football']['distance_value_display'], '')
        self.assertEqual(missing['football']['ball_on_value_display'], '—')

    def test_save_reload_retains_formats_without_game_database(self):
        grid = next(p['layout'] for p in preset_descriptors() if p['id'] == 'grid')
        with tempfile.TemporaryDirectory() as folder:
            paths = resolve_paths(Path(folder)).ensure()
            library = PresentationLayouts(paths)
            self.assertTrue(library.save('Scoreboard Grid', grid)['ok'])
            reopened = PresentationLayouts(paths)
            self.assertEqual(reopened.current_layout(), grid)
            self.assertFalse(list(Path(folder).glob('*.db')))
            self.assertEqual(json.loads(json.dumps(grid)), grid)
