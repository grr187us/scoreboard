"""Unit tests for ``host.soccer_bridge``'s pure view-model builders.

Mirrors the style of football's view-model tests: hand-built ``SoccerState``
values, no service, no store, no filesystem. ``soccer_operator_view_model``
needs a live ``SoccerService`` (it reads ``materialized_state``/undo/period
decision/mercy from it), so it is covered in
``tests/integration/test_soccer_bridge.py`` instead; this file covers
``soccer_spectator_view_model``, which takes a raw ``SoccerState`` directly.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from scoreboard.domain.soccer.rules import default_soccer_rules
from scoreboard.domain.soccer.state import CardEvent, ShootoutKick, default_state
from scoreboard.host.soccer_bridge import soccer_spectator_view_model


class SpectatorViewModelTests(unittest.TestCase):
    def test_idle_pregame_shape(self) -> None:
        state = default_state()
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["period"], "PRE")
        self.assertEqual(view["period_display"], "Pregame")
        self.assertEqual(view["lifecycle"], "PRE_GAME")
        self.assertEqual(view["teams"]["home"]["name"], "HOME")
        self.assertEqual(view["teams"]["home"]["score"], 0)
        self.assertEqual(view["clocks"]["game"]["display"], "30:00")
        self.assertFalse(view["clocks"]["game"]["running"])
        self.assertEqual(view["board"]["hidden_widgets"], [])

    def test_every_period_has_a_display_string(self) -> None:
        for label in (
            "PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL",
        ):
            with self.subTest(period=label):
                state = replace(default_state(), period=label)
                view = soccer_spectator_view_model(state)
                self.assertTrue(view["period_display"])
                self.assertIsInstance(view["period_display"], str)

    def test_final_hides_the_clock_widgets(self) -> None:
        state = replace(default_state(), period="FINAL", lifecycle="FINAL")
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["board"]["hidden_widgets"], ["game_clock_label", "game_clock_value"])

    def test_shootout_hides_the_clock_widgets(self) -> None:
        state = replace(default_state(), period="SHOOTOUT")
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["board"]["hidden_widgets"], ["game_clock_label", "game_clock_value"])

    def test_live_period_shows_no_hidden_widgets(self) -> None:
        state = replace(default_state(), period="1st", lifecycle="IN_PROGRESS")
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["board"]["hidden_widgets"], [])

    def test_stats_and_their_display_strings(self) -> None:
        state = replace(
            default_state(),
            home_shots=4, home_saves=2, home_corners=3, home_fouls=1,
        )
        view = soccer_spectator_view_model(state)
        home = view["soccer"]["home"]
        self.assertEqual(home["shots"], 4)
        self.assertEqual(home["shots_display"], "S 4")
        self.assertEqual(home["saves_display"], "SV 2")
        self.assertEqual(home["corners_display"], "COR 3")
        self.assertEqual(home["fouls_display"], "F 1")

    def test_cards_blank_at_zero(self) -> None:
        state = default_state()
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["soccer"]["home"]["cards"]["display"], "")
        self.assertEqual(view["soccer"]["home"]["cards"]["yellow_display"], "")
        self.assertEqual(view["soccer"]["home"]["cards"]["rows"], [])

    def test_cards_are_counted_and_rowed_per_team(self) -> None:
        cards = (
            CardEvent(team="home", kind="yellow", player_number=10, period="1st", clock_display="32:14"),
            CardEvent(team="home", kind="yellow", player_number=11, period="1st", clock_display="20:00"),
            CardEvent(team="away", kind="red", player_number=5, period="2nd", clock_display="10:00"),
        )
        state = replace(default_state(), cards=cards)
        view = soccer_spectator_view_model(state)
        home_cards = view["soccer"]["home"]["cards"]
        self.assertEqual(home_cards["yellow"], 2)
        self.assertEqual(home_cards["red"], 0)
        self.assertEqual(home_cards["display"], "Y 2 · R 0")
        self.assertEqual(len(home_cards["rows"]), 2)
        away_cards = view["soccer"]["away"]["cards"]
        self.assertEqual(away_cards["red"], 1)
        self.assertEqual(len(away_cards["rows"]), 1)
        self.assertIn("#5", away_cards["rows"][0]["display"])

    def test_shootout_view_before_any_kick(self) -> None:
        state = replace(default_state(), period="SHOOTOUT", shootout_first_kicker="home")
        view = soccer_spectator_view_model(state, rules=default_soccer_rules())
        shootout = view["soccer"]["shootout"]
        self.assertTrue(shootout["active"])
        self.assertEqual(shootout["first_kicker"], "home")
        self.assertEqual(shootout["next_team"], "home")
        self.assertEqual(shootout["home_made"], 0)
        self.assertEqual(shootout["away_made"], 0)
        self.assertEqual(shootout["tally_display"], "0-0")

    def test_shootout_view_reflects_kicks(self) -> None:
        kicks = (
            ShootoutKick(team="home", round=1, kicker_number=7, made=True),
            ShootoutKick(team="away", round=1, kicker_number=9, made=False),
        )
        state = replace(
            default_state(), period="SHOOTOUT", shootout_first_kicker="home", shootout_kicks=kicks,
        )
        view = soccer_spectator_view_model(state, rules=default_soccer_rules())
        shootout = view["soccer"]["shootout"]
        self.assertEqual(shootout["home_made"], 1)
        self.assertEqual(shootout["away_made"], 0)
        self.assertEqual(shootout["tally_display"], "1-0")
        self.assertEqual(shootout["next_team"], "home")

    def test_shootout_inactive_outside_the_shootout_period(self) -> None:
        state = default_state()
        view = soccer_spectator_view_model(state)
        self.assertFalse(view["soccer"]["shootout"]["active"])
        self.assertIsNone(view["soccer"]["shootout"]["next_team"])

    def test_status_blank_when_nothing_is_raised(self) -> None:
        state = default_state()
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["status"]["display"], "")
        self.assertFalse(view["status"]["active"])

    def test_status_shows_the_raised_word(self) -> None:
        state = replace(default_state(), game_status="WEATHER")
        view = soccer_spectator_view_model(state)
        self.assertTrue(view["status"]["active"])
        self.assertEqual(view["status"]["label"], "WEATHER")

    def test_schema_version_and_revision_pass_through(self) -> None:
        state = replace(default_state(), revision=7)
        view = soccer_spectator_view_model(state)
        self.assertEqual(view["revision"], 7)
        self.assertEqual(view["schema_version"], state.schema_version)


if __name__ == "__main__":
    unittest.main()
