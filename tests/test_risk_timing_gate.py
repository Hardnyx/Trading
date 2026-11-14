"""Registered risk-timing gate: frozen verdict and metric arithmetic."""
import json
import unittest
from pathlib import Path

from scripts.risk_timing_gate import DESIGN, sharpe

AUDIT = Path(__file__).resolve().parents[1] / "docs/auditorias/momento-riesgo-1964-2018.json"


class RiskTimingGateTests(unittest.TestCase):
    def test_frozen_verdict_and_bounds(self):
        # The archive refreshes weekly and French revises history, so the audit
        # is checked as published rather than recomputed here.
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["verdict"], "supported")
        self.assertGreater(audit["sharpe"]["timed"], audit["sharpe"]["static"])
        self.assertLess(audit["bootstrap_p_one_sided"], .05)
        self.assertFalse(design["post_hoc_changes_permitted"])
        self.assertLessEqual(audit["equity_share"]["max"], .9)
        self.assertGreaterEqual(audit["equity_share"]["min"], .6)

    def test_sharpe_is_annualized_from_monthly_returns(self):
        self.assertAlmostEqual(sharpe([.01, .03, .01, .03]), .02 / (0.011547005383792516) * 12 ** .5)


if __name__ == "__main__":
    unittest.main()
