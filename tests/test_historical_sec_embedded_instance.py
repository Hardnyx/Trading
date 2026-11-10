"""Synthetic original SEC accession with an embedded extracted XBRL instance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_sec_embedded_instance import (
    embedded_instance, instance_facts, compare, SCHEMA,
)
from scripts.historical_sec_fsd_intake import extract
from tests.test_historical_sec_fsd_intake import archive, ORIGINAL
from tests.test_historical_sec_numeric_concordance import (
    xhtml, complete_filing_with_primary,
)


def xbrl(*, amount="123.50", cik="123", segment=False, duplicate=None,
         namespace="http://fasb.org/us-gaap/2024"):
    dimension = ('<xbrli:segment><xbrldi:explicitMember dimension="a:b">'
                 'X</xbrldi:explicitMember></xbrli:segment>') if segment else ''
    extra = (f'<us-gaap:NetIncomeLoss contextRef="c" unitRef="usd">'
             f'{duplicate}</us-gaap:NetIncomeLoss>') if duplicate is not None else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:us-gaap="{namespace}"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
 <xbrli:context id="c"><xbrli:entity>
  <xbrli:identifier>{cik}</xbrli:identifier>{dimension}
 </xbrli:entity><xbrli:period>
  <xbrli:startDate>2023-01-01</xbrli:startDate>
  <xbrli:endDate>2023-12-31</xbrli:endDate>
 </xbrli:period></xbrli:context>
 <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <us-gaap:NetIncomeLoss contextRef="c" unitRef="usd">{amount}</us-gaap:NetIncomeLoss>
 {extra}
</xbrli:xbrl>'''.encode()


def filing_with_instance(instance, *, filename="original.xml",
                         kind="XML", duplicate=False):
    attachment = (b"<DOCUMENT>\n<TYPE>" + kind.encode()
                  + b"\n<FILENAME>" + filename.encode()
                  + b"\n<TEXT>\n" + instance
                  + b"\n</TEXT>\n</DOCUMENT>\n")
    raw = complete_filing_with_primary(xhtml())
    tail = b"</SEC-DOCUMENT>\n"
    assert raw.endswith(tail)
    return (raw[:-len(tail)] + attachment +
            (attachment if duplicate else b"") + tail)


class EmbeddedInstanceTests(unittest.TestCase):
    def fixture(self, directory, instance=None, *, raw=None):
        root = Path(directory)
        archive_path = archive(root / "2024q4.zip")
        report = extract(archive_path, "2024-12-31T21:00:00Z", ["123"])
        file = root / (ORIGINAL + ".txt")
        file.write_bytes(raw if raw is not None else
                         filing_with_instance(xbrl() if instance is None else instance))
        return archive_path, report, file

    def test_original_attachment_matches_only_selected_consolidated_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            source, report, path = self.fixture(directory)
            result = compare(report, path, ORIGINAL, archive_path=source)
            self.assertEqual(result["schema"], SCHEMA)
            self.assertTrue(result["source_fsd_archive_bytes_reverified"])
            self.assertTrue(result["embedded_instance_found_in_same_original_submission"])
            self.assertEqual(result["comparison_counts"]["exact_literal_match"], 1)
            self.assertEqual(result["selected_rows"], 1)
            self.assertFalse(result["original_primary_inline_document_numeric_facts_reconciled"])
            self.assertFalse(result["original_first_publication_independently_verified"])
            self.assertEqual(result["eligible_full_engine_cuts_added"], 0)
            self.assertEqual(result["confirmatory_origins_added"], 0)

    def test_different_numeric_values_and_duplicate_contexts_never_cherry_picked(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, path = self.fixture(directory, xbrl(amount="125"))
            self.assertEqual(compare(report, path, ORIGINAL)
                             ["comparison_counts"]["decimal_mismatch"], 1)
            path.write_bytes(filing_with_instance(xbrl(duplicate="125")))
            self.assertEqual(compare(report, path, ORIGINAL)
                             ["comparison_counts"]["ambiguous_instance"], 1)
            path.write_bytes(filing_with_instance(xbrl(segment=True)))
            self.assertEqual(compare(report, path, ORIGINAL)
                             ["comparison_counts"]["missing_in_embedded_instance"], 1)
            path.write_bytes(filing_with_instance(xbrl(cik="456")))
            self.assertEqual(compare(report, path, ORIGINAL)
                             ["comparison_counts"]["missing_in_embedded_instance"], 1)

    def test_missing_duplicate_or_mislabeled_attachment_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            _, report, path = self.fixture(directory)
            for raw in (complete_filing_with_primary(xhtml()),
                        filing_with_instance(xbrl(), filename="other.xml"),
                        filing_with_instance(xbrl(), duplicate=True),
                        filing_with_instance(xbrl(), kind="EX-99")):
                with self.subTest(raw_prefix=raw[-85:]), self.assertRaises(ValueError):
                    path.write_bytes(raw)
                    compare(report, path, ORIGINAL)

    def test_original_zip_modification_and_unsafe_xml_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, report, path = self.fixture(directory)
            tampered = copy.deepcopy(report)
            tampered["facts"][0]["value_decimal_as_filed"] = "0"
            with self.assertRaisesRegex(ValueError, "FSD rows differ"):
                compare(tampered, path, ORIGINAL, archive_path=source)
            path.write_bytes(filing_with_instance(
                b"<!DOCTYPE x><xbrli:xbrl someAttribute=\"very-long-value\"/>"))
            with self.assertRaisesRegex(ValueError, "DTD"):
                compare(report, path, ORIGINAL)
            path.write_bytes(filing_with_instance(
                b"<?xml version='1.0'?><broken>" + b"x"*60))
            with self.assertRaisesRegex(ValueError, "not well-formed"):
                compare(report, path, ORIGINAL)
            path.write_bytes(filing_with_instance(xbrl(namespace="http://evil.example")))
            self.assertEqual(compare(report, path, ORIGINAL)
                             ["comparison_counts"]["missing_in_embedded_instance"], 1)


if __name__ == "__main__":
    unittest.main()
