"""Build a fail-closed economic materiality readiness matrix for H0.3.

The seven units, benchmark definitions and cash costs are sourced solely from
the frozen protocols. Missing economically material effects remain null. This
diagnostic does not load realized market outcomes or authorize inference.
"""
import argparse
import json
from math import isfinite
from pathlib import Path

try:
    from scripts.prospective_study_registry import read_contract, check_contract
except ModuleNotFoundError:
    from prospective_study_registry import read_contract, check_contract

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "confirmatory-economic-materiality-readiness-v1"
TEST_IDS = [
    f"{kind}:{h}" for kind in ("return_mse", "ranking_ic")
    for h in (21, 63, 252)
] + ["net_economic_value:21"]
EXPECTED_COSTS = {
    "commissionFixed": 0, "commissionBps": 0, "spreadBps": 5,
    "slippageBps": 2, "capitalGainsTax": 0,
}
METRICS = {
    "return_mse": (
        "squared-arithmetic-total-return-difference",
        "equal origins and equal eligible instruments within each origin",
        "ex-ante link between prediction-error reduction and net decision value",
        False,
    ),
    "ranking_ic": (
        "Spearman-correlation-point-difference",
        "same eligible instrument intersection within each origin",
        "ex-ante link between incremental rank information and tradable net value",
        False,
    ),
    "net_economic_value": (
        "annualized-monthly-paired-log-return-difference",
        "paired sequential eligible monthly accounts in USD",
        "investor risk, implementation costs and reference-relative net utility",
        True,
    ),
}
TURNOVER_EXAMPLES = (0.0, 0.25, 0.5, 1.0)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def frozen_inputs(v2, v1):
    """Reject even in-memory replacements of original reference definitions."""
    live_v2, live_v1 = read_contract()
    require(v1 == live_v1 and v2 == live_v2,
            "Materiality inputs differ from repository's frozen source contracts")
    check_contract(v2, v1)
    require([test["id"] for test in v2["primary_tests"]] == TEST_IDS and
            [test["id"] for test in v1["primary_tests"]] == list(METRICS) and
            v1["horizons_sessions"] == [21, 63, 252] and
            v2["forecast_target"] == v1["forecast_target"] and
            "arithmetic total return" in v1["forecast_target"],
            "Frozen seven-test definitions changed")
    costs = v1["costs"]
    require(costs["base"] == EXPECTED_COSTS and
            costs["stress"] ==
            "triple spread and slippage; base costs are an explicit scenario, not observed broker quotes"
            and "no double-counting" in costs["dividends"] and
            "never forecast" in costs["cash"],
            "Frozen cost or cash-flow assumptions changed")
    effects = v2["economic_effect_thresholds"]
    require(effects["status"] == "unjustified-power-not-established" and
            all(effects[k] is None for k in METRICS) and
            v2["activation"]["formal_inference_enabled"] is False and
            v2["activation"]["confirmatory_collection_open"] is False,
            "Unsupported effect thresholds or activation")
    return True


def materiality_rows(v2, v1):
    frozen_inputs(v2, v1)
    originals = {test["id"]: test for test in v1["primary_tests"]}
    rows = []
    for test in v2["primary_tests"]:
        parent, horizon = test["parent"], test["horizon_sessions"]
        original = originals[parent]
        require(horizon in original["horizons_sessions"],
                "Registered horizon has no original reference")
        unit, aggregation, evidence, monetary = METRICS[parent]
        rows.append({
            "hypothesis_id": test["id"],
            "parent": parent,
            "horizon_sessions": horizon,
            "reference_frozen_v1": original["reference"],
            "effect_definition_frozen_v1": original["effect"],
            "measurement_unit": unit,
            "origin_aggregation": aggregation,
            "directly_account_based": monetary,
            "required_independent_materiality_basis": evidence,
            "minimum_economically_material_effect": None,
            "independent_evidence_sha256": None,
            "independent_evidence_as_of": None,
            "unit_consistent_power_calibration": None,
            "reviewed_before_confirmatory_outcomes": False,
            "eligible_for_formal_confirmation": False,
        })
    require([row["hypothesis_id"] for row in rows] == TEST_IDS,
            "Materiality matrix differs from frozen seven hypotheses")
    return rows


def friction_sensitivity(v1, turnover=TURNOVER_EXAMPLES):
    """Simple per-traded-notional parameter budget, not realized execution cost."""
    require(v1["costs"]["base"] == EXPECTED_COSTS and
            v1["costs"]["stress"].startswith("triple spread and slippage"),
            "Cost scenarios differ from original protocol")
    require(isinstance(turnover, (tuple, list)) and bool(turnover) and
            len(set(map(str, turnover))) == len(turnover) and
            all(type(t) in (int, float) and isfinite(t) and
                0 <= t <= 1 for t in turnover),
            "Turnover examples must be distinct hypothetical NAV fractions")
    base = EXPECTED_COSTS["spreadBps"]+EXPECTED_COSTS["slippageBps"]
    stressed = 3*base
    return {
        "base_parameter_sum_bps_per_traded_notional": base,
        "triple_stress_parameter_sum_bps_per_traded_notional": stressed,
        "incremental_stress_bps_per_traded_notional": stressed-base,
        "execution_spread_convention_verified": False,
        "realized_turnover_measured": False,
        "annualized_log_alpha_threshold_derived": False,
        "illustrative_examples": [{
            "hypothetical_one_way_turnover_fraction_of_nav": t,
            "base_parameter_budget_bps_of_nav": round(base*t, 6),
            "stress_parameter_budget_bps_of_nav": round(stressed*t, 6),
            "incremental_stress_budget_bps_of_nav": round((stressed-base)*t, 6),
        } for t in turnover],
    }


def analyze(v2, v1):
    rows = materiality_rows(v2, v1)
    return {
        "schema": SCHEMA,
        "status": "independent-economic-materiality-evidence-pending",
        "frozen_development_protocol": "docs/protocolo-replay-integral-v1.json",
        "frozen_prospective_protocol": "docs/protocolo-confirmacion-integral-v2.json",
        "primary_hypotheses": len(rows),
        "economically_material_effects_justified": 0,
        "economically_material_effects_registered": False,
        "development_outcomes_used_for_threshold_selection": False,
        "market_outcomes_read": False,
        "realized_account_returns_read": False,
        "independent_power_established": False,
        "registered_v2_modified": False,
        "formal_inference_enabled": False,
        "predictive_validation": "not-established",
        "rows": rows,
        "friction_parameter_sensitivity": friction_sensitivity(v1),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    v2, v1 = read_contract()
    result = analyze(v2, v1)
    if args.verify:
        require(result["primary_hypotheses"] == 7 and
                all(row["minimum_economically_material_effect"] is None and
                    not row["eligible_for_formal_confirmation"]
                    for row in result["rows"]) and
                result["economically_material_effects_registered"] is False and
                result["formal_inference_enabled"] is False and
                result["friction_parameter_sensitivity"]
                      ["incremental_stress_bps_per_traded_notional"] == 14,
                "Readiness report incorrectly claims verified materiality")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n",
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("rows", "friction_parameter_sensitivity")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
