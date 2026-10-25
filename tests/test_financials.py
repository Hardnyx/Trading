from pathlib import Path
import unittest
import json

from scripts import refresh_data as module


class FinancialPeriods(unittest.TestCase):
    def test_ttm_annual_plus_ytd_minus_prior_ytd(self):
        facts = {"Revenue": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "val": 100},
            {"start": "2026-01-01", "end": "2026-06-30", "filed": "2026-07-25", "val": 65},
            {"start": "2025-01-01", "end": "2025-06-30", "filed": "2026-07-25", "val": 50},
        ]}}}
        self.assertEqual(module.ttm(facts, ["Revenue"], "2026-10-24")["value"], 115)
        self.assertEqual(module.ttm(facts, ["Revenue"], "2026-03-01")["value"], 100)

    def test_future_filing_is_not_available_at_cutoff(self):
        facts = {"EPS": {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "val": 10},
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-12-01", "val": 100},
        ]}}}
        self.assertEqual(module.ttm(facts, ["EPS"], "2026-10-24", "USD/shares")["value"], 10)

    def test_missing_facts_remain_missing(self):
        self.assertIsNone(module.ttm({}, ["Revenue"], "2026-10-24"))
        self.assertIsNone(module.instant({}, ["Shares"], "2026-10-24", "shares"))

    def test_inconsistent_split_adjusted_eps_is_not_used_for_valuation(self):
        stock = {
            "symbol": "TEST", "splits": [{"date": "2026-04-06", "ratio": 25}],
            "financials": {
                "eps": {"value": 167.95, "method": "TTM", "period_end": "2026-06-30"},
                "net_income": {"value": 5404000000, "method": "FY", "period_end": "2025-12-31"},
                "shares": {"value": 751380500, "period_end": "2026-07-27"},
            },
        }
        warning = module.flag_inconsistent_eps(stock, "2026-10-25")
        self.assertIn("BPA no comparable", warning)
        self.assertIsNone(stock["financials"]["eps"])
        self.assertEqual(stock["financials"]["eps_unverified"]["value"], 167.95)
        self.assertEqual(stock["quality_flags"], ["eps_share_income_scale_mismatch"])

    def test_consistent_eps_remains_available(self):
        stock = {
            "symbol": "TEST", "splits": [{"date": "2025-11-17", "ratio": 10}],
            "financials": {
                "eps": {"value": 3.46, "method": "TTM", "period_end": "2026-09-30"},
                "net_income": {"value": 14766452000, "method": "TTM", "period_end": "2026-09-30"},
                "shares": {"value": 4106325903, "period_end": "2026-09-30"},
            },
        }
        self.assertIsNone(module.flag_inconsistent_eps(stock, "2026-10-25"))
        self.assertEqual(stock["financials"]["eps"]["value"], 3.46)

    def test_bls_missing_values_are_omitted(self):
        original = module.download
        fixture = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [
            {"year": "2026", "period": "M09", "value": "-"},
            {"year": "2026", "period": "M08", "value": "4.1"},
            {"year": "2026", "period": "M07", "value": "4.0"},
        ]}]}}
        try:
            module.download = lambda *args, **kwargs: json.dumps(fixture).encode()
            series = module.bls_series("LNS14000000", "Desempleo", "2026-10-24")
            self.assertEqual(series["value"], 4.1)
            self.assertEqual(len(series["history"]), 2)
        finally:
            module.download = original


if __name__ == "__main__":
    unittest.main()
