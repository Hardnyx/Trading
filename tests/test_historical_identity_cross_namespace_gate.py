"""Cross-namespace duplicate guards with synthetic CUSIP and foreign ISIN evidence."""
import copy
import unittest

from scripts.historical_identity_cross_namespace_gate import (
    PROTOCOL, combine, source_contract, template,
)
from scripts.historical_foreign_isin_vendor_identity import (
    reconcile as reconcile_foreign,
)
from scripts.historical_vendor_identity import reconcile as reconcile_cusip


def fixtures():
    original = {
        "cut": "2024-12-31", "spy_original_accession": "spy-original",
        "spy_original_sha256": "a"*64,
        "full_engine_replay_ready": False, "positive_spy_weight": 1.,
        "counts": {"positive_positions": 3},
        "requests": [
            {"source_position": 0, "cusip": "037833100", "weight": .6,
             "original_ticker_observation": "AAA", "vendor_instrument_id": None,
             "vendor_price_series_verified": False},
            {"source_position": 1, "cusip": "594918104", "weight": .35,
             "original_ticker_observation": "BBB", "vendor_instrument_id": None,
             "vendor_price_series_verified": False},
            {"source_position": 2, "cusip": "000000000", "weight": .05,
             "original_ticker_observation": None, "vendor_instrument_id": None,
             "vendor_price_series_verified": False},
        ],
    }
    foreign = {
        "schema": "historical-foreign-isin-requests-v1", "cut": "2024-12-31",
        "source_accession": "spy-original", "source_original_sha256": "a"*64,
        "public_available_after_day": "2024-11-29",
        "source_vendor_id_certified": False, "original_cusip_corrected": False,
        "full_engine_eligible_cuts": 0, "foreign_isin_request_positions": 1,
        "distinct_foreign_isin_requests": 1, "foreign_isin_request_weight": .05,
        "unresolved_identifier_positions": 0, "unresolved_identifier_weight": 0.,
        "source_spy_weight": .05, "original_invalid_cusip_positions": 1,
        "requests": [{
            "original_isin": "GB0002634946", "source_positions": [2],
            "reported_spy_weight": .05, "spy_accession": "spy-original",
            "decision_cut": "2024-12-31", "original_sec_sha256": "a"*64,
            "source_identity_role": "original-foreign-isin-vendor-enquiry-only",
        }],
        "unresolved": [],
    }
    return original, foreign


def cusip_row(cusip="037833100", native="GLOBAL-ID-1"):
    return {
        "cusip": cusip, "provider_instrument_id": native,
        "id_namespace": "FIGI", "security_type": "COMMON_STOCK",
        "currency": "USD", "exchange_mic": "XNAS",
        "valid_from": "2000-01-01", "valid_to": "2030-01-01",
        "record_as_of": "2024-12-31", "_source_sha256": "b"*64,
        "_provider": "fixture",
    }


def foreign_row(native="GLOBAL-ID-2"):
    return {
        "original_isin": "GB0002634946", "provider_instrument_id": native,
        "id_namespace": "FIGI", "security_type": "COMMON_STOCK",
        "currency": "GBP", "exchange_mic": "XLON",
        "valid_from": "2000-01-01", "valid_to": "2030-01-01",
        "record_as_of": "2024-12-31", "_source_sha256": "c"*64,
        "_provider": "fixture",
    }


def reports(original, foreign, cusip=None, isin=None):
    c = reconcile_cusip(original, cusip if cusip is not None else
                        [cusip_row()], [], "d"*64)
    f = reconcile_foreign(foreign, isin if isin is not None else
                          [foreign_row()], [], "e"*64)
    return c, f


class CrossNamespaceTests(unittest.TestCase):
    def test_distinct_global_keys_keep_source_weights_separate(self):
        original, foreign = fixtures()
        report = combine(original, foreign, *reports(original, foreign))
        self.assertEqual(report["protocol"], PROTOCOL)
        self.assertEqual(report["positive_spy_positions"], 3)
        self.assertEqual(report["distinct_permanent_key_collisions"], 0)
        self.assertEqual(report["source_position_count_by_status"],
                         {"no-admissible-cross-source-candidate": 1,
                          "retrospective-cross-source-candidate": 2})
        self.assertAlmostEqual(sum(report["source_spy_weight_by_status"].values()), 1.)
        self.assertFalse(report["historical_prices_certified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)

    def test_identical_key_across_cusip_and_isin_is_quarantined(self):
        original, foreign = fixtures()
        c, f = reports(original, foreign, isin=[foreign_row(native="GLOBAL-ID-1")])
        result = combine(original, foreign, c, f)
        self.assertEqual(result["distinct_permanent_key_collisions"], 1)
        self.assertEqual(result["source_position_count_by_status"],
                         {"no-admissible-cross-source-candidate": 1,
                          "shared-provider-key-quarantined": 2})
        self.assertEqual(result["source_spy_weight_by_status"]["shared-provider-key-quarantined"],
                         .65)
        self.assertIsNone(result["positions"][0]["candidate_security_key"])
        self.assertIsNone(result["positions"][2]["candidate_security_key"])
        self.assertEqual(len(result["collision_references"][0]["original_identifiers"]), 2)

    def test_original_invalid_cusip_is_not_mapped_twice(self):
        original, foreign = fixtures()
        foreign["requests"][0]["source_positions"] = [0]
        with self.assertRaisesRegex(ValueError, "references overlap"):
            template(original, foreign)
        original, foreign = fixtures()
        foreign["requests"][0]["reported_spy_weight"] = .06
        with self.assertRaisesRegex(ValueError, "references overlap"):
            template(original, foreign)
        original, foreign = fixtures()
        foreign["requests"] = []
        with self.assertRaisesRegex(ValueError, "coverage"):
            template(original, foreign)

    def test_cusip_report_must_include_full_original_denominator(self):
        original, foreign = fixtures()
        c, f = reports(original, foreign)
        c["positions"] = c["positions"][:2]
        with self.assertRaisesRegex(ValueError, "omits original"):
            combine(original, foreign, c, f)
        original, foreign = fixtures()
        c, f = reports(original, foreign)
        c["positions"][2]["candidate_security_key"] = c["positions"][0]["candidate_security_key"]
        c["positions"][2]["status"] = "retrospective-identity-candidate"
        with self.assertRaisesRegex(ValueError, "Invalid original CUSIP"):
            combine(original, foreign, c, f)

    def test_foreign_report_cannot_omit_source_positions_or_claim_price_proof(self):
        original, foreign = fixtures()
        c, f = reports(original, foreign)
        f["positions"] = []
        with self.assertRaisesRegex(ValueError, "omits a requested"):
            combine(original, foreign, c, f)
        c, f = reports(original, foreign)
        f["positions"][0]["original_price_vintage_verified"] = True
        with self.assertRaisesRegex(ValueError, "claims certification"):
            combine(original, foreign, c, f)

    def test_cut_hash_mismatch_and_source_weight_change_fail_closed(self):
        original, foreign = fixtures()
        c, f = reports(original, foreign)
        f["request_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "mismatch"):
            combine(original, foreign, c, f)
        original, foreign = fixtures()
        c, f = reports(original, foreign)
        original["positive_spy_weight"] = 1.01
        with self.assertRaisesRegex(ValueError, "positions or weights"):
            combine(original, foreign, c, f)


    def test_cusip_and_foreign_keys_retain_their_original_vendor_currency(self):
        original, foreign = fixtures()
        report = combine(original, foreign, *reports(original, foreign))
        self.assertEqual(report["positions"][0]["candidate_security_key"]["quote_currency"],
                         "USD")
        self.assertEqual(report["positions"][2]["candidate_security_key"]["quote_currency"],
                         "GBP")
        self.assertEqual(report["positions"][2]["candidate_security_key"]["exchange_mic"],
                         "XLON")
        self.assertFalse(report["historical_prices_certified"])

    def test_original_archived_sec_template_reconciles_without_vendor(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_foreign_isin_requests import build_requests as foreign_requests
        from scripts.historical_sec_alternate_identity import audit
        original = build_requests()
        foreign = foreign_requests(audit())
        template_out = template(original, foreign)
        self.assertEqual(template_out["positive_spy_positions"], 504)
        self.assertEqual(template_out["foreign_isin_positions"], 26)
        self.assertEqual(template_out["valid_cusip_positions"], 478)
        self.assertAlmostEqual(template_out["positive_spy_weight"], .99989845, places=7)
        self.assertEqual(template_out["vendor_rows_received"], 0)
        self.assertEqual(template_out["full_engine_eligible_cuts"], 0)


if __name__ == "__main__":
    unittest.main()
