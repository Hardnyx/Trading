"""Joint bootstrap Holm checks based exclusively on synthetic effects."""
import copy
import json
from pathlib import Path
import random
import unittest

from scripts.confirmatory_familywise_bootstrap import (
    SCHEMA, stable_seed, joint_null_series, holm_any_reject,
    joint_bootstrap_pvalues, joint_first_holm_reject, verify_protocol,
    simulate, wilson,
)

ROOT = Path(__file__).resolve().parents[1]


def registry():
    return json.loads((ROOT/"docs/protocolo-confirmacion-integral-v2.json")
                      .read_text(encoding="utf-8"))


class JointHolmBootstrapTests(unittest.TestCase):
    def test_contract_is_frozen_and_inactive(self):
        protocol = registry()
        self.assertEqual(verify_protocol(protocol), (7, .05, 10000, (12, 24)))
        for group, key, bad in [
            ("activation", "formal_inference_enabled", True),
            ("bootstrap", "draws", 100),
            ("sampling", "minimum_mature_eligible_months", 48),
            ("multiplicity", "alpha", .1),
        ]:
            modified = copy.deepcopy(protocol)
            modified[group][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_protocol(modified)

    def test_correlated_synthetic_series_reproducible(self):
        a = joint_null_series(random.Random(3), 96, .6, .75)
        self.assertEqual(a, joint_null_series(random.Random(3), 96, .6, .75))
        self.assertEqual(len(a), 7)
        self.assertTrue(all(len(column) == 96 for column in a))
        self.assertNotEqual(a, joint_null_series(random.Random(3), 96, .6, 0))

    def test_optimized_rejection_matches_full_joint_pvalues(self):
        for phi in (0., .6):
            for rho in (0., .75):
                for block in (12, 24):
                    columns = joint_null_series(
                        random.Random(42), 96, phi, rho)
                    draws = 1600
                    p = joint_bootstrap_pvalues(
                        columns, block, draws, random.Random(100))
                    actual = joint_first_holm_reject(
                        columns, block, draws, random.Random(100))
                    self.assertEqual(actual, holm_any_reject(p),
                                     msg=(phi, rho, block))

    def test_joint_positive_and_nonpositive_cases(self):
        self.assertTrue(joint_first_holm_reject(
            [[1.]*96 for _ in range(7)], 24, 10000, random.Random(4)))
        self.assertFalse(joint_first_holm_reject(
            [[-1.]*96 for _ in range(7)], 24, 10000, random.Random(4)))
        self.assertFalse(joint_first_holm_reject(
            [[0.]*96 for _ in range(7)], 24, 10000, random.Random(4)))
        with self.assertRaisesRegex(ValueError, "aligned eligible months"):
            joint_first_holm_reject(
                [[1.]*96 for _ in range(6)] + [[1.]*95],
                24, 10000, random.Random(4))

    def test_scenario_seeds_do_not_depend_on_iteration_order(self):
        self.assertEqual(
            stable_seed(20261109, 96, .6, .75, "bootstrap", 24),
            stable_seed(20261109, 96, .6, .75, "bootstrap", 24))
        self.assertNotEqual(
            stable_seed(20261109, 96, .6, .75, "bootstrap", 24),
            stable_seed(20261109, 96, .6, .75, "bootstrap", 12))

    def test_joint_global_null_diagnostic_is_not_predictive_validation(self):
        p = registry()
        first = simulate(p, repetitions=3, months=(96,),
                         phis=(.6,), rhos=(0.,))
        second = simulate(p, repetitions=3, months=(96,),
                          phis=(.6,), rhos=(0.,))
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], SCHEMA)
        self.assertEqual(len(first["rows"]), 2)
        self.assertFalse(first["formal_inference_enabled"])
        self.assertTrue(first["strong_fwer_control_not_established"])
        self.assertTrue(all(row["null_repetitions"] == 3
                            for row in first["rows"]))
        self.assertEqual(wilson(0, 100)[0], 0.0)
        self.assertEqual(wilson(100, 100)[1], 1.0)

    def test_invalid_synthetic_grid_rejected(self):
        with self.assertRaises(ValueError):
            simulate(registry(), months=(95,), repetitions=1)
        with self.assertRaises(ValueError):
            simulate(registry(), rhos=(1.,), repetitions=1)


if __name__ == "__main__":
    unittest.main()
