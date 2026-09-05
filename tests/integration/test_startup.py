"""Startup handoff tests with real recovery/storage and mocked native windows."""
from unittest.mock import MagicMock, patch

from scoreboard.host.app import WindowHost
from scoreboard.host.startup import StartupBridge
from scoreboard.infrastructure.persistence import read_action_history
from tests.integration.test_host_application import ApplicationTestCase


class StartupSurfaceTests(ApplicationTestCase):
    def saved(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('add_score', {'team': 'home', 'points': 6})
        bridge.command('game_clock_start')
        self.monotonic.advance(20)
        app.shutdown()

    def test_inspection_and_closing_without_choice_do_not_start_service(self):
        self.saved()
        app = self.make_application()
        before = read_action_history(self.paths.database)
        host = WindowHost(app)
        with patch('scoreboard.host.app.webview.create_window') as create, patch('scoreboard.host.app.webview.start'):
            host.run(interactive=True)
        api = create.call_args.kwargs['js_api']
        self.assertIsInstance(api, StartupBridge)
        self.assertFalse(hasattr(api, 'command'))
        report = api.get_recovery()
        self.assertEqual(report['source'], 'PRIMARY')
        self.assertIsNotNone(report['checkpoint_at'])
        self.assertEqual(report['view']['clocks']['game']['display'], '11:40')
        self.assertIsNone(app.service)
        self.assertEqual(before, read_action_history(self.paths.database))

    def test_resume_hands_over_once_to_normal_bridge_with_stopped_clocks(self):
        self.saved()
        app = self.make_application()
        host = WindowHost(app)
        startup = MagicMock()
        host.startup_window = startup
        api = StartupBridge(app.recovery_payload, host._choose_startup)
        with patch('scoreboard.host.app.webview.create_window') as create:
            api.resume_recovered_game()
            api.start_new_game()  # duplicate/late callback cannot replace the choice
        create.assert_called_once()
        self.assertIs(create.call_args.kwargs['js_api'], app.bridge)
        self.assertEqual(app.service.state.home_score, 6)
        self.assertFalse(app.service.state.game_clock.running)
        startup.destroy.assert_called_once()

    def test_new_choice_preserves_saved_history(self):
        self.saved()
        app = self.make_application()
        host = WindowHost(app)
        with patch('scoreboard.host.app.webview.create_window'):
            StartupBridge(app.recovery_payload, host._choose_startup).start_new_game()
        self.assertEqual(app.service.state.home_score, 0)
        self.assertIn('add_score', [r['command'] for r in read_action_history(self.paths.database)])

    def test_backup_source_and_unavailable_resume_are_explicit(self):
        self.saved()
        self.paths.database.write_bytes(b'broken')
        app = self.make_application()
        report = app.recovery_payload()
        self.assertTrue(report['using_backup'])
        self.assertIn('BACKUP', report['message'])
        self.assertFalse(report['view']['clocks']['game']['running'])

    def test_resume_without_saved_game_is_rejected_without_session(self):
        app = self.make_application()
        host = WindowHost(app)
        with self.assertRaises(ValueError):
            StartupBridge(app.recovery_payload, host._choose_startup).resume_recovered_game()
        self.assertIsNone(app.bridge)
