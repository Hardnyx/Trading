"""Synthetic inline-XBRL/FSD numeric parity, with ambiguity rejection."""
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.historical_sec_numeric_concordance import (
    SCHEMA, compare, exact_primary_facts, primary_inline_document,
)
from scripts.historical_sec_fsd_intake import extract
from tests.test_historical_sec_fsd_intake import archive, ORIGINAL


def xhtml(*, amount="123.50", segmented=False, extra="", double=False,
          context_start="2023-01-01", context_end="2023-12-31",
          taxonomy="2024", unit="iso4217:USD"):
    seg = ('<xbrli:segment><xbrldi:explicitMember dimension="a:b">X</xbrldi:explicitMember>'
           '</xbrli:segment>') if segmented else ""
    return f'''<html xmlns="http://www.w3.org/1999/xhtml"
     xmlns:xbrli="http://www.xbrl.org/2003/instance"
     xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
     xmlns:us-gaap="http://fasb.org/us-gaap/{taxonomy}"
     xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
     xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
    <xbrli:context id="c"><xbrli:entity><xbrli:identifier>123</xbrli:identifier>
    {seg}</xbrli:entity><xbrli:period>
    <xbrli:startDate>{context_start}</xbrli:startDate><xbrli:endDate>{context_end}</xbrli:endDate>
    </xbrli:period></xbrli:context>
    <xbrli:unit id="usd"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c"
     unitRef="usd">{amount}</ix:nonFraction>
    {('<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="c" unitRef="usd">200.00</ix:nonFraction>' if double else '')}
    {extra}</html>'''.encode()


def complete_filing_with_primary(html):
    return (b"<SEC-DOCUMENT>0000000123-24-000001.txt : 20241110\n"
            b"<SEC-HEADER>\nACCESSION NUMBER:\t0000000123-24-000001\n"
            b"CONFORMED SUBMISSION TYPE:\t10-K\n"
            b"<ACCEPTANCE-DATETIME>20241110130000\n"
            b"FILED AS OF DATE:\t20241110\n"
            b"FILER:\nCENTRAL INDEX KEY:\t123\n</SEC-HEADER>\n"
            b"<DOCUMENT>\n<TYPE>10-K\n<FILENAME>annual.htm\n<TEXT>\n"
            + html + b"\n</TEXT>\n</DOCUMENT>\n"
            b"<DOCUMENT>\n<TYPE>EX-99\n<FILENAME>supplement.htm\n"
            b"<TEXT>\nexhibit</TEXT>\n</DOCUMENT>\n"
            b"</SEC-DOCUMENT>\n")


class SecNumericConcordanceTests(unittest.TestCase):
    def fixture(self, directory, primary=None):
        root = Path(directory)
        zp = archive(root/"2024q4.zip")
        fsd = extract(zp, "2024-12-31T21:00:00Z", ["123"])
        original = root/(ORIGINAL+".txt")
        original.write_bytes(complete_filing_with_primary(
            primary if primary is not None else xhtml()))
        return zp, fsd, original

    def test_exact_decimal_matching_with_original_primary_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path, report, original = self.fixture(directory)
            result = compare(report, original, ORIGINAL, archive_path=archive_path)
            self.assertEqual(result["schema"], SCHEMA)
            self.assertEqual(result["original_primary_filename"], "annual.htm")
            self.assertTrue(result["original_header_matches_derived_fsd"])
            self.assertTrue(result["source_fsd_zip_hash_reverified"])
            self.assertTrue(result["derived_fsd_rows_reproduced_from_original_zip"])
            self.assertEqual(result["comparison_counts"]["exact_match"], 1)
            self.assertEqual(result["selected_derived_rows"], 1)
            self.assertTrue(result["original_primary_sha256"])
            self.assertFalse(result["full_xbrl_document_numeric_fact_set_reconciled"])
            self.assertFalse(result["original_filing_publication_independently_verified"])
            self.assertEqual(result["eligible_full_engine_cuts_added"],0)
            self.assertEqual(result["predictive_validation"],"not-established")

    def test_archive_reextract_rejects_edited_derived_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            zp, report, original = self.fixture(directory)
            changes = (
                ("value_decimal_as_filed", "123.50001"),
                ("ddate", "2023-09-30"),
                ("segments", "ClassOfStock=Preferred;"),
                ("uom", "shares"),
            )
            for key, wrong in changes:
                modified = copy.deepcopy(report)
                modified["facts"][0][key] = wrong
                with self.subTest(key=key), self.assertRaisesRegex(
                        ValueError, "FSD report data differ"):
                    compare(modified, original, ORIGINAL, archive_path=zp)
            without_source = compare(report, original, ORIGINAL)
            self.assertFalse(
                without_source["derived_fsd_rows_reproduced_from_original_zip"])

    def test_sgml_whitespace_before_xml_declaration_is_parse_only(self):
        with tempfile.TemporaryDirectory() as directory:
            xml_header = b" \n<?xml version='1.0' encoding='UTF-8'?>\n"
            raw = xml_header + xhtml()
            zip_path, report, original = self.fixture(directory, raw)
            result = compare(report, original, ORIGINAL, archive_path=zip_path)
            self.assertEqual(result["comparison_counts"]["exact_match"], 1)
            self.assertTrue(result["derived_fsd_rows_reproduced_from_original_zip"])
            self.assertFalse(result["original_filing_publication_independently_verified"])
            original.write_bytes(complete_filing_with_primary(
                b"junk\n" + raw))
            with self.assertRaises(ValueError):
                compare(report, original, ORIGINAL)


    def test_original_sec_xbrl_text_wrapper_is_parse_only(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = b"<?xml version='1.0' encoding='UTF-8'?>\n" + xhtml()
            transport = b"<XBRL>\n" + xml + b"\n</XBRL>"
            original_zip, report, file = self.fixture(directory,transport)
            result = compare(report,file,ORIGINAL,archive_path=original_zip)
            self.assertEqual(result["comparison_counts"]["exact_match"],1)
            self.assertFalse(result["full_xbrl_document_numeric_fact_set_reconciled"])
            self.assertFalse(result["original_filing_publication_independently_verified"])
            self.assertEqual(result["eligible_full_engine_cuts_added"],0)
            file.write_bytes(complete_filing_with_primary(
                b"<XBRL>\n" + xml + b"\n</XML>"))
            with self.assertRaises(ValueError):
                compare(report,file,ORIGINAL)

    def test_minute_only_original_header_is_not_reported_as_exact_match(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory)
            from tests.test_historical_sec_original_filing import complete_filing
            # Keep the original numeric primary and original document identity;
            # only mutate the acceptance second in its SEC-HEADER.
            raw = original.read_bytes().replace(
                b"<ACCEPTANCE-DATETIME>20241110130000",
                b"<ACCEPTANCE-DATETIME>20241110130017")
            original.write_bytes(raw)
            target = next(x for x in report["submissions"] if x["adsh"] == ORIGINAL)
            target["accepted_eastern_as_filed"] += ".0"
            result = compare(report, original, ORIGINAL)
            self.assertFalse(result["original_header_matches_derived_fsd"])
            self.assertTrue(result["original_header_fsd_minute_only_consistent"])
            self.assertEqual(result["comparison_counts"]["exact_match"], 1)
            self.assertEqual(result["eligible_full_engine_cuts_added"], 0)

    def test_decimal_mismatch_and_no_float_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory, xhtml(amount="123.50001"))
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["decimal_mismatch"],1)
            self.assertEqual(result["comparison_counts"]["exact_match"],0)

    def test_segmented_context_never_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory, xhtml(segmented=True))
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["missing_in_original_subset"],1)

    def test_original_conflicts_are_not_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory, xhtml(double=True))
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["ambiguous_original"],1)

    def test_unknown_duration_or_tag_does_not_match(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory, xhtml(
                context_start="2023-10-01"))
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["missing_in_original_subset"],1)
            report["facts"][0]["tag"]="UnsupportedAccountingConcept"
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["unsupported_derived_tag_or_unit"],1)

    def test_ambiguous_primary_and_unsafe_inline_xml_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory)
            original.write_bytes(complete_filing_with_primary(xhtml()).
                                 replace(b"</SEC-DOCUMENT>",
                                   b"<DOCUMENT>\n<TYPE>10-K\n<FILENAME>other.htm\n"
                                   b"<TEXT>\n"+xhtml()+b"\n</TEXT>\n</DOCUMENT>\n"
                                   b"</SEC-DOCUMENT>"))
            with self.assertRaises(ValueError):
                compare(report, original, ORIGINAL)
            original.write_bytes(complete_filing_with_primary(
                b"<!DOCTYPE x><html/>"))
            with self.assertRaises(ValueError):
                compare(report, original, ORIGINAL)
            original.write_bytes(complete_filing_with_primary(b"<html><unclosed>"))
            with self.assertRaises(ValueError):
                compare(report, original, ORIGINAL)

    def test_legacy_missing_segment_column_not_a_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            zp = archive(Path(directory)/"2024q4.zip", segments=False)
            report = extract(zp, "2024-12-31T21:00:00Z", ["123"])
            original = Path(directory)/(ORIGINAL+".txt")
            original.write_bytes(complete_filing_with_primary(xhtml()))
            result = compare(report, original, ORIGINAL)
            self.assertEqual(result["comparison_counts"]["ineligible_derived_dimension"],1)
            self.assertEqual(result["comparison_counts"]["exact_match"],0)

    def test_provenance_mismatch_rejected_before_numeric_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, original = self.fixture(directory)
            bad = copy.deepcopy(report)
            bad["submissions"][0]["form"]="10-Q"
            with self.assertRaises(ValueError):
                compare(bad, original, ORIGINAL)


if __name__=="__main__":
    unittest.main()
