"""Consistency checks for the frozen feasibility and first-cut inventories."""
import json
from pathlib import Path
from statistics import NormalDist
import unittest

from scripts.historical_replay_plan import DEPENDENCIES

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class StudyDesignAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = load("docs/protocolo-replay-integral-v1.json")
        cls.feasibility = load("data/historical/study-feasibility-v1/report.json")
        cls.first_cut = load("data/historical/full-engine-input-audit-v1/manifest.json")

    def test_statistical_minimum_matches_frozen_protocol(self):
        p, a = self.protocol, self.feasibility
        self.assertEqual(a["study"]["scheduled_origins"], len(p["expected_cuts"]))
        self.assertEqual(a["study"]["first_origin"], p["expected_cuts"][0])
        self.assertEqual(a["study"]["last_origin"], p["expected_cuts"][-1])
        self.assertFalse(a["study"]["independent_holdout_registered"])
        tests = sum(len(row["horizons_sessions"]) for row in p["primary_tests"])
        self.assertEqual(tests, a["primary_inference"]["family_tests"])
        lengths = p["uncertainty"]["block_lengths_months"]
        self.assertEqual(a["primary_inference"]["minimum_origins_for_largest_block"], 4 * max(lengths))
        counts = {str(b): len(p["expected_cuts"]) // b for b in lengths}
        self.assertEqual(a["primary_inference"]["blocks_with_current_calendar"], counts)
        self.assertFalse(a["primary_inference"]["meets_full_length_block_minimum"])
        self.assertEqual(a["decision"], "NO_CONFIRMATORY_TEST_WITH_PRESENT_DATA")

    def test_optimistic_sensitivity_is_labelled_and_reproducible(self):
        f = self.feasibility["optimistic_sensitivity"]
        self.assertTrue(f["not_empirical_power"])
        alpha = self.protocol["multiple_testing"]["familywise_alpha"]
        family = self.feasibility["primary_inference"]["family_tests"]
        numerator = NormalDist().inv_cdf(1 - alpha / family) + NormalDist().inv_cdf(0.8)
        for origins, by_block in f["minimum_detectable_effect_in_block_sd"].items():
            for length, value in by_block.items():
                expected = numerator / ((int(origins) // int(length)) ** 0.5)
                self.assertAlmostEqual(value, expected, places=3)

    def test_first_cut_has_documented_gaps_not_false_readiness(self):
        first, a = self.first_cut, self.feasibility
        self.assertEqual(first["candidate_cut"], a["study"]["first_diagnostic_cut"])
        self.assertIn(first["candidate_cut"], self.protocol["expected_cuts"])
        self.assertTrue(first["candidate_selection"]["retrospective_only"])
        self.assertFalse(first["eligible_full_engine"])
        self.assertEqual(first["status"], "blocked")
        components = first["components"]
        self.assertEqual(len(components), len(DEPENDENCIES))
        self.assertEqual({item["component"] for item in components}, set(DEPENDENCIES))
        for item in components:
            self.assertEqual(item["dependencies"], list(DEPENDENCIES[item["component"]]))
            self.assertIn(item["status"], ("blocked", "verified-source"))
            self.assertEqual(bool(item["blockers"]), item["status"] == "blocked")
            self.assertTrue(item["evidence"])
            self.assertTrue(item["recovery_owner_role"])
            self.assertFalse(item["named_owner_assigned"])
        self.assertEqual(first["input_audit"]["components_verified_source"], 2)
        self.assertEqual(first["input_audit"]["components_blocked"], 12)

    def test_observations_are_not_reclassified_as_certifications(self):
        a = self.feasibility
        self.assertEqual(a["study"]["full_engine_eligible_origins"], 0)
        self.assertEqual(a["study"]["full_engine_executed_origins"], 0)
        self.assertFalse(a["source_inventory"]["continuous_price_identity_verified"])
        self.assertFalse(a["source_inventory"]["execution_cashflows_verified"])
        self.assertFalse(self.first_cut["candidate_selection"]["does_not_certify_eligibility"] is False)


if __name__ == "__main__":
    unittest.main()
