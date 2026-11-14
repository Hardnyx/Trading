"""fondo-v2 acceptance results stay reproducible and above their registered limits."""
import json
import unittest
from pathlib import Path

from scripts.fund_v2_acceptance import DESIGN, t3, t4

AUDIT = Path(__file__).resolve().parents[1] / "docs/auditorias/fondo-v2-aceptacion.json"


class FundV2AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = json.loads(DESIGN.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    def test_long_history_is_reproduced(self):
        fresh = t3(self.design)["results"]["70/25/5"]
        frozen = self.audit["T3_long_history"]["results"]["70/25/5"]
        self.assertAlmostEqual(fresh["max_drawdown"], frozen["max_drawdown"], places=10)
        self.assertAlmostEqual(fresh["annualized_return"], frozen["annualized_return"], places=10)

    def test_etf_era_meets_every_registered_limit(self):
        self.assertTrue(all(self.audit["T4_etf_era"]["acceptance"].values()))
        self.assertLessEqual(self.audit["T4_etf_era"]["tracking_error_annualized"], .015)

    def test_exception_threshold_matches_the_long_history(self):
        source = (DESIGN.parents[1] / "dist/assets/js/strategic-fund.mjs").read_text(encoding="utf-8")
        worst = self.audit["T3_long_history"]["results"]["70/25/5"]["max_drawdown"]
        self.assertIn(f"worstHistoricalDrawdown: {round(worst, 3)}", source)


if __name__ == "__main__":
    unittest.main()
