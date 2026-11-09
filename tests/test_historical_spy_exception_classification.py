"""Adversarial tests for original SEC asset-category exception classification."""
import csv
import io
import unittest
from scripts.historical_spy_exception_classification import (
    classify_xml, audit, csv_output,
)


def fixture():
    original = [
        {"cusip": "000000000", "weight": .03, "name": "Issuer A",
         "title": "Short-term holding"},
        {"cusip": "037833100", "weight": .97, "name": "Issuer B",
         "title": "Equity"},
    ]
    xml = """<nport>
    <invstOrSec><name>Issuer A</name><title>Short-term holding</title>
      <cusip>000000000</cusip><pctVal>3</pctVal><assetCat>STIV</assetCat>
      <curCd>USD</curCd><payoffProfile>Long</payoffProfile>
      <issuerTyp>CORP</issuerTyp></invstOrSec>
    <invstOrSec><name>Issuer B</name><title>Equity</title>
      <cusip>037833100</cusip><pctVal>97</pctVal><assetCat>EC</assetCat>
      <curCd>USD</curCd><payoffProfile>Long</payoffProfile></invstOrSec>
    </nport>""".encode()
    exceptions = [{"source_position": 0, "cusip_as_reported": "000000000",
                   "reported_spy_weight": .03}]
    return xml, original, exceptions


class SourceAssetReviewTests(unittest.TestCase):
    def test_source_classification_does_not_relabel_instruments_as_stocks(self):
        raw, originals, exceptions = fixture()
        rows = classify_xml(raw, originals, exceptions, "accession-a",
                            "2024-11-29", "2024-12-31")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_asset_category"], "STIV")
        self.assertEqual(rows[0]["review_track"], "other-source-asset-classification-review")
        self.assertEqual(rows[0]["cusip_as_reported"], "000000000")
        self.assertNotIn("provider_instrument_id", rows[0])
        csv_rows = list(csv.DictReader(io.StringIO(csv_output({"positions": rows}))))
        self.assertEqual(len(csv_rows), 1)
        self.assertEqual(csv_rows[0]["source_currency"], "USD")

    def test_equity_like_category_still_requires_independent_identity(self):
        raw, originals, exceptions = fixture()
        modified = raw.replace(b"<assetCat>STIV</assetCat>",
                               b"<assetCat>EC</assetCat>")
        rows = classify_xml(modified, originals, exceptions, "a", "2024-11-29", "2024-12-31")
        self.assertEqual(rows[0]["review_track"], "equity-like-source-identity-review")
        self.assertEqual(rows[0]["cusip_as_reported"], "000000000")

    def test_future_replacement_or_wrong_position_is_rejected(self):
        raw, originals, exceptions = fixture()
        bad = raw.replace(b"<cusip>000000000</cusip>", b"<cusip>037833100</cusip>")
        with self.assertRaisesRegex(ValueError, "identity or weight"):
            classify_xml(bad, originals, exceptions, "a", "2024-11-29", "2024-12-31")
        exceptions[0]["source_position"] = 1
        with self.assertRaisesRegex(ValueError, "exception set changed"):
            classify_xml(raw, originals, exceptions, "a", "2024-11-29", "2024-12-31")

    def test_inflated_weight_duplicate_and_xml_entity_are_rejected(self):
        raw, originals, exceptions = fixture()
        with self.assertRaisesRegex(ValueError, "weight"):
            classify_xml(raw, originals, [{"source_position": 0,
                                           "cusip_as_reported": "000000000",
                                           "reported_spy_weight": .99}],
                         "a", "2024-11-29", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "position count"):
            classify_xml(raw, originals, exceptions * 2, "a", "2024-11-29", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            classify_xml(b"<!DOCTYPE foo>" + raw, originals, exceptions,
                         "a", "2024-11-29", "2024-12-31")

    def test_original_sec_source_exception_categories_reconcile(self):
        result = audit()
        self.assertEqual(result["cut"], "2024-12-31")
        self.assertEqual(result["invalid_or_missing_cusip_positions"], 26)
        self.assertAlmostEqual(result["original_spy_weight"], .03033174, places=7)
        self.assertAlmostEqual(sum(result["asset_category_weight"].values()),
                               result["original_spy_weight"], places=10)
        self.assertFalse(result["historical_equity_universe_certified"])
        self.assertEqual(result["vendor_security_ids_verified"], 0)


if __name__ == "__main__":
    unittest.main()
