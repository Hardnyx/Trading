"""Reject symbol-only SEC/N-PORT identity promotion; retain equity class."""
import copy
import hashlib
import unittest

from scripts.sec_first_cut_equity_bridge import registered_securities, bridge
from tests.test_historical_sec_numeric_concordance import complete_filing_with_primary
from scripts.historical_vendor_identity import valid_cusip

def xml(*, extra_equity=False, header=True):
    th = ('<tr><th>Title of each class</th><th>Trading Symbol</th>'
          '<th>Name of exchange on which registered</th></tr>' if header else '')
    more = ('<tr><td>Common stock class B</td><td>MSFT</td>'
            '<td>NASDAQ</td></tr>' if extra_equity else '')
    return ('''<html><body><table>''' + th +
       '''<tr><td>Common stock, $0.00000625 par value per share</td>
          <td>MSFT</td><td>NASDAQ</td></tr>
          <tr><td>3.125% Notes due 2028</td><td>MSFT</td><td>NASDAQ</td></tr>
          <tr><td>2.625% Notes due 2033</td><td>MSFT</td><td>NASDAQ</td></tr>'''
          + more + '</table></body></html>').encode()

def filing(primary):
    return complete_filing_with_primary(primary).replace(
        b"0000000123-24-000001", b"0000950170-24-118967"
    ).replace(b"<TYPE>10-K", b"<TYPE>10-Q"
    ).replace(b"<FILENAME>annual.htm", b"<FILENAME>msft-20240930.htm"
    ).replace(b"CENTRAL INDEX KEY:\t123", b"CENTRAL INDEX KEY:\t789019"
    ).replace(b"<ACCEPTANCE-DATETIME>20241110130000",
              b"<ACCEPTANCE-DATETIME>20241030160717"
    ).replace(b"FILED AS OF DATE:\t20241110",
              b"FILED AS OF DATE:\t20241030")

def evidence(raw):
    obs = {
      "cut": "2024-12-31T21:00:00Z",
      "source_provenance": {"original_edgar_filing": {
        "accession": "0000950170-24-118967", "cik": "789019",
        "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}},
      "accepted_eastern": {"original_edgar_header": "2024-10-30 16:07:17"}
    }
    req = {
      "cut": "2024-12-31", "spy_original_accession": "0001752724-24-000001",
      "spy_original_sha256": "a"*64,
      "source_market_commit": "b"*40,
      "source_manifest_sha256": "c"*64,
      "identifier_manifest_sha256": "d"*64,
      "identifier_archive_sha256": "e"*64,
      "counts": {"positive_positions":1},
      "requests": [{
        "source_position": 0, "cusip": "594918104",
        "weight":0.06, "original_spy_name": "MICROSOFT CORP",
        "original_ticker_observation":"MSFT",
        "ticker_receipts": [{"fund":"IVV","accession":"0001752724-24-000001",
                "available_after_day":"2024-11-01","original_sha256":"f"*64}],
        "vendor_instrument_id": None, "vendor_price_series_verified": False,
        "original_price_vintage_verified": False, "production_eligible":False,
      }],
      "full_engine_replay_ready":False, "production_eligible":False
    }
    return req,obs

class EquityBridgeTests(unittest.TestCase):
    def test_original_security_table_is_class_aware(self):
        registrations = registered_securities(
            b"<XBRL>\n" + b"<?xml version='1.0'?>\n" +
            xml() + b"\n</XBRL>\n")
        self.assertEqual(len(registrations),3)
        self.assertEqual(registrations[0]["security_class"],"common-stock")
        self.assertEqual(sum(x["trading_symbol_as_filed"]=="MSFT"
                             for x in registrations),3)

    def test_one_original_source_candidate_does_not_promote_price_identity(self):
        raw=filing(b"<XBRL>\n"+b"<?xml version='1.0'?>\n"+
                   xml()+b"\n</XBRL>\n")
        req,obs=evidence(raw)
        result=bridge(raw,req,obs)
        self.assertEqual(result["issuer_cik_as_filed"],"789019")
        self.assertEqual(result["spy_cusip_as_filed"],"594918104")
        self.assertTrue(valid_cusip(result["spy_cusip_as_filed"]))
        self.assertTrue(result["ticker_not_a_unique_security_identifier"])
        self.assertEqual(len(result["other_registration_classes_with_same_symbol"]),2)
        self.assertFalse(result["independent_historical_cik_to_cusip_permanent_mapping_verified"])
        self.assertIsNone(result["vendor_instrument_id"])
        self.assertEqual(result["eligible_full_engine_cuts_added"],0)

    def test_actual_dated_spy_source_contains_unique_msft_ticker_candidate(self):
        from scripts.historical_identity_requests import build_requests
        source = build_requests()
        observations = [
            row for row in source["requests"]
            if row["original_ticker_observation"] == "MSFT"
        ]
        self.assertEqual(source["cut"], "2024-12-31")
        self.assertEqual(len(observations), 1)
        position = observations[0]
        self.assertTrue(valid_cusip(position["cusip"]))
        self.assertTrue(position["ticker_receipts"])
        self.assertTrue(all(receipt["available_after_day"] < source["cut"]
                            for receipt in position["ticker_receipts"]))
        self.assertIsNone(position["vendor_instrument_id"])
        self.assertFalse(position["vendor_price_series_verified"])

    def test_ambiguous_stale_or_tampered_evidence_is_rejected(self):
        original=filing(b"<XBRL>\n"+b"<?xml version='1.0'?>\n"+
                        xml()+b"\n</XBRL>\n")
        for mode in ("multiple_equity", "missing_headers", "wrong_hash",
                     "future_ticker", "future_cut", "two_positions", "vendor_id",
                     "missing_receipt", "wrong_cusip"):
            with self.subTest(mode=mode):
                raw=original
                req,obs=evidence(raw)
                if mode == "multiple_equity":
                    raw=filing(b"<XBRL>\n<?xml version='1.0'?>\n"+
                               xml(extra_equity=True)+b"\n</XBRL>\n")
                    req,obs=evidence(raw)
                elif mode == "missing_headers":
                    raw=filing(xml(header=False))
                    req,obs=evidence(raw)
                elif mode == "wrong_hash":
                    obs["source_provenance"]["original_edgar_filing"]["sha256"]="0"*64
                elif mode == "future_ticker":
                    req["requests"][0]["ticker_receipts"][0]["available_after_day"]="2025-01-01"
                elif mode == "future_cut":
                    req["cut"]="2024-10-01"
                elif mode == "two_positions":
                    req["requests"].append(copy.deepcopy(req["requests"][0]))
                    req["requests"][1]["source_position"]=1
                    req["counts"]["positive_positions"]=2
                elif mode == "vendor_id":
                    req["requests"][0]["vendor_instrument_id"]="provider-1"
                elif mode == "missing_receipt":
                    req["requests"][0]["ticker_receipts"]=[]
                else:
                    req["requests"][0]["cusip"]="594918105"
                with self.assertRaises(ValueError):
                    bridge(raw,req,obs)

if __name__ == "__main__":
    unittest.main()
