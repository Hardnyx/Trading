"""Synthetic familywise diagnostics cannot become market inferential approval."""
import copy
from itertools import product
from math import isclose
import unittest

from scripts.confirmatory_calibration_gate import (
    SCHEMA, EXPECTED_TESTS, exact_binomial_limits, read_scenarios, evaluate,
)


def diagnostic_fixtures(global_k=0, partial_k=0):
    full = {
        "schema": "confirmatory-joint-null-bootstrap-v1",
        "scope": "seven-correlated-synthetic-effects-under-complete-global-null",
        "simulation_seed": 20261109,
        "bootstrap_draws_per_replication": 10000,
        "nominal_holm_familywise_alpha": .05,
        "trading_outcomes_read": False,
        "real_market_effects_used": False,
        "formal_inference_enabled": False,
        "confirmatory_collection_open": False,
        "strong_fwer_control_not_established": True,
        "oracle_valid_for_real_market_effects": False,
        "oracle_uses_true_synthetic_parameters": True,
        "family_test_names": EXPECTED_TESTS,
        "rows": [],
    }
    partial = {
        "schema": "confirmatory-partial-null-holm-v1",
        "status": "synthetic-partial-null-stress-only",
        "simulation_seed": 20261110,
        "bootstrap_draws_per_replication": 10000,
        "nominal_familywise_alpha": .05,
        "true_null_indices": [0, 1, 2, 3],
        "shifted_false_null_indices": [4, 5, 6],
        "shifted_effect_unconditional_sd_assumed": .5,
        "real_market_outcomes_used": False,
        "registered_v2_modified": False,
        "confirmatory_inference_enabled": False,
        "strong_fwer_control_not_established": True,
        "oracle_not_applicable_to_unknown_market_dgp": True,
        "oracle_uses_known_synthetic_phi": True,
        "hypotheses": EXPECTED_TESTS,
        "rows": [],
    }
    for n, phi, rho, block in product((96, 192), (0., .6), (0., .75), (12, 24)):
        full["rows"].append({
            "months": n, "monthly_ar1_phi_assumed": phi,
            "cross_test_rho_assumed": rho, "block_months": block,
            "null_repetitions": 256, "familywise_any_rejections": global_k,
            "oracle_any_rejections": 0,
            "bootstrap_only_rejections": global_k,
            "oracle_only_rejections": 0,
        })
    for n, rho, block in product((96, 192), (0., .75), (12, 24)):
        partial["rows"].append({
            "months": n, "monthly_ar1_phi_assumed": .6,
            "cross_test_rho_assumed": rho, "block_months": block,
            "repetitions": 128,
            "false_family_rejections": partial_k,
            "oracle_false_family_rejections": 0,
            "false_family_bootstrap_only": partial_k,
            "false_family_oracle_only": 0,
            "any_shifted_rejections": 64,
        })
    return full, partial


class CalibrationGateTests(unittest.TestCase):
    def test_extreme_exact_binomial_limits(self):
        q = .05 / 48
        low, high = exact_binomial_limits(0, 128, q)
        self.assertEqual(low, 0.)
        self.assertTrue(isclose(high, 1-q**(1/128), rel_tol=1e-12))
        self.assertGreater(high, .05)
        low, high = exact_binomial_limits(128, 128, q)
        self.assertEqual(high, 1.)
        self.assertTrue(isclose(low, q**(1/128), rel_tol=1e-12))
        with self.assertRaises(ValueError):
            exact_binomial_limits(True, 128, q)
        with self.assertRaises(ValueError):
            exact_binomial_limits(129, 128, q)
        with self.assertRaises(ValueError):
            exact_binomial_limits(5, 128, .5)

    def test_zero_rejections_cannot_certify_the_fixed_128_rep_grid(self):
        report = evaluate(*diagnostic_fixtures())
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(len(report["rows"]), 24)
        self.assertEqual(report["synthetic_calibration_result"], "inconclusive")
        self.assertFalse(report["synthetic_grid_upper_bounds_all_below_nominal"])
        self.assertEqual(report["bootstrap_scenarios_with_simultaneous_lower_bound_above_nominal"], 0)
        self.assertFalse(report["real_market_calibration_certified"])
        self.assertFalse(report["candidate_method_selection_permitted"])
        self.assertFalse(report["formal_inference_enabled"])

    def test_detects_excess_without_promoting_favorable_scenarios(self):
        report = evaluate(*diagnostic_fixtures(global_k=77, partial_k=25))
        self.assertEqual(report["synthetic_calibration_result"],
                         "excess-rejection-detected")
        self.assertEqual(report["bootstrap_scenarios_with_simultaneous_lower_bound_above_nominal"], 24)
        for row in report["rows"]:
            self.assertGreater(row["bootstrap_simultaneous_exact95"][0], .05)
        self.assertFalse(report["real_market_calibration_certified"])

    def test_rejects_incomplete_modified_or_duplicate_grids(self):
        for variant in ("drop", "duplicate", "future", "counts", "flags", "pair", "oracle"):
            global_report, partial_report = diagnostic_fixtures(global_k=10,
                                                                partial_k=10)
            if variant == "drop":
                global_report["rows"].pop()
            elif variant == "duplicate":
                global_report["rows"][1] = copy.deepcopy(global_report["rows"][0])
            elif variant == "future":
                partial_report["simulation_seed"] = 99
            elif variant == "counts":
                partial_report["rows"][0]["repetitions"] = 96
            elif variant == "flags":
                global_report["formal_inference_enabled"] = True
            elif variant == "pair":
                global_report["rows"][0]["bootstrap_only_rejections"] = 9
            elif variant == "oracle":
                partial_report["rows"][0]["oracle_false_family_rejections"] = 4
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                evaluate(global_report, partial_report)

    def test_scenarios_and_shared_oracle_counts_are_constrained(self):
        global_report, partial_report = diagnostic_fixtures()
        self.assertEqual(len(read_scenarios(global_report, "global")), 16)
        self.assertEqual(len(read_scenarios(partial_report, "partial")), 8)
        global_report["rows"][1]["oracle_any_rejections"] = 1
        global_report["rows"][1]["oracle_only_rejections"] = 1
        with self.assertRaisesRegex(ValueError, "Oracle counts disagree"):
            read_scenarios(global_report, "global")


if __name__ == "__main__":
    unittest.main()
