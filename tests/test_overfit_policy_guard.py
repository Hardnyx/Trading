"""Adversarial regression tests for the overfitting governance gate."""
import copy
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.overfit_policy_guard import (
    ROOT, audit, check_policy, check_temporal_fold, check_trial,
    verify_append_only_log
)

BASE_FOLD = {
    "split": "expanding-walk-forward",
    "outer_origin": "2026-11-30",
    "model_selected_by": "2026-11-20",
    "inner_validation_start": "2026-09-01",
    "inner_validation_end": "2026-10-01",
    "inner_validation_label_matured_by": "2026-11-10",
    "all_preprocessing_fit_inside_train": True,
    "all_candidates_logged": True,
    "label_overlap_purged": True,
    "embargo_decision_documented": True,
    "training_labels": [
        {"prediction_date": "2026-07-01", "outcome_matured_at": "2026-08-01"}
    ],
    "outer_outcomes_used": False,
    "confirmatory_outcomes_used": False
}
BASE_TRIAL = {
    "trial_id": "test-case",
    "reason": "Reproducible numerical bug correction",
    "recorded_at": "2026-11-08T15:00:00Z",
    "result_data_used": "development-only",
    "model_affecting": True,
    "old_cohort": "baseline-a",
    "new_cohort": "corrected-b",
    "first_eligible_new_origin": "2026-11-30",
    "search_attempts": 1,
    "all_search_attempts_logged": True,
    "evidence_role": "research",
    "new_independent_holdout_required": True,
    "reuses_inspected_period": False,
    "claim_predictive_validation": False
}


class OverfitPolicyGuardTests(unittest.TestCase):
    def test_current_registered_studies_remain_unvalidated(self):
        report = audit()
        self.assertEqual(report["already_inspected_development_months"], 48)
        self.assertEqual(report["newly_logged_trials"], 0)
        self.assertFalse(report["model_overfitting_absence_proven"])
        self.assertEqual(report["predictive_skill"], "not-established")

    def test_cli_runs_in_ci(self):
        result = subprocess.run(
            [sys.executable, str(Path(ROOT) / "scripts/overfit_policy_guard.py"),
             "--verify"], capture_output=True, text=True, check=True
        )
        self.assertIn("guardrails-active-no-proof-of-generalization", result.stdout)

    def test_mandatory_controls_cannot_be_weakened(self):
        policy = check_policy()
        self.assertTrue(policy["selection"]["no_seed_shopping"])
        self.assertEqual(policy["inference"]["primary_tests"], 7)
        self.assertFalse(policy["selection"]["previously_inspected_history_as_holdout"])

    def test_chronological_nested_fold_admits_mature_labels(self):
        self.assertTrue(check_temporal_fold(BASE_FOLD))

    def test_training_label_overlap_and_immature_inner_score_rejected(self):
        changed = copy.deepcopy(BASE_FOLD)
        changed["training_labels"][0]["outcome_matured_at"] = "2026-09-20"
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            check_temporal_fold(changed)
        changed = copy.deepcopy(BASE_FOLD)
        changed["inner_validation_label_matured_by"] = "2026-12-02"
        with self.assertRaisesRegex(ValueError, "not mature"):
            check_temporal_fold(changed)

    def test_feature_fit_or_candidate_selection_on_future_test_rejected(self):
        for key, value in (
            ("split", "random-k-fold"),
            ("all_preprocessing_fit_inside_train", False),
            ("all_candidates_logged", False),
            ("label_overlap_purged", False),
            ("embargo_decision_documented", False),
            ("outer_outcomes_used", True),
            ("confirmatory_outcomes_used", True),
        ):
            changed = copy.deepcopy(BASE_FOLD)
            changed[key] = value
            with self.assertRaises(ValueError, msg=key):
                check_temporal_fold(changed)

    def test_new_model_cohort_cannot_inherit_scored_period(self):
        self.assertTrue(check_trial(BASE_TRIAL))
        changed = dict(BASE_TRIAL, new_cohort="baseline-a")
        with self.assertRaisesRegex(ValueError, "previous confirmatory"):
            check_trial(changed)
        changed = dict(BASE_TRIAL, first_eligible_new_origin="2026-11-08")
        with self.assertRaisesRegex(ValueError, "earlier origins"):
            check_trial(changed)

    def test_outcome_informed_tuning_is_not_independent_confirmation(self):
        changed = dict(BASE_TRIAL, result_data_used="confirmatory-inspected")
        with self.assertRaisesRegex(ValueError, "inspected confirmation"):
            check_trial(changed)
        changed.update(evidence_role="exploratory")
        self.assertTrue(check_trial(changed))
        for key, value in (
            ("new_independent_holdout_required", False),
            ("reuses_inspected_period", True),
            ("new_cohort", "baseline-a"),
        ):
            bad = dict(changed, **{key: value})
            with self.assertRaises(ValueError, msg=key):
                check_trial(bad)

    def test_model_trial_history_is_append_only(self):
        old = {"schema": "trading-model-trial-log-v1",
               "trials": [dict(BASE_TRIAL)]}
        new = {"schema": "trading-model-trial-log-v1",
               "trials": [dict(BASE_TRIAL), dict(BASE_TRIAL, trial_id="next")]}
        self.assertTrue(verify_append_only_log(old, new))
        new["trials"][0]["reason"] = "Rewritten after inspection"
        with self.assertRaisesRegex(ValueError, "not append-only"):
            verify_append_only_log(old, new)
        with self.assertRaisesRegex(ValueError, "not append-only"):
            verify_append_only_log(old, {"schema": old["schema"], "trials": []})

    def test_trial_selection_is_not_predictive_skill(self):
        with self.assertRaisesRegex(ValueError, "certify predictive skill"):
            check_trial(dict(BASE_TRIAL, claim_predictive_validation=True))
        with self.assertRaisesRegex(ValueError, "complete searched"):
            check_trial(dict(BASE_TRIAL, all_search_attempts_logged=False))


if __name__ == "__main__":
    unittest.main()
