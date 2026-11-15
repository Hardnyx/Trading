"""The v3 confirmatory registration: v2 untouched, inference closed, rules fixed."""
import hashlib
import json
import unittest
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


class ProtocolV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v3 = json.loads((DOCS / "protocolo-confirmacion-integral-v3.json").read_text(encoding="utf-8"))

    def test_predecessor_is_unchanged(self):
        digest = hashlib.sha256((DOCS / "protocolo-confirmacion-integral-v2.json").read_bytes()).hexdigest()
        self.assertEqual(self.v3["predecessor"]["sha256"], digest)

    def test_inference_stays_closed_until_operational_blockers_resolve(self):
        a = self.v3["activation"]
        self.assertFalse(a["confirmatory_collection_open"])
        self.assertFalse(a["formal_inference_enabled"])
        self.assertTrue(a["remaining_blockers"])
        self.assertFalse(self.v3["post_hoc_changes_permitted"])

    def test_registered_family_and_thresholds(self):
        c, h = self.v3["confirmatory_test"], self.v3["harm_monitor"]
        self.assertEqual(c["id"], "ranking_ic:21")
        self.assertEqual(c["material_threshold"], 0.03)
        self.assertEqual(self.v3["sampling"]["horizon_sessions"], [21])
        self.assertEqual(self.v3["sampling"]["fixed_analysis_after_mature_eligible_months"], 120)
        self.assertAlmostEqual(h["alpha_per_look"] * 10, 0.05)
        for path in self.v3["evidence_for_redesign"]:
            self.assertTrue((DOCS.parent / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
