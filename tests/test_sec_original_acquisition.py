"""Stubbed SEC HTTP acquisition; no external downloads in CI."""
import copy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.sec_original_acquisition import (
    SCHEMA, acquire, get_original, select_lead, validate_agent,
)
from tests.test_historical_sec_original_filing import complete_filing, ORIGINAL


def lead_for_test():
    raw = complete_filing()
    return raw, {
        "schema": "historical-sec-first-cut-original-source-leads-v1",
        "eligible_full_engine_cuts_added": 0,
        "predictive_validation": "not-established",
        "sources": [{
            "accession": ORIGINAL,
            "cik": "123",
            "form": "10-K",
            "filed_date": "2024-11-10",
            "accepted_eastern": "2024-11-10 13:00:00",
            "index_url": ("https://www.sec.gov/Archives/edgar/data/"
                          "123/000000012324000001/"+ORIGINAL+"-index.html"),
            "full_submission_url": ("https://www.sec.gov/Archives/edgar/data/"
                                    "123/000000012324000001/"+ORIGINAL+".txt"),
            "original_full_submission_sha256": None,
            "original_full_submission_bytes_obtained": False,
            "first_publication_independently_verified": False,
            "full_submission_size_bytes_reported_in_index": len(raw),
        }],
    }


class Response:
    status = 200
    def __init__(self, request, body, *, url=None, status=200, size=None):
        self.status = status
        self._url = url or request.full_url
        self.raw = io.BytesIO(body)
        self.headers = {
            "Content-Length": str(len(body) if size is None else size),
            "Content-Type": "text/plain",
            "Date": "Mon, 09 Nov 2026 21:00:00 GMT",
        }
    def read(self, size=-1): return self.raw.read(size)
    def geturl(self): return self._url
    def __enter__(self): return self
    def __exit__(self, *args): self.raw.close()


class SecOriginalAcquisitionTests(unittest.TestCase):
    AGENT = "Trading research contact@researchdomain.org"

    def test_valid_acquisition_preserves_first_published_uncertainty(self):
        raw, lead = lead_for_test()
        with tempfile.TemporaryDirectory() as d:
            out = acquire(lead, ORIGINAL, d, user_agent=self.AGENT,
                opener=lambda req,timeout: Response(req,raw),
                observed_at=datetime(2026,11,9,tzinfo=timezone.utc))
            self.assertEqual(out["schema"], SCHEMA)
            self.assertTrue(out["indexed_bytes_match"])
            self.assertTrue(out["original_header_matches_official_index_lead"])
            self.assertFalse(out["first_publication_independently_verified"])
            self.assertFalse(out["numeric_xbrl_facts_reconciled"])
            self.assertEqual(out["eligible_full_engine_cuts_added"],0)
            self.assertEqual((Path(d)/(ORIGINAL+".txt")).read_bytes(),raw)
            self.assertEqual(json.loads(
                (Path(d)/(ORIGINAL+".receipt.json")).read_text()),out)
            with self.assertRaises(ValueError):
                acquire(lead, ORIGINAL, d, user_agent=self.AGENT,
                        opener=lambda req,timeout: Response(req,raw))

    def test_reject_bad_status_redirect_and_wrong_length(self):
        raw, lead = lead_for_test()
        url = lead["sources"][0]["full_submission_url"]
        for mode in ("status","redirect","size","html"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                def opener(req,timeout):
                    return Response(req,b"<html>Forbidden</html>" if mode=="html"
                        else raw,
                        status=403 if mode=="status" else 200,
                        url=url+"/redirect" if mode=="redirect" else url,
                        size=len(raw)+1 if mode=="size" else None)
                with self.assertRaises(ValueError):
                    acquire(lead, ORIGINAL, d,user_agent=self.AGENT,opener=opener)
                self.assertEqual(list(Path(d).iterdir()),[])

    def test_reject_wrong_header_and_wrong_indexed_size(self):
        raw, lead = lead_for_test()
        for mode in ("form", "index"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                local = copy.deepcopy(lead)
                if mode=="index":
                    local["sources"][0]["full_submission_size_bytes_reported_in_index"] += 1
                wrong = raw.replace(b"CONFORMED SUBMISSION TYPE:\t10-K",
                                    b"CONFORMED SUBMISSION TYPE:\t10-Q")
                with self.assertRaises(ValueError):
                    acquire(local, ORIGINAL, d, user_agent=self.AGENT,
                        opener=lambda req,timeout: Response(req,
                            wrong if mode=="form" else raw))
                self.assertEqual(list(Path(d).iterdir()),[])

    def test_allowlist_and_user_agent_are_mandatory(self):
        raw, lead = lead_for_test()
        self.assertEqual(select_lead(lead,ORIGINAL)["cik"],"123")
        for agent in (None,"bot","Trading test@example.com","\nroot@host.org"):
            with self.subTest(agent=agent), self.assertRaises(ValueError):
                validate_agent(agent)
        with self.assertRaises(ValueError):
            get_original("https://evil.example/filing.txt",user_agent=self.AGENT,
                         opener=lambda req,timeout: Response(req,raw))
        bad = copy.deepcopy(lead)
        bad["sources"][0]["full_submission_url"] = "https://hostile.invalid/thing"
        with self.assertRaises(ValueError):
            select_lead(bad,ORIGINAL)


if __name__=="__main__":
    unittest.main()
