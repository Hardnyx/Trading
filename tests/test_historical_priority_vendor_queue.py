"""Crosscheck source-weight priority requests and their optional vendor statuses."""
import copy
import csv
import io
import unittest

from scripts.historical_priority_vendor_queue import (
    build_queue, summarize_reconciliation, template_csv, exception_csv, PROTOCOL,
)
from scripts.historical_vendor_identity import request_hash


def synthetic():
    requests = {
        "cut": "2024-12-31",
        "source_market_commit": "frozen-market",
        "source_manifest_sha256": "a"*64,
        "identifier_manifest_sha256": "b"*64,
        "identifier_archive_sha256": "c"*64,
        "spy_original_accession": "filing-2024",
        "spy_original_sha256": "d"*64,
        "positive_spy_weight": 1.,
        "requests": [
            {"source_position": 0, "cusip": "037833100", "weight": .6,
             "original_ticker_observation": "AAA", "vendor_instrument_id": None,
             "vendor_price_series_verified": False, "original_price_vintage_verified": False},
            {"source_position": 1, "cusip": "594918104", "weight": .2,
             "original_ticker_observation": "BBB", "vendor_instrument_id": None,
             "vendor_price_series_verified": False, "original_price_vintage_verified": False},
            {"source_position": 2, "cusip": "594918104", "weight": .2,
             "original_ticker_observation": "BBB", "vendor_instrument_id": None,
             "vendor_price_series_verified": False, "original_price_vintage_verified": False},
        ],
    }
    gap = {
        "cut": "2024-12-31", "historical_universe_certified": False,
        "requests_are_research_only": True,
        "historical_positive_spy_weight": 1.,
        "source_spy_weight_not_covered_by_pilot": .4,
        "source_positive_positions_not_covered_by_pilot": 2,
        "source_invalid_cusip_positions_not_covered_by_pilot": 0,
        "distinct_valid_cusips_not_covered_by_pilot": 1,
        "priority_vendor_identity_requests": [{
            "cusip": "594918104", "reported_positive_weight": .4,
            "source_positions": [1, 2], "original_source_tickers": ["BBB"],
            "price_identifier_verified": False,
            "reason": "source-disclosed-spy-position-not-in-retrospective-pilot",
        }],
    }
    membership = {
        "schema": "historical-spy-membership-audit-v1",
        "first_candidate_cut": "2024-12-31",
        "price_vendor_identity_certified": False,
        "full_engine_eligible_cuts": 0,
        "cut_summaries": [{
            "cut": "2024-12-31",
            "status": "source-backed-spy-membership-only",
            "spy_accession": "filing-2024",
            "available_after_day": "2024-11-29",
            "as_of": "2024-09-30",
            "positive_positions": 3,
        }],
        "source_provenance": {
            "source_market_commit": "frozen-market",
            "provider_manifest_sha256": "a"*64,
            "identifier_manifest_sha256": "b"*64,
            "archived_observations_sha256": "c"*64,
        },
        "first_cut_pilot_ticker_overlap": gap,
    }
    return requests, membership


class PriorityQueueTests(unittest.TestCase):
    def test_groups_duplicate_position_cusips_but_keeps_full_origin_trace(self):
        requests, membership = synthetic()
        result = build_queue(requests, membership)
        self.assertEqual(result["protocol"], PROTOCOL)
        self.assertEqual(result["priority_cusips"], 1)
        self.assertEqual(result["priority_requests"][0]["source_positions"], [1, 2])
        self.assertAlmostEqual(result["omitted_valid_cusip_weight"], .4)
        self.assertEqual(result["sec_request_sha256"], request_hash(requests))
        self.assertEqual(result["historical_security_master_certified"], False)
        rows = list(csv.DictReader(io.StringIO(template_csv(result))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cusip"], "594918104")
        self.assertEqual(rows[0]["source_positions"], "1;2")
        self.assertNotIn("provider_instrument_id", rows[0])

    def test_invalid_original_cusip_has_separate_review_and_reconciled_weight(self):
        requests, membership = synthetic()
        requests["requests"].append({
            "source_position": 3, "cusip": "000000000", "weight": .05,
            "original_ticker_observation": None, "vendor_instrument_id": None,
            "vendor_price_series_verified": False, "original_price_vintage_verified": False,
        })
        requests["positive_spy_weight"] = 1.05
        membership["cut_summaries"][0]["positive_positions"] = 4
        overlap = membership["first_cut_pilot_ticker_overlap"]
        overlap["historical_positive_spy_weight"] = 1.05
        overlap["source_spy_weight_not_covered_by_pilot"] = .45
        overlap["source_positive_positions_not_covered_by_pilot"] = 3
        overlap["source_invalid_cusip_positions_not_covered_by_pilot"] = 1
        queue = build_queue(requests, membership)
        self.assertEqual(queue["priority_cusips"], 1)
        self.assertAlmostEqual(queue["omitted_source_spy_weight"], .45)
        self.assertAlmostEqual(queue["omitted_valid_cusip_weight"], .4)
        self.assertAlmostEqual(queue["omitted_invalid_or_missing_cusip_weight"], .05)
        self.assertEqual(queue["invalid_cusip_review_cases"][0]["source_position"], 3)
        self.assertEqual(queue["invalid_cusip_review_cases"][0]["cusip_as_reported"], "000000000")
        exception_rows = list(csv.DictReader(io.StringIO(exception_csv(queue))))
        self.assertEqual(len(exception_rows), 1)
        self.assertEqual(exception_rows[0]["review_reason"], "invalid-or-missing-original-sec-cusip")
        self.assertNotIn("provider_instrument_id", exception_rows[0])

        # The audit must not paper over a false source weight by subtraction.
        overlap["source_spy_weight_not_covered_by_pilot"] = .46
        with self.assertRaisesRegex(ValueError, "weight mismatch"):
            build_queue(requests, membership)

    def test_source_hash_and_filing_clocks_cannot_be_substituted(self):
        request, membership = synthetic()
        membership["source_provenance"]["provider_manifest_sha256"] = "e"*64
        with self.assertRaisesRegex(ValueError, "source hashes"):
            build_queue(request, membership)
        request, membership = synthetic()
        membership["cut_summaries"][0]["available_after_day"] = "2024-12-31"
        with self.assertRaisesRegex(ValueError, "not identical"):
            build_queue(request, membership)

    def test_priority_rows_cannot_change_original_weights_or_source_positions(self):
        request, membership = synthetic()
        item = membership["first_cut_pilot_ticker_overlap"]["priority_vendor_identity_requests"][0]
        item["reported_positive_weight"] = .5
        with self.assertRaisesRegex(ValueError, "weight"):
            build_queue(request, membership)
        request, membership = synthetic()
        item = membership["first_cut_pilot_ticker_overlap"]["priority_vendor_identity_requests"][0]
        item["source_positions"] = [1, 1]
        with self.assertRaisesRegex(ValueError, "duplicated"):
            build_queue(request, membership)
        request, membership = synthetic()
        item = membership["first_cut_pilot_ticker_overlap"]["priority_vendor_identity_requests"][0]
        item["source_positions"] = [0, 1]
        with self.assertRaisesRegex(ValueError, "CUSIP"):
            build_queue(request, membership)

    def test_missing_or_falsely_certified_vendor_identity_fails_closed(self):
        request, membership = synthetic()
        item = membership["first_cut_pilot_ticker_overlap"]["priority_vendor_identity_requests"][0]
        item["price_identifier_verified"] = True
        with self.assertRaisesRegex(ValueError, "falsely asserts"):
            build_queue(request, membership)
        request, membership = synthetic()
        request["requests"][1]["vendor_instrument_id"] = "BBGFAKED"
        with self.assertRaisesRegex(ValueError, "vendor-enriched"):
            build_queue(request, membership)

    def test_reconciliation_is_by_source_position_not_ticker_or_name(self):
        request, membership = synthetic()
        queue = build_queue(request, membership)
        vendor = {
            "cut": "2024-12-31",
            "request_sha256": queue["sec_request_sha256"],
            "vendor_manifest_sha256": "e"*64,
            "full_engine_replay_ready": False,
            "positions": [
                {"source_position": i, "cusip": cusip,
                 "status": "retrospective-identity-candidate" if i else "no-provider-evidence",
                 "historical_availability_certified": False,
                 "price_history_verified": False,
                 "production_eligible": False,
                } for i, cusip in enumerate(("037833100", "594918104", "594918104"))
            ],
        }
        result = summarize_reconciliation(queue, vendor)
        self.assertEqual(result["status_counts_by_distinct_cusip"],
                         {"retrospective-identity-candidate": 1})
        self.assertAlmostEqual(result["source_spy_weight_by_status"]["retrospective-identity-candidate"], .4)
        self.assertEqual(result["full_engine_eligible_cuts"], 0)
        vendor["positions"][2]["status"] = "conflicting-provider-identities"
        with self.assertRaisesRegex(ValueError, "conflicting vendor states"):
            summarize_reconciliation(queue, vendor)
        vendor["positions"][2]["status"] = "retrospective-identity-candidate"
        vendor["positions"][2]["price_history_verified"] = True
        with self.assertRaisesRegex(ValueError, "promoted"):
            summarize_reconciliation(queue, vendor)

    def test_real_originals_generate_the_same_351_priorities(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_spy_membership_audit import audit
        queue = build_queue(build_requests(), audit())
        self.assertEqual(queue["cut"], "2024-12-31")
        self.assertEqual(queue["priority_cusips"], 351)
        self.assertAlmostEqual(queue["omitted_source_spy_weight"], .38488811, places=7)
        self.assertAlmostEqual(queue["omitted_valid_cusip_weight"], .35455637, places=7)
        self.assertAlmostEqual(queue["omitted_invalid_or_missing_cusip_weight"], .03033174, places=7)
        self.assertGreater(queue["omitted_invalid_or_missing_cusip_positions"], 0)
        self.assertEqual(len(queue["invalid_cusip_review_cases"]),
                         queue["omitted_invalid_or_missing_cusip_positions"])
        self.assertAlmostEqual(queue["omitted_valid_cusip_weight"] +
                               queue["omitted_invalid_or_missing_cusip_weight"],
                               queue["omitted_source_spy_weight"], places=10)
        self.assertFalse(queue["vendor_identifiers_received"])
        self.assertEqual(queue["full_engine_eligible_cuts"], 0)


if __name__ == "__main__":
    unittest.main()
