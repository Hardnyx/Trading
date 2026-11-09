"""Fail-closed public SPY membership and ticker-overlap regression cases."""
import copy
import unittest

from scripts.historical_spy_membership_audit import (
    FIRST_CUT, audit, build_result, filing_transitions, pilot_overlap, summarize_cut,
)


def source(cut, accession, as_of, positions, status="source-available",
           available_after_day="2024-11-29", mapped_weight=None):
    if mapped_weight is None:
        mapped_weight = sum(p["weight"] for p in positions if p["weight"] > 0 and
                            p.get("ticker_observation"))
    return {"cut": cut, "spy_source": {
        "status": status, "accession": accession, "as_of": as_of,
        "available_after_day": available_after_day,
    }, "positions": positions, "mapped_positive_weight": mapped_weight}


def position(cusip="037833100", weight=.6, ticker="AAA", known="2024-11-29"):
    return {"cusip": cusip, "weight": weight,
            "price_instrument_binding": None,
            "identifier_status": "explicit-ticker-observed" if ticker else
                                 "no-prior-explicit-ticker",
            "ticker_observation": ({
                "source_ticker": ticker, "as_of": "2024-09-30",
                "evidence": [{"raw_sha256": "a"*64, "available_after_day": known}]
            } if ticker else None)}


class HistoricalMembershipAuditTests(unittest.TestCase):
    def test_filing_membership_and_pilot_ticker_overlap_remain_noncausal(self):
        row = source(FIRST_CUT, "accession-a", "2024-09-30", [
            position(), position("594918104", .4, "BBB")])
        report = build_result([row], ["AAA", "OTHER"], {"fixture": True})
        self.assertEqual(report["fresh_public_spy_holdings_cuts"], 1)
        self.assertEqual(report["first_cut_pilot_ticker_overlap"]["exact_public_ticker_string_matches"], 1)
        self.assertEqual(report["first_cut_pilot_ticker_overlap"]["pilot_unmatched_symbols"], ["OTHER"])
        self.assertFalse(report["continuous_historical_universe_certified"])
        self.assertFalse(report["price_vendor_identity_certified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)

    def test_reverse_spy_coverage_detects_missing_positions_despite_pilot_matches(self):
        row = source(FIRST_CUT, "accession-a", "2024-09-30", [
            position("037833100", .6, "AAA"),
            position("594918104", .4, "BBB"),
        ])
        overlap = pilot_overlap(row, ["AAA"])
        self.assertEqual(overlap["pilot_stock_symbols"], 1)
        self.assertEqual(overlap["exact_public_ticker_string_matches"], 1)
        self.assertAlmostEqual(overlap["historical_positive_spy_weight"], 1)
        self.assertAlmostEqual(overlap["source_cusip_weight_covered_by_pilot_ticker_strings"], .6)
        self.assertAlmostEqual(overlap["source_spy_weight_not_covered_by_pilot"], .4)
        self.assertEqual(overlap["distinct_valid_cusips_not_covered_by_pilot"], 1)
        self.assertEqual(overlap["priority_vendor_identity_requests"][0]["cusip"], "594918104")
        self.assertFalse(overlap["priority_vendor_identity_requests"][0]["price_identifier_verified"])

    def test_omission_queue_groups_duplicated_cusips_without_inventing_ids(self):
        row = source(FIRST_CUT, "accession-a", "2024-09-30", [
            position("037833100", .4, "AAA"),
            position("594918104", .3, "BBB"),
            position("594918104", .3, "BBB"),
        ])
        overlap = pilot_overlap(row, ["AAA"])
        self.assertEqual(overlap["source_positive_positions_not_covered_by_pilot"], 2)
        self.assertEqual(overlap["distinct_valid_cusips_not_covered_by_pilot"], 1)
        self.assertAlmostEqual(overlap["priority_vendor_identity_requests"][0]["reported_positive_weight"], .6)
        self.assertEqual(overlap["priority_vendor_identity_requests"][0]["source_positions"], [1, 2])
        self.assertTrue(overlap["requests_are_research_only"])

    def test_stale_filing_cannot_retain_an_investable_membership(self):
        row = source(FIRST_CUT, "old", "2024-08-01",
                     [position()], "stale-or-invalid-source")
        with self.assertRaisesRegex(ValueError, "Blocked historical cut"):
            summarize_cut(row)
        row["positions"], row["mapped_positive_weight"] = [], 0
        self.assertEqual(summarize_cut(row)["positive_positions"], 0)

    def test_filing_must_be_public_before_cut_and_not_older_than_120_days(self):
        row = source(FIRST_CUT, "accession-a", "2024-09-30",
                     [position()], available_after_day=FIRST_CUT)
        with self.assertRaisesRegex(ValueError, "not public/fresh"):
            summarize_cut(row)
        row["spy_source"]["available_after_day"] = "2024-11-29"
        row["spy_source"]["as_of"] = "2024-01-31"
        with self.assertRaisesRegex(ValueError, "not public/fresh"):
            summarize_cut(row)

    def test_ticker_observation_must_have_earlier_public_source(self):
        row = source(FIRST_CUT, "accession-a", "2024-09-30", [
            position(known="2025-01-01")])
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            summarize_cut(row)

    def test_filing_transition_measures_cusip_disclosure_only(self):
        earlier = source(FIRST_CUT, "a", "2024-09-30", [position()])
        same = source("2025-01-31", "a", "2024-09-30", [position()])
        later = source("2025-02-28", "b", "2024-12-31",
                       [position("594918104", 1, "BBB")],
                       available_after_day="2025-02-28")
        changes = filing_transitions([earlier, same, later])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["newly_disclosed_cusips"], ["594918104"])
        self.assertEqual(changes[0]["no_longer_disclosed_cusips"], ["037833100"])
        self.assertIn("not listings, delistings", changes[0]["interpretation"])

    def test_ambiguous_ticker_string_cannot_become_a_security_match(self):
        row = source(FIRST_CUT, "a", "2024-09-30",
                     [position("037833100", .6, "AAA"),
                      position("594918104", .4, "AAA")])
        overlap = pilot_overlap(row, ["AAA"])
        self.assertEqual(overlap["ambiguous_ticker_string_matches"], 1)
        self.assertEqual(overlap["exact_public_ticker_string_matches"], 0)
        self.assertEqual(overlap["candidate_matched_spy_weight"], 0)

    def test_unverified_price_binding_is_rejected(self):
        pos = position()
        pos["price_instrument_binding"] = {"FIGI": "faked"}
        row = source(FIRST_CUT, "a", "2024-09-30", [pos])
        with self.assertRaisesRegex(ValueError, "promoted"):
            summarize_cut(row)

    def test_real_frozen_originals_and_filing_changes_reconcile(self):
        report = audit()
        self.assertEqual(report["study_cuts"], 48)
        self.assertEqual(report["fresh_public_spy_holdings_cuts"], 26)
        self.assertEqual(report["blocked_or_stale_spy_holdings_cuts"], 22)
        self.assertGreater(report["distinct_filing_transitions"], 0)
        self.assertTrue(report["source_provenance"]["archive_matches_independent_derivation"])
        self.assertFalse(report["issuer_delisting_events_verified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)
        overlap = report["first_cut_pilot_ticker_overlap"]
        self.assertEqual(overlap["pilot_stock_symbols"], 127)
        self.assertEqual(overlap["exact_public_ticker_string_matches"], 127)
        self.assertGreater(overlap["source_spy_weight_not_covered_by_pilot"], 0)
        self.assertGreater(overlap["distinct_valid_cusips_not_covered_by_pilot"], 0)


if __name__ == "__main__":
    unittest.main()
