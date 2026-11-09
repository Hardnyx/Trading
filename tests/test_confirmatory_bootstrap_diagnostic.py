"""Synthetic bootstrap diagnostics cannot use results or promote v2 inference."""
import copy
import random
import unittest

from scripts.confirmatory_bootstrap_diagnostic import (
    SCHEMA, ar1_series, first_step_reject, protocol_parameters, simulate,
    wilson_interval,
)


def registry():
    return {
        "schema": "full-engine-prospective-registration-v2",
        "status": "registered-methodology-inactive-confirmatory-inference",
        "activation": {
            "formal_inference_enabled": False,
            "confirmatory_collection_open": False,
        },
        "primary_tests": [{"id": f"test-{k}"} for k in range(7)],
        "multiplicity": {
            "method": "Holm step-down", "alpha": .05,
            "direction": "one-sided positive advantage",
        },
        "bootstrap": {
            "block_lengths_months": [12, 24], "draws": 10000,
            "seed": 20261030, "minimum_complete_blocks": 4,
        },
        "sampling": {"minimum_mature_eligible_months": 96},
    }


class BootstrapDiagnosticTests(unittest.TestCase):
    def test_registered_threshold_and_sample_minimum_are_not_relaxed(self):
        alpha, draws, blocks = protocol_parameters(registry())
        self.assertAlmostEqual(alpha, .05/7)
        self.assertEqual(draws, 10000)
        self.assertEqual(blocks, (12, 24))
        for section, key, bad in [
            ("bootstrap", "draws", 300),
            ("bootstrap", "block_lengths_months", [4, 12]),
            ("sampling", "minimum_mature_eligible_months", 48),
            ("multiplicity", "alpha", .1),
            ("activation", "formal_inference_enabled", True),
        ]:
            altered = copy.deepcopy(registry())
            altered[section][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                protocol_parameters(altered)

    def test_synthetic_ar1_repeatable_and_stationary_scale_is_documented(self):
        one = ar1_series(random.Random(42), 192, .6)
        two = ar1_series(random.Random(42), 192, .6)
        self.assertEqual(one, two)
        self.assertNotEqual(one, ar1_series(random.Random(42), 192, 0))

    def test_bootstrap_uses_one_sided_positive_advantage(self):
        alpha = .05/7
        self.assertFalse(first_step_reject([0.]*96, 24, alpha, 200,
                                           random.Random(1)))
        self.assertFalse(first_step_reject([-1.]*96, 24, alpha, 200,
                                           random.Random(1)))
        self.assertTrue(first_step_reject([1.]*96, 24, alpha, 10000,
                                          random.Random(1)))
        with self.assertRaisesRegex(ValueError, "monthly bootstrap"):
            first_step_reject([1.]*97, 24, alpha, 10000, random.Random(1))

    def test_early_cutoff_matches_full_exceedance_count(self):
        # With centered identical positive values, all bootstrap null means
        # are zero; changing draw count cannot manufacture a positive tail.
        for draws in (1000, 10000):
            self.assertTrue(first_step_reject([2.]*96, 12, .05/7,
                                               draws, random.Random(123)))
        self.assertFalse(first_step_reject([1., -1.]*48, 12, .05/7,
                                            10000, random.Random(123)))

    def test_only_synthetic_scenarios_are_reported(self):
        first = simulate(registry(), repetitions=6, seed=36)
        second = simulate(registry(), repetitions=6, seed=36)
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], SCHEMA)
        self.assertEqual(len(first["rows"]), 16)
        self.assertTrue(first["not_familywise_error_or_trading_power"])
        self.assertFalse(first["formal_inference_activated"])
        self.assertTrue(all(0 <= r["simulated_rejection_rate"] <= 1
                            for r in first["rows"]))
        self.assertEqual(wilson_interval(0, 100)[0], 0)
        self.assertEqual(wilson_interval(100, 100)[1], 1)

    def test_invalid_synthetic_grid_is_rejected(self):
        with self.assertRaises(ValueError):
            simulate(registry(), repetitions=0)
        with self.assertRaises(ValueError):
            simulate(registry(), repetitions=2, months=(95,))
        with self.assertRaises(ValueError):
            simulate(registry(), repetitions=2, phis=(1.0,))


if __name__ == "__main__":
    unittest.main()
