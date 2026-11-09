"""Fail-closed original foreign-ISIN evidence request and denominator tests."""
import copy
import csv
import io
import unittest

from scripts.historical_foreign_isin_requests import (
    build_requests, request_hash, to_csv, FIELDS,
)


def source():
    return {
        "schema": "historical-sec-alternate-identity-review-v1",
        "cut": "2024-12-31", "source_accession": "spy-filing",
        "source_original_sha256": "a"*64,
        "source_public_available_after_day": "2024-11-29",
        "original_invalid_or_missing_cusip_positions": 2,
        "original_spy_weight": .1,
        "original_cusip_rewritten": False,
        "vendor_identifiers_certified": 0,
        "full_engine_eligible_cuts": 0,
        "positions": [{
            "source_position": i, "cusip_as_reported": "000000000",
            "reported_spy_weight": .06 if i == 0 else .04,
            "explicit_isins": ["GB0002634946"], "invalid_isin_observations": [],
            "explicit_ticker_hints": ["AAA"], "original_lei_hint": "",
            "structural_us_isin_cusip_candidate": None,
            "review_status": "original-non-us-isin-only",
            "source_accession": "spy-filing",
            "source_original_sha256": "a"*64,
            "public_available_after_day": "2024-11-29",
            "decision_cut": "2024-12-31",
        } for i in range(2)],
    }


class ForeignIsinRequestTests(unittest.TestCase):
    def test_duplicate_identical_isins_are_one_enquiry_without_losing_positions(self):
        result = build_requests(source())
        self.assertEqual(result["foreign_isin_request_positions"], 2)
        self.assertEqual(result["distinct_foreign_isin_requests"], 1)
        self.assertEqual(result["requests"][0]["source_positions"], [0, 1])
        self.assertEqual(result["requests"][0]["original_isin"], "GB0002634946")
        self.assertAlmostEqual(result["foreign_isin_request_weight"], .1)
        self.assertEqual(result["unresolved_identifier_positions"], 0)
        self.assertFalse(result["automatic_historical_universe_promotion"])
        self.assertEqual(len(request_hash(result)), 64)
        rows = list(csv.DictReader(io.StringIO(to_csv(result["requests"], FIELDS))))
        self.assertEqual(rows[0]["source_positions"], "0;1")
        self.assertNotIn("provider_instrument_id", rows[0])

    def test_ambiguous_or_invalid_isin_is_quarantined_and_counted(self):
        fixture = source()
        fixture["positions"][1]["review_status"] = "ambiguous-original-valid-isins"
        fixture["positions"][1]["explicit_isins"] = ["GB0002634946", "US0378331005"]
        result = build_requests(fixture)
        self.assertEqual(result["foreign_isin_request_positions"], 1)
        self.assertEqual(result["unresolved_identifier_positions"], 1)
        self.assertAlmostEqual(result["unresolved_identifier_weight"], .04)
        self.assertAlmostEqual(result["foreign_isin_request_weight"], .06)
        fixture = source()
        fixture["positions"][1]["explicit_isins"] = ["GB0002634947"]
        result = build_requests(fixture)
        self.assertEqual(result["unresolved_identifier_positions"], 1)

    def test_original_cusip_and_future_publication_are_never_replaced(self):
        fixture = source()
        fixture["positions"][1]["cusip_as_reported"] = "037833100"
        with self.assertRaisesRegex(ValueError, "source position"):
            build_requests(fixture)
        fixture = source()
        fixture["source_public_available_after_day"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "promoted"):
            build_requests(fixture)

    def test_weight_duplicate_and_provenance_tampering_are_rejected(self):
        fixture = source()
        fixture["positions"][1]["reported_spy_weight"] = .05
        with self.assertRaisesRegex(ValueError, "denominator"):
            build_requests(fixture)
        fixture = source()
        fixture["positions"][1]["source_position"] = 0
        with self.assertRaisesRegex(ValueError, "position"):
            build_requests(fixture)
        fixture = source()
        fixture["positions"][1]["source_original_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "provenance"):
            build_requests(fixture)

    def test_actual_26_original_sec_positions_remain_in_denominator(self):
        from scripts.historical_sec_alternate_identity import audit
        result = build_requests(audit())
        self.assertEqual(result["original_invalid_cusip_positions"], 26)
        self.assertAlmostEqual(result["source_spy_weight"], .03033173560207, places=10)
        self.assertEqual(result["foreign_isin_request_positions"] +
                         result["unresolved_identifier_positions"], 26)
        self.assertAlmostEqual(result["foreign_isin_request_weight"] +
                               result["unresolved_identifier_weight"],
                               result["source_spy_weight"], places=10)
        self.assertEqual(result["full_engine_eligible_cuts"], 0)


if __name__ == "__main__":
    unittest.main()
