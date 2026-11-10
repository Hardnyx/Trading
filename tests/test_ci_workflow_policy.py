"""Check that expensive workflows cannot silently return to every push."""
import unittest
from scripts.ci_workflow_policy import FAST, FULL, PAGES, validate


class SelectiveCiPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fast = FAST.read_text(encoding="utf-8")
        cls.full = FULL.read_text(encoding="utf-8")
        cls.pages = PAGES.read_text(encoding="utf-8")

    def test_repository_workflow_contract(self):
        self.assertTrue(all(validate(
            self.fast, self.full, self.pages).values()))

    def test_full_audit_must_be_manual(self):
        with self.assertRaisesRegex(ValueError, "manual"):
            validate(self.fast, self.full.replace(
                "  workflow_dispatch:\n",
                "  push:\n    branches: [main]\n  workflow_dispatch:\n", 1),
                self.pages)

    def test_monte_carlo_not_enabled_in_fast_ci(self):
        with self.assertRaisesRegex(ValueError, "expensive"):
            validate(self.fast + "\n      - run: python scripts/confirmatory_hac_stress.py",
                     self.full, self.pages)

    def test_causal_gate_kept_on_fast_runs(self):
        with self.assertRaisesRegex(ValueError, "mandatory"):
            validate(self.fast.replace(
                "scripts/overfit_policy_guard.py --verify",
                "scripts/overfit_policy_guard.py --skip"),
                self.full, self.pages)

    def test_full_familywise_calibration_not_dropped(self):
        with self.assertRaisesRegex(ValueError, "lost"):
            validate(self.fast, self.full.replace(
                "scripts/confirmatory_calibration_gate.py --verify",
                "scripts/confirmatory_calibration_gate.py --skip"),
                self.pages)

    def test_pages_paths_and_refresh_call_kept(self):
        with self.assertRaisesRegex(ValueError, "Pages"):
            validate(self.fast, self.full,
                     self.pages.replace("'dist/**'", "'docs/**'", 1))
        with self.assertRaisesRegex(ValueError, "Pages"):
            validate(self.fast, self.full,
                     self.pages.replace("  workflow_call:\n",
                                        "  renamed_call:\n", 1))


if __name__ == "__main__":
    unittest.main()
