"""Keyboard metadata is constrained without adding another command API."""
from scoreboard.host.bridge import build_command
from tests.integration.test_host_application import ApplicationTestCase
from scoreboard.infrastructure.persistence import read_action_history


class KeyboardSourceTests(ApplicationTestCase):
    def test_keyboard_source_is_kept_for_prompt_accept_and_rejection(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('game_clock_start')
        args = {'source': 'operator-keyboard'}
        prompt = bridge.command('quarter_forward', args, 1)
        self.assertTrue(prompt['confirmation_required'])
        accepted = bridge.command('quarter_forward', {**args, 'confirmed': True}, 1)
        self.assertTrue(accepted['accepted'])
        bridge.command('quarter_forward', args, 1)
        rows = read_action_history(self.paths.database)[-3:]
        self.assertTrue(all(r['source'] == 'operator-keyboard' for r in rows))
        self.assertEqual(rows[-1]['error_code'], 'STALE_REVISION')

    def test_invalid_source_values_are_refused(self):
        for source in ('remote', '', None, 42, [], {}):
            with self.subTest(source=source):
                error = build_command('add_score', {'team':'home', 'points':6, 'source':source})
                self.assertEqual(error.code, 'INVALID_ARGUMENTS')
