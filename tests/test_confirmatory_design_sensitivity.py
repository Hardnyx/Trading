"""Exact combinatorial checks for prospective sample sensitivity (no outcomes)."""
import copy
import unittest

from scripts.confirmatory_design_sensitivity import (
    analyze, minimum_positive_blocks, upper_binomial_tail,
)


def contract():
    return {"schema": "full-engine-prospective-registration-v2",
            "primary_tests": [{"id": str(i)} for i in range(7)],
            "multiplicity": {"method": "Holm step-down", "alpha": 0.05},
            "bootstrap": {"block_lengths_months": [12, 24]},
            "sampling": {"minimum_mature_eligible_months": 96}}


class DesignSensitivityTests(unittest.TestCase):
    def test_exact_sign_resolution_distinct_from_bootstrap(self):
        result = analyze(contract())
        blocks = {(r["mature_months"], r["block_months"]): r for r in result["rows"]}
        self.assertEqual(blocks[96, 24]["nonoverlapping_blocks"], 4)
        self.assertEqual(blocks[96, 24]["exact_sign_min_one_sided_p"], 1 / 16)
        self.assertFalse(blocks[96, 24]["sign_test_can_cross_first_holm_step"])
        self.assertEqual(blocks[192, 24]["sign_test_min_positive_blocks"], 8)
        self.assertAlmostEqual(blocks[192, 24]["illustrative_sign_power_at_p80"], .8**8, places=6)
        self.assertAlmostEqual(blocks[96, 24]["optimistic_normal_mde_block_sd"], 1.646, places=3)
        self.assertTrue(result["not_the_registered_bootstrap"])
        self.assertFalse(result["formal_inference_performed"])

    def test_exact_tails_and_first_holm_resolution(self):
        alpha = .05 / 7
        self.assertEqual(upper_binomial_tail(4, 4, .5), .0625)
        self.assertEqual(upper_binomial_tail(8, 8, .5), 1 / 256)
        self.assertIsNone(minimum_positive_blocks(7, alpha))
        self.assertEqual(minimum_positive_blocks(8, alpha), 8)
        self.assertEqual(minimum_positive_blocks(16, alpha), 14)

    def test_contract_weakening_rejected(self):
        for key, value in (("primary_tests", [{"id":"one"}]),
                           ("bootstrap", {"block_lengths_months": [12]}),
                           ("sampling", {"minimum_mature_eligible_months": 48}),
                           ("multiplicity", {"method":"Holm step-down","alpha": 0.10})):
            altered = copy.deepcopy(contract())
            altered[key] = value
            with self.assertRaises(ValueError):
                analyze(altered)

    def test_invalid_scenarios_rejected(self):
        with self.assertRaises(ValueError):
            analyze(contract(), origins=(0,))
        with self.assertRaises(ValueError):
            upper_binomial_tail(2, 3, 1.1)


if __name__ == "__main__":
    unittest.main()
