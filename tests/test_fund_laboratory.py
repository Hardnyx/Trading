"""Registered fund laboratory: frozen verdicts and dated inputs."""
import json
import unittest
from pathlib import Path

from scripts.fund_laboratory import DESIGN, annualized_equity, cape

AUDIT = Path(__file__).resolve().parents[1] / "docs/auditorias/laboratorio-fondo-v1.json"


class FundLaboratoryTests(unittest.TestCase):
    def test_frozen_verdicts(self):
        design = json.loads(DESIGN.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        self.assertFalse(design["post_hoc_changes_permitted"])
        self.assertEqual(audit["L1"]["5_years"]["engine_trailing_earnings"]["verdict"], "not-supported")
        self.assertEqual(audit["L1"]["10_years"]["engine_trailing_earnings"]["verdict"], "supported")
        self.assertEqual(audit["L2"]["verdict"], "supported")
        self.assertFalse(audit["L3"]["1990-2018"]["flag_intl_drawdown_worse_by_5pp"])

    def test_inputs_are_dated(self):
        rows = [{"price": 100.0, "dividend": 12.0, "earnings": 10.0, "cpi": 100.0} for _ in range(200)]
        self.assertAlmostEqual(annualized_equity(rows, 10, 1), 1.01 ** 12 - 1)
        self.assertAlmostEqual(cape(rows, 150), 10.0)
        rows[148]["earnings"] = 1000.0  # inside the 3-month publication lag: ignored
        self.assertAlmostEqual(cape(rows, 150), 10.0)
        self.assertIsNone(cape(rows, 100))


if __name__ == "__main__":
    unittest.main()
