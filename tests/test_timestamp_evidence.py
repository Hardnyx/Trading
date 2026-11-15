"""Evidence timestamps: pending detection and tamper evidence, offline."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import timestamp_evidence as te

ROOT = Path(__file__).resolve().parents[1]


class TimestampEvidenceTests(unittest.TestCase):
    def test_only_new_or_changed_files_are_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data/forecasts").mkdir(parents=True)
            (root / "data/timestamps").mkdir(parents=True)
            a = root / "data/forecasts/a.json"
            a.write_text("1")
            self.assertEqual([r["path"] for r in te.pending(root)], ["data/forecasts/a.json"])
            (root / "data/timestamps/x.manifest.json").write_text(json.dumps(
                {"files": [{"path": "data/forecasts/a.json", "sha256": te.sha256(a)}]}))
            self.assertEqual(te.pending(root), [])
            a.write_text("2")
            self.assertEqual(len(te.pending(root)), 1)

    def test_published_tokens_verify_and_reject_a_changed_manifest(self):
        if not shutil.which("openssl"):
            self.skipTest("openssl unavailable")
        manifest = sorted((ROOT / "data/timestamps").glob("*.manifest.json"))[0]
        stem = manifest.name[:-len(".manifest.json")]
        token = manifest.parent / f"{stem}.freetsa.tsr"
        self.assertTrue(te.verify_token(manifest, token, "freetsa"))
        with tempfile.TemporaryDirectory() as tmp:
            forged = Path(tmp) / manifest.name
            forged.write_bytes(manifest.read_bytes() + b" ")
            self.assertFalse(te.verify_token(forged, token, "freetsa"))
        self.assertEqual(te.sha256(ROOT / te.AUTHORITIES["freetsa"]["ca"]), te.FREETSA_CA_SHA256)


if __name__ == "__main__":
    unittest.main()
