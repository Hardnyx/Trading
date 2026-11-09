"""Lower bound on the calendar required for a frozen monthly prospective study.

This is arithmetic on the registered cadence, not a forecast of trading
sessions, missing observations or the probability of holding a model cohort.
No market outcomes are loaded and the inactive v2 contract is not modified.
"""
import argparse
import json
from pathlib import Path
import re

if __package__:
    from .confirmatory_familywise_bootstrap import verify_protocol, require
else:
    from confirmatory_familywise_bootstrap import verify_protocol, require

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "confirmatory-minimum-calendar-feasibility-v1"
EXPECTED_FIRST_MONTH = "2026-11"
EXPECTED_FIRST_POSSIBLE_CUT = "2026-11-09"
EXPECTED_MIN_MONTHS = 96
EXPECTED_MAX_HORIZON_SESSIONS = 252


def parse_month(month):
    require(isinstance(month, str) and
            re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) is not None,
            "Expected a canonical YYYY-MM month")
    year, m = map(int, month.split("-"))
    require(year >= 1, "Invalid calendar year")
    return year*12 + m-1


def format_month(zero_based_month):
    require(type(zero_based_month) is int and zero_based_month >= 12,
            "Invalid calendar month ordinal")
    year, month = divmod(zero_based_month, 12)
    return f"{year:04d}-{month+1:02d}"


def earliest_eligible_months(first_month, count):
    require(type(count) is int and count > 0,
            "Eligible monthly origin count must be a positive integer")
    first = parse_month(first_month)
    return [format_month(first+offset) for offset in range(count)]


def evaluate(protocol):
    family, alpha, draws, blocks = verify_protocol(protocol)
    schedule = protocol["sampling"]
    require(schedule["first_month"] == EXPECTED_FIRST_MONTH
            and schedule["first_possible_cut"] == EXPECTED_FIRST_POSSIBLE_CUT
            and schedule["origin_frequency"] == "monthly"
            and schedule["cut_rule"] ==
            "last observed US-exchange closing session of each NY calendar month"
            and schedule["minimum_mature_eligible_months"] ==
            EXPECTED_MIN_MONTHS
            and schedule["minimum_contiguous_months_for_largest_block"] ==
            EXPECTED_MIN_MONTHS
            and schedule["exclude_previously_examined"] is True
            and schedule["retain_absent_months"] is True
            and schedule["exclude_missing_from_numerator_without_replacing_with_cash"] is True
            and protocol["activation"]["confirmatory_collection_open"] is False
            and protocol["activation"]["formal_inference_enabled"] is False
            and protocol["horizons_sessions"] == [21, 63, 252]
            and family == 7 and alpha == .05
            and draws == 10000 and blocks == (12, 24)
            and protocol["fixed_cohort"]["restart_incompatible_changes"] is True
            and protocol["fixed_cohort"]["never_pool_code_or_source_cohorts"] is True,
            "Prospective cadence, horizon or frozen-cohort conditions changed")
    months = earliest_eligible_months(
        schedule["first_month"], schedule["minimum_mature_eligible_months"])
    first, last = months[0], months[-1]
    require(first == "2026-11" and last == "2034-10" and len(months) == 96,
            "Unexpected 96-month lower bound")
    return {
        "schema": SCHEMA,
        "scope": "best-case-calendar-lower-bound-no-market-outcomes",
        "first_possible_month": first,
        "earliest_month_of_96th_eligible_origin": last,
        "monthly_origins_required": len(months),
        "full_months_spanned_inclusive": len(months),
        "monthly_boundaries_after_first_before_last": len(months)-1,
        "scenario": "one eligible full-engine origin every month, no missing months and no model cohort resets",
        "eligible_months_all_observed_or_verified": False,
        "calendar_eligibility_guaranteed": False,
        "all_original_source_vintages_verified": False,
        "full_engine_original_forecasts_archived": False,
        "longest_registered_horizon_sessions": EXPECTED_MAX_HORIZON_SESSIONS,
        "full_horizon_maturity_rule": "last eligible origin needs 252 actual observed US-exchange sessions after origin, not 252 calendar days",
        "full_horizon_maturity_at_96th_origin": False,
        "calendar_date_of_final_252_session_outcome_estimated": None,
        "confirmation_can_finish_at_96th_origin": False,
        "any_missing_eligible_month_or_cohort_restart_can_delay_lower_bound": True,
        "previously_inspected_development_cuts_used_as_independent": False,
        "method_replacement_by_calendar_shortcut_permitted": False,
        "registered_v2_modified": False,
        "formal_inference_enabled": False,
        "predictive_validity_established": False,
        "idealized_months": months,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    protocol = json.loads(
        (ROOT/"docs/protocolo-confirmacion-integral-v2.json")
        .read_text(encoding="utf-8"))
    result = evaluate(protocol)
    if args.verify:
        require(result["earliest_month_of_96th_eligible_origin"] == "2034-10"
                and result["monthly_origins_required"] == 96
                and result["confirmation_can_finish_at_96th_origin"] is False
                and result["calendar_date_of_final_252_session_outcome_estimated"] is None
                and result["formal_inference_enabled"] is False,
                "Prospective calendar lower bound misreported")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)
                               + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k != "idealized_months"}, sort_keys=True))


if __name__ == "__main__":
    main()
