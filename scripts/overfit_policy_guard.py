"""Fail-closed governance checks for selection, tuning leakage and cohort reuse.

The audit protects documented rules; it cannot prove a model has no overfitting
or detect an unrecorded experiment outside the supplied trial registry.
"""
import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = "docs/politica-control-sobreajuste-v1.json"
LOG = "data/validation/model-trials-v1.json"
V1 = "docs/protocolo-replay-integral-v1.json"
V2 = "docs/protocolo-confirmacion-integral-v2.json"
ORIGINAL_V1_SHA256 = "6a8d5f716292c04f8663a3e54a39e8dda5a7843fdae9a28045286570aba4addc"

SELECTION_GUARDS = (
    "no_confirmatory_outcome_guided_tuning", "no_lookahead_in_features_or_labels",
    "all_tried_variants_recorded", "no_seed_shopping",
    "no_horizon_or_metric_cherry_picking",
    "no_exclusion_based_on_realized_performance",
    "preregister_candidate_and_baselines_before_confirmatory_scores",
    "report_all_primary_hypotheses"
)
TEMPORAL_GUARDS = (
    "nested_training_only_when_tuning", "all_learned_preprocessing_inside_training",
    "training_labels_mature_before_selection",
    "purge_train_labels_overlapping_inner_validation",
    "embargo_documented_if_design_requires",
    "no_random_k_fold_for_time_series",
    "no_training_on_outer_or_confirmatory_outcomes"
)
REVISION_GUARDS = (
    "model_affecting_changes_start_new_cohort",
    "outcomes_inspected_before_change_force_exploratory_role",
    "previously_scored_confirmatory_period_never_reused_for_new_model",
    "do_not_pool_incompatible_source_or_model_cohorts",
    "score_review_no_automatic_reoptimization",
    "record_all_candidate_trials_and_search_space"
)
INFERENCE_GUARDS = (
    "no_interim_primary_hypothesis_peeking_without_registered_alpha_spending",
    "no_automatic_proof_from_holm_after_model_search",
    "minimum_economic_effect_and_power_still_pending",
    "avoid_unsupported_overfit_free_conclusion"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def proper_day(value, name):
    require(isinstance(value, str), "Missing " + name)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid date: " + name) from exc
    require(result.isoformat() == value, "Noncanonical date: " + name)
    return result


def proper_instant(value, name):
    require(isinstance(value, str), "Missing " + name)
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid instant: " + name) from exc
    require(moment.tzinfo is not None and moment.utcoffset() is not None,
            "Timezone required: " + name)
    return moment


def check_policy(root=ROOT):
    root = Path(root)
    policy = load(root / POLICY)
    v1_raw = (root / V1).read_bytes()
    v1 = json.loads(v1_raw)
    v2 = load(root / V2)
    require(hashlib.sha256(v1_raw).hexdigest() == ORIGINAL_V1_SHA256,
            "Frozen v1 methodology was rewritten")
    require(policy.get("schema") == "trading-overfitting-control-v1" and
            policy.get("role") ==
            "research-governance-addendum-not-frozen-protocol-amendment" and
            policy.get("current_assessment") == "not-established" and
            policy.get("no_claim_of_zero_overfitting") is True,
            "Governance cannot certify absence of overfitting")
    frozen = policy["frozen_studies"]
    require(frozen["development_protocol"] == V1 and
            frozen["prospective_protocol"] == V2 and
            frozen["original_development_cuts"] == 48 and
            frozen["independent_eligible_origins"] == 0 and
            len(v1["expected_cuts"]) == 48 and
            v1["sample_role"] == "previously-inspected-development-history" and
            v1["independent_holdout"]["registered"] is False and
            policy["selection"]["previously_inspected_history_as_holdout"] is False and
            policy["selection"]["historical_retrospective_data"] == "development-only",
            "Previously inspected development history was relabelled independent")
    require(v2["schema"] == "full-engine-prospective-registration-v2" and
            v2["status"] == "registered-methodology-inactive-confirmatory-inference" and
            v2["sampling"]["first_possible_cut"] == "2026-11-09" and
            v2["sampling"]["minimum_mature_eligible_months"] >= 96 and
            v2["sampling"]["exclude_previously_examined"] is True and
            v2["fixed_cohort"]["never_pool_code_or_source_cohorts"] is True and
            v2["activation"]["confirmatory_collection_open"] is False and
            v2["activation"]["formal_inference_enabled"] is False,
            "Confirmatory registration was weakened or falsely activated")
    expected = [f"{family}:{h}" for family in ("return_mse", "ranking_ic")
                for h in (21, 63, 252)] + ["net_economic_value:21"]
    require([item["id"] for item in v2["primary_tests"]] == expected and
            v2["multiplicity"]["method"] == "Holm step-down" and
            v2["multiplicity"]["alpha"] == 0.05 and
            v2["economic_effect_thresholds"]["status"] ==
            "unjustified-power-not-established" and
            all(v2["economic_effect_thresholds"][key] is None for key in
                ("return_mse", "ranking_ic", "net_economic_value")),
            "Registered test family or pending economic thresholds were changed")
    for section, keys in (("selection", SELECTION_GUARDS),
                          ("temporal_validation", TEMPORAL_GUARDS),
                          ("revision_policy", REVISION_GUARDS),
                          ("inference", INFERENCE_GUARDS)):
        require(all(policy[section].get(key) is True for key in keys),
                "Mandatory anti-overfitting control disabled: " + section)
    require(policy["temporal_validation"]["default"] ==
            "chronological-expanding-or-rolling-walk-forward" and
            policy["inference"]["primary_tests"] == 7 and
            policy["inference"]["holm_familywise_alpha"] == 0.05 and
            policy["inference"]["minimum_eligible_mature_months"] >= 96 and
            policy["acceptance"]["formal_prediction_skill_unestablished"] is True,
            "Validation sample, model selection or evidence gates were relaxed")
    return policy


def check_temporal_fold(fold):
    """Verify a documented fold. Dates describe when labels became known."""
    require(fold.get("split") in ("expanding-walk-forward", "rolling-walk-forward"),
            "Random or retrospective fold is not an admissible temporal split")
    outer = proper_day(fold.get("outer_origin"), "outer origin")
    selection = proper_day(fold.get("model_selected_by"), "selection freeze")
    inner_start = proper_day(fold.get("inner_validation_start"), "inner start")
    inner_end = proper_day(fold.get("inner_validation_end"), "inner end")
    last_label = proper_day(fold.get("inner_validation_label_matured_by"),
                            "inner validation label maturity")
    require(inner_start <= inner_end <= last_label <= selection < outer,
            "Training/selection used a label not mature before outer origin")
    require(fold.get("all_preprocessing_fit_inside_train") is True and
            fold.get("all_candidates_logged") is True and
            fold.get("label_overlap_purged") is True and
            fold.get("embargo_decision_documented") is True,
            "Nested tuning, purge, embargo or trial evidence is missing")
    labels = fold.get("training_labels")
    require(isinstance(labels, list) and len(labels) > 0,
            "Missing dated training labels")
    for row in labels:
        start = proper_day(row.get("prediction_date"), "training origin")
        end = proper_day(row.get("outcome_matured_at"), "training label end")
        require(start <= end < inner_start and end <= selection,
                "Overlapping or future-mature training label entered inner validation")
    require(fold.get("outer_outcomes_used") is False and
            fold.get("confirmatory_outcomes_used") is False,
            "Outer/confirmatory outcomes contaminated model selection")
    return True


def check_trial(trial):
    """A candidate changed after inspected outcomes cannot inherit a holdout."""
    require(isinstance(trial.get("trial_id"), str) and trial["trial_id"].strip() and
            isinstance(trial.get("reason"), str) and trial["reason"].strip(),
            "Trial is missing identity or technical rationale")
    logged = proper_instant(trial.get("recorded_at"), "trial registration")
    require(trial.get("result_data_used") in
            ("none", "development-only", "confirmatory-inspected"),
            "Trial data role is missing")
    require(trial.get("model_affecting") in (True, False) and
            trial.get("old_cohort") and trial.get("new_cohort") and
            isinstance(trial.get("search_attempts"), int) and
            not isinstance(trial["search_attempts"], bool) and
            trial["search_attempts"] >= 1,
            "Trial cohort/attempt metadata incomplete")
    changed = trial["model_affecting"]
    if changed:
        require(trial["old_cohort"] != trial["new_cohort"],
                "Model-affecting change reused previous confirmatory cohort")
        first = proper_day(trial.get("first_eligible_new_origin"), "new origin")
        require(first > logged.date(),
                "A revised model cannot claim earlier origins as independent")
    if trial["result_data_used"] == "confirmatory-inspected":
        require(trial.get("evidence_role") == "exploratory" and
                trial.get("new_independent_holdout_required") is True and
                trial.get("reuses_inspected_period") is False and
                trial["old_cohort"] != trial["new_cohort"],
                "Outcome-informed revision reused inspected confirmation")
    if trial.get("claim_predictive_validation") is True:
        raise ValueError("No tuning trial can certify predictive skill")
    require(trial.get("all_search_attempts_logged") is True,
            "Missing complete searched-candidate register")
    return True


def audit(root=ROOT):
    root = Path(root)
    policy = check_policy(root)
    ledger = load(root / LOG)
    require(ledger.get("schema") == "trading-model-trial-log-v1" and
            ledger.get("record_scope") ==
            "new_trials_from_policy_adoption_only; not a complete reconstruction of all prior model trials" and
            isinstance(ledger.get("trials"), list),
            "Tuning log falsely represents prior attempts as fully documented")
    seen = set()
    for trial in ledger["trials"]:
        check_trial(trial)
        require(trial["trial_id"] not in seen, "Duplicate trial identifier")
        seen.add(trial["trial_id"])
    return {"policy": policy["schema"], "status": "guardrails-active-no-proof-of-generalization",
            "already_inspected_development_months": 48, "newly_logged_trials": len(seen),
            "eligible_confirmatory_months_certified_here": 0,
            "model_overfitting_absence_proven": False,
            "predictive_skill": "not-established"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.parse_args(argv)
    print(json.dumps(audit(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
