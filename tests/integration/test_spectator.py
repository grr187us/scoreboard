"""Task 8 authority/publication regressions, without wall-clock timing."""
from scoreboard.application.snapshots import snapshot_to_state, state_to_snapshot
from scoreboard.host.bridge import SpectatorBridge
from tests.integration.test_host_application import ApplicationTestCase


class SpectatorFoundationTests(ApplicationTestCase):
    def test_accepted_commands_push_once_without_tick_rejections_do_not(self):
        app = self.make_application()
        bridge = app.start_new()
        pushes = []
        app.set_publisher(lambda name, view: pushes.append((name, view)))
        result = bridge.command('add_score', {'team': 'home', 'points': 6}, 0)
        self.assertTrue(result['accepted'])
        self.assertEqual([name for name, _ in pushes], ['operator', 'spectator'])
        self.assertEqual(pushes[1][1]['revision'], 1)
        self.assertEqual(pushes[1][1]['teams']['home']['score'], 6)
        bridge.command('add_score', {'team': 'home', 'points': 6}, 0)
        self.assertEqual(len(pushes), 2)

    def test_expired_zero_survives_commands_reopen_and_recovery_until_clear(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('game_clock_start')
        self.assertEqual(bridge.spectator_snapshot()['clocks']['play']['display'], '—')
        bridge.command('play_clock_preset', {'seconds': 25})
        bridge.command('play_clock_start')
        self.monotonic.advance(26)
        app.tick()
        bridge.command('add_score', {'team': 'home', 'points': 6})
        app.spectator_closed()
        app.spectator_opened()
        reopened = SpectatorBridge(bridge.spectator_snapshot).get_snapshot()
        self.assertEqual(reopened['clocks']['play']['display'], '0')
        self.assertEqual(reopened['revision'], app.service.revision)
        app.shutdown()
        recovered = self.make_application().resume()
        self.assertEqual(recovered.spectator_snapshot()['clocks']['play']['display'], '0')
        recovered.command('play_clock_clear')
        self.assertEqual(recovered.spectator_snapshot()['clocks']['play']['display'], '—')

    def test_spectator_uses_clear_wording_and_expanded_live_quarter(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('set_quarter', {'label': '2nd', 'confirmed': True})
        view = bridge.spectator_snapshot()

        self.assertEqual(view['quarter'], '2nd')
        self.assertEqual(view['quarter_display'], '2nd Quarter')
        self.assertEqual(view['clocks']['play']['display'], '—')

        bridge.command('game_clock_start')
        bridge.command('play_clock_preset', {'seconds': 25})
        bridge.command('play_clock_start')
        running = bridge.spectator_snapshot()
        self.assertTrue(running['clocks']['game']['running'])
        self.assertTrue(running['clocks']['play']['running'])

    def test_active_play_clock_reopen_has_current_complete_snapshot(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('game_clock_start')
        bridge.command('play_clock_preset', {'seconds': 40})
        bridge.command('play_clock_start')
        app.spectator_closed()
        self.monotonic.advance(7)
        app.spectator_opened()
        current = SpectatorBridge(bridge.spectator_snapshot).get_snapshot()
        self.assertEqual(current['clocks']['play']['display'], '33')
        self.assertTrue(current['clocks']['play']['running'])
        self.assertEqual(current['revision'], 3)

    def test_push_failure_during_command_leaves_operator_usable_and_clocks_running(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('game_clock_start')
        def fail(name, view):
            if name == 'spectator':
                raise RuntimeError('injected renderer failure')
        app.set_publisher(fail)
        result = bridge.command('add_score', {'team': 'away', 'points': 6})
        self.assertTrue(result['accepted'])
        self.monotonic.advance(5)
        result = bridge.command('add_score', {'team': 'home', 'points': 3})
        self.assertTrue(result['accepted'])
        self.assertEqual(result['view']['clocks']['game']['display'], '29:55')
        self.assertTrue(result['view']['clocks']['game']['running'])
        self.assertFalse(result['view']['health']['display']['open'])

    def test_lifecycle_transitions_name_lock_undo_and_countdown_boundaries(self):
        app = self.make_application()
        bridge = app.start_new()
        bridge.command('quarter_forward', {'confirmed': True})
        self.assertEqual(app.service.state.lifecycle, 'IN_PROGRESS')
        self.assertFalse(bridge.command('set_team_name', {'team': 'home', 'name': 'EAGLES'})['accepted'])
        # Follow-up 01: leaving PRE loads a fresh quarter clock, so a simple
        # quarter-only Undo could not restore the discarded pregame countdown
        # and is deliberately refused (matches
        # GameClockCommandTests.test_a_confirmed_quarter_change_cannot_be_undone).
        self.assertFalse(bridge.command('undo')['accepted'])
        self.assertEqual(app.service.state.lifecycle, 'IN_PROGRESS')
        bridge.command('set_quarter', {'label': 'HALF', 'confirmed': True})
        self.assertEqual(app.service.state.lifecycle, 'HALFTIME')
        self.assertEqual(bridge.spectator_snapshot()['clocks']['event']['display'], '15:00')
        for seconds, display, phase in [(900, '15:00', 'HALFTIME'), (181, '3:01', 'HALFTIME'),
                                        (180, '3:00', 'WARMUP'), (0, '0:00', 'WARMUP')]:
            bridge.command('game_clock_correct', {'seconds': seconds})
            event = bridge.spectator_snapshot()['clocks']['event']
            self.assertEqual((event['display'], event['phase']), (display, phase))
            self.assertEqual(event['warmup_follows'], '3:00' if phase == 'HALFTIME' else None)
        bridge.command('game_clock_start')
        # docs/MVP_REQUIREMENTS.md 4.3: "only an accepted quarter transition
        # enters IN_PROGRESS" -- a game-clock Start at the end of warmup no
        # longer carries an implicit quarter change, so lifecycle stays
        # HALFTIME until the operator explicitly (and now confirmed) advances
        # the quarter.
        self.assertEqual(app.service.state.lifecycle, 'HALFTIME')
        bridge.command('quarter_forward', {'confirmed': True})
        self.assertEqual(app.service.state.lifecycle, 'IN_PROGRESS')
        bridge.command('end_game')
        self.assertEqual(app.service.state.lifecycle, 'FINAL')
        bridge.command('new_game', {'confirmed': True})
        self.assertEqual(app.service.state.lifecycle, 'PRE_GAME')

    def test_legacy_snapshot_zero_keeps_previous_blank_behavior(self):
        app = self.make_application()
        app.start_new()
        old = state_to_snapshot(app.service.state)
        del old['play_clock_cleared']
        self.assertTrue(snapshot_to_state(old).play_clock_cleared)
