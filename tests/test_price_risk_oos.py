"""Registered 2008-2019 price risk test: inputs and verdict rules."""
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts.price_risk_oos_inputs import DESIGN, adjusted_history


def write(path, rows, header):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


class PriceRiskOosTests(unittest.TestCase):
    def test_dividends_adjust_prior_closes_only(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "X"
            folder.mkdir()
            write(folder / "2010.csv.gz", [["2010-01-04", 1, 1, 1, 100, 5], ["2010-01-05", 1, 1, 1, 99, 5],
                                           ["2010-01-06", 1, 1, 1, 101, 5]],
                  ["date", "open", "high", "low", "close", "volume"])
            write(folder / "events.csv.gz", [["2010-01-05", "dividend", 2.0], ["2011-01-03", "dividend", 9.0]],
                  ["date", "type", "value"])
            rows = adjusted_history("X", "2010-12-31", archive=Path(root))
        self.assertEqual([r["adj_close"] for r in rows[1:]], [99, 101])
        self.assertAlmostEqual(rows[0]["adj_close"], 100 * (1 - 2 / 100))
        # Multiplicative rule: the ex-date return is P1 / (P0 - dividend).
        self.assertAlmostEqual(rows[1]["adj_close"] / rows[0]["adj_close"], 99 / (100 - 2))

    def test_registration_is_frozen_out_of_the_prior_audit_window(self):
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        self.assertLess(design["period"]["last_cut"], "2021-11-15")
        self.assertFalse(design["post_hoc_changes_permitted"])
        self.assertFalse(design["engine"]["parameters_changed"])
        self.assertNotIn("SGOV", design["instruments"])
        audit = json.loads((DESIGN.parent / "auditorias/price-risk-oos-2008-2019.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["A_calibration"]["verdict"], "inconclusive")
        self.assertEqual(audit["B_improvement"]["verdict"], "inconclusive")
        self.assertFalse(audit["production_eligible"])


if __name__ == "__main__":
    unittest.main()
