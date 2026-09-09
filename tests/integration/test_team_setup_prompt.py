"""The soft prompt that says the teams have not been chosen yet (spec 1.1/1.2).

Owner request 5, decision 1: after a New Game the Teams drawer opens by itself
and can be dismissed, but "teams not chosen" must be impossible to miss and the
kickoff confirmation must say it in words. Python owns both sentences -- the
operator page only copies them -- so they are pinned here rather than in the
page's JavaScript.

The wall never shows an instruction meant for the booth, so the spectator view
model deliberately has no ``setup`` block at all.
"""

from __future__ import annotations

from scoreboard.domain.state import DEFAULT_AWAY_NAME, DEFAULT_HOME_NAME
from scoreboard.host.bridge import DisplayLink, ScoreboardBridge

from tests.integration.support import TemporaryDataDirectoryTest

BOTH = "Choose the HOME and AWAY teams before kickoff."
HOME_ONLY = "Choose the HOME team before kickoff."
AWAY_ONLY = "Choose the AWAY team before kickoff."


class SetupPromptTestCase(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.bridge = ScoreboardBridge(
            self.service, self.store, display=DisplayLink()
        )

    def send(self, name, args=None):
        return self.bridge.command(name, args or {}, self.service.revision)

    def setup_block(self) -> dict:
        return self.bridge.get_snapshot()["setup"]


class SetupBlockTests(SetupPromptTestCase):
    """'The operator view says which side is still a placeholder.'"""

    def test_a_fresh_game_flags_both_sides(self) -> None:
        self.assertEqual(self.service.state.home_name, DEFAULT_HOME_NAME)
        self.assertEqual(self.service.state.away_name, DEFAULT_AWAY_NAME)

        setup = self.setup_block()

        self.assertTrue(setup["teams_pending"])
        self.assertTrue(setup["home_pending"])
        self.assertTrue(setup["away_pending"])
        self.assertEqual(setup["detail"], BOTH)

    def test_naming_the_home_team_leaves_only_the_away_side_flagged(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})

        setup = self.setup_block()

        self.assertTrue(setup["teams_pending"])
        self.assertFalse(setup["home_pending"])
        self.assertTrue(setup["away_pending"])
        self.assertEqual(setup["detail"], AWAY_ONLY)

    def test_naming_the_away_team_leaves_only_the_home_side_flagged(self) -> None:
        self.send("set_team_name", {"team": "away", "name": "Eagles"})

        setup = self.setup_block()

        self.assertTrue(setup["home_pending"])
        self.assertFalse(setup["away_pending"])
        self.assertEqual(setup["detail"], HOME_ONLY)

    def test_naming_both_teams_clears_the_prompt(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})
        self.send("set_team_name", {"team": "away", "name": "Eagles"})

        setup = self.setup_block()

        self.assertFalse(setup["teams_pending"])
        self.assertFalse(setup["home_pending"])
        self.assertFalse(setup["away_pending"])
        self.assertEqual(setup["detail"], "")

    def test_after_kickoff_nothing_is_pending_even_with_default_names(self) -> None:
        """A team really called HOME stops being nagged once the game is live."""

        self.send("quarter_forward", {"confirmed": True})
        self.assertEqual(self.service.state.lifecycle, "IN_PROGRESS")

        setup = self.setup_block()

        self.assertFalse(setup["teams_pending"])
        self.assertFalse(setup["home_pending"])
        self.assertFalse(setup["away_pending"])
        self.assertEqual(setup["detail"], "")

    def test_a_new_game_brings_the_prompt_back(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})
        self.send("set_team_name", {"team": "away", "name": "Eagles"})
        self.assertFalse(self.setup_block()["teams_pending"])

        self.send("new_game", {"confirmed": True})

        setup = self.setup_block()
        self.assertTrue(setup["teams_pending"])
        self.assertEqual(setup["detail"], BOTH)

    def test_the_wall_never_receives_the_operator_prompt(self) -> None:
        self.assertNotIn("setup", self.bridge.spectator_snapshot())


class KickoffConfirmationTests(SetupPromptTestCase):
    """'The confirmation that starts the game names the unchosen teams.'"""

    def confirmation(self) -> dict:
        result = self.send("quarter_forward")
        self.assertFalse(result["accepted"])
        self.assertTrue(result["confirmation_required"])
        return result["confirmation"]

    def test_leaving_pre_with_both_names_default_says_so_first(self) -> None:
        confirmation = self.confirmation()

        self.assertTrue(confirmation["detail"].startswith(BOTH))
        self.assertIn("Change quarter from PRE to 1st.", confirmation["detail"])
        # Only the detail gains the sentence; the other two are unchanged. A
        # fresh game still has kickoff time on the clock, so this is the
        # discard-the-countdown wording rather than the plain one.
        self.assertEqual(
            confirmation["accept_label"],
            "Start 1st quarter — discard remaining pregame time",
        )
        self.assertEqual(confirmation["title"], "Discard remaining pregame time?")

    def test_one_named_team_still_names_the_other(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})

        self.assertTrue(self.confirmation()["detail"].startswith(AWAY_ONLY))

    def test_with_both_teams_chosen_the_wording_is_unchanged(self) -> None:
        self.send("set_team_name", {"team": "home", "name": "Tigers"})
        self.send("set_team_name", {"team": "away", "name": "Eagles"})

        detail = self.confirmation()["detail"]

        self.assertTrue(detail.startswith("Change quarter from PRE to 1st."))
        self.assertNotIn("before kickoff", detail)

    def test_the_plain_kickoff_wording_carries_the_sentence_too(self) -> None:
        """Both PRE->live branches are prefixed, not only the discard one.

        With the kickoff countdown already run down there is nothing to
        discard, so ``_quarter_confirmation`` takes its other return.
        """

        self.send("game_clock_correct", {"seconds": 0})
        confirmation = self.confirmation()

        self.assertTrue(confirmation["detail"].startswith(BOTH))
        self.assertEqual(confirmation["title"], "Confirm quarter change")
        self.assertEqual(confirmation["accept_label"], "Change to 1st")

    def test_a_quarter_change_that_is_not_kickoff_is_never_prefixed(self) -> None:
        self.send("quarter_forward", {"confirmed": True})

        detail = self.send("quarter_forward")["confirmation"]["detail"]

        self.assertTrue(detail.startswith("Change quarter from 1st to 2nd."))
        self.assertNotIn("before kickoff", detail)

    def test_confirming_the_kickoff_still_changes_the_quarter(self) -> None:
        """The prompt is words only: it blocks nothing (decision 1, soft prompt)."""

        result = self.send("quarter_forward", {"confirmed": True})

        self.assertTrue(result["accepted"])
        self.assertEqual(self.service.state.quarter, "1st")
