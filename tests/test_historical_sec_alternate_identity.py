"""Original SEC ISIN extraction and preservation of ambiguous identifiers."""
import csv
import io
import unittest

from scripts.historical_sec_alternate_identity import (
    audit, csv_output, isin_valid, literal_identifiers, review_source,
)
import xml.etree.ElementTree as ET


def example(isin="US0378331005", cusip="000000000", weight=.03, extra=""):
    raw = ("""<nport><invstOrSec><name>Original</name><title>Equity</title>
      <cusip>""" + cusip + """</cusip><pctVal>""" + str(weight * 100) + """</pctVal>
      <identifiers><isin value='""" + isin + """'/>""" + extra + """</identifiers>
    </invstOrSec></nport>""").encode()
    positions = [{"cusip": cusip, "weight": weight, "name": "Original", "title": "Equity"}]
    exceptions = [{"source_position": 0, "cusip_as_reported": cusip,
                   "reported_spy_weight": weight}]
    return raw, positions, exceptions


class AlternateIdentityTests(unittest.TestCase):
    def test_iso_6166_luhn_and_original_us_cusip_candidate(self):
        self.assertTrue(isin_valid("US0378331005"))
        self.assertTrue(isin_valid("US5949181045"))
        self.assertTrue(isin_valid("GB0002634946"))
        self.assertFalse(isin_valid("US0378331006"))
        self.assertFalse(isin_valid("US037833100"))
        raw, positions, exceptions = example()
        result = review_source(raw, positions, exceptions, "a", "b"*64,
                               "2024-11-29", "2024-12-31")
        self.assertEqual(result[0]["review_status"], "structural-us-isin-cusip-candidate")
        self.assertEqual(result[0]["structural_us_isin_cusip_candidate"], "037833100")
        self.assertEqual(result[0]["cusip_as_reported"], "000000000")
        self.assertEqual(result[0]["decision_cut"], "2024-12-31")
        self.assertNotIn("provider_instrument_id", result[0])
        csv_rows = list(csv.DictReader(io.StringIO(csv_output({"positions": result}))))
        self.assertEqual(csv_rows[0]["structural_us_isin_cusip_candidate"], "037833100")

    def test_foreign_valid_isin_not_promoted_to_us_cusip(self):
        raw, positions, exceptions = example("GB0002634946")
        result = review_source(raw, positions, exceptions, "a", "b"*64,
                               "2024-11-29", "2024-12-31")
        self.assertEqual(result[0]["review_status"], "original-non-us-isin-only")
        self.assertIsNone(result[0]["structural_us_isin_cusip_candidate"])

    def test_invalid_and_conflicting_original_isins_are_quarantined(self):
        raw, positions, exceptions = example("US0378331006")
        result = review_source(raw, positions, exceptions, "a", "b"*64,
                               "2024-11-29", "2024-12-31")
        self.assertEqual(result[0]["review_status"], "invalid-original-isin-only")
        xml, positions, exceptions = example("US0378331005",
                                extra='<isin value="US5949181045"/>')
        result = review_source(xml, positions, exceptions, "a", "b"*64,
                               "2024-11-29", "2024-12-31")
        self.assertEqual(result[0]["review_status"], "ambiguous-original-us-isin-cusips")
        self.assertIsNone(result[0]["structural_us_isin_cusip_candidate"])

    def test_other_description_is_literal_and_names_are_never_identifiers(self):
        node = ET.fromstring("""<invstOrSec><name>US0378331005</name>
          <identifiers><other otherDesc="ISIN" value="US0378331005"/>
          <other otherDesc="ticker" value="AAPL"/></identifiers></invstOrSec>""")
        values, tickers = literal_identifiers(node)
        self.assertEqual(values, ["US0378331005"])
        self.assertEqual(tickers, ["AAPL"])
        name_only = ET.fromstring("<invstOrSec><name>US0378331005</name></invstOrSec>")
        self.assertEqual(literal_identifiers(name_only), ([], []))

    def test_rejects_future_filing_modified_original_fields_and_duplicate_exception(self):
        raw, positions, exceptions = example()
        with self.assertRaisesRegex(ValueError, "not public"):
            review_source(raw, positions, exceptions, "a", "b"*64,
                          "2024-12-31", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            review_source(raw.replace(b"<name>Original", b"<name>Other"), positions,
                          exceptions, "a", "b"*64, "2024-11-29", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "position count changed"):
            review_source(raw, positions, exceptions * 2, "a", "b"*64,
                          "2024-11-29", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            review_source(b"<!DOCTYPE x>" + raw, positions, exceptions, "a",
                          "b"*64, "2024-11-29", "2024-12-31")

    def test_real_sec_archive_is_reparsed_and_all_26_reconcile(self):
        result = audit()
        self.assertEqual(result["cut"], "2024-12-31")
        self.assertEqual(result["original_invalid_or_missing_cusip_positions"], 26)
        self.assertAlmostEqual(result["original_spy_weight"], .03033173560207, places=10)
        self.assertEqual(sum(result["review_status_counts"].values()), 26)
        self.assertFalse(result["original_cusip_rewritten"])
        self.assertEqual(result["us_isin_candidates_corroborated_by_independent_source"], 0)
        self.assertEqual(result["full_engine_eligible_cuts"], 0)


if __name__ == "__main__":
    unittest.main()
