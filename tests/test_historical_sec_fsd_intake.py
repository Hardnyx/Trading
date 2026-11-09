"""Synthetic SEC FSD ZIPs cover admission, amendments and provenance barriers."""
import copy
import csv
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.historical_sec_fsd_intake import (
    SOURCE_PAGE, as_filed_acceptance, cutoff_timestamp, cik_number,
    extract, template,
)

ORIGINAL = "0000000123-24-000001"
AMENDED = "0000000123-24-000002"
LATE = "0000000123-24-000003"
OTHER = "0000000456-24-000004"


def tsv(fields, rows):
    stream = StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def archive(path, *, bad_num=False, segments=True, duplicate=False,
            malicious=False):
    subs = [
        (ORIGINAL, "123", "Example", "10-K", "20231231", "20241110",
         "2024-11-10 13:00:00", "original.xml"),
        (AMENDED, "123", "Example", "10-K/A", "20231231", "20241230",
         "2024-12-30 17:00:00", "amended.xml"),
        (LATE, "123", "Example", "10-Q", "20240930", "20241231",
         "2024-12-31 16:30:00", "late.xml"),
        (OTHER, "456", "Other", "10-K", "20231231", "20241201",
         "2024-12-01 11:00:00", "other.xml"),
    ]
    subfields = ("adsh", "cik", "name", "form", "period", "filed",
                 "accepted", "instance")
    numfields = ["adsh", "tag", "version", "coreg", "ddate", "qtrs",
                 "uom", "value", "footnote"]
    if segments:
        numfields.append("segments")
    nums = []
    for adsh, amount in ((ORIGINAL, "123.50"), (AMENDED, "125.25"),
                         (LATE, "200"), (OTHER, "300")):
        row = {"adsh": adsh, "tag": "NetIncomeLoss",
               "version": "us-gaap/2024", "coreg": "", "ddate": "20231231",
               "qtrs": "4", "uom": "USD", "value": amount, "footnote": ""}
        if segments:
            row["segments"] = "" if adsh != AMENDED else "Restatement=Adjustment;"
        nums.append(row)
    if bad_num:
        nums[0]["value"] = "NaN"
    if duplicate:
        nums.append(copy.deepcopy(nums[0]))
    with ZipFile(path, "w") as file:
        file.writestr("sub.txt", tsv(subfields, [dict(zip(subfields, s)) for s in subs]))
        file.writestr("num.txt", tsv(numfields, nums))
        if malicious:
            file.writestr("../payload.txt", "bad")
    return path


class SecFsdIntakeTests(unittest.TestCase):
    def test_as_filed_acceptance_respects_decision_time_not_filing_period(self):
        accepted = as_filed_acceptance("2024-12-31 16:30:00")
        self.assertGreater(accepted, cutoff_timestamp("2024-12-31T21:00:00Z"))
        self.assertLess(as_filed_acceptance("2024-12-30 17:00:00"),
                        cutoff_timestamp("2024-12-31T21:00:00Z"))
        for bad in ("2024-12-31T16:30:00Z", "nonsense", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                as_filed_acceptance(bad)
        for bad in ("2024-12-31T16:00:00", "2024-13-31T21:00:00Z"):
            with self.assertRaises(ValueError):
                cutoff_timestamp(bad)

    def test_preserves_original_and_precut_amendment_without_folding(self):
        with tempfile.TemporaryDirectory() as td:
            path = archive(Path(td)/"2024q4.zip")
            report = extract(path, "2024-12-31T21:00:00Z", ["0000000123"])
            self.assertEqual(report["selected_submission_count"], 2)
            self.assertEqual(report["excluded_target_submissions_after_cutoff"], 1)
            self.assertEqual(report["selected_fact_count"], 2)
            self.assertEqual({v["adsh"] for v in report["facts"]}, {ORIGINAL, AMENDED})
            self.assertEqual({v["value_decimal_as_filed"] for v in report["facts"]},
                             {"123.50", "125.25"})
            self.assertTrue(report["segments_column_present_in_num"])
            self.assertTrue(any(v["segments"] for v in report["facts"]))
            self.assertFalse(all(v["consolidated_unsegmented_candidate"]
                                 for v in report["facts"]))
            self.assertTrue(any(v["consolidated_unsegmented_candidate"]
                                for v in report["facts"]))
            self.assertTrue(any(v["amendment"] for v in report["facts"]))
            self.assertTrue(report["duplicate_periods_from_multiple_submissions_not_auto_resolved"])
            self.assertFalse(report["fundamentals_and_quality_component_certified"])
            self.assertFalse(report["original_filing_publication_independently_verified"])
            self.assertEqual(report["eligible_full_engine_cuts_added"], 0)

    def test_preserves_legacy_missing_segments_column_as_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            p = archive(Path(td)/"2024q4.zip", segments=False)
            r = extract(p, "2024-12-31T21:00:00Z", ["123"],
                        tag_filters=["NetIncomeLoss"])
            self.assertFalse(r["segments_column_present_in_num"])
            self.assertTrue(all(f["segments"] is None for f in r["facts"]))
            self.assertTrue(all(f["consolidated_unsegmented_candidate"] is False
                                for f in r["facts"]))
            self.assertTrue(all(f["ready_for_historical_valuation"] is False
                                for f in r["facts"]))

    def test_rejects_duplicate_keys_corrupt_values_unsafe_archive_and_limit(self):
        for mode in ("duplicate", "bad_num", "malicious", "limit"):
            with tempfile.TemporaryDirectory() as td:
                p = archive(Path(td)/"2024q4.zip",
                            duplicate=mode=="duplicate",
                            bad_num=mode=="bad_num", malicious=mode=="malicious")
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    extract(p, "2024-12-31T21:00:00Z", ["123"],
                            max_facts=1 if mode == "limit" else 50000)

    def test_does_not_infer_ticker_identity_from_cik_or_current_membership(self):
        with tempfile.TemporaryDirectory() as td:
            p = archive(Path(td)/"2024q4.zip")
            r = extract(p, "2024-12-31T21:00:00Z", ["456"],
                        tag_filters=["NetIncomeLoss"])
            self.assertEqual(r["selected_fact_count"], 1)
            self.assertEqual(r["requested_ciks"], ["456"])
            self.assertFalse(r["ticker_identity_or_security_master_certified"])
            self.assertEqual(r["confirmatory_origins_added"], 0)
            self.assertIn("/456/", r["submissions"][0]["edgar_submission_folder"])
            self.assertTrue(r["archive_sha256"])
            self.assertEqual(r["source_official_page"], SOURCE_PAGE)

    def test_missing_inputs_are_a_request_not_a_fake_certification(self):
        r = template()
        self.assertTrue(r["local_zip_required"])
        self.assertTrue(r["original_filing_archive_and_publication_audit_needed"])
        self.assertEqual(r["eligible_full_engine_cuts"], 0)
        self.assertFalse(r["source_website_access_not_attempted"] is False)
        for bad in ("", "-1", "abc", "0000000000", "12345678901"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cik_number(bad)


if __name__ == "__main__":
    unittest.main()
