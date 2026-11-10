"""Protect prospective signal capture and selective shadow audit timing."""
import unittest
from scripts.ci_workflow_policy import POOL, SIGNAL, PAGES, validate_refresh_dependents, validate_page_reuse


class RefreshDependentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = POOL.read_text(encoding="utf-8")
        cls.signal = SIGNAL.read_text(encoding="utf-8")
        cls.pages = PAGES.read_text(encoding="utf-8")

    def test_current_workflow_schedule(self):
        self.assertTrue(all(validate_refresh_dependents(
            self.pool, self.signal).values()))

    def test_daily_pool_reactivation_is_rejected(self):
        changed = self.pool.replace(
            "  schedule:\n    # Weekly shadow research after the Friday market close and refresh.\n    - cron: '37 2 * * 0'\n",
            "  workflow_run:\n    workflows: [Refresh market data]\n    types: [completed]\n",
        )
        with self.assertRaisesRegex(ValueError, "weekly"):
            validate_refresh_dependents(changed, self.signal)

    def test_exploratory_methods_are_not_dropped(self):
        changed = self.pool.replace(
            "node scripts/antithetic_selection_research.mjs", "echo skipped", 1)
        with self.assertRaisesRegex(ValueError, "preserved"):
            validate_refresh_dependents(changed, self.signal)

    def test_daily_signal_and_failed_refresh_evidence_are_required(self):
        changed = self.signal.replace(
            "    workflows: [Refresh market data]\n",
            "    workflows: [Unrelated]\n", 1)
        with self.assertRaisesRegex(ValueError, "each completed"):
            validate_refresh_dependents(self.pool, changed)
        changed = self.signal.replace(
            "github.event.workflow_run.conclusion", "success", 1)
        with self.assertRaisesRegex(ValueError, "failed refresh"):
            validate_refresh_dependents(self.pool, changed)

    def test_signal_pages_only_follows_new_evidence(self):
        changed = self.signal.replace(
            "    if: needs.ledger.outputs.published_changes == 'true'\n", "", 1)
        with self.assertRaisesRegex(ValueError, "newly committed"):
            validate_refresh_dependents(self.pool, changed)
        changed = self.signal.replace(
            "steps.verify.outputs.changed", "steps.other.outputs.changed", 1)
        with self.assertRaisesRegex(ValueError, "newly committed"):
            validate_refresh_dependents(self.pool, changed)

    def test_weekly_pool_keeps_manual_access(self):
        changed = self.pool.replace("  workflow_dispatch:\n", "", 1)
        with self.assertRaisesRegex(ValueError, "weekly"):
            validate_refresh_dependents(changed, self.signal)


    def test_pages_does_not_duplicate_python_after_successful_refresh(self):
        self.assertTrue(all(validate_page_reuse(
            self.pages, self.signal).values()))
        bad = self.signal.replace(
            "github.event.workflow_run.conclusion == 'success'",
            "true", 1)
        with self.assertRaisesRegex(ValueError, "only reuse"):
            validate_page_reuse(self.pages, bad)

    def test_pages_always_checks_js_and_preserves_full_python_path(self):
        bad = self.pages.replace(
            "        default: false", "        default: true", 1)
        with self.assertRaisesRegex(ValueError, "full Python"):
            validate_page_reuse(bad, self.signal)
        bad = self.pages.replace("          npm test\n", "", 1)
        with self.assertRaisesRegex(ValueError, "full Python"):
            validate_page_reuse(bad, self.signal)


if __name__ == "__main__":
    unittest.main()
