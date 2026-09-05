"""Bundle A: pregame game-clock workflow and quarter safety boundaries."""

from __future__ import annotations

import tempfile
import unittest

from scoreboard.application.service import ScoreboardService
from scoreboard.application.recovery import inspect_recovery
from scoreboard.domain import commands as cmd
from scoreboard.domain.commands import Command, CommandType
from scoreboard.host.bridge import spectator_view_model
from scoreboard.infrastructure.paths import resolve_paths
from scoreboard.infrastructure.persistence import GameStore, read_action_history
from tests.integration.support import FakeMonotonic, FakeWallClock


class PregameGameClockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeMonotonic()
        self.service = ScoreboardService(monotonic_clock=self.clock)

    def submit(self, command):
        result = self.service.submit(command)
        self.assertTrue(result.accepted, result.error)
        return result

    def enter_first(self) -> None:
        prompt = self.service.submit(cmd.quarter_forward())
        self.assertTrue(prompt.confirmation_required)
        self.submit(cmd.quarter_forward(confirmed=True))

    def test_new_game_and_pregame_controls_use_one_authoritative_30_minute_clock(self):
        state = self.service.state
        self.assertEqual((state.quarter, state.lifecycle), ("PRE", "PRE_GAME"))
        self.assertEqual((state.game_clock.seconds, state.game_clock.running), (1800.0, False))
        view = spectator_view_model(state)
        self.assertEqual(view["clocks"]["game"]["display"], "30:00")
        self.assertEqual(view["clocks"]["event"]["title"], "KICKOFF IN")
        self.assertEqual(view["clocks"]["event"]["display"], "30:00")

        self.submit(cmd.game_clock_start())
        self.assertEqual(self.service.state.lifecycle, "PRE_GAME")
        self.assertFalse(self.service.state.play_clock.running)
        self.clock.advance(90.5)
        stopped = self.submit(cmd.game_clock_stop())
        self.assertAlmostEqual(stopped.state.game_clock.seconds, 1709.5)
        corrected = self.submit(cmd.game_clock_correct(61.5))
        self.assertEqual((corrected.state.game_clock.seconds, corrected.state.game_clock.running), (61.5, False))
        reset = self.submit(cmd.game_clock_reset())
        self.assertEqual((reset.state.game_clock.seconds, reset.state.game_clock.running), (1800.0, False))

    def test_pregame_expiry_stays_pre_and_does_not_clear_play_clock(self):
        self.submit(cmd.play_clock_preset_start(25.0))
        self.submit(cmd.game_clock_correct(1.0))
        self.submit(cmd.game_clock_start())
        self.clock.advance(2.0)
        observed = self.service.observe_tick()
        self.assertTrue(observed.game_clock_expired)
        self.assertFalse(observed.play_clock_cleared)
        self.assertEqual((observed.state.quarter, observed.state.lifecycle), ("PRE", "PRE_GAME"))
        self.assertEqual((observed.state.game_clock.seconds, observed.state.game_clock.running), (0.0, False))
        self.assertTrue(observed.state.play_clock.running)

    def test_all_quarter_paths_need_a_same_revision_confirmation_and_cancel_changes_nothing(self):
        for command in (cmd.quarter_forward(), cmd.set_quarter("1st")):
            with self.subTest(command=command.type):
                before = self.service.state
                prompt = self.service.submit(command)
                self.assertTrue(prompt.confirmation_required)
                self.assertEqual(prompt.state, before)
                self.assertEqual(prompt.confirmation["accept_label"],
                                 "Start 1st quarter — discard remaining pregame time")
                self.assertEqual(prompt.confirmation["title"], "Discard remaining pregame time?")

        self.submit(cmd.quarter_forward(confirmed=True))
        self.assertEqual((self.service.state.quarter, self.service.state.game_clock.seconds), ("1st", 720.0))
        prompt = self.service.submit(cmd.quarter_back())
        self.assertTrue(prompt.confirmation_required)
        self.assertIn("from 1st to PRE", prompt.confirmation["detail"])
        self.submit(cmd.quarter_back(confirmed=True))
        self.assertEqual((self.service.state.quarter, self.service.state.game_clock.seconds), ("PRE", 1800.0))

    def test_zero_pregame_uses_normal_confirmation_and_live_clock_coupling_returns_in_first(self):
        self.submit(cmd.game_clock_correct(0.0))
        prompt = self.service.submit(cmd.quarter_forward())
        self.assertTrue(prompt.confirmation_required)
        self.assertEqual(prompt.confirmation["accept_label"], "Change to 1st")
        self.assertNotIn("discard remaining pregame", prompt.confirmation["detail"].lower())
        self.submit(cmd.quarter_forward(confirmed=True))
        self.submit(cmd.play_clock_preset_start(25.0))
        started = self.submit(cmd.game_clock_start())
        self.assertTrue(started.state.game_clock.running)
        self.assertFalse(started.state.play_clock.running)

    def test_stale_confirmed_direct_selection_is_rejected(self):
        prompt = self.service.submit(cmd.set_quarter("1st", source="operator-keyboard"))
        self.assertTrue(prompt.confirmation_required)
        revision = self.service.revision
        self.submit(cmd.add_score("home", 6))
        stale = self.service.submit(Command(
            CommandType.SET_QUARTER, label="1st", confirmed=True,
            source="operator-keyboard", expected_revision=revision,
        ))
        self.assertFalse(stale.accepted)
        self.assertEqual(stale.error.code, cmd.STALE_REVISION)


class PregameRecoveryAndHistoryTests(unittest.TestCase):
    def test_recovery_stops_and_restores_pregame_game_clock_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            paths = resolve_paths(root)
            paths.ensure()
            monotonic = FakeMonotonic()
            store = GameStore.open(paths, wall_clock=FakeWallClock())
            service = ScoreboardService(monotonic_clock=monotonic)
            store.begin_session(service.state)
            start = cmd.game_clock_start()
            result = service.submit(start)
            store.record_command(start, result)
            monotonic.advance(17.25)
            store.checkpoint(service.materialized_state())
            store.close()
            recovered = inspect_recovery(paths)
            self.assertEqual((recovered.state.quarter, recovered.state.lifecycle), ("PRE", "PRE_GAME"))
            self.assertFalse(recovered.state.game_clock.running)
            self.assertAlmostEqual(recovered.state.game_clock.seconds, 1782.75)
            rows = read_action_history(paths.database)
            self.assertEqual(rows[-1]["command"], "game_clock_start")
