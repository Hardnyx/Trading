"""Adversarial tests for a precommitted synthetic HAC familywise audit."""
import copy
from math import isclose
from pathlib import Path
import unittest

import numpy as np
from scipy.stats import norm

from scripts.confirmatory_hac_stress import (
    ALPHA, GRID_COUNT, INNOVATIONS, LAG, NULL_INDICES, PHIS, REPETITIONS,
    SCHEMA, SEED, TEST_IDS, hac_one_sided_pvalues, holm_masks,
    read_design, seed_for, simulate, synthetic_effects, validate_design,
)
from scripts.confirmatory_partial_null_bootstrap import holm_rejections
from scripts.prospective_study_registry import read_contract


class HacStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = read_design()
        cls.protocol, _ = read_contract()

    def test_published_design_is_immutable_and_not_a_v3_activation(self):
        self.assertEqual(self.design["synthetic_data"]["scenario_count"], 64)
        self.assertEqual(self.design["synthetic_data"]["repetitions_per_scenario"], 512)
        self.assertEqual(self.design["synthetic_data"]["independent_simulation_seed"],
                         20261112)
        self.assertFalse(self.design["activation"]["formal_inference_enabled"])
        self.assertFalse(self.design["calibration_evaluation"]["candidate_approval_permitted"])
        for location, key, new in (
                ("method", "lag_months", 24),
                ("method", "lag_tuning_permitted", True),
                ("synthetic_data", "independent_simulation_seed", 9),
                ("synthetic_data", "scenario_count", 16),
                ("multiplicity", "alpha", .1),
                ("calibration_evaluation", "candidate_approval_permitted", True),
                ("activation", "formal_inference_enabled", True)):
            with self.subTest(location=location,key=key):
                changed = copy.deepcopy(self.design)
                changed[location][key] = new
                with self.assertRaises(ValueError):
                    validate_design(changed)

    def test_lrv_matches_scalar_bartlett_autocovariances(self):
        x = np.array([0.1, 0.0, 1.2, 0.4, 0.8, 0.3, 1.1, 0.2,
                      -0.1, 0.7, 0.6, 0.5, 0.9, -0.3], dtype=float)
        z = np.tile(x, (1, 7, 1))
        p, bad = hac_one_sided_pvalues(z, lag=3)
        centered = x-x.mean()
        n = len(x)
        lrv = centered.dot(centered)/n
        for k in range(1, 4):
            gamma = centered[k:].dot(centered[:-k])/n
            lrv += 2*(1-k/4)*gamma
        expected = norm.sf(x.mean()*np.sqrt(n/lrv))
        self.assertEqual(bad, 0)
        self.assertTrue(all(isclose(v, expected, rel_tol=1e-12)
                            for v in p[0]))
        const, invalid = hac_one_sided_pvalues(np.ones((2,7,96)))
        self.assertEqual(invalid, 14)
        self.assertTrue(np.array_equal(const, np.ones((2,7))))
        with self.assertRaises(ValueError):
            hac_one_sided_pvalues(np.ones((2,6,96)))

    def test_vectorized_holm_equals_existing_full_step_down(self):
        samples = np.array([
            [.001,.002,.01,.02,.03,.04,.05],
            [.009,.009,.009,.009,.009,.009,.009],
            [1.,1.,1.,1.,1.,1.,1.],
            [.002,.007,.012,.018,.025,.04,.05],
            [.05,.04,.03,.02,.01,.001,.003],
        ])
        actual = holm_masks(samples)
        for row in range(samples.shape[0]):
            reference = holm_rejections(samples[row].tolist(), ALPHA)
            self.assertEqual(set(np.flatnonzero(actual[row])), set(reference))
        with self.assertRaises(ValueError):
            holm_masks(np.array([[0.01]*6]))

    def test_ar1_marginals_and_shifted_indices(self):
        for distribution in INNOVATIONS:
            a = synthetic_effects(
                np.random.Generator(np.random.PCG64(44)), 96, .6, .75,
                distribution, "partial", repetitions=12)
            b = synthetic_effects(
                np.random.Generator(np.random.PCG64(44)), 96, .6, .75,
                distribution, "global", repetitions=12)
            self.assertEqual(a.shape, (12,7,96))
            self.assertTrue(np.allclose(a[:, :4, :], b[:, :4, :]))
            self.assertTrue(np.allclose(a[:, 4:, :]-b[:, 4:, :], .5))
            self.assertTrue(np.isfinite(a).all())

    def test_independent_seed_is_stable_and_separated(self):
        self.assertEqual(seed_for(96,.6,.75,"gaussian","global"),
                         seed_for(96,.6,.75,"gaussian","global"))
        self.assertNotEqual(seed_for(96,.6,.75,"gaussian","global"),
                            seed_for(96,.6,.75,"gaussian","partial"))
        self.assertNotEqual(seed_for(96,.6,.75,"gaussian","global"),
                            seed_for(192,.6,.75,"gaussian","global"))
        self.assertEqual(SEED, 20261112)
        self.assertEqual(len(TEST_IDS), 7)
        self.assertEqual(GRID_COUNT, 64)
        self.assertEqual(LAG, 12)

    def test_small_repetition_smoke_cannot_claim_registered_evidence(self):
        output = simulate(self.design, self.protocol, repetitions=3)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertEqual(output["synthetic_scenario_count"], 64)
        self.assertFalse(output["design_repetition_count_fully_executed"])
        self.assertFalse(output["candidate_approved_for_market_inference"])
        self.assertFalse(output["market_outcomes_read"])
        self.assertFalse(output["formal_inference_enabled"])
        self.assertTrue(all(row["independent_repetitions"] == 3
                            and row["false_family_rejections"] <= 3
                            for row in output["rows"]))


if __name__ == "__main__":
    unittest.main()
