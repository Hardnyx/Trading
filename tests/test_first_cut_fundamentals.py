"""First-cut fundamentals reuse the engine's cutoff and reject leaked filings."""
import unittest

from scripts import first_cut_fundamentals as fc

BINDING = {"positions": [
    {"status": "verified", "symbol": "AAA", "cusip": "1", "name": "A", "weight": .5},
    {"status": "verified", "symbol": "BBB", "cusip": "2", "name": "B", "weight": .3},
    {"status": "no-public-series", "symbol": None, "cusip": "3", "name": "C", "weight": .2},
]}


class FirstCutFundamentalsTests(unittest.TestCase):
    def test_only_verified_members_and_no_leaked_filing(self):
        def financials(cik, cut):
            filed = "2024-11-01" if cik == 1 else "2025-02-01"
            return {"entity": "X", "eps": {"value": 2.0, "period_end": "2024-09-30", "filed": filed}}
        members = fc.collect("2024-12-31", BINDING, {"AAA": 1, "BBB": 2}, financials=financials, pause=0)
        self.assertEqual([m["symbol"] for m in members], ["AAA", "BBB"])
        self.assertEqual(members[0]["status"], "available")
        self.assertEqual(members[0]["latest_filed"], "2024-11-01")
        self.assertEqual(members[1]["status"], "error")
        self.assertIn("leaked", members[1]["error"])

    def test_missing_cik_is_reported(self):
        members = fc.collect("2024-12-31", BINDING, {}, financials=lambda c, d: {}, pause=0)
        self.assertTrue(all(m["status"] == "no-sec-cik-for-ticker" for m in members))


if __name__ == "__main__":
    unittest.main()
