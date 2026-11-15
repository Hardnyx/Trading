"""Registered 21-session family calibration: arithmetic, Holm and frozen summary."""
import json
import unittest
from pathlib import Path

import numpy as np

from scripts.confirmatory_family21_stress import DESIGN, FAMILY, holm, iid_pvalues, simulate

AUDIT = Path(__file__).resolve().parents[1] / "docs/auditorias/calibracion-familia-21-v1.json"


class Family21StressTests(unittest.TestCase):
    def test_holm_and_iid_pvalues(self):
        p = np.array([[0.01, 0.02, 0.04], [0.04, 0.5, 0.01]])
        self.assertTrue(np.array_equal(holm(p), [[True, True, True], [False, False, True]]))
        x = np.ones((1, FAMILY, 50)) + np.linspace(-1, 1, 50)
        self.assertTrue(np.all(iid_pvalues(x) < 1e-6))

    def test_registered_summary_is_frozen_and_smoke_runs(self):
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        self.assertFalse(design["post_hoc_changes_permitted"])
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertTrue(audit["design_budget_fully_executed"])
        kvb = audit["summary"]["B-kvb-full-bandwidth"]
        self.assertEqual(kvb["excess_scenarios"], 5)
        self.assertEqual(kvb["excess_by_phi"], {"0": 0, "0.3": 0, "0.6": 0, "0.85": 5})
        self.assertFalse(audit["formal_inference_enabled"])
        smoke = simulate(design, repetitions=4, draws=500)
        self.assertFalse(smoke["design_budget_fully_executed"])
        self.assertEqual(len(smoke["rows"]), 128)


if __name__ == "__main__":
    unittest.main()
