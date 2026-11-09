"""No unit conversion or price assumption can invent economic thresholds."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.confirmatory_economic_materiality import (
    SCHEMA, TEST_IDS, analyze, friction_sensitivity, frozen_inputs,
    materiality_rows,
)
from scripts.prospective_study_registry import read_contract


class MaterialityReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v2, cls.v1 = read_contract()

    def test_exact_family_units_and_maturity_horizons(self):
        rows = materiality_rows(self.v2, self.v1)
        self.assertEqual([r["hypothesis_id"] for r in rows], TEST_IDS)
        self.assertEqual([r["horizon_sessions"] for r in rows],
                         [21, 63, 252, 21, 63, 252, 21])
        self.assertEqual({r["measurement_unit"] for r in rows[:3]},
                         {"squared-arithmetic-total-return-difference"})
        self.assertEqual({r["measurement_unit"] for r in rows[3:6]},
                         {"Spearman-correlation-point-difference"})
        self.assertEqual(rows[6]["measurement_unit"],
                         "annualized-monthly-paired-log-return-difference")
        self.assertTrue(all(r["reference_frozen_v1"] and
                            r["effect_definition_frozen_v1"] for r in rows))
        self.assertFalse(any(r["eligible_for_formal_confirmation"] for r in rows))

    def test_null_materiality_and_confirmatory_status(self):
        report = analyze(self.v2, self.v1)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["economically_material_effects_justified"], 0)
        self.assertFalse(report["economically_material_effects_registered"])
        self.assertFalse(report["market_outcomes_read"])
        self.assertFalse(report["formal_inference_enabled"])
        self.assertFalse(report["independent_power_established"])
        self.assertTrue(all(r["minimum_economically_material_effect"] is None
                            and r["independent_evidence_sha256"] is None
                            and r["unit_consistent_power_calibration"] is None
                            for r in report["rows"]))

    def test_base_stress_budget_is_not_annualized_net_alpha(self):
        costs = friction_sensitivity(self.v1)
        self.assertEqual(costs["base_parameter_sum_bps_per_traded_notional"], 7)
        self.assertEqual(costs["triple_stress_parameter_sum_bps_per_traded_notional"], 21)
        self.assertEqual(costs["incremental_stress_bps_per_traded_notional"], 14)
        self.assertEqual([
            (row["base_parameter_budget_bps_of_nav"],
             row["incremental_stress_budget_bps_of_nav"])
            for row in costs["illustrative_examples"]],
            [(0, 0), (1.75, 3.5), (3.5, 7), (7, 14)])
        self.assertFalse(costs["execution_spread_convention_verified"])
        self.assertFalse(costs["realized_turnover_measured"])
        self.assertFalse(costs["annualized_log_alpha_threshold_derived"])

    def test_invalid_turnover_examples_rejected(self):
        for value in ((-1,), (1.1,), (float("nan"),),
                      (0, 0.0), ("1",), (True,), ()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                friction_sensitivity(self.v1, value)

    def test_mutations_of_frozen_inputs_fail_closed(self):
        for change in ("benchmark", "horizon", "cost", "stress", "activation",
                       "economic-effect", "holm", "return-definition"):
            v1, v2 = copy.deepcopy(self.v1), copy.deepcopy(self.v2)
            if change == "benchmark":
                v1["primary_tests"][0]["reference"] = "cash-only"
            elif change == "horizon":
                v2["primary_tests"][0]["horizon_sessions"] = 252
            elif change == "cost":
                v1["costs"]["base"]["spreadBps"] = 0
            elif change == "stress":
                v1["costs"]["stress"] = "no stress"
            elif change == "activation":
                v2["activation"]["formal_inference_enabled"] = True
            elif change == "economic-effect":
                v2["economic_effect_thresholds"]["return_mse"] = .1
            elif change == "holm":
                v2["multiplicity"]["alpha"] = .1
            elif change == "return-definition":
                v1["forecast_target"] = "log return"
            with self.subTest(change=change), self.assertRaises(ValueError):
                frozen_inputs(v2, v1)

    def test_cli_archives_only_pending_review(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"materiality.json"
            subprocess.run(
                [sys.executable,
                 str(root/"scripts/confirmatory_economic_materiality.py"),
                 "--verify", "--output", str(output)],
                cwd=root, check=True, capture_output=True, text=True)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["primary_hypotheses"], 7)
            self.assertFalse(report["economically_material_effects_registered"])


if __name__ == "__main__":
    unittest.main()
