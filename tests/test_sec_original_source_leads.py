"""Public SEC index leads cannot be mistaken for original filing evidence."""
import json
from pathlib import Path
import unittest

from scripts.historical_sec_fsd_intake import as_filed_acceptance, cutoff_timestamp
from scripts.historical_sec_original_filing import request_template


class SecOriginalSourceLeadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads((Path(__file__).resolve().parents[1] /
            "data/historical/sec-first-cut-original-source-leads-v1.json")
                           .read_text(encoding="utf-8"))

    def test_real_accession_and_official_edgar_paths_are_consistent(self):
        report = self.r
        self.assertEqual(report["schema"],
            "historical-sec-first-cut-original-source-leads-v1")
        self.assertEqual(len(report["sources"]), 1)
        lead = report["sources"][0]
        self.assertEqual(lead["accession"], "0000950170-24-118967")
        self.assertEqual(lead["cik"], "789019")
        self.assertEqual(lead["form"], "10-Q")
        self.assertEqual(lead["period_end"], "2024-09-30")
        self.assertEqual(lead["filed_date"], "2024-10-30")
        prefix = ("https://www.sec.gov/Archives/edgar/data/"
                  f'{lead["cik"]}/{lead["accession"].replace("-", "")}/')
        self.assertEqual(lead["full_submission_url"],
                         prefix + lead["accession"] + ".txt")
        self.assertEqual(lead["index_url"],prefix+lead["accession"]+"-index.html")
        self.assertTrue(lead["primary_document_url"].startswith(prefix))
        self.assertTrue(lead["xbrl_instance_url"].startswith(prefix))
        self.assertGreater(lead["full_submission_size_bytes_reported_in_index"],
                           10000000)
        self.assertLess(as_filed_acceptance(lead["accepted_eastern"]),
                        cutoff_timestamp(report["cut"]))
        self.assertEqual(request_template()["schema"],
                         "historical-sec-original-filing-request-v1")

    def test_no_filing_or_market_certification_from_index(self):
        report = self.r
        self.assertFalse(report["selected_after_inspecting_prediction_outcomes"])
        self.assertEqual(report["eligible_full_engine_cuts_added"], 0)
        self.assertEqual(report["confirmatory_origins_added"], 0)
        self.assertEqual(report["predictive_validation"], "not-established")
        for lead in report["sources"]:
            self.assertIsNone(lead["original_full_submission_sha256"])
            for key in ("first_publication_independently_verified",
                "original_full_submission_bytes_obtained",
                "original_instance_bytes_obtained",
                "derived_fsd_fact_reconciled",
                "historic_cik_security_link_verified",
                "eligible_for_full_engine_historical_replay"):
                self.assertIs(lead[key], False)


if __name__=="__main__":
    unittest.main()
