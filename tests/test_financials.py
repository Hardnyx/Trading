from pathlib import Path
import unittest
import json
from copy import deepcopy
from unittest.mock import patch

from scripts import refresh_data as module


class FinancialPeriods(unittest.TestCase):
    def test_missing_net_income_cannot_bypass_split_basis_recovery_and_block(self):
        eps = {"value": 167.95, "period_end": "2026-06-30", "filed": "2026-08-04",
               "method": "TTM", "components": [
                   {"filed": "2026-02-18", "val": 165.57},
                   {"filed": "2026-08-04", "val": 3.88},
                   {"filed": "2026-08-04", "val": 1.5}]}
        prices = {"price": 153.14, "price_date": "2026-10-26", "source_url": "https://example.test/",
                  "history": [{"date": "2026-10-26", "close": 153.14, "adj_close": 153.14}],
                  "splits": [{"date": "2026-04-06", "ratio": 25}]}
        report = {"form": "10-Q", "filing_date": "2026-08-04", "report_date": "2026-06-30"}
        with patch.object(module, "prices", return_value=prices), \
             patch.object(module, "financials", side_effect=lambda *a, **k: {"eps": deepcopy(eps), "net_income": None, "refresh_status": "available"}) as fetch, \
             patch.object(module, "filings", return_value=[report]):
            asset, errors = module.build_asset(("TEST", "Example", "Industrial", 1, .05, 20), "2026-10-26", {})
        self.assertEqual(fetch.call_count, 2)
        self.assertIsNone(asset["financials"]["eps"])
        self.assertEqual(asset["financials"]["eps_unverified"]["value"], 167.95)
        self.assertTrue(any("base por acción" in e for e in errors))
        for row in eps["components"]:
            row["filed"] = "2026-08-04"
        self.assertIsNone(module.eps_split_basis_problem({"symbol": "TEST", "splits": prices["splits"], "financials": {"eps": eps}}, "2026-10-26"))

    def test_submission_keeps_reporting_period_separate_from_filing_date(self):
        body = {"filings": {"recent": {"form": ["10-Q"], "filingDate": ["2026-10-23"],
            "reportDate": ["2026-09-30"], "accessionNumber": ["0000000001-26-000001"],
            "primaryDocument": ["quarter.htm"], "acceptanceDateTime": ["2026-10-23T12:00:00Z"]}}}
        original = module.download
        try:
            module.download = lambda *args, **kwargs: json.dumps(body).encode()
            row = module.filings(1, "2026-10-26")[0]
            self.assertEqual(row["report_date"], "2026-09-30")
            self.assertEqual(row["filing_date"], "2026-10-23")
            self.assertEqual(module.filings(1, "2026-10-22"), [])
        finally:
            module.download = original

    def test_ttm_annual_plus_ytd_minus_prior_ytd(self):
        facts = {"Revenue": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "val": 100},
            {"start": "2026-01-01", "end": "2026-06-30", "filed": "2026-07-25", "val": 65},
            {"start": "2025-01-01", "end": "2025-06-30", "filed": "2026-07-25", "val": 50},
        ]}}}
        self.assertEqual(module.ttm(facts, ["Revenue"], "2026-10-24")["value"], 115)
        self.assertEqual(module.ttm(facts, ["Revenue"], "2026-03-01")["value"], 100)

    def test_later_proxy_statement_does_not_supersede_the_annual_report(self):
        # DEF 14A pay-versus-performance tables repeat net income with their
        # own scale tagging (here: in thousands) and are filed after the 10-K.
        facts = {"NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 8852000000, "filed": "2026-02-25", "form": "10-K"},
            {"start": "2025-01-01", "end": "2025-12-31", "val": 8852000, "filed": "2026-04-06", "form": "DEF 14A"},
            {"start": "2025-01-01", "end": "2025-12-31", "val": 8900000000, "filed": "2026-05-01", "form": "10-K/A"},
        ]}}}
        row = module.ttm(facts, ["NetIncomeLoss"], "2026-10-26")
        self.assertEqual(row["value"], 8900000000)  # a periodic amendment still restates
        facts["NetIncomeLoss"]["units"]["USD"].pop()
        self.assertEqual(module.ttm(facts, ["NetIncomeLoss"], "2026-10-26")["value"], 8852000000)
        self.assertFalse(module.periodic_form("DEF 14A"))
        self.assertTrue(module.periodic_form(None))  # original iXBRL rows carry their own form check

    def test_provider_spin_off_adjustments_are_not_share_splits(self):
        history = [
            {"period_end": "2026-04-30", "shares_unadjusted": 238_600_000},
            {"period_end": "2026-07-16", "shares_unadjusted": 236_600_000},
            {"period_end": "2024-03-31", "shares_unadjusted": 2_460_000_000},
            {"period_end": "2024-07-28", "shares_unadjusted": 24_530_000_000},
        ]
        asset = {"splits": [
            {"date": "2026-06-01", "ratio": 1.241},   # FedEx Freight spin-off
            {"date": "2024-06-10", "ratio": 10.0},    # genuine 10:1 split
            {"date": "2021-11-02", "ratio": 1.973},   # no share observations, not a simple ratio
            {"date": "2023-02-08", "ratio": 1.5},     # no share observations, simple 3:2
        ], "financials": {"history": history}}
        module.classify_corporate_actions(asset)
        self.assertEqual([(r["date"], r["ratio"]) for r in asset["splits"]],
                         [("2024-06-10", 10.0), ("2023-02-08", 1.5)])
        adjustments = {r["date"]: r for r in asset["price_adjustments"]}
        self.assertAlmostEqual(adjustments["2026-06-01"]["observed_share_ratio"], 236.6 / 238.6)
        self.assertIsNone(adjustments["2021-11-02"]["observed_share_ratio"])
        self.assertEqual(adjustments["2026-06-01"]["classification"], "price_adjustment_not_share_split")

    def test_adjustment_close_to_one_is_not_confirmed_by_unchanged_shares(self):
        asset = {"splits": [{"date": "2025-10-30", "ratio": 1.061}], "financials": {"history": [
            {"period_end": "2025-09-30", "shares_unadjusted": 634_900_000},
            {"period_end": "2025-12-31", "shares_unadjusted": 635_700_000}]}}
        module.classify_corporate_actions(asset)
        self.assertEqual(asset["splits"], [])
        self.assertTrue(module.simple_ratio(1.25) and module.simple_ratio(0.1))
        self.assertFalse(module.simple_ratio(1.057))

    def test_future_filing_is_not_available_at_cutoff(self):
        facts = {"EPS": {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "val": 10},
            {"start": "2025-01-01", "end": "2025-12-31", "filed": "2026-12-01", "val": 100},
        ]}}}
        self.assertEqual(module.ttm(facts, ["EPS"], "2026-10-24", "USD/shares")["value"], 10)

    def test_diluted_earnings_components_are_collected_separately(self):
        tags = {'EarningsPerShareDiluted': 5,
                'IncomeLossFromContinuingOperationsPerDilutedShare': 4,
                'IncomeLossFromDiscontinuedOperationsNetOfTaxPerDilutedShare': 1}
        body = {'facts': {'us-gaap': {tag: {'units': {'USD/shares': [{
            'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-02-01', 'val': val,
            'accn': 'original'}]}} for tag, val in tags.items()}}}
        original = module.download
        try:
            module.download = lambda *args, **kwargs: json.dumps(body).encode()
            f = module.financials(1, '2026-10-26')
            self.assertEqual(f['eps']['value'], 5)
            self.assertEqual(f['continuing_eps']['value'], 4)
            self.assertEqual(f['discontinued_eps']['value'], 1)
            self.assertEqual(f['continuing_eps']['components'][0]['accn'], 'original')
        finally:
            module.download = original

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
