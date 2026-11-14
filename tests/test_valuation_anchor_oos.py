"""Registered index and bond anchor test: arithmetic and frozen verdicts."""
import json
import unittest

from scripts.valuation_anchor_oos import DESIGN, bond_realized, equity_anchor, equity_realized, score, verdict


class ValuationAnchorTests(unittest.TestCase):
    def test_returns_and_anchor_use_only_dated_information(self):
        rows = [{"price": 100.0, "dividend": 12.0, "earnings": 5.0, "cpi": 100.0, "gs10": 5.0} for _ in range(30)]
        self.assertAlmostEqual(equity_realized(rows, 13), 1.01 ** 12 - 1)
        self.assertAlmostEqual(bond_realized(rows, 13), 0.05)
        rows[16]["earnings"] = 50.0  # A later earnings figure must not reach the origin.
        self.assertAlmostEqual(equity_anchor(rows, 16, .06, .6), .06 + .6 * (.05 + 0 - .06))

    def test_verdict_rule_and_registered_result(self):
        self.assertEqual(verdict({"r2_os": -.01, "p_one_sided": .01}), "not-supported")
        self.assertEqual(verdict({"r2_os": .01, "p_one_sided": .2}), "inconclusive")
        perfect = score([("x", 1.0, 0.0, 1.0), ("y", 2.0, 0.0, 2.0), ("z", 0.5, 0.0, 0.4)])
        self.assertGreater(perfect["r2_os"], .9)
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        self.assertFalse(design["post_hoc_changes_permitted"])
        audit = json.loads((DESIGN.parent / "auditorias/valuation-anchor-oos-1900-2018.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["equity_anchor"]["verdict"], "not-supported")
        self.assertEqual(audit["bond_anchor"]["verdict"], "supported")


if __name__ == "__main__":
    unittest.main()
