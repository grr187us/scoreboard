"""Unit tests for scoreboard.domain.soccer.rules.

Table-driven over spec section 3.2's period-decision-relevant combinations
(overtime_periods x shootout_enabled) and every mercy_applies choice, per the
task's ownership row.
"""

from __future__ import annotations

import unittest

from scoreboard.domain.soccer.rules import (
    SOCCER_RULE_FIELDS,
    RulesError,
    SoccerRules,
    default_soccer_rules,
)


class SoccerRulesDefaultsTests(unittest.TestCase):
    def test_shipped_defaults_match_spec_section_8(self) -> None:
        rules = default_soccer_rules()
        self.assertEqual(rules.half_seconds, 2400.0)
        self.assertEqual(rules.halftime_seconds, 600.0)
        self.assertEqual(rules.pregame_seconds, 1800.0)
        self.assertEqual(rules.overtime_periods, 2)
        self.assertEqual(rules.overtime_seconds, 600.0)
        self.assertFalse(rules.golden_goal)
        self.assertFalse(rules.shootout_enabled)
        self.assertEqual(rules.shootout_initial_kickers, 5)
        self.assertTrue(rules.shootout_credit_goal)
        self.assertEqual(rules.mercy_differential, 9)
        self.assertEqual(rules.mercy_applies, "halftime_and_second_half")
        self.assertTrue(rules.stop_clock_on_goal)
        self.assertEqual(rules.clock_direction, "down")
        self.assertEqual(rules.weather_seconds, 1800.0)

    def test_period_seconds(self) -> None:
        rules = default_soccer_rules()
        self.assertEqual(rules.period_seconds("PRE"), rules.pregame_seconds)
        self.assertEqual(rules.period_seconds("HALF"), rules.halftime_seconds)
        self.assertEqual(rules.period_seconds("1st"), rules.half_seconds)
        self.assertEqual(rules.period_seconds("2nd"), rules.half_seconds)
        self.assertEqual(rules.period_seconds("OT1"), rules.overtime_seconds)
        self.assertEqual(rules.period_seconds("OT2"), rules.overtime_seconds)
        self.assertIsNone(rules.period_seconds("SHOOTOUT"))
        self.assertIsNone(rules.period_seconds("FINAL"))

    def test_to_dict_and_from_payload_round_trip(self) -> None:
        rules = SoccerRules(half_seconds=2100.0, overtime_periods=1)
        payload = rules.to_dict()
        restored = SoccerRules.from_payload(payload)
        self.assertEqual(restored, rules)

    def test_from_payload_ignores_unknown_keys_and_keeps_missing_defaults(self) -> None:
        restored = SoccerRules.from_payload({"half_seconds": 2100.0, "bogus": 1})
        self.assertEqual(restored.half_seconds, 2100.0)
        self.assertEqual(restored.halftime_seconds, default_soccer_rules().halftime_seconds)

    def test_from_payload_rejects_non_mapping(self) -> None:
        with self.assertRaises(RulesError):
            SoccerRules.from_payload("not a mapping")

    def test_with_changes(self) -> None:
        rules = default_soccer_rules().with_changes(shootout_enabled=True)
        self.assertTrue(rules.shootout_enabled)


class SoccerRulesValidationTests(unittest.TestCase):
    def test_half_seconds_range(self) -> None:
        SoccerRules(half_seconds=5 * 60.0)
        SoccerRules(half_seconds=60 * 60.0)
        with self.assertRaises(RulesError):
            SoccerRules(half_seconds=4 * 60.0)
        with self.assertRaises(RulesError):
            SoccerRules(half_seconds=61 * 60.0)

    def test_overtime_periods_range(self) -> None:
        for value in (0, 1, 2):
            SoccerRules(overtime_periods=value)
        with self.assertRaises(RulesError):
            SoccerRules(overtime_periods=3)
        with self.assertRaises(RulesError):
            SoccerRules(overtime_periods=-1)

    def test_shootout_initial_kickers_range(self) -> None:
        SoccerRules(shootout_initial_kickers=1)
        SoccerRules(shootout_initial_kickers=11)
        with self.assertRaises(RulesError):
            SoccerRules(shootout_initial_kickers=0)
        with self.assertRaises(RulesError):
            SoccerRules(shootout_initial_kickers=12)

    def test_mercy_differential_range(self) -> None:
        SoccerRules(mercy_differential=0)
        SoccerRules(mercy_differential=20)
        with self.assertRaises(RulesError):
            SoccerRules(mercy_differential=21)
        with self.assertRaises(RulesError):
            SoccerRules(mercy_differential=-1)

    def test_mercy_applies_every_choice(self) -> None:
        for choice in ("halftime_and_second_half", "any_time", "off"):
            SoccerRules(mercy_applies=choice)
        with self.assertRaises(RulesError):
            SoccerRules(mercy_applies="sometimes")

    def test_clock_direction_choices(self) -> None:
        SoccerRules(clock_direction="down")
        SoccerRules(clock_direction="up")
        with self.assertRaises(RulesError):
            SoccerRules(clock_direction="sideways")

    def test_toggle_fields_reject_non_bool(self) -> None:
        with self.assertRaises(RulesError):
            SoccerRules(golden_goal="yes")  # type: ignore[arg-type]

    def test_weather_seconds_range(self) -> None:
        SoccerRules(weather_seconds=1.0)
        SoccerRules(weather_seconds=1800.0)
        with self.assertRaises(RulesError):
            SoccerRules(weather_seconds=1801.0)


class OvertimeShootoutCombinationTests(unittest.TestCase):
    """Table-driven: every overtime_periods x shootout_enabled combination is constructible
    and reports coherent period_seconds -- the period-decision prompt (soccer_service) filters
    what is *offered*, but every rules combination itself must remain valid."""

    def test_every_combination_is_valid_and_period_seconds_holds(self) -> None:
        for overtime_periods in (0, 1, 2):
            for shootout_enabled in (False, True):
                with self.subTest(overtime_periods=overtime_periods, shootout_enabled=shootout_enabled):
                    rules = SoccerRules(
                        overtime_periods=overtime_periods, shootout_enabled=shootout_enabled
                    )
                    self.assertEqual(rules.period_seconds("OT1"), rules.overtime_seconds)
                    self.assertEqual(rules.period_seconds("OT2"), rules.overtime_seconds)


class SoccerRuleFieldsTests(unittest.TestCase):
    def test_every_field_row_names_a_real_dataclass_field_except_the_note_row(self) -> None:
        known = {f.name for f in SoccerRules.__dataclass_fields__.values()}
        for name, _label, kind in SOCCER_RULE_FIELDS:
            if kind == "note":
                self.assertNotIn(name, known, "the note row must not shadow a real field")
                continue
            self.assertIn(name, known)

    def test_kinds_are_one_of_the_documented_set(self) -> None:
        for _name, _label, kind in SOCCER_RULE_FIELDS:
            self.assertIn(kind, {"clock", "count", "toggle", "choice", "note"})


if __name__ == "__main__":
    unittest.main()
