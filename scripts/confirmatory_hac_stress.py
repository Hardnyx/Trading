"""Independent synthetic stress audit of a precommitted Bartlett HAC candidate.

The design was published before this implementation. It tests the finite
sample false familywise rejection frequency of marginal one-sided HAC normal
p-values with complete Holm step-down. It never reads market returns, enables
the prospective v2 protocol or selects a method for real-market inference.
"""
import argparse
import hashlib
import json
from itertools import product
from math import isfinite, sqrt
from pathlib import Path

import numpy as np
from scipy.stats import norm

if __package__:
    from .confirmatory_familywise_bootstrap import verify_protocol, require
    from .confirmatory_calibration_gate import exact_binomial_limits
else:
    from confirmatory_familywise_bootstrap import verify_protocol, require
    from confirmatory_calibration_gate import exact_binomial_limits

ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "docs/estudio-calibracion-hac-v1.json"
DESIGN_GIT_BLOB_SHA1 = "aac38411e5b157cc4ce0db5788b94005050635c9"
SCHEMA = "confirmatory-hac-independent-stress-v1"
ALPHA = 0.05
REPETITIONS = 512
SEED = 20261112
LAG = 12
FAMILY = 7
MONTHS = (96, 192)
PHIS = (0.0, 0.3, 0.6, 0.85)
RHOS = (0.0, 0.75)
INNOVATIONS = ("gaussian", "standardized_student_t_df5")
NULL_LAYOUTS = ("global", "partial")
BURN = 256
GRID_COUNT = 64
NULL_INDICES = (0, 1, 2, 3)
SHIFTED_INDICES = (4, 5, 6)
TEST_IDS = [f"{family}:{h}" for family in ("return_mse", "ranking_ic")
            for h in (21, 63, 252)] + ["net_economic_value:21"]


def read_design(path=DESIGN_PATH):
    raw = Path(path).read_bytes()
    blob = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    digest = hashlib.sha1(blob).hexdigest()
    require(digest == DESIGN_GIT_BLOB_SHA1,
            "Published diagnostic prespecification changed")
    design = json.loads(raw)
    validate_design(design)
    return design


def validate_design(design):
    require(design.get("schema") == "confirmatory-hac-independent-stress-design-v1"
            and design.get("design_role") ==
            "exploratory-synthetic-precommitment-not-inference-registration"
            and design.get("registration_base_commit") ==
            "ef0899c935197315a66b9341616b7d7bce20d0d8",
            "Independent synthetic study identity changed")
    method = design["method"]
    require(method["lag_months"] == LAG
            and method["lag_tuning_permitted"] is False
            and method["autocovariance_divisor"] == "n"
            and method["p_value"] == "scipy.stats.norm.sf(test_statistic)"
            and method["nonpositive_or_nonfinite_lrv_p_value"] == 1,
            "Fixed Bartlett HAC candidate modified")
    multi = design["multiplicity"]
    require(multi["alpha"] == ALPHA
            and multi["hypotheses"] == TEST_IDS
            and multi["procedure"] == "Holm step-down on marginal p-values"
            and multi["true_null_indices_partial"] == list(NULL_INDICES)
            and multi["shifted_false_null_indices_partial"] ==
            list(SHIFTED_INDICES)
            and multi["shifted_effect_in_marginal_sd_units"] == 0.5,
            "Frozen test family or synthetic effect changed")
    dgp = design["synthetic_data"]
    require(dgp["monthly_counts"] == list(MONTHS)
            and dgp["ar1_phi"] == list(PHIS)
            and dgp["cross_hypothesis_factor_correlations"] == list(RHOS)
            and dgp["innovation_families"] == list(INNOVATIONS)
            and dgp["null_configurations"] == list(NULL_LAYOUTS)
            and dgp["autoregression_burn_in_months"] == BURN
            and dgp["repetitions_per_scenario"] == REPETITIONS
            and dgp["independent_simulation_seed"] == SEED
            and dgp["scenario_count"] == GRID_COUNT,
            "Published scenario grid or simulation budget modified")
    calibration = design["calibration_evaluation"]
    require(calibration["nominal_familywise_error"] == ALPHA
            and calibration["simultaneous_confidence"] == 0.95
            and calibration["per_tail_probability"] == 0.05/(2*GRID_COUNT)
            and calibration["candidate_approval_permitted"] is False
            and calibration["method_or_bandwidth_selection_by_inspected_results_permitted"] is False,
            "Unregistered synthetic decision rule")
    activation = design["activation"]
    require(design["real_market_data_permitted"] is False
            and activation["registered_v2_modified"] is False
            and activation["confirmatory_collection_open"] is False
            and activation["formal_inference_enabled"] is False
            and activation["no_market_outcomes_read"] is True,
            "Synthetic diagnostics must not enable market inference")


def seed_for(n, phi, rho, innovation, null_layout, seed=SEED):
    token = f"{seed}|{n}|{phi:g}|{rho:g}|{innovation}|{null_layout}"
    return int.from_bytes(hashlib.sha256(token.encode("ascii")).digest()[:8],
                          "big")


def synthetic_effects(rng, n, phi, rho, innovation, null_layout,
                      repetitions=REPETITIONS, burn=BURN):
    """Independent replicates; common-factor correlated stationary AR1 effects.

    Burn-in removes zero initial conditions. Student-t5 shocks are scaled to
    unit variance; all seven columns retain marginal unconditional unit
    variance. No outcome or risk model parameter is inferred from markets.
    """
    require(type(n) is int and n > LAG
            and 0 <= phi < 1 and 0 <= rho < 1
            and innovation in INNOVATIONS and null_layout in NULL_LAYOUTS
            and type(repetitions) is int and repetitions > 0
            and type(burn) is int and burn >= 0,
            "Invalid synthetic effect inputs")
    shape = (repetitions, n+burn, FAMILY+1)
    if innovation == "gaussian":
        shocks = rng.standard_normal(shape)
    else:
        shocks = rng.standard_t(5, size=shape) / sqrt(5/3)
    last = np.zeros((repetitions, FAMILY+1), dtype=np.float64)
    effects = np.empty((repetitions, n, FAMILY+1), dtype=np.float64)
    scale = sqrt(1-phi*phi)
    for t in range(n+burn):
        last = phi*last + scale*shocks[:, t, :]
        if t >= burn:
            effects[:, t-burn, :] = last
    out = (sqrt(rho)*effects[:, :, :1] +
           sqrt(1-rho)*effects[:, :, 1:]).transpose(0, 2, 1).copy()
    if null_layout == "partial":
        out[:, SHIFTED_INDICES, :] += 0.5
    return out


def hac_one_sided_pvalues(columns, lag=LAG):
    """Bartlett long-run variance, demeaned gamma_k with divisor n."""
    x = np.asarray(columns, dtype=np.float64)
    require(x.ndim == 3 and x.shape[1] == FAMILY and x.shape[2] > lag
            and type(lag) is int and lag >= 0
            and np.all(np.isfinite(x)),
            "HAC effects require aligned finite monthly series")
    n = x.shape[2]
    avg = x.mean(axis=2)
    centered = x - avg[:, :, None]
    long_run_var = np.sum(centered*centered, axis=2)/n
    for k in range(1, lag+1):
        gamma = np.sum(centered[:, :, k:] * centered[:, :, :-k],
                       axis=2)/n
        long_run_var += 2*(1-k/(lag+1))*gamma
    good = np.isfinite(long_run_var) & (long_run_var > 0)
    p = np.ones_like(avg)
    z = avg[good]*np.sqrt(n/long_run_var[good])
    p[good] = norm.sf(z)
    return p, int(np.count_nonzero(~good))


def holm_masks(pvalues, alpha=ALPHA):
    """Full Holm step-down; one rejection in any true null is a false family."""
    p = np.asarray(pvalues, dtype=np.float64)
    require(p.ndim == 2 and p.shape[1] == FAMILY
            and np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
            and 0 < alpha < 1, "Invalid seven-test marginal probabilities")
    order = np.argsort(p, axis=1, kind="stable")
    ordered = np.take_along_axis(p, order, axis=1)
    cutoffs = alpha/np.arange(FAMILY, 0, -1)
    sorted_reject = np.logical_and.accumulate(ordered <= cutoffs, axis=1)
    mask = np.zeros_like(sorted_reject, dtype=bool)
    np.put_along_axis(mask, order, sorted_reject, axis=1)
    return mask


def simulate(design, protocol, repetitions=REPETITIONS):
    validate_design(design)
    hypotheses, alpha, _, _ = verify_protocol(protocol)
    require(hypotheses == FAMILY and alpha == ALPHA and
            type(repetitions) is int and repetitions > 0,
            "Registered v2 seven-test family or simulation inputs changed")
    rows = []
    for n, phi, rho, innovation, layout in product(
            MONTHS, PHIS, RHOS, INNOVATIONS, NULL_LAYOUTS):
        random = np.random.Generator(np.random.PCG64(
            seed_for(n, phi, rho, innovation, layout)))
        effects = synthetic_effects(
            random, n, phi, rho, innovation, layout, repetitions=repetitions)
        pvalues, invalid = hac_one_sided_pvalues(effects)
        rejected = holm_masks(pvalues)
        null_columns = range(FAMILY) if layout == "global" else NULL_INDICES
        false = np.any(rejected[:, list(null_columns)], axis=1)
        count = int(false.sum())
        lower, upper = exact_binomial_limits(
            count, repetitions, 0.05/(2*GRID_COUNT))
        row = {
            "months": n, "ar1_phi_assumed": phi,
            "cross_hypothesis_rho_assumed": rho,
            "innovation_family": innovation, "null_configuration": layout,
            "true_null_indices": list(null_columns),
            "independent_repetitions": repetitions,
            "false_family_rejections": count,
            "false_family_rate": round(count/repetitions, 6),
            "simultaneous_exact95_interval": [round(lower, 6),
                                                round(upper, 6)],
            "lower_bound_above_nominal": lower > ALPHA,
            "upper_bound_at_or_below_nominal": upper <= ALPHA,
            "invalid_long_run_variance_count": invalid,
            "shifted_false_null_any_rejections": (
                int(np.any(rejected[:, list(SHIFTED_INDICES)], axis=1).sum())
                if layout == "partial" else None),
        }
        rows.append(row)
    require(len(rows) == GRID_COUNT, "Precommitted scenario count changed")
    excess = sum(row["lower_bound_above_nominal"] for row in rows)
    grid_upper = all(row["upper_bound_at_or_below_nominal"] for row in rows)
    return {
        "schema": SCHEMA,
        "study_design_git_blob_sha1": DESIGN_GIT_BLOB_SHA1,
        "scope": "independent-synthetic-HAC-research-only",
        "design_frozen_before_simulation": True,
        "simulation_seed": SEED,
        "repetitions_per_scenario": repetitions,
        "design_repetition_count_fully_executed": repetitions == REPETITIONS,
        "synthetic_scenario_count": GRID_COUNT,
        "hac_lag_months_fixed": LAG,
        "normal_asymptotic_p_values_not_exact": True,
        "nominal_holm_familywise_alpha": alpha,
        "simultaneous_confidence_over_64_scenarios": 0.95,
        "synthetic_excess_fwer_scenarios": excess,
        "synthetic_grid_upper_bounds_all_below_nominal": grid_upper,
        "synthetic_calibration_result": (
            "excess-rejection-detected" if excess else
            "grid-upper-bounds-met" if grid_upper else "inconclusive"),
        "candidate_approved_for_market_inference": False,
        "lag_or_dgp_selected_from_results": False,
        "market_outcomes_read": False,
        "original_v2_modified": False,
        "formal_inference_enabled": False,
        "predictive_skill_established": False,
        "rows": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    design = read_design()
    protocol = json.loads(
        (ROOT/"docs/protocolo-confirmacion-integral-v2.json")
        .read_text(encoding="utf-8"))
    report = simulate(design, protocol)
    if args.verify:
        require(report["design_repetition_count_fully_executed"] is True
                and report["synthetic_scenario_count"] == GRID_COUNT
                and report["candidate_approved_for_market_inference"] is False
                and report["market_outcomes_read"] is False
                and report["formal_inference_enabled"] is False,
                "HAC design verification failed")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+"\n",
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
