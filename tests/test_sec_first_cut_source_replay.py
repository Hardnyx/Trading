"""Synthetic source-integrity tests: restore must not trust cache identity."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.sec_first_cut_source_replay import audit, SCHEMA
from tests.test_historical_sec_fsd_intake import archive, ORIGINAL
from tests.test_historical_sec_original_filing import complete_filing


class SecFirstCutSourceReplayTests(unittest.TestCase):
    def fixture(self, base):
        base = Path(base)
        zpath = archive(base / "2024q4.zip")
        opath = base / (ORIGINAL + ".txt")
        opath.write_bytes(complete_filing())
        fsd, edgar = zpath.read_bytes(), opath.read_bytes()
        reference = {
            "schema": "sec-first-cut-original-source-observation-v1",
            "sample_role": "previously-inspected-retrospective-development",
            "cut": "2024-12-31T21:00:00Z",
            "eligible_full_engine_cuts_added": 0,
            "confirmatory_origins_added": 0,
            "predictive_validation": "not-established",
            "source_provenance": {
                "original_fsd_zip": {
                    "sha256": hashlib.sha256(fsd).hexdigest(),
                    "bytes": len(fsd),
                    "url": "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip",
                },
                "original_edgar_filing": {
                    "sha256": hashlib.sha256(edgar).hexdigest(),
                    "bytes": len(edgar),
                    "accession": ORIGINAL,
                    "cik": "123",
                    "url": "https://www.sec.gov/Archives/edgar/data/123/" +
                           ORIGINAL.replace("-", "") + "/" + ORIGINAL + ".txt",
                },
            },
            "accepted_eastern": {
                "original_edgar_header": "2024-11-10 13:00:00",
            },
        }
        fsd_receipt = base / "2024q4.receipt.json"
        original_receipt = base / (ORIGINAL + ".receipt.json")
        fsd_receipt.write_text(json.dumps({
            "schema": "sec-first-cut-fsd-acquisition-receipt-v1",
            "source_url": reference["source_provenance"]["original_fsd_zip"]["url"],
            "zip_sha256": reference["source_provenance"]["original_fsd_zip"]["sha256"],
            "zip_bytes": len(fsd),
            "members_present": ["num.txt", "sub.txt"],
            "original_source_historically_available_verified": False,
            "original_filing_publication_independently_verified": False,
            "eligible_full_engine_cuts_added": 0,
            "confirmatory_origins_added": 0,
            "predictive_validation": "not-established",
        }))
        original_receipt.write_text(json.dumps({
            "schema": "historical-sec-original-acquisition-receipt-v1",
            "source_url": reference["source_provenance"]["original_edgar_filing"]["url"],
            "original_sha256": reference["source_provenance"]["original_edgar_filing"]["sha256"],
            "original_bytes": len(edgar),
            "accession": ORIGINAL,
            "cik": "123",
            "indexed_bytes_match": True,
            "original_header_matches_official_index_lead": True,
            "first_publication_independently_verified": False,
            "numeric_xbrl_facts_reconciled": False,
            "eligible_full_engine_cuts_added": 0,
            "confirmatory_origins_added": 0,
            "predictive_validation": "not-established",
        }))
        return [zpath, opath, fsd_receipt, original_receipt, reference]

    def test_exact_source_bytes_and_receipts_required_for_cache_replay(self):
        with tempfile.TemporaryDirectory() as d:
            bundle = self.fixture(d)
            result = audit(*bundle)
            self.assertEqual(result["schema"], SCHEMA)
            self.assertTrue(result["sec_header_identity_and_acceptance_reverified"])
            self.assertFalse(result["historical_point_in_time_eligibility_verified"])
            self.assertEqual(result["eligible_full_engine_cuts_added"], 0)

    def test_cache_tampering_rejected_before_extraction(self):
        for mode in ("zip", "original", "receipt_hash", "receipt_cert",
                     "header", "eligibility", "structure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                inputs = self.fixture(d)
                if mode == "zip":
                    inputs[0].write_bytes(b"corrupted")
                elif mode == "original":
                    inputs[1].write_bytes(b"altered")
                elif mode == "receipt_hash":
                    receipt = json.loads(inputs[2].read_text())
                    receipt["zip_sha256"] = "0" * 64
                    inputs[2].write_text(json.dumps(receipt))
                elif mode == "receipt_cert":
                    receipt = json.loads(inputs[3].read_text())
                    receipt["first_publication_independently_verified"] = True
                    inputs[3].write_text(json.dumps(receipt))
                elif mode == "header":
                    inputs[4]["accepted_eastern"]["original_edgar_header"] = (
                        "2024-11-10 13:00:01")
                elif mode == "eligibility":
                    inputs[4]["eligible_full_engine_cuts_added"] = 1
                else:
                    receipt = json.loads(inputs[2].read_text())
                    receipt["members_present"] = ["sub.txt", "num.txt", "fake.txt"]
                    inputs[2].write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    audit(*inputs)


    def test_manual_cache_key_is_bound_to_both_source_digests(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/sec-first-cut-source.yml").read_text()
        observed = json.loads((root /
            "data/historical/sec-first-cut-original-source-observation-v1.json").read_text())
        sources = observed["source_provenance"]
        fsd = sources["original_fsd_zip"]["sha256"]
        edgar = sources["original_edgar_filing"]["sha256"]
        key = "sec-first-cut-originals-v1-" + fsd + "-" + edgar
        self.assertEqual(workflow.count("          key: " + key), 2)
        self.assertEqual(workflow.count("uses: actions/cache/restore@v4"), 1)
        self.assertEqual(workflow.count("uses: actions/cache/save@v4"), 1)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertNotIn("  schedule:", workflow)
        restored = workflow.index("uses: actions/cache/restore@v4")
        verified = workflow.index("id: source_integrity")
        saved = workflow.index("uses: actions/cache/save@v4")
        extracted = workflow.index("id: fsd_extraction")
        self.assertTrue(restored < verified < saved < extracted)
        self.assertIn(
            "steps.source_integrity.outcome == 'success'",
            workflow.split("uses: actions/cache/save@v4", 1)[0])
        self.assertIn("python scripts/sec_first_cut_source_replay.py",
                      workflow)
        published = workflow.split(
            "- name: Preserve research receipts without raw original archives", 1)[1]
        self.assertNotIn("2024q4.zip", published)
        self.assertNotIn("0000950170-24-118967.txt", published)



if __name__ == "__main__":
    unittest.main()
