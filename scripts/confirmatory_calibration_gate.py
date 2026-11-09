"""Audit synthetic familywise calibration without approving market inference.

Use simultaneous exact binomial confidence limits for the 24 fixed scenarios
of the frozen joint-global-null and partial-null diagnostics. This is a
read-only design audit; it cannot validate an unknown real-market DGP.
"""

import argparse
import json
from itertools import product
from pathlib import Path
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "confirmatory-familywise-calibration-gate-v1"
FAMILY_ALPHA = 0.05
CONFIDENCE = 0.95
EXPECTED_SCENARIOS = 24
EXPECTED_TESTS = [f"{kind}:{h}" for kind in ("return_mse", "ranking_ic")
                  for h in (21, 63, 252)] + ["net_economic_value:21"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_binomial_limits(successes, trials, tail_probability):
    """Conservative two-sided Clopper-Pearson limits at 2*tail_probability.

    The caller splits the total confidence budget over every scenario and
    both interval tails; the trials must be independent within each scenario.
    """
    require(type(successes) is int and type(trials) is int
            and trials > 0 and 0 <= successes <= trials
            and 0 < tail_probability < 0.5,
            "Invalid exact-binomial confidence limit arguments")
    lower = (float(beta.ppf(tail_probability, successes, trials-successes+1))
             if successes else 0.0)
    upper = (float(beta.ppf(1-tail_probability, successes+1, trials-successes))
             if successes < trials else 1.0)
    return lower, upper


def checked_count(row, field, trials):
    value = row.get(field)
    require(type(value) is int and 0 <= value <= trials,
            f"Invalid count: {field}")
    return value


def check_paired_counts(row, trials, bootstrap, oracle, bootstrap_only,
                        oracle_only):
    b = checked_count(row, bootstrap, trials)
    o = checked_count(row, oracle, trials)
    b_only = checked_count(row, bootstrap_only, trials)
    o_only = checked_count(row, oracle_only, trials)
    require(b_only <= b and o_only <= o and
            b-o == b_only-o_only and
            b_only+o_only <= trials and
            b_only <= trials-o and o_only <= trials-b,
            "Paired diagnostic counts do not reconcile")
    return b, o


def expected_grid(kind):
    if kind == "global":
        return set(product((96, 192), (0.0, 0.6), (0.0, 0.75), (12, 24)))
    return set(product((96, 192), (0.6,), (0.0, 0.75), (12, 24)))


def read_scenarios(report, kind):
    """Enforce the registered synthetic design before evaluating its counts."""
    require(isinstance(report, dict), "Report must be a JSON object")
    if kind == "global":
        require(report.get("schema") == "confirmatory-joint-null-bootstrap-v1"
                and report.get("simulation_seed") == 20261109
                and report.get("scope") ==
                "seven-correlated-synthetic-effects-under-complete-global-null"
                and report.get("trading_outcomes_read") is False
                and report.get("real_market_effects_used") is False
                and report.get("formal_inference_enabled") is False
                and report.get("confirmatory_collection_open") is False
                and report.get("strong_fwer_control_not_established") is True
                and report.get("oracle_valid_for_real_market_effects") is False
                and report.get("oracle_uses_true_synthetic_parameters") is True,
                "Global-null report is not an inert synthetic diagnostic")
        reps = 256
        count_field = "familywise_any_rejections"
        oracle_field = "oracle_any_rejections"
        b_only_field, o_only_field = "bootstrap_only_rejections", "oracle_only_rejections"
    else:
        require(report.get("schema") == "confirmatory-partial-null-holm-v1"
                and report.get("simulation_seed") == 20261110
                and report.get("status") == "synthetic-partial-null-stress-only"
                and report.get("true_null_indices") == [0, 1, 2, 3]
                and report.get("shifted_false_null_indices") == [4, 5, 6]
                and report.get("shifted_effect_unconditional_sd_assumed") == 0.5
                and report.get("real_market_outcomes_used") is False
                and report.get("registered_v2_modified") is False
                and report.get("confirmatory_inference_enabled") is False
                and report.get("strong_fwer_control_not_established") is True
                and report.get("oracle_not_applicable_to_unknown_market_dgp") is True
                and report.get("oracle_uses_known_synthetic_phi") is True,
                "Partial-null report is not an inert synthetic diagnostic")
        reps = 128
        count_field = "false_family_rejections"
        oracle_field = "oracle_false_family_rejections"
        b_only_field, o_only_field = "false_family_bootstrap_only", "false_family_oracle_only"
    require(report.get("bootstrap_draws_per_replication") == 10000
            and report.get("nominal_holm_familywise_alpha",
                           report.get("nominal_familywise_alpha")) == FAMILY_ALPHA
            and isinstance(report.get("rows"), list),
            "Frozen draw count, alpha, or rows changed")
    if kind == "global":
        require(report.get("family_test_names") == EXPECTED_TESTS,
                "Joint test family has changed")
    else:
        require(report.get("hypotheses") == EXPECTED_TESTS,
                "Partial-null test family has changed")
    rows = []
    visited = set()
    same_oracle = {}
    grid = expected_grid(kind)
    for record in report["rows"]:
        require(isinstance(record, dict), "Scenario must be an object")
        n = record.get("months")
        phi = record.get("monthly_ar1_phi_assumed")
        rho = record.get("cross_test_rho_assumed")
        block = record.get("block_months")
        scenario = (n, phi, rho, block)
        require(scenario in grid and scenario not in visited,
                "Unexpected or duplicate synthetic scenario")
        visited.add(scenario)
        trials = record.get("null_repetitions" if kind == "global" else "repetitions")
        require(type(trials) is int and trials == reps,
                "Synthetic repetition count differs from recorded design")
        b, o = check_paired_counts(
            record, trials, count_field, oracle_field,
            b_only_field, o_only_field)
        if kind == "partial":
            checked_count(record, "any_shifted_rejections", trials)
        key = (n, phi, rho)
        if key in same_oracle:
            require(same_oracle[key] == o,
                    "Oracle counts disagree across block lengths on shared draws")
        else:
            same_oracle[key] = o
        rows.append({"source": kind, "months": n, "phi": phi,
                     "rho": rho, "block_months": block,
                     "repetitions": trials, "bootstrap_rejections": b,
                     "oracle_rejections": o})
    require(visited == grid,
            "Missing synthetic scenarios from a fixed calibration grid")
    return sorted(rows, key=lambda r: (r["months"], r["phi"], r["rho"], r["block_months"]))


def evaluate(global_report, partial_report):
    """Classify synthetic-only evidence; never activate protocol v2."""
    scenarios = (read_scenarios(global_report, "global") +
                 read_scenarios(partial_report, "partial"))
    require(len(scenarios) == EXPECTED_SCENARIOS,
            "Calibration family must contain 24 prespecified scenarios")
    tail = (1-CONFIDENCE)/(2*len(scenarios))
    output = []
    for row in scenarios:
        n = row["repetitions"]
        lower, upper = exact_binomial_limits(
            row["bootstrap_rejections"], n, tail)
        oracle_lower, oracle_upper = exact_binomial_limits(
            row["oracle_rejections"], n, tail)
        output.append({**row,
                       "bootstrap_rate": round(row["bootstrap_rejections"]/n, 6),
                       "bootstrap_simultaneous_exact95": [round(lower, 6), round(upper, 6)],
                       "bootstrap_excess_evidence": lower > FAMILY_ALPHA,
                       "bootstrap_upper_below_nominal": upper <= FAMILY_ALPHA,
                       "oracle_rate": round(row["oracle_rejections"]/n, 6),
                       "oracle_simultaneous_exact95": [round(oracle_lower, 6),
                                                        round(oracle_upper, 6)]})
    oversized = sum(row["bootstrap_excess_evidence"] for row in output)
    certified_grid = all(row["bootstrap_upper_below_nominal"] for row in output)
    return {
        "schema": SCHEMA,
        "scope": "previously-inspected-synthetic-design-only",
        "synthetic_scenario_count": len(output),
        "nominal_familywise_alpha": FAMILY_ALPHA,
        "simultaneous_confidence": CONFIDENCE,
        "per_tail_probability": tail,
        "bound": "two-sided exact Clopper-Pearson with Bonferroni over 24 scenario intervals",
        "confidence_intervals_require_independent_repetitions_within_each_scenario": True,
        "scenario_sensitivity_not_a_proof_for_other_distributions": True,
        "candidate_method_selection_permitted": False,
        "new_market_data_used": False,
        "registered_v2_modified": False,
        "formal_inference_enabled": False,
        "synthetic_calibration_result": (
            "excess-rejection-detected" if oversized else
            "grid-upper-bounds-met" if certified_grid else
            "inconclusive"),
        "bootstrap_scenarios_with_simultaneous_lower_bound_above_nominal": oversized,
        "synthetic_grid_upper_bounds_all_below_nominal": certified_grid,
        "real_market_calibration_certified": False,
        "trading_predictive_validation": "not-established",
        "rows": output,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-report", required=True, type=Path)
    parser.add_argument("--partial-report", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    global_report = json.loads(args.global_report.read_text(encoding="utf-8"))
    partial_report = json.loads(args.partial_report.read_text(encoding="utf-8"))
    result = evaluate(global_report, partial_report)
    if args.verify:
        require(result["synthetic_scenario_count"] == 24 and
                result["formal_inference_enabled"] is False and
                result["real_market_calibration_certified"] is False and
                result["candidate_method_selection_permitted"] is False,
                "Synthetic calibration cannot enable market inference")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n",
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
