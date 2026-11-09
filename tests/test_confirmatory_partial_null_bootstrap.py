"""Holm partial-null diagnostics use only known synthetic effect series."""
import json
from pathlib import Path
import random

import numpy as np
import unittest

from scripts.confirmatory_familywise_bootstrap import (
    joint_bootstrap_pvalues, joint_null_series, verify_protocol,
)
from scripts.confirmatory_partial_null_bootstrap import (
    SCHEMA, holm_rejections, joint_bootstrap_holm_rejections, simulate,
)

ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT/"docs/protocolo-confirmacion-integral-v2.json")
                      .read_text(encoding="utf-8"))


class PartialNullBootstrapTests(unittest.TestCase):
    def test_holm_checks_each_ordered_threshold(self):
        self.assertEqual(holm_rejections([1.]*7), frozenset())
        self.assertEqual(holm_rejections([0.001, .007, .009, 1, 1, 1, 1]),
                         frozenset((0, 1, 2)))
        self.assertEqual(holm_rejections([.006, .008, .010, .012, .015, .024, .06]),
                         frozenset(range(6)))
        self.assertEqual(holm_rejections([0., 0., 1., 1., 1., 1., 1.]),
                         frozenset((0, 1)))
        for bad in ([0.]*6, [float("nan")]*7, [-.01]*7, [1.01]*7):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                holm_rejections(bad)

    def test_vectorized_decision_matches_full_shared_bootstrap(self):
        for n in (96, 192):
            for rho in (0., .75):
                for block in (12, 24):
                    columns = joint_null_series(random.Random(42), n, .6, rho)
                    for idx in (4, 5, 6):
                        columns[idx] = [v+.5 for v in columns[idx]]
                    pvalues = joint_bootstrap_pvalues(
                        columns, block, 1500, random.Random(321))
                    rng = random.Random(321)
                    indices = np.array([
                        [rng.randrange(n) for _ in range(n//block)]
                        for _ in range(1500)], dtype=np.int32)
                    actual = joint_bootstrap_holm_rejections(
                        columns, block, indices)
                    self.assertEqual(actual, holm_rejections(pvalues),
                                     msg=(n, rho, block))

    def test_forced_nonrejections_and_valid_rejections(self):
        negatives = [[-1.]*96 for _ in range(7)]
        self.assertEqual(joint_bootstrap_holm_rejections(
            negatives, 24, np.zeros((16, 4), dtype=np.int32)), frozenset())
        columns = [[0.]*96 for _ in range(4)]+[[1.]*96 for _ in range(3)]
        self.assertEqual(joint_bootstrap_holm_rejections(
            columns, 24, np.zeros((10000, 4), dtype=np.int32)),
            frozenset((4, 5, 6)))
        with self.assertRaises(ValueError):
            joint_bootstrap_holm_rejections(
                columns, 24, np.zeros((0, 4), dtype=np.int32))
        with self.assertRaises(ValueError):
            joint_bootstrap_holm_rejections(
                columns, 24, np.full((10, 4), -1, dtype=np.int32))
        with self.assertRaises(ValueError):
            joint_bootstrap_holm_rejections(
                columns, 24, np.full((10, 4), 96, dtype=np.int32))
        with self.assertRaises(ValueError):
            joint_bootstrap_holm_rejections(
                columns[:-1]+[[0.]*95], 24,
                np.zeros((100, 4), dtype=np.int32))

    def test_protocol_flags_reproducibility_and_paired_invariant(self):
        self.assertEqual(verify_protocol(protocol()), (7, .05, 10000, (12, 24)))
        one = simulate(protocol(), repetitions=2, months=(96,), rhos=(0.,))
        self.assertEqual(one, simulate(protocol(), repetitions=2,
                                       months=(96,), rhos=(0.,)))
        self.assertEqual(one["schema"], SCHEMA)
        self.assertEqual(len(one["rows"]), 2)
        self.assertFalse(one["real_market_outcomes_used"])
        self.assertFalse(one["confirmatory_inference_enabled"])
        self.assertTrue(one["strong_fwer_control_not_established"])
        self.assertEqual(one["true_null_indices"], [0, 1, 2, 3])
        self.assertEqual(one["shifted_false_null_indices"], [4, 5, 6])
        for row in one["rows"]:
            self.assertEqual(
                row["false_family_rejections"] -
                row["oracle_false_family_rejections"],
                row["false_family_bootstrap_only"] -
                row["false_family_oracle_only"])
            self.assertLessEqual(row["any_shifted_rejections"], 2)

    def test_invalid_design_rejected(self):
        with self.assertRaises(ValueError):
            simulate(protocol(), repetitions=0)
        with self.assertRaises(ValueError):
            simulate(protocol(), months=(95,), repetitions=1)
        with self.assertRaises(ValueError):
            simulate(protocol(), rhos=(1.,), repetitions=1)


if __name__ == "__main__":
    unittest.main()
