"""Fail-closed SEC Form 13F historical source and CUSIP/class reconciliation."""
import gzip
import hashlib
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.historical_independent_13f import (
    ACCESSION, CIK, FIRST_PUBLISHED, SCHEMA, URL, archived,
    acquire, compare, parse_table, source_payload, validate_archive,
    validate_complete_original,
)


def row(cusip, name="TEST CORP", title="COM", unit="SH", option=""):
    opt = f"<putCall>{option}</putCall>" if option else ""
    return (f"<infoTable><nameOfIssuer>{name}</nameOfIssuer>"
            f"<titleOfClass>{title}</titleOfClass><cusip>{cusip}</cusip>"
            f"<value>10</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>"
            f"<sshPrnamtType>{unit}</sshPrnamtType></shrsOrPrnAmt>{opt}"
            f"</infoTable>")


def table(*rows):
    return ('<?xml version="1.0"?><informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">' + ''.join(rows) + '</informationTable>').encode()


def spy():
    return {"total_positive_sec_positions":504,"valid_original_cusip_positions":478,
            "permanent_security_identity_certified":False,"full_engine_eligible_cuts_added":0,
            "cut":"2024-12-31", "position_rows":[
                {"source_position":i,"cusip":"594918104" if i==0 else "037833100",
                 "original_spy_name":"Microsoft" if i==0 else "Issuer", "weight":1/478}
                for i in range(478)]}


def original():
    return {"accession":ACCESSION,"accepted_utc":FIRST_PUBLISHED,
            "raw_sha256":"a"*64,"raw_byte_count":200}


class Original13fTests(unittest.TestCase):
    def test_original_xml_class_and_share_unit_only(self):
        parsed=parse_table(table(row("594918104"),row("037833100",unit="PRN"),row("594918104",option="CALL")))
        self.assertEqual(len(parsed),3)
        result=compare(parsed,spy(),original())
        self.assertEqual(result["status_counts"]["independent-13f-cusip-and-class-observed"],1)
        self.assertEqual(result["status_counts"]["no-independent-original-13f-shares"],477)
        self.assertEqual(result["full_engine_eligible_cuts_added"],0)
        self.assertFalse(result["vendor_historical_security_master_certified"])

    def test_reject_13f_evidence_for_an_earlier_spy_cut(self):
        changed = spy()
        changed["cut"] = "2024-10-31"
        with self.assertRaisesRegex(ValueError, "denominator/eligibility"):
            compare(parse_table(table(row("594918104"))), changed, original())

    def test_original_holdings_period_must_match_frozen_quarter(self):
        filing = {**original(), "cik": CIK, "form": "13F-HR",
                  "filed": "20241113"}
        def document(period):
            return (b"<SEC-DOCUMENT>\\n<SEC-HEADER>\\n"
                    + b"CONFORMED PERIOD OF REPORT: " + period
                    + b"\\n</SEC-HEADER>\\n")
        with patch("scripts.historical_independent_13f.parse_original",
                   return_value=filing), \\
             patch("scripts.historical_independent_13f.source_payload",
                   return_value=table(row("594918104"))):
            _, parsed = validate_complete_original(document(b"20240930"))
            self.assertEqual(len(parsed), 1)
            for period in (b"20241231", b"", b"20240930\\nCONFORMED PERIOD OF REPORT: 20240930"):
                with self.subTest(period=period), self.assertRaisesRegex(
                        ValueError, "holdings period"):
                    validate_complete_original(document(period))

    def test_recollection_uses_pinned_original_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = Path(tmp) / "original.gz"
            receipt = Path(tmp) / "receipt.json"
            saved.write_bytes(b"already archived")
            receipt.write_text("{}")
            with patch("scripts.historical_independent_13f.ORIGINAL", saved), \\
                 patch("scripts.historical_independent_13f.RECEIPT", receipt), \\
                 patch("scripts.historical_independent_13f.archived",
                       return_value=(original(), [])), \\
                 patch("scripts.historical_independent_13f.spy_review", return_value=spy()), \\
                 patch("scripts.historical_independent_13f.get_original",
                       side_effect=AssertionError("Unexpected redownload")):
                report = acquire(user_agent=None)
            self.assertEqual(report["full_engine_eligible_cuts_added"], 0)

    def test_conflicting_class_is_not_selected(self):
        source=parse_table(table(row("594918104",title="COM"),row("594918104",title="CL A")))
        result=compare(source,spy(),original())
        self.assertEqual(result["status_counts"]["ambiguous-independent-13f-issuer-or-class"],1)

    def test_reject_unsafe_and_broken_xml(self):
        for source in (b'<!DOCTYPE informationTable><informationTable/>',b'<broken/>',table(row('594918104',title=''))):
            with self.subTest(source=source[:35]), self.assertRaises(ValueError):
                parse_table(source)

    def test_reject_13f_with_no_valid_sec_information_table(self):
        source=(b'<SEC-DOCUMENT>ignored\n<SEC-HEADER>header</SEC-HEADER>\n'
                b'<DOCUMENT>\n<TYPE>13F-HR\n<FILENAME>file.xml\n<TEXT>\n<XML>\n<?xml version="1.0"?>\n</XML>\n</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>')
        with self.assertRaisesRegex(ValueError,"information table missing"):
            source_payload(source)

    def test_archive_digest_and_provenance_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/"data/historical/independent-13f-v1"
            base.mkdir(parents=True)
            raw=b"test original bytes"*7
            gz=gzip.compress(raw,mtime=0)
            (base/(ACCESSION+".txt.gz")).write_bytes(gz)
            (base/"receipt.json").write_text(json.dumps({"archive_sha256":hashlib.sha256(gz).hexdigest(),
                "schema":SCHEMA,"source_url":URL,"original_13f_accession":ACCESSION,
                "original_sha256":hashlib.sha256(raw).hexdigest(),
                "original_byte_count":len(raw),
                "original_13f_accepted_utc":FIRST_PUBLISHED,
                "first_publication_independently_authenticated":False,
                "predictive_validation":"not-established",
                "full_engine_eligible_cuts_added":0}))
            with patch('scripts.historical_independent_13f.validate_complete_original',return_value=(original(),[{}])):
                x,y=archived(tmp)
                self.assertEqual(x["accession"],ACCESSION)
                self.assertEqual(len(y),1)
            intact = json.loads((base/"receipt.json").read_text())
            for key, altered in (("original_13f_accepted_utc", "2024-12-31T21:00:00+00:00"),
                                 ("first_publication_independently_authenticated", True),
                                 ("predictive_validation", "validated")):
                changed = dict(intact)
                changed[key] = altered
                (base/"receipt.json").write_text(json.dumps(changed))
                with self.subTest(field=key), self.assertRaisesRegex(
                        ValueError, "receipt differs"):
                    archived(tmp)
            (base/"receipt.json").write_text('{"archive_sha256":"bad"}')
            with self.assertRaisesRegex(ValueError,"compressed archive changed"):
                archived(tmp)

    def test_real_archive_when_present_remains_research_only(self):
        base=Path(__file__).resolve().parents[1]/"data/historical/independent-13f-v1"
        if not (base/"receipt.json").is_file():
            self.skipTest("Independent 13F original not yet acquired")
        original_file,rows=archived()
        from scripts.historical_spy_issuer_lei import review
        result=compare(rows,review(),original_file)
        self.assertEqual(result["spy_valid_cusip_positions"],478)
        self.assertFalse(result["vendor_historical_security_master_certified"])
        self.assertEqual(result["full_engine_eligible_cuts_added"],0)


if __name__=="__main__": unittest.main()
