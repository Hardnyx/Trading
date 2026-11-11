"""Freeze exact original Vanguard SEC 13F evidence and research-only status."""
import unittest

from scripts.historical_independent_13f import ACCESSION, SCHEMA, archived, compare
from scripts.historical_spy_issuer_lei import review


class IndependentManager13fOriginalArchiveTests(unittest.TestCase):
    def test_archived_original_and_all_spy_cusips_are_reproducible(self):
        original, rows = archived()
        self.assertEqual(original["accession"], ACCESSION)
        self.assertEqual(original["raw_byte_count"], 7166174)
        self.assertEqual(
            original["raw_sha256"],
            "9ad4a1d7fa286d96273cc57e95188a5392d7aae2f2358d0250fa8c3f3a2a0527")
        report = compare(rows, review(), original)
        self.assertEqual(report["schema"], SCHEMA)
        self.assertEqual(report["original_information_table_rows"], 14733)
        self.assertEqual(report["original_nonoption_share_rows"], 14733)
        self.assertEqual(report["spy_positive_positions"], 504)
        self.assertEqual(report["spy_valid_cusip_positions"], 478)
        self.assertEqual(report["status_counts"], {
            "independent-13f-cusip-and-class-observed": 478,
        })
        self.assertEqual(len(report["positions"]), 478)
        self.assertTrue(all(r["other_manager_name_as_filed"]
                            and r["other_manager_class_as_filed"]
                            and r["review_status"] ==
                            "independent-13f-cusip-and-class-observed"
                            for r in report["positions"]))
        self.assertFalse(report["vendor_historical_security_master_certified"])
        self.assertFalse(report["issuer_cik_security_binding_certified"])
        self.assertFalse(report["historical_prices_or_actions_certified"])
        self.assertFalse(report["original_first_publication_independently_authenticated"])
        self.assertEqual(report["full_engine_eligible_cuts_added"], 0)


if __name__ == "__main__":
    unittest.main()
