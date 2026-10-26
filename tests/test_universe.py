"""Tests de escala y resolución del universo de instrumentos."""
import json
import unittest
from unittest.mock import patch
import urllib.error

from scripts import refresh_data as collector
from scripts.universe import AUTO_CIK, EXTRA_STOCKS, EXTRA_ETFS, expanded_universe


class UniverseTests(unittest.TestCase):
    def test_universe_contains_unique_160_stocks_and_100_etfs(self):
        specs = collector.ASSETS + expanded_universe()
        self.assertEqual(len(specs), 260)
        self.assertEqual(len({x[0] for x in specs}), 260)
        self.assertEqual(sum(x[3] is None for x in specs), 100)
        self.assertEqual(sum(x[3] == AUTO_CIK for x in specs), 131)
        self.assertEqual(len(EXTRA_STOCKS), 131)
        self.assertEqual(len(EXTRA_ETFS), 56)

    def test_stale_single_ticker_does_not_backdate_market_price_cut(self):
        items = [
            {"symbol": "SPY", "price_date": "2026-10-23"},
            {"symbol": "AAPL", "price_date": "2026-10-23"},
            {"symbol": "MSFT", "price_date": "2026-10-23"},
            {"symbol": "ILLQ", "price_date": "2026-10-20"},
        ]
        self.assertEqual(collector.common_price_cutoff(items), "2026-10-23")
        items[0]["price_date"] = "2026-10-20"
        self.assertEqual(collector.common_price_cutoff(items), "2026-10-23")

    def test_official_cik_mapping_matches_exact_symbol(self):
        registry = {"0": {"ticker": "AVGO", "cik_str": 1730168},
                    "1": {"ticker": "GS", "cik_str": 886982},
                    "2": {"ticker": "NOT-AVGO", "cik_str": 100}}
        with patch.object(collector, "ASSETS", []), \
             patch.object(collector, "expanded_universe", return_value=[
               ("AVGO", "Broadcom", "Tecnología", AUTO_CIK, 0.06, 22),
               ("GS", "Goldman Sachs", "Financiero", AUTO_CIK, 0.04, 15),
             ]), \
             patch.object(collector, "download", return_value=json.dumps(registry).encode()) as request:
            rows, warnings = collector.resolved_universe({})
        self.assertEqual([x[3] for x in rows], [1730168, 886982])
        self.assertEqual(warnings, [])
        self.assertIn("www.sec.gov/files/company_tickers.json", request.call_args.args[0])
        self.assertTrue(request.call_args.kwargs["sec"])

    def test_registry_failure_preserves_prior_verified_cik_without_reclassifying_stock_as_etf(self):
        with patch.object(collector, "ASSETS", []), \
             patch.object(collector, "expanded_universe", return_value=[
               ("AVGO", "Broadcom", "Tecnología", AUTO_CIK, 0.06, 22),
               ("FICT", "Unknown", "Tecnología", AUTO_CIK, 0.06, 22),
             ]), \
             patch.object(collector, "download", side_effect=urllib.error.URLError("offline")):
            rows, warnings = collector.resolved_universe({"AVGO": {"cik": 1730168}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "AVGO")
        self.assertEqual(rows[0][3], 1730168)
        self.assertEqual(len(warnings), 1)
        self.assertIn("FICT", warnings[0])


if __name__ == "__main__":
    unittest.main()
