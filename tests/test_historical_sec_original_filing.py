"""Fail-closed original EDGAR SEC-HEADER reconciliation with synthetic bytes."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.historical_sec_original_filing import (
    parse_original, reconcile, request_template,
)
from scripts.historical_sec_fsd_intake import extract
from tests.test_historical_sec_fsd_intake import ORIGINAL, archive


def complete_filing(accession=ORIGINAL, cik="123", form="10-K",
                    filing="20241110", accepted="20241110130000",
                    *, suffix=True):
    raw = (
        "<SEC-DOCUMENT>0000000123-24-000001.txt : 20241110\n"
        "<SEC-HEADER>\n"
        f"ACCESSION NUMBER:\t{accession}\n"
        f"CONFORMED SUBMISSION TYPE:\t{form}\n"
        f"<ACCEPTANCE-DATETIME>{accepted}\n"
        f"FILED AS OF DATE:\t{filing}\n"
        "FILER:\n"
        " COMPANY DATA:\n"
        f" CENTRAL INDEX KEY:\t{cik}\n"
        "</SEC-HEADER>\n"
        "<DOCUMENT><TYPE>10-K\n"
        "<TEXT>Original financial report</TEXT></DOCUMENT>\n"
    )
    if suffix:
        raw += "</SEC-DOCUMENT>\n"
    return raw.encode("ascii")


class OriginalFilingIntakeTests(unittest.TestCase):
    def fixture(self, folder):
        td = Path(folder)
        zip_path = archive(td/"2024q4.zip")
        report = extract(zip_path, "2024-12-31T21:00:00Z", ["123"])
        raw_path = td/(ORIGINAL+".txt")
        raw_path.write_bytes(complete_filing())
        return zip_path, report, raw_path

    def test_original_header_matches_and_carries_no_eligibility(self):
        with tempfile.TemporaryDirectory() as d:
            archive_path, report, source = self.fixture(d)
            check = reconcile(report, source, ORIGINAL, archive_path=archive_path,
                              expected_original_sha256=hashlib.sha256(
                                  source.read_bytes()).hexdigest())
            self.assertTrue(check["header_form_filed_accepted_cik_accession_match"])
            self.assertTrue(check["fsd_original_zip_bytes_reverified"])
            self.assertTrue(check["external_filing_sha256_supplied"])
            self.assertTrue(check["original_filing_bytes_present_and_hashed"])
            self.assertFalse(check["original_filing_first_publication_independently_verified"])
            self.assertFalse(check["original_document_numeric_facts_reconciled"])
            self.assertEqual(check["eligible_full_engine_cuts_added"], 0)
            self.assertEqual(check["confirmatory_origins_added"], 0)

    def test_zero_fraction_sec_fsd_matches_original_second_exactly(self):
        with tempfile.TemporaryDirectory() as d:
            _, report, original = self.fixture(d)
            record = next(r for r in report["submissions"]
                          if r["adsh"] == ORIGINAL)
            record["accepted_eastern_as_filed"] += ".0"
            reconciled = reconcile(report, original, ORIGINAL)
            self.assertTrue(reconciled["header_form_filed_accepted_cik_accession_match"])
            self.assertFalse(reconciled["original_filing_first_publication_independently_verified"])
            record["accepted_eastern_as_filed"] = record[
                "accepted_eastern_as_filed"].replace(".0", ".1")
            with self.assertRaises(ValueError):
                reconcile(report, original, ORIGINAL)

    def test_mismatched_original_headers_and_truncated_files_rejected(self):
        mutations = {
            "form": complete_filing(form="10-Q"),
            "cik": complete_filing(cik="456"),
            "accepted": complete_filing(accepted="20241111130000"),
            "filed": complete_filing(filing="20241111"),
            "accession": complete_filing(accession="0000000123-24-000009"),
            "truncated": complete_filing(suffix=False),
            "not-document": complete_filing().replace(b"<SEC-DOCUMENT>",b"<HTML>"),
        }
        for name, raw in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                _, report, file_path = self.fixture(d)
                file_path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    reconcile(report, file_path, ORIGINAL)

    def test_postcutoff_filing_and_wrong_fsd_identity_fail(self):
        with tempfile.TemporaryDirectory() as d:
            _, report, original_path = self.fixture(d)
            with self.assertRaises(ValueError):
                reconcile(report, original_path, "0000000123-24-000003")
            bad = copy.deepcopy(report)
            bad["submissions"][0]["cik"] = "456"
            with self.assertRaises(ValueError):
                reconcile(bad, original_path, ORIGINAL)
            bad = copy.deepcopy(report)
            bad["submissions"][0]["accepted_utc"] = "2024-12-31T23:00:00+00:00"
            with self.assertRaises(ValueError):
                reconcile(bad, original_path, ORIGINAL)

    def test_wrong_archive_hash_and_original_digest_fail(self):
        with tempfile.TemporaryDirectory() as d:
            zp, report, original_path = self.fixture(d)
            with self.assertRaises(ValueError):
                reconcile(report, original_path, ORIGINAL,
                          expected_original_sha256="0"*64)
            bad = copy.deepcopy(report)
            bad["archive_sha256"] = "1"*64
            with self.assertRaises(ValueError):
                reconcile(bad, original_path, ORIGINAL, archive_path=zp)

    def test_duplicate_ciks_or_missing_sec_header_fail(self):
        with self.assertRaises(ValueError):
            parse_original(complete_filing().replace(
                b"</SEC-HEADER>",b"CENTRAL INDEX KEY:\t456\n</SEC-HEADER>"), ORIGINAL)
        with self.assertRaises(ValueError):
            parse_original(complete_filing().replace(
                b"</SEC-HEADER>",b""), ORIGINAL)

    def test_request_is_not_a_fabricated_original(self):
        t = request_template()
        self.assertTrue(t["sec_original_record_not_downloaded_by_template"])
        self.assertTrue(t["first_dissemination_and_numeric_reconciliation_still_required"])
        self.assertEqual(t["eligible_full_engine_cuts"],0)


if __name__ == "__main__":
    unittest.main()
