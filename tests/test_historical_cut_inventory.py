"""H2 calendar inventory: exclusions, pending cuts and audited cuts, stubbed archive."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts import historical_cut_inventory as inv


def build(root):
    (root / "data/historical/provider-inputs-v1").mkdir(parents=True)
    (root / "data/historical/identifier-observations-v1").mkdir(parents=True)
    audit = root / "data/historical/full-engine-input-audit-v1"
    audit.mkdir(parents=True)
    (root / inv.MANIFEST).write_text(json.dumps({"cuts": ["2024-11-29", "2024-12-31", "2025-03-31"]}))
    fresh = {"status": "source-available", "accession": "a", "as_of": "x", "age_days": 90}
    matrix = [{"cut": "2024-11-29", "positions": [], "spy_source": {"status": "stale-or-invalid-source"}},
              {"cut": "2024-12-31", "positions": [{}], "spy_source": fresh},
              {"cut": "2025-03-31", "positions": [{}], "spy_source": fresh}]
    (root / inv.OBSERVATIONS).write_bytes(gzip.compress(json.dumps({"matrix": matrix}).encode()))
    (audit / "report.json").write_text(json.dumps({
        "input_checks_passed": False, "snapshot_sha256": "h",
        "checks": {"identity": {"passed": False},
                   "universe": {"passed": True, "members": 3, "spy_weight_covered": .9, "spy_weight_with_ttm_eps": .8}}}))


class InventoryTests(unittest.TestCase):
    def test_every_cut_has_a_status_and_pending_cuts_are_not_accounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            result = inv.inventory(root)
        status = {r["cut"]: r["status"] for r in result["rows"]}
        self.assertEqual(status, {"2024-11-29": "excluded", "2024-12-31": "audited-blocked", "2025-03-31": "pending"})
        self.assertEqual(result["rows"][1]["failed_checks"], ["identity"])
        self.assertFalse(result["every_cut_accounted"])


if __name__ == "__main__":
    unittest.main()
