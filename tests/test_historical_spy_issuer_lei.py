"""Source-bound original SEC issuer LEI requests: checksum and denominator."""
import csv
import io
import unittest

from scripts.historical_spy_issuer_lei import (
    SCHEMA, classify_lei, queue_csv, review, valid_lei,
)


class HistoricalSpyIssuerLeiTests(unittest.TestCase):
    def test_iso_17442_check_digits(self):
        self.assertTrue(valid_lei("5493006QMFDDMYWIAM13"))
        self.assertTrue(valid_lei("5493001KJTIIGC8Y1R12"))
        self.assertFalse(valid_lei("5493006QMFDDMYWIAM14"))
        self.assertFalse(valid_lei("5493006QMFDDMYWIAM1"))
        self.assertFalse(valid_lei("N/A"))
        self.assertFalse(valid_lei("5493006QMFDDMYWIAM1x"))

    def test_missing_unavailable_and_invalid_are_not_promoted(self):
        self.assertEqual(classify_lei(""), ("missing-original-issuer-lei", None))
        self.assertEqual(classify_lei("N/A"), ("issuer-lei-not-available-as-filed", None))
        self.assertEqual(classify_lei("5493006QMFDDMYWIAM14"),
                         ("invalid-original-issuer-lei", None))
        self.assertEqual(classify_lei("5493006QMFDDMYWIAM13"),
                         ("valid-original-issuer-lei-hint", "5493006QMFDDMYWIAM13"))

    def test_original_sec_file_reopened_and_504_rows_reconciled(self):
        report = review()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["total_positive_sec_positions"], 504)
        self.assertEqual(report["valid_original_cusip_positions"], 478)
        self.assertEqual(report["invalid_original_cusip_positions"], 26)
        self.assertEqual(sum(report["original_lei_status_counts"].values()), 504)
        self.assertEqual(len(report["position_rows"]), 504)
        self.assertTrue(all(r["original_spy_sha256"] == report["spy_original_sha256"]
                            for r in report["position_rows"]))
        self.assertFalse(report["permanent_security_identity_certified"])
        self.assertFalse(report["vendor_publication_independently_verified"])
        self.assertEqual(report["full_engine_eligible_cuts_added"], 0)
        rows = list(csv.DictReader(io.StringIO(queue_csv(report))))
        self.assertEqual(len(rows), 478)
        self.assertEqual(len({int(r["source_position"]) for r in rows}), 478)
        self.assertEqual([float(r["weight"]) for r in rows],
                         sorted((float(r["weight"]) for r in rows), reverse=True))
        self.assertTrue(all(r["original_spy_accession"] == report["spy_original_accession"]
                            and r["cut"] == "2024-12-31" for r in rows))
        self.assertTrue(all(not r["issuer_lei_hint"] or valid_lei(r["issuer_lei_hint"])
                            for r in rows))
        self.assertTrue(all(r["issuer_lei_status"] != "valid-original-issuer-lei-hint"
                            or r["issuer_lei_hint"] for r in rows))
        # A valid issuer LEI is not a unique tradeable instrument identifier.
        self.assertNotIn("provider_instrument_id", rows[0])


if __name__ == "__main__":
    unittest.main()
