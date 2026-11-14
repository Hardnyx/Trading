"""Adversarial tests for the precommitted synthetic fixed-b familywise audit."""
import copy
from math import isclose
import unittest

import numpy as np
from scipy.stats import norm

from scripts.confirmatory_fixed_b_stress import (
    ARMS, INTERVALS, REFERENCE_DRAWS, REFERENCE_SEED, SCHEMA, SEED,
    arm_b, arm_lags, bartlett_statistics, monte_carlo_pvalues, read_design,
    reference_distribution, reference_seed, simulate, validate_design,
)
from scripts.confirmatory_hac_stress import SEED as HAC_SEED, hac_one_sided_pvalues
from scripts.prospective_study_registry import read_contract


class FixedBStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = read_design()
        cls.protocol, _ = read_contract()

    def test_published_design_is_immutable_and_never_activates_inference(self):
        self.assertEqual([arm["id"] for arm in self.design["arms"]], list(ARMS))
        self.assertEqual(self.design["synthetic_data"]["independent_simulation_seed"], 20261114)
        self.assertNotEqual(SEED, HAC_SEED)
        self.assertNotEqual(SEED, REFERENCE_SEED)
        self.assertFalse(self.design["calibration_evaluation"]["candidate_approval_permitted"])
        for location, key, new in (
                ("reference_distribution", "draws_per_b", 1000),
                ("reference_distribution", "reference_seed", SEED),
                ("synthetic_data", "independent_simulation_seed", HAC_SEED),
                ("synthetic_data", "repetitions_per_scenario", 64),
                ("multiplicity", "alpha", .1),
                ("calibration_evaluation", "interval_count", 64),
                ("calibration_evaluation", "arm_or_bandwidth_selection_by_inspected_results_permitted", True),
                ("activation", "formal_inference_enabled", True)):
            with self.subTest(location=location, key=key):
                changed = copy.deepcopy(self.design)
                changed[location][key] = new
                with self.assertRaises(ValueError):
                    validate_design(changed)
        dropped = copy.deepcopy(self.design)
        dropped["arms"] = dropped["arms"][:1]
        with self.assertRaises(ValueError):
            validate_design(dropped)

    def test_fft_statistic_matches_scalar_bartlett_and_the_hac_study(self):
        x = np.array([0.1, 0.0, 1.2, 0.4, 0.8, 0.3, 1.1, 0.2, -0.1, 0.7, 0.6, 0.5, 0.9, -0.3])
        n = len(x)
        centered = x - x.mean()
        for lags in (0, 3, n - 1):
            lrv = centered.dot(centered)/n
            for k in range(1, lags + 1):
                lrv += 2*(1 - k/(lags + 1))*centered[k:].dot(centered[:-k])/n
            expected = x.mean()*np.sqrt(n/lrv)
            self.assertTrue(isclose(bartlett_statistics(x[None, :], lags)[0], expected, rel_tol=1e-10))
        # Lag 12 reproduces the failed HAC statistic exactly; only the tail differs.
        effects = np.random.Generator(np.random.PCG64(7)).standard_normal((4, 7, 96))
        p_hac, _ = hac_one_sided_pvalues(effects)
        self.assertTrue(np.allclose(norm.sf(bartlett_statistics(effects, 12)), p_hac, rtol=1e-10))
        self.assertTrue(np.all(np.isnan(bartlett_statistics(np.ones((2, 7, 96)), 12))))
        with self.assertRaises(ValueError):
            bartlett_statistics(np.ones((2, 7, 96)), 96)

    def test_monte_carlo_pvalues_are_valid_and_never_zero(self):
        ref = np.sort(np.array([-1.0, 0.0, 0.5, 1.0, 2.0]))
        p = monte_carlo_pvalues(np.array([3.0, 1.0, -5.0, np.nan]), ref)
        self.assertTrue(np.allclose(p, [1/6, 3/6, 6/6, 1.0]))

    def test_reference_is_seeded_per_b_and_heavier_than_gaussian_for_full_bandwidth(self):
        self.assertNotEqual(reference_seed("1"), reference_seed("0.125"))
        a = reference_distribution("1", 199, draws=4000, length=200)
        b = reference_distribution("1", 199, draws=4000, length=200)
        self.assertTrue(np.array_equal(a, b))
        # KVB's 95% one-sided critical value is far above the Gaussian 1.645.
        self.assertGreater(np.quantile(a, .95), 2.5)
        small = reference_distribution("0.125", 25, draws=4000, length=200)
        self.assertLess(np.quantile(small, .95), np.quantile(a, .95))

    def test_arm_bandwidths_follow_the_registration(self):
        self.assertEqual((arm_lags(ARMS[0], 96), arm_b(ARMS[0], 96)), (12, "0.125"))
        self.assertEqual((arm_lags(ARMS[0], 192), arm_b(ARMS[0], 192)), (12, "0.0625"))
        self.assertEqual((arm_lags(ARMS[1], 96), arm_b(ARMS[1], 96)), (95, "1"))
        self.assertEqual((arm_lags(ARMS[1], 192), arm_b(ARMS[1], 192)), (191, "1"))

    def test_small_smoke_cannot_claim_registered_evidence(self):
        output = simulate(self.design, self.protocol, repetitions=3, draws=500)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(len(output["rows"]), INTERVALS)
        self.assertFalse(output["design_budget_fully_executed"])
        self.assertEqual(set(output["arms"]), set(ARMS))
        self.assertFalse(output["candidate_approved_for_market_inference"])
        self.assertFalse(output["arm_or_bandwidth_selected_from_results"])
        self.assertFalse(output["formal_inference_enabled"])
        self.assertEqual(REFERENCE_DRAWS, 100000)
        self.assertTrue(all(row["false_family_rejections"] <= 3 for row in output["rows"]))


if __name__ == "__main__":
    unittest.main()
