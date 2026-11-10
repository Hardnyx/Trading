"""Check that expensive workflows cannot silently return to every push."""
import unittest
from scripts.ci_workflow_policy import (
    FAST, FULL, PAGES, WORKFLOW_DIR, validate, validate_actions_budget,
)


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

    def test_standard_runner_and_schedule_inventory(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        self.assertTrue(all(validate_actions_budget(workflows).values()))

    def test_unreviewed_paid_runner_is_rejected(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        target = "pool-opportunity.yml"
        self.assertIn("runs-on: ubuntu-latest", workflows[target])
        workflows[target] = workflows[target].replace(
            "runs-on: ubuntu-latest", "runs-on: ubuntu-16-cores", 1)
        with self.assertRaisesRegex(ValueError, "Nonstandard"):
            validate_actions_budget(workflows)

    def test_excessive_job_timeout_is_rejected(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        target = "pool-opportunity.yml"
        self.assertIn("timeout-minutes: 15", workflows[target])
        workflows[target] = workflows[target].replace(
            "timeout-minutes: 15", "timeout-minutes: 240", 1)
        with self.assertRaisesRegex(ValueError, "timeout"):
            validate_actions_budget(workflows)

    def test_unreviewed_automatic_schedule_is_rejected(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        target = "portfolio-robustness.yml"
        self.assertIn("  workflow_dispatch:\n", workflows[target])
        workflows[target] = workflows[target].replace(
            "  workflow_dispatch:\n",
            "  workflow_dispatch:\n  schedule:\n    - cron: '0 * * * *'\n", 1)
        with self.assertRaisesRegex(ValueError, "Scheduled"):
            validate_actions_budget(workflows)
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        target = "pool-opportunity.yml"
        self.assertIn("- cron: '37 2 * * 0'", workflows[target])
        workflows[target] = workflows[target].replace(
            "- cron: '37 2 * * 0'", "- cron: '37 2 * * *'", 1)
        with self.assertRaisesRegex(ValueError, "Scheduled"):
            validate_actions_budget(workflows)

    def test_multiline_runner_or_timeout_cannot_hide_below_valid_job(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in WORKFLOW_DIR.glob("*.yml")
        }
        target = "pool-opportunity.yml"
        extra = workflows[target] + (
            "\n  unreviewed:\n    runs-on:\n      group: premium\n"
            "    timeout-minutes: 10\n"
        )
        with self.assertRaisesRegex(ValueError, "Nonstandard"):
            validate_actions_budget({**workflows, target: extra})
        extra = workflows[target] + (
            "\n  unreviewed:\n    runs-on: ubuntu-latest\n"
            "    timeout-minutes: \n"
        )
        with self.assertRaisesRegex(ValueError, "timeout"):
            validate_actions_budget({**workflows, target: extra})


if __name__ == "__main__":
    unittest.main()
