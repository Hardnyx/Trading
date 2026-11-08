"""Validate historical identity requests against original archived N-PORT facts."""
import copy
import json
from pathlib import Path
import unittest

from scripts.historical_identity_requests import (
    build_requests, ensure_original_position, evidence_before_cut,
)


class HistoricalIdentityRequestsTests(unittest.TestCase):
    def test_real_archive_produces_unmapped_dated_requests(self):
        report = build_requests()
        self.assertEqual(report["cut"], "2024-12-31")
        self.assertFalse(report["full_engine_replay_ready"])
        self.assertEqual(report["counts"]["positive_positions"], len(report["requests"]))
        self.assertGreater(report["counts"]["with_explicit_ticker"], 0)
        self.assertEqual(report["counts"]["positive_positions"],
                         report["counts"]["with_explicit_ticker"] +
                         report["counts"]["without_explicit_ticker"])
        self.assertGreater(report["explicit_ticker_weight"], 0.96)
        self.assertLess(report["explicit_ticker_weight"], 0.97)
        for row in report["requests"]:
            self.assertIsNone(row["vendor_instrument_id"])
            self.assertFalse(row["vendor_price_series_verified"])
            self.assertFalse(row["original_price_vintage_verified"])
            self.assertFalse(row["production_eligible"])
            for receipt in row["ticker_receipts"]:
                self.assertLess(receipt["available_after_day"], report["cut"])

    def test_derivation_is_deterministic(self):
        self.assertEqual(build_requests(), build_requests())

    def test_rejects_synthetic_price_binding_from_original_ticker(self):
        original = {"cusip": "037833100", "name": "issuer", "title": "common",
                    "symbol": None, "weight": 0.01}
        annotated = {**original, "price_instrument_binding": {"ticker": "AAPL"}}
        with self.assertRaisesRegex(ValueError, "silently promoted"):
            ensure_original_position(original, annotated)

    def test_rejects_rewritten_sec_holdings(self):
        original = {"cusip": "037833100", "name": "issuer", "title": "common",
                    "symbol": None, "weight": 0.01}
        annotated = {**original, "price_instrument_binding": None, "weight": 0.1}
        with self.assertRaisesRegex(ValueError, "changed original SPY weight"):
            ensure_original_position(original, annotated)

    def test_rejects_filing_published_after_cut(self):
        receipt = {"fund": "IVV", "accession": "0001752724-25-043800",
                   "available_after_day": "2025-03-01",
                   "source_url": "https://www.sec.gov/",
                   "raw_sha256": "a" * 64}
        with self.assertRaisesRegex(ValueError, "not available"):
            evidence_before_cut(receipt, "2024-12-31")


if __name__ == "__main__":
    unittest.main()
