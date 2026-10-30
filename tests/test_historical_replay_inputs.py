"""Tests for the fail-closed historical macro replay-input adapter."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_sources import MARKET_COMMIT, PROTOCOL, SERIES, archive, canonical
from scripts.historical_replay_inputs import materialize_macro_inputs, write_bundle
from tests.test_historical_sources import record


class HistoricalMacroReplayInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cuts = ["2022-10-31"]
        source = record()
        pointer, _ = archive(self.root, "macro/2022-10-31/DGS3MO.json.gz", source)
        self.pointer = {**pointer, "status": "available",
                        "vintage_day": "2022-10-30",
                        "last_observation": "2022-10-30", "observations": 1}
        self.manifest = {
            "protocol": PROTOCOL, "source_market_commit": MARKET_COMMIT,
            "cuts": self.cuts, "series_ids": ["DGS3MO"],
            "macro": {"2022-10-31": {"DGS3MO": self.pointer}}
        }
        self.save_manifest()

    def save_manifest(self):
        (self.root / "manifest.json").write_bytes(canonical(self.manifest) + b"\n")

    def build(self):
        return materialize_macro_inputs(self.root, self.cuts, SERIES[:1])

    def test_materializes_only_verified_prior_day_provider_vintage(self):
        bundle = self.build()
        self.assertEqual(bundle["verified_records"], 1)
        self.assertFalse(bundle["full_model_replay_ready"])
        self.assertFalse(bundle["production_eligible"])
        row = bundle["macro"]["2022-10-31"]["DGS3MO"]
        self.assertEqual(row["known_by_day"], "2022-10-30")
        self.assertEqual(row["date"], "2022-10-30")
        self.assertEqual(row["value"], 2.5)
        self.assertEqual(row["source_sha256"], self.pointer["raw_sha256"])
        target = self.root / "out.json.gz"
        self.assertEqual(write_bundle(bundle, target), write_bundle(bundle, target))
        self.assertEqual(json.loads(gzip.decompress(target.read_bytes())), bundle)

    def test_rejects_missing_misdated_or_misidentified_sources(self):
        self.manifest["source_market_commit"] = "other"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Source protocol"):
            self.build()
        self.manifest["source_market_commit"] = MARKET_COMMIT
        self.manifest["macro"]["2022-10-31"]["DGS3MO"]["status"] = "unavailable"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Missing historical"):
            self.build()
        self.manifest["macro"]["2022-10-31"]["DGS3MO"]["status"] = "available"
        self.manifest["macro"]["2022-10-31"]["DGS3MO"]["vintage_day"] = "2026-10-29"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "vintage mismatch"):
            self.build()
        self.manifest["macro"]["2022-10-31"]["DGS3MO"]["vintage_day"] = "2022-10-30"
        self.save_manifest()
        with self.assertRaises(ValueError):
            materialize_macro_inputs(self.root, ["2022-10-31"], SERIES[:2])
        with self.assertRaises(ValueError):
            materialize_macro_inputs(self.root, ["2022-11-30"], SERIES[:1])

    def test_rejects_tampered_raw_archive_even_when_pointer_unchanged(self):
        p = self.root / self.pointer["path"]
        p.write_bytes(p.read_bytes() + b"alteration")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.build()


if __name__ == "__main__":
    unittest.main()
