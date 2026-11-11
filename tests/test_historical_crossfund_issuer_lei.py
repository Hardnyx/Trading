"""Literal SEC cross-fund CUSIP/issuer-LEI comparison at a frozen PIT cut."""
import csv
import io
import unittest

from scripts.historical_crossfund_issuer_lei import (
    CUT, SCHEMA, compare, eligible_pointers, queue_csv, review_crossfund,
)

LEI_A = "5493006QMFDDMYWIAM13"
LEI_B = "5493001KJTIIGC8Y1R12"


def spy_fixture():
    return {
        "schema": "historical-spy-original-issuer-lei-review-v1",
        "cut": CUT,
        "spy_original_accession": "0001752724-24-264697",
        "spy_original_sha256": "a" * 64,
        "total_positive_sec_positions": 3,
        "valid_original_cusip_positions": 2,
        "invalid_original_cusip_positions": 1,
        "permanent_security_identity_certified": False,
        "full_engine_eligible_cuts_added": 0,
        "position_rows": [
            {"source_position": 0, "cusip": "037833100", "weight": 0.4,
             "original_spy_name": "A", "original_issuer_lei_as_filed": LEI_A,
             "issuer_lei_hint": LEI_A},
            {"source_position": 1, "cusip": "594918104", "weight": 0.5,
             "original_spy_name": "B", "original_issuer_lei_as_filed": LEI_B,
             "issuer_lei_hint": LEI_B},
            {"source_position": 2, "cusip": "000000000", "weight": 0.1,
             "original_spy_name": "Foreign", "original_issuer_lei_as_filed": "N/A",
             "issuer_lei_hint": ""},
        ],
    }


def document(fund="ILCB", accession="0001752724-24-295861"):
    return {"fund": fund, "accession": accession,
            "raw_sha256": "b" * 64, "as_of": "2024-10-31",
            "available_after_day": "2024-12-30"}


def observation(cusip="037833100", lei=LEI_A, pointer=None):
    pointer = pointer or document()
    return {"cusip": cusip, "issuer_lei_as_filed": lei,
            "valid_original_issuer_lei": lei if lei in (LEI_A, LEI_B) else "",
            "fund": pointer["fund"], "accession": pointer["accession"],
            "original_sha256": pointer["raw_sha256"],
            "holdings_as_of": pointer["as_of"],
            "available_after_day": pointer["available_after_day"]}


class CrossFundOriginalLeiTests(unittest.TestCase):
    def test_literal_agreement_is_not_instrument_certification(self):
        doc = document()
        report = compare(spy_fixture(), [observation()], [doc])
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["valid_original_cusip_positions"], 2)
        self.assertEqual(report["invalid_original_cusip_positions"], 1)
        self.assertEqual(report["crossfund_lei_agreement_positions"], 1)
        self.assertEqual(report["crossfund_conflict_positions"], 0)
        self.assertFalse(report["permanent_security_identity_certified"])
        self.assertEqual(report["full_engine_eligible_cuts_added"], 0)
        rows = list(csv.DictReader(io.StringIO(queue_csv(report))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cusip"], "594918104")
        self.assertEqual(rows[1]["crossfund_corroborated_issuer_lei"], LEI_A)
        self.assertNotIn("provider_instrument_id", rows[0])

    def test_conflicting_spy_and_fund_leis_are_not_matched(self):
        report = compare(spy_fixture(), [observation(lei=LEI_B)], [document()])
        self.assertEqual(report["crossfund_conflict_positions"], 1)
        self.assertEqual(report["position_rows"][0]["crossfund_status"],
                         "conflicting-spy-and-other-fund-issuer-lei")
        self.assertEqual(report["position_rows"][0]["crossfund_corroborated_issuer_lei"], "")

    def test_conflicting_other_fund_leis_remain_quarantined(self):
        second = document("ISCB", "0001752724-24-295863")
        report = compare(spy_fixture(),
                         [observation(), observation(lei=LEI_B, pointer=second)],
                         [document(), second])
        self.assertEqual(report["crossfund_conflict_positions"], 1)
        self.assertEqual(report["position_rows"][0]["crossfund_status"],
                         "conflicting-original-fund-issuer-leis")
        self.assertEqual(report["position_rows"][0]["crossfund_corroborated_issuer_lei"], "")

    def test_other_fund_cusip_without_valid_lei_is_not_corrob(self):
        report = compare(spy_fixture(), [observation(lei="N/A")], [document()])
        self.assertEqual(report["crossfund_lei_agreement_positions"], 0)
        self.assertEqual(report["position_rows"][0]["crossfund_status"],
                         "other-original-fund-lei-unavailable")

    def test_other_fund_lei_cannot_fill_missing_spy_lei(self):
        spy = spy_fixture()
        spy["position_rows"][0]["issuer_lei_hint"] = ""
        report = compare(spy, [observation()], [document()])
        self.assertEqual(report["position_rows"][0]["crossfund_status"],
                         "other-fund-lei-without-spy-issuer-lei")
        self.assertEqual(report["position_rows"][0]["crossfund_corroborated_issuer_lei"], "")

    def test_source_hash_or_availability_mutation_fails_closed(self):
        doc = document()
        for wrong in ("original_sha256", "available_after_day", "holdings_as_of"):
            candidate = observation()
            candidate[wrong] = "1999-01-01" if wrong != "original_sha256" else "c" * 64
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "proof or cutoff"):
                compare(spy_fixture(), [candidate], [doc])
        future = document()
        future["available_after_day"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "proof or cutoff"):
            compare(spy_fixture(), [observation(pointer=future)], [future])

    def test_selector_uses_only_conservatively_public_fund_originals(self):
        a = document("ILCB", "0001752724-24-295861")
        future = {**a, "accession": "0001752725-25-011111", "as_of": "2024-11-30",
                  "available_after_day": "2025-01-29"}
        old = {**a, "accession": "0001752724-24-001111", "as_of": "2024-08-01",
               "available_after_day": "2024-09-30"}
        manifest = {"protocol": "historical-identifier-sources-v1",
                    "source_market_commit": "8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5",
                    "funds": {"IVV": "S000004310", "ITOT": "S000004317",
                              "IYY": "S000004330", "ISCB": "S000004433",
                              "ILCB": "S000004367"},
                    "collection_complete": True, "errors": [],
                    "documents": [old, a, future]}
        self.assertEqual(eligible_pointers(manifest), [a])
        duplicate = {**a, "accession": "0001752724-24-999999"}
        manifest["documents"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Ambiguous amendments"):
            eligible_pointers(manifest)

    def test_real_frozen_sec_sources_are_reopened_with_no_vendor_promotion(self):
        report = review_crossfund()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["cut"], "2024-12-31")
        self.assertEqual(report["original_fund_documents_reparsed"], 5)
        self.assertEqual(report["valid_original_cusip_positions"], 478)
        self.assertEqual(report["invalid_original_cusip_positions"], 26)
        self.assertEqual(sum(report["crossfund_status_counts"].values()), 478)
        self.assertGreater(report["original_fund_positions_read"], 0)
        self.assertTrue(all(receipt["available_after_day"] < report["cut"]
                            for receipt in report["original_fund_source_receipts"]))
        self.assertTrue(report["crossfund_sources_are_other_original_funds_not_issuer_or_vendor_master"])
        self.assertFalse(report["permanent_security_identity_certified"])
        self.assertFalse(report["vendor_historical_publication_verified"])
        self.assertEqual(report["full_engine_eligible_cuts_added"], 0)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(queue_csv(report))))), 478)


if __name__ == "__main__":
    unittest.main()
