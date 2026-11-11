"""Synthetic, offline mutation tests of Bloomberg v4 original-byte receipts."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.historical_bloomberg_warehouse_receipt import (
    canonical, pointer, sha256, verify_stage,
)


class WarehouseReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "raw").mkdir()
        self.db = sqlite3.connect(self.root / "warehouse.sqlite3")
        self.db.executescript("""
            CREATE TABLE raw_sources(raw_hash TEXT PRIMARY KEY,path TEXT,
                request_json TEXT,retrieved_at TEXT,synthetic INTEGER);
            CREATE TABLE pit_records(record_id TEXT PRIMARY KEY,record_json TEXT,
                raw_hash TEXT,quality_class TEXT,synthetic INTEGER,retrieved_at TEXT);
        """)
        self.retrieved = "2026-11-10T00:00:00Z"
        self.published = "2024-12-31T21:00:00Z"
        original = {"price": 421.2, "published": self.published, "available": self.published}
        self.original_hash = self.archive(original)
        self.row = {
            "dataset_id": "daily_prices", "security_id": "VENDOR-ID-1", "field": "close",
            "value": 421.2, "observation_date": "2024-12-31", "period_end": None,
            "published_at": self.published, "first_available_at": self.published,
            "source_document_id": "PROVIDER-ORIGINAL", "vintage_id": "v1",
            "source_id": "offline-original", "request_id": "one", "valid_from": None,
            "valid_until": None, "unit": "USD/share", "currency": "USD",
            "adjusted_basis": "unadjusted-causal", "quality_class": "VERIFIED_PIT",
            "synthetic": False, "retrieved_at": self.retrieved,
            "evidence": {
                "semantics_verified": True, "value_locator": "/records/0/value",
                "availability_basis": "original-dated-provider",
                "availability_source": "local-original",
                "original_document_sha256": self.original_hash,
                "original_value_pointer": "/price",
                "original_publication_pointer": "/published",
                "original_availability_pointer": "/available",
            },
        }
        interchange = {
            "schema": "pit-source-document-v1", "synthetic": False,
            "retrieved_at": self.retrieved,
            "records": [{k: v for k, v in self.row.items() if k not in ("raw_hash", "retrieved_at", "synthetic")}],
        }
        self.interchange_hash = self.archive(interchange)
        self.row["raw_hash"] = self.interchange_hash
        self.stage = {"schema": "bloomberg-trading-stage-v1",
                      "source_hashes": [self.interchange_hash],
                      "normalized_asof_records": [copy.deepcopy(self.row)]}
        self.db.execute("INSERT INTO pit_records VALUES(?,?,?,?,?,?)",
                        (sha256(canonical(self.row)), canonical(self.row).decode(),
                         self.interchange_hash, "VERIFIED_PIT", 0, self.retrieved))
        self.db.commit()

    def archive(self, data):
        raw = canonical(data)
        digest = hashlib.sha256(raw).hexdigest()
        path = self.root / "raw" / (digest + ".json")
        path.write_bytes(raw)
        self.db.execute("INSERT INTO raw_sources VALUES(?,?,?,?,?)",
                        (digest, str(path.resolve()), "{}", self.retrieved, 0))
        return digest

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_both_archive_layers_and_original_pointers_reopened(self):
        result = verify_stage(self.stage, self.root)
        self.assertEqual(result["warehouse_stage_records_verified"], 1)
        self.assertEqual(result["warehouse_source_files_reopened"], 2)
        self.assertEqual(result["warehouse_original_documents_reopened"], 1)
        self.assertTrue(result["original_value_and_timestamp_pointers_rechecked"])
        self.assertFalse(result["original_vendor_publication_independently_authenticated"])
        self.assertFalse(result["stage_asof_selection_independently_recomputed"])
        self.assertEqual(result["full_engine_eligible_cuts_added"], 0)

    def test_does_not_mutate_original_db(self):
        before = self.db.execute("SELECT count(*) FROM pit_records").fetchone()[0]
        verify_stage(self.stage, self.root)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pit_records").fetchone()[0], before)

    def test_mutated_stage_record_does_not_match_warehouse(self):
        self.stage["normalized_asof_records"][0]["value"] = 999
        with self.assertRaisesRegex(ValueError, "unchanged v4 warehouse"):
            verify_stage(self.stage, self.root)

    def test_stage_source_citation_not_in_rows_is_rejected(self):
        self.stage["source_hashes"] = [self.original_hash]
        with self.assertRaisesRegex(ValueError, "source citations are not supported"):
            verify_stage(self.stage, self.root)

    def test_cannot_duplicate_stage_record(self):
        self.stage["normalized_asof_records"].append(copy.deepcopy(self.row))
        with self.assertRaisesRegex(ValueError, "Repeated stage record"):
            verify_stage(self.stage, self.root)

    def test_raw_interchange_bytes_must_match_sha256(self):
        (self.root / "raw" / (self.interchange_hash + ".json")).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            verify_stage(self.stage, self.root)

    def test_original_provider_bytes_must_match_sha256(self):
        (self.root / "raw" / (self.original_hash + ".json")).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            verify_stage(self.stage, self.root)

    def test_original_provider_must_be_archived_not_only_referenced(self):
        self.db.execute("DELETE FROM raw_sources WHERE raw_hash=?", (self.original_hash,))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "missing or synthetic"):
            verify_stage(self.stage, self.root)

    def test_original_publication_pointer_is_rechecked(self):
        # A different but hash-valid original is not silently interchangeable.
        changed = {"price": 421.2, "published": "2024-12-30T21:00:00Z",
                   "available": self.published}
        altered_hash = self.archive(changed)
        changed_row = copy.deepcopy(self.row)
        changed_row["evidence"]["original_document_sha256"] = altered_hash
        changed_document = json.loads((self.root / "raw" / (self.interchange_hash + ".json")).read_text())
        changed_document["records"][0]["evidence"]["original_document_sha256"] = altered_hash
        changed_interchange_hash = self.archive(changed_document)
        changed_row["raw_hash"] = changed_interchange_hash
        self.db.execute("INSERT INTO pit_records VALUES(?,?,?,?,?,?)",
                        (sha256(canonical(changed_row)), canonical(changed_row).decode(),
                         changed_interchange_hash, "VERIFIED_PIT", 0, self.retrieved))
        self.db.commit()
        self.stage["normalized_asof_records"] = [changed_row]
        with self.assertRaisesRegex(ValueError, "publication or availability differs"):
            verify_stage(self.stage, self.root)

    def test_original_value_pointer_is_rechecked(self):
        changed = {"price": 0.01, "published": self.published, "available": self.published}
        altered_hash = self.archive(changed)
        changed_row = copy.deepcopy(self.row)
        changed_row["evidence"]["original_document_sha256"] = altered_hash
        changed_document = json.loads((self.root / "raw" / (self.interchange_hash + ".json")).read_text())
        changed_document["records"][0]["evidence"]["original_document_sha256"] = altered_hash
        changed_interchange_hash = self.archive(changed_document)
        changed_row["raw_hash"] = changed_interchange_hash
        self.db.execute("INSERT INTO pit_records VALUES(?,?,?,?,?,?)",
                        (sha256(canonical(changed_row)), canonical(changed_row).decode(),
                         changed_interchange_hash, "VERIFIED_PIT", 0, self.retrieved))
        self.db.commit()
        self.stage["normalized_asof_records"] = [changed_row]
        with self.assertRaisesRegex(ValueError, "Original provider value differs"):
            verify_stage(self.stage, self.root)

    def test_missing_warehouse_refused(self):
        with self.assertRaisesRegex(ValueError, "warehouse database is missing"):
            verify_stage(self.stage, self.root / "raw")

    def test_synthetic_provenance_refused(self):
        self.db.execute("UPDATE raw_sources SET synthetic=1 WHERE raw_hash=?",
                        (self.interchange_hash,))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "missing or synthetic"):
            verify_stage(self.stage, self.root)

    def test_bad_original_json_pointer_rejected(self):
        with self.assertRaisesRegex(ValueError, "pointer not found"):
            pointer({}, "/missing")
        with self.assertRaisesRegex(ValueError, "array index"):
            pointer([1], "/9")
        self.assertEqual(pointer({"a/b": {"~": 2}}, "/a~1b/~0"), 2)


if __name__ == "__main__":
    unittest.main()
