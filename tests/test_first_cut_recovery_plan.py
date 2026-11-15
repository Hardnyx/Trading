"""H1.1 recovery plan stays aligned with the frozen first-cut inventory."""
import json
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data/historical/full-engine-input-audit-v1"


class RecoveryPlanTests(unittest.TestCase):
    def test_plan_covers_every_inventory_component_once_without_certifying(self):
        plan = json.loads((BASE / "recovery-plan-v1.json").read_text(encoding="utf-8"))
        inventory = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
        names = [c["component"] for c in plan["components"]]
        self.assertEqual(sorted(names), sorted(c["component"] for c in inventory["components"]))
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(plan["certification"])
        self.assertFalse(plan["outcomes_consulted"])
        verified = {c["component"] for c in inventory["components"] if c["status"] == "verified-source"}
        self.assertEqual(verified, {c["component"] for c in plan["components"] if c["group"] == "verified"})
        self.assertTrue(all(c["group"] in plan["groups"] for c in plan["components"]))


if __name__ == "__main__":
    unittest.main()
