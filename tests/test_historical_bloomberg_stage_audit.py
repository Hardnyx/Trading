"""Synthetic mutation tests for the private Bloomberg-v4/SEC source bridge."""
import copy
import unittest

from scripts.historical_bloomberg_stage_audit import audit, canonical, sha256, template, valid_original_cusip

CUT = "2024-12-31"
DECISION = "2024-12-31T16:00:00-05:00"
HASH = "a" * 64


def record(security, dataset, field, value, **kwargs):
    row = {
        "security_id": security, "dataset_id": dataset, "field": field,
        "value": value, "quality_class": "VERIFIED_PIT", "synthetic": False,
        "published_at": "2024-10-01T14:00:00Z",
        "first_available_at": "2024-10-01T14:01:00Z",
        "retrieved_at": "2026-11-10T00:00:00Z", "raw_hash": HASH,
        "vintage_id": "2024-10-01", "source_document_id": "PROVIDER-VERSION-1",
        "source_id": "offline-provider-original", "license_scope": "private-local-only",
        "unit": "identifier", "currency": None, "observation_date": None,
        "evidence": {"semantics_verified": True,
                     "availability_basis": "provider-versioned-original",
                     "availability_source": "local-original-reference",
                     "value_locator": "/records/0/value"},
    }
    row.update(kwargs)
    return row


def stage(rows):
    snapshot = {"requested_as_of": CUT, "price_as_of": CUT,
                "production_eligible": False, "pit_certified": False,
                "synthetic": False}
    return {"schema": "bloomberg-trading-stage-v1", "cutoff": DECISION,
            "snapshot": snapshot, "snapshot_sha256": sha256(canonical(snapshot)),
            "normalized_asof_records": rows, "source_hashes": [],
            "blockers": [{"component": "prices"}], "engine_dispatch_enabled": False,
            "full_model_replay_ready": False, "production_eligible": False}


def requests():
    return {"cut": CUT, "requests": [
        {"cusip": "594918104", "source_position": 181,
         "weight": 0.06566774536397, "original_ticker_observation": "MSFT"},
        {"cusip": "037833100", "source_position": 12,
         "weight": 0.08, "original_ticker_observation": "AAPL"},
    ]}


def rows():
    return [
        record("VENDOR-ID-1", "identifier_history", "cusip", "594918104",
               valid_from="2020-01-01", valid_until="2030-01-01"),
        record("VENDOR-ID-1", "identifier_history", "ticker", "MSFT",
               valid_from="2020-01-01", valid_until="2030-01-01"),
        record("VENDOR-ID-1", "security_master", "currency", "USD"),
        record("VENDOR-ID-1", "security_master", "type", "stock"),
        record("VENDOR-ID-1", "security_master", "exchange_mic", "XNAS"),
        record("VENDOR-ID-1", "daily_prices", "close", 421.2,
               observation_date=CUT, unit="USD/share", currency="USD",
               published_at=DECISION, first_available_at=DECISION,
               adjusted_basis="unadjusted-causal"),
    ]


class HistoricalBloombergStageAuditTests(unittest.TestCase):
    def test_valid_source_intersection_stays_research_only(self):
        result = audit(stage(rows()), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 1)
        self.assertEqual(result["counts"]["no-versioned-v4-cusip-record"], 1)
        self.assertFalse(result["permanent_identity_certified"])
        self.assertFalse(result["vendor_publication_independently_verified"])
        self.assertEqual(result["full_engine_eligible_cuts_added"], 0)
        self.assertEqual(result["positions"][0]["versioned_raw_close_sessions"], 1)

    def test_pre_cut_original_retrieval_is_temporally_admissible(self):
        sample = rows()
        for item in sample[:-1]:
            item["retrieved_at"] = "2024-12-30T14:00:00Z"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 1)

    def test_invalid_sec_cusip_stays_on_separate_foreign_isin_route(self):
        req = requests()
        req["requests"].append({"cusip": "000000000", "source_position": 500,
                                "weight": 0.001, "original_ticker_observation": None})
        sample = rows()
        sample.append(record("VENDOR-FOREIGN", "identifier_history", "cusip", "000000000",
                             valid_from="2020-01-01", valid_until="2030-01-01"))
        result = audit(stage(sample), req)
        self.assertEqual(result["counts"]["invalid-original-cusip-requires-isin-source-review"], 1)
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 1)
        self.assertTrue(valid_original_cusip("594918104"))
        self.assertFalse(valid_original_cusip("594918105"))
        self.assertFalse(valid_original_cusip("000000000"))

    def test_original_foreign_isin_crosscheck_is_not_vendor_identity(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_sec_alternate_identity import audit as audit_alternates
        original, alternate = build_requests(), audit_alternates()
        result = audit(stage([]), original, alternate)
        self.assertEqual(result["total_original_sec_positions"], 504)
        self.assertEqual(result["valid_original_cusip_positions"], 478)
        self.assertEqual(result["invalid_original_cusip_positions"], 26)
        self.assertEqual(result["foreign_isin_positions_reconciled_to_original"], 26)
        self.assertEqual(result["counts"]["original-foreign-isin-separate-vendor-route"], 26)
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        self.assertTrue(result["original_sec_foreign_isin_route_reverified"])
        self.assertFalse(result["permanent_identity_certified"])

    def test_foreign_isin_route_rejects_mutated_original_receipts(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_sec_alternate_identity import audit as audit_alternates
        original, alternate = build_requests(), audit_alternates()
        altered = copy.deepcopy(alternate)
        altered["positions"][0]["cusip_as_reported"] = "594918104"
        with self.assertRaisesRegex(ValueError, "SEC foreign-ISIN route was changed"):
            audit(stage([]), original, altered)
        altered = copy.deepcopy(alternate)
        altered["positions"][0]["explicit_isins"] = ["US5949181045"]
        with self.assertRaisesRegex(ValueError, "SEC foreign-ISIN route was changed"):
            audit(stage([]), original, altered)
        altered = copy.deepcopy(alternate)
        altered["positions"].append(copy.deepcopy(altered["positions"][0]))
        with self.assertRaisesRegex(ValueError, "positions do not match"):
            audit(stage([]), original, altered)
        altered = copy.deepcopy(alternate)
        altered["source_original_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            audit(stage([]), original, altered)

    def test_validator_agrees_with_existing_security_master_cusip_check(self):
        # Retain parity with the first-cut provider identity importer.
        from scripts.historical_vendor_identity import valid_cusip
        for value in ("594918104", "037833100", "594918105", "000000000",
                      "US5949181045", "ABCD00000", "12@BC0000"):
            self.assertEqual(valid_original_cusip(value), valid_cusip(value))

    def test_private_stage_cli_requires_original_warehouse(self):
        from scripts.historical_bloomberg_stage_audit import main
        with self.assertRaisesRegex(ValueError, "--warehouse-root is required"):
            main(["--stage", "does-not-exist.json"])

    def test_schema_only_template_is_not_evidence(self):
        self.assertEqual(template()["required_v4_fields"]["identifier_history"],
                         ["cusip", "ticker"])
        self.assertFalse(template()["production_eligible"])

    def test_stage_hash_tampering_rejected(self):
        source = stage(rows())
        source["snapshot"]["requested_as_of"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "snapshot and original SEC cut differ"):
            audit(source, requests())
        source["snapshot"]["requested_as_of"] = CUT
        source["snapshot"]["assets"] = []
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            audit(source, requests())

    def test_no_after_close_stage(self):
        source = stage(rows())
        source["cutoff"] = "2024-12-31T17:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "NY 16:00 decision clock"):
            audit(source, requests())

    def test_no_fractional_second_after_frozen_close(self):
        source = stage(rows())
        source["cutoff"] = "2024-12-31T16:00:00.000001-05:00"
        with self.assertRaisesRegex(ValueError, "NY 16:00 decision clock"):
            audit(source, requests())

    def test_no_promoted_synthetic_stage(self):
        source = stage(rows())
        source["snapshot"]["synthetic"] = True
        source["snapshot_sha256"] = sha256(canonical(source["snapshot"]))
        with self.assertRaisesRegex(ValueError, "cannot assert production/PIT/synthetic"):
            audit(source, requests())

    def test_current_snapshot_or_future_timestamp_never_matches(self):
        sample = rows()
        sample[0]["quality_class"] = "CURRENT_SNAPSHOT_ONLY"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        sample = rows()
        sample[0]["first_available_at"] = "2025-01-01T00:00:00Z"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        sample = rows()
        sample[0]["published_at"] = "2026-01-01T00:00:00Z"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)

    def test_unbounded_or_future_identity_interval_cannot_match(self):
        sample = rows()
        sample[0].pop("valid_until")
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        sample = rows()
        sample[0]["valid_from"] = "2025-01-01"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)

    def test_missing_raw_source_digest_or_original_pointer_cannot_match(self):
        sample = rows()
        sample[0]["raw_hash"] = "invalid"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        sample = rows()
        sample[0]["evidence"]["value_locator"] = None
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)

    def test_missing_original_sec_ticker_stays_unlinked(self):
        req = requests()
        req["requests"][0]["original_ticker_observation"] = None
        report = audit(stage(rows()), req)
        self.assertEqual(report["matched_versioned_raw_close_at_cut"], 0)
        self.assertEqual(report["counts"]["missing-original-sec-ticker-observation"], 1)

    def test_mismatched_sec_original_ticker_is_blocked(self):
        sample = rows()
        sample[1]["value"] = "AAPL"
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["sec-v4-ticker-conflict"], 1)

    def test_duplicate_cusip_candidates_are_quarantined(self):
        sample = rows()
        sample.append(record("VENDOR-ID-2", "identifier_history", "cusip", "594918104",
                             valid_from="2020-01-01", valid_until="2030-01-01"))
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["ambiguous-v4-security-identity"], 1)

    def test_native_id_shared_across_two_sec_cusips_is_quarantined(self):
        sample = rows()
        sample.append(record("VENDOR-ID-1", "identifier_history", "cusip", "037833100",
                             valid_from="2020-01-01", valid_until="2030-01-01"))
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["v4-security-key-reused-for-distinct-cusips"], 2)

    def test_missing_mic_stops_price_promotion(self):
        sample = [r for r in rows() if r["field"] != "exchange_mic"]
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["missing-usd-stock-and-exchange-mic-original-metadata"], 1)

    def test_future_session_close_cannot_have_been_published_in_october(self):
        sample = rows()
        sample[-1]["published_at"] = "2024-10-01T14:00:00Z"
        sample[-1]["first_available_at"] = "2024-10-01T14:01:00Z"
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 0)
        self.assertEqual(result["counts"]["no-original-raw-close-at-decision-cut"], 1)

    def test_decision_day_preclose_or_later_publication_is_not_admissible(self):
        sample = rows()
        sample[-1]["published_at"] = "2024-12-31T20:59:59Z"
        sample[-1]["first_available_at"] = "2024-12-31T20:59:59Z"
        self.assertEqual(audit(stage(sample), requests())["matched_versioned_raw_close_at_cut"], 0)
        sample = rows()
        sample[-1]["published_at"] = "2024-12-31T21:00:01Z"
        sample[-1]["first_available_at"] = "2024-12-31T21:00:01Z"
        # Correct chronology alone does not make a quote available at the
        # earlier, immutable 16:00 New York research decision clock.
        self.assertEqual(audit(stage(sample), requests())["matched_versioned_raw_close_at_cut"], 0)

    def test_prior_session_cannot_be_published_before_its_observation(self):
        sample = rows()
        sample.insert(-1, record(
            "VENDOR-ID-1", "daily_prices", "close", 419.0,
            observation_date="2024-12-30", unit="USD/share", currency="USD",
            published_at="2024-12-29T21:00:00Z",
            first_available_at="2024-12-29T21:00:00Z",
            adjusted_basis="unadjusted-causal"))
        result = audit(stage(sample), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 1)
        self.assertEqual(result["positions"][0]["versioned_raw_close_sessions"], 1)

    def test_adjusted_prices_are_not_raw_close_evidence(self):
        sample = rows()
        sample[-1]["adjusted_basis"] = "split-adjusted"
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["no-original-raw-close-at-decision-cut"], 1)

    def test_conflicting_closing_prices_are_quarantined(self):
        sample = rows()
        sample.append(record("VENDOR-ID-1", "daily_prices", "close", 430.1,
                             observation_date=CUT, unit="USD/share", currency="USD",
                             published_at=DECISION, first_available_at=DECISION,
                             adjusted_basis="unadjusted-causal"))
        result = audit(stage(sample), requests())
        self.assertEqual(result["counts"]["conflicting-raw-close-at-identical-session"], 1)

    def test_collector_used_hash_subset_does_not_hide_available_identity(self):
        # v4 'source_hashes' lists sources used by completed stage assets only.
        # An incomplete stage can still expose original versioned identity rows.
        result = audit(stage(rows()), requests())
        self.assertEqual(result["matched_versioned_raw_close_at_cut"], 1)
        self.assertEqual(result["source_hashes_in_stage"], 0)


if __name__ == "__main__":
    unittest.main()
