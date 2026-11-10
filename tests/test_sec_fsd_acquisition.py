"""Offline SEC FSD acquisition: original bytes, URL, bounds and failure cleanup."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.sec_fsd_acquisition import acquire, SCHEMA, URL
from tests.test_historical_sec_fsd_intake import archive

AGENT = "Trading Research contact@researchdomain.org"


class Response:
    def __init__(self, req, payload, *, status=200, redirect=False, advertised=None):
        self.status = status
        self.url = req.full_url + "/redirect" if redirect else req.full_url
        self.body = io.BytesIO(payload)
        self.headers = {
            "Content-Length": str(len(payload) if advertised is None else advertised),
            "Date": "Tue, 10 Nov 2026 16:00:00 GMT",
        }

    def read(self, count=-1):
        return self.body.read(count)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.body.close()


class SecFsdAcquisitionTests(unittest.TestCase):
    def test_original_zip_and_immutable_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = archive(root / "2024q4.zip").read_bytes()
            out = root / "out"
            def opener(req, timeout):
                self.assertEqual(req.full_url, URL)
                self.assertEqual(timeout, 120)
                self.assertIn("User-agent", req.headers)
                return Response(req, raw)
            result = acquire(out, user_agent=AGENT, opener=opener,
                             observed_at=datetime(2026, 11, 10, tzinfo=timezone.utc))
            self.assertEqual(result["schema"], SCHEMA)
            self.assertEqual((out/"2024q4.zip").read_bytes(), raw)
            self.assertEqual(json.loads((out/"2024q4.receipt.json").read_text()), result)
            self.assertEqual(result["eligible_full_engine_cuts_added"], 0)
            self.assertFalse(result["original_source_historically_available_verified"])
            with self.assertRaisesRegex(ValueError, "already exists"):
                acquire(out, user_agent=AGENT, opener=opener)

    def test_failed_http_or_corrupt_source_leaves_no_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            raw = archive(root/"2024q4.zip").read_bytes()
            for mode in ("status", "redirect", "length", "html", "truncated"):
                with self.subTest(mode=mode):
                    out = root/mode
                    payload = b"<html>" + b"x"*200 if mode == "html" else (
                        raw[:200] if mode == "truncated" else raw)
                    def opener(req, timeout):
                        return Response(req, payload,
                            status=403 if mode == "status" else 200,
                            redirect=mode == "redirect",
                            advertised=len(payload)+1 if mode == "length" else None)
                    with self.assertRaises((ValueError, OSError)):
                        acquire(out, user_agent=AGENT, opener=opener)
                    self.assertFalse((out/"2024q4.zip").exists())
                    self.assertFalse((out/"2024q4.receipt.json").exists())

    def test_pinned_quarter_and_real_contact_required(self):
        with tempfile.TemporaryDirectory() as d:
            def unused(req, timeout):
                self.fail("Unexpected outbound request")
            for q in ("2024q3", "2025q1", "../../secret"):
                with self.subTest(q=q), self.assertRaises(ValueError):
                    acquire(d, quarter=q, user_agent=AGENT, opener=unused)
            with self.assertRaises(ValueError):
                acquire(d, user_agent="bot", opener=unused)

    def test_zip_without_sub_num_does_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            stream = io.BytesIO()
            with ZipFile(stream, "w") as z:
                z.writestr("other.txt", "x"*200)
            with self.assertRaisesRegex(ValueError, "SUB and NUM"):
                acquire(Path(d)/"out", user_agent=AGENT,
                        opener=lambda req, timeout: Response(req, stream.getvalue()))


if __name__ == "__main__":
    unittest.main()
