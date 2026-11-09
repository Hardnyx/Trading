"""Prospective calendar feasibility is a lower bound, not an OOS result."""
import copy
import unittest

from scripts.confirmatory_calendar_floor import (
    SCHEMA, earliest_eligible_months, evaluate, format_month, parse_month,
)
from scripts.prospective_study_registry import read_contract


class ProspectiveCalendarFloorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol, _ = read_contract()

    def test_frozen_monthly_count_and_last_origin(self):
        report = evaluate(self.protocol)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["first_possible_month"], "2026-11")
        self.assertEqual(report["earliest_month_of_96th_eligible_origin"],
                         "2034-10")
        self.assertEqual(len(report["idealized_months"]), 96)
        self.assertEqual(report["monthly_boundaries_after_first_before_last"], 95)
        self.assertEqual(report["idealized_months"][0], "2026-11")
        self.assertEqual(report["idealized_months"][-1], "2034-10")

    def test_no_fake_exchange_session_calendar_or_mature_outcome(self):
        report = evaluate(self.protocol)
        self.assertEqual(report["longest_registered_horizon_sessions"], 252)
        self.assertIsNone(report["calendar_date_of_final_252_session_outcome_estimated"])
        self.assertFalse(report["confirmation_can_finish_at_96th_origin"])
        self.assertFalse(report["full_horizon_maturity_at_96th_origin"])
        self.assertFalse(report["eligible_months_all_observed_or_verified"])
        self.assertFalse(report["formal_inference_enabled"])
        self.assertTrue(report["any_missing_eligible_month_or_cohort_restart_can_delay_lower_bound"])

    def test_month_calculation_crosses_leap_years_without_session_guesses(self):
        self.assertEqual(earliest_eligible_months("2026-11", 1), ["2026-11"])
        self.assertEqual(earliest_eligible_months("2026-11", 3),
                         ["2026-11", "2026-12", "2027-01"])
        self.assertEqual(format_month(parse_month("2026-11")+95), "2034-10")
        self.assertEqual(earliest_eligible_months("2026-11",96)[95], "2034-10")

    def test_mutations_in_sample_count_cohort_and_cut_rules_fail(self):
        changes = (
            ("sampling","minimum_mature_eligible_months",48),
            ("sampling","first_month","2022-10"),
            ("sampling","origin_frequency","daily"),
            ("sampling","cut_rule","last calendar day"),
            ("sampling","exclude_previously_examined",False),
            ("sampling","retain_absent_months",False),
            ("fixed_cohort","restart_incompatible_changes",False),
            ("activation","formal_inference_enabled",True),
        )
        for section, key, value in changes:
            test_protocol = copy.deepcopy(self.protocol)
            test_protocol[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                evaluate(test_protocol)

    def test_rejects_invalid_calendar_inputs(self):
        for first in ("2026-0", "2026-13", "26-11", "2026-00", None):
            with self.subTest(first=first), self.assertRaises(ValueError):
                parse_month(first)
        for count in (0,-1,1.5,False):
            with self.subTest(count=count), self.assertRaises(ValueError):
                earliest_eligible_months("2026-11",count)


if __name__ == "__main__":
    unittest.main()
