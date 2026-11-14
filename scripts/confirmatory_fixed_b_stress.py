"""Independent synthetic stress audit of two precommitted fixed-b candidates.

The design (docs/estudio-calibracion-fixed-b-v1.json) was published before
this implementation. Arm A keeps the failed Bartlett lag-12 statistic and
replaces its Gaussian tail by the fixed-b reference for b = 12/n; arm B uses
the full-bandwidth Kiefer-Vogelsang-Bunzel statistic (b = 1). Both arms are
evaluated on the frozen HAC synthetic generator with a new seed, Holm over the
seven v2 tests and exact simultaneous bounds over 128 intervals. It never
reads market returns, enables the prospective v2 protocol or selects an arm.
"""
import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

import numpy as np

if __package__:
    from .confirmatory_familywise_bootstrap import verify_protocol, require
    from .confirmatory_calibration_gate import exact_binomial_limits
    from .confirmatory_hac_stress import (synthetic_effects, holm_masks, seed_for,
                                          FAMILY, MONTHS, PHIS, RHOS, INNOVATIONS,
                                          NULL_LAYOUTS, NULL_INDICES, SHIFTED_INDICES,
                                          TEST_IDS, BURN)
else:
    from confirmatory_familywise_bootstrap import verify_protocol, require
    from confirmatory_calibration_gate import exact_binomial_limits
    from confirmatory_hac_stress import (synthetic_effects, holm_masks, seed_for,
                                         FAMILY, MONTHS, PHIS, RHOS, INNOVATIONS,
                                         NULL_LAYOUTS, NULL_INDICES, SHIFTED_INDICES,
                                         TEST_IDS, BURN)

ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "docs/estudio-calibracion-fixed-b-v1.json"
DESIGN_GIT_BLOB_SHA1 = "44a46e21d9adf1a33a569618be2add89c91b21b1"
SCHEMA = "confirmatory-fixed-b-independent-stress-v1"
ALPHA = 0.05
REPETITIONS = 512
SEED = 20261114
REFERENCE_SEED = 20261115
REFERENCE_LENGTH = 1200
REFERENCE_DRAWS = 100000
REFERENCE_CHUNK = 2000
LAG_A = 12
SCENARIOS_PER_ARM = 64
INTERVALS = 128
ARMS = ("A-fixed-b-lag12", "B-kvb-full-bandwidth")


def read_design(path=DESIGN_PATH):
    raw = Path(path).read_bytes()
    blob = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    require(hashlib.sha1(blob).hexdigest() == DESIGN_GIT_BLOB_SHA1,
            "Published fixed-b prespecification changed")
    design = json.loads(raw)
    validate_design(design)
    return design


def validate_design(design):
    require(design.get("schema") == "confirmatory-fixed-b-independent-stress-design-v1"
            and design.get("design_role") ==
            "exploratory-synthetic-precommitment-not-inference-registration"
            and design.get("registration_base_commit") ==
            "b2e8faf31bd1d39da7aa0bb22168665b763f6e3a",
            "Independent fixed-b study identity changed")
    require([arm["id"] for arm in design["arms"]] == list(ARMS),
            "Registered arms changed")
    ref = design["reference_distribution"]
    require(ref["series_length"] == REFERENCE_LENGTH
            and ref["draws_per_b"] == REFERENCE_DRAWS
            and ref["reference_seed"] == REFERENCE_SEED
            and ref["bandwidth_lags_by_b"] == {"0.125": 150, "0.0625": 75, "1": 1199}
            and ref["independent_of_evaluation_seed"] is True,
            "Registered reference distribution changed")
    multi = design["multiplicity"]
    require(multi["alpha"] == ALPHA and multi["hypotheses"] == TEST_IDS
            and multi["procedure"] == "Holm step-down on marginal p-values"
            and multi["true_null_indices_partial"] == list(NULL_INDICES)
            and multi["shifted_false_null_indices_partial"] == list(SHIFTED_INDICES)
            and multi["shifted_effect_in_marginal_sd_units"] == 0.5,
            "Frozen test family or synthetic effect changed")
    dgp = design["synthetic_data"]
    require(dgp["monthly_counts"] == list(MONTHS) and dgp["ar1_phi"] == list(PHIS)
            and dgp["cross_hypothesis_factor_correlations"] == list(RHOS)
            and dgp["innovation_families"] == list(INNOVATIONS)
            and dgp["null_configurations"] == list(NULL_LAYOUTS)
            and dgp["autoregression_burn_in_months"] == BURN
            and dgp["repetitions_per_scenario"] == REPETITIONS
            and dgp["independent_simulation_seed"] == SEED
            and dgp["scenario_count_per_arm"] == SCENARIOS_PER_ARM,
            "Published scenario grid or simulation budget modified")
    calibration = design["calibration_evaluation"]
    require(calibration["nominal_familywise_error"] == ALPHA
            and calibration["simultaneous_confidence"] == 0.95
            and calibration["interval_count"] == INTERVALS
            and calibration["per_tail_probability"] == 0.05/(2*INTERVALS)
            and calibration["candidate_approval_permitted"] is False
            and calibration["arm_or_bandwidth_selection_by_inspected_results_permitted"] is False
            and calibration["both_arms_reported_whatever_the_result"] is True,
            "Unregistered synthetic decision rule")
    activation = design["activation"]
    require(design["real_market_data_permitted"] is False
            and activation["registered_v2_modified"] is False
            and activation["confirmatory_collection_open"] is False
            and activation["formal_inference_enabled"] is False
            and activation["no_market_outcomes_read"] is True,
            "Synthetic diagnostics must not enable market inference")


def bartlett_statistics(columns, lags):
    """sqrt(n)*mean/sqrt(Bartlett LRV), demeaned gamma_k with divisor n.

    Autocovariances come from one FFT per series, so every lag up to n-1 costs
    the same as a few. Non-positive or non-finite LRV gives NaN (p = 1).
    """
    x = np.asarray(columns, dtype=np.float64)
    require(x.ndim >= 2 and np.all(np.isfinite(x)), "Statistics need finite series")
    n = x.shape[-1]
    require(type(lags) is int and 0 <= lags < n, "Bandwidth must lie in [0, n-1]")
    centered = x - x.mean(axis=-1, keepdims=True)
    size = 1 << (2*n - 1).bit_length()
    spectrum = np.fft.rfft(centered, n=size, axis=-1)
    gamma = np.fft.irfft(spectrum*np.conj(spectrum), n=size, axis=-1)[..., :lags+1]/n
    weights = 1 - np.arange(1, lags+1)/(lags+1)
    lrv = gamma[..., 0] + 2*np.sum(gamma[..., 1:]*weights, axis=-1)
    stat = np.full(lrv.shape, np.nan)
    good = np.isfinite(lrv) & (lrv > 0)
    stat[good] = x.mean(axis=-1)[good]*np.sqrt(n/lrv[good])
    return stat


def reference_seed(b, seed=REFERENCE_SEED):
    token = f"{seed}|{b}"
    return int.from_bytes(hashlib.sha256(token.encode("ascii")).digest()[:8], "big")


def reference_distribution(b, lags, draws=REFERENCE_DRAWS, length=REFERENCE_LENGTH,
                           chunk=REFERENCE_CHUNK):
    """Sorted null statistics on independent Gaussian series for one b."""
    rng = np.random.Generator(np.random.PCG64(reference_seed(b)))
    values = []
    left = draws
    while left:
        size = min(chunk, left)
        values.append(bartlett_statistics(rng.standard_normal((size, length)), lags))
        left -= size
    ref = np.concatenate(values)
    require(np.all(np.isfinite(ref)), "Reference statistics must be finite")
    return np.sort(ref)


def monte_carlo_pvalues(stats, sorted_reference):
    """(1 + #{ref >= t}) / (1 + R); undefined statistics give p = 1."""
    stats = np.asarray(stats, dtype=np.float64)
    r = len(sorted_reference)
    p = np.ones_like(stats)
    good = np.isfinite(stats)
    exceed = r - np.searchsorted(sorted_reference, stats[good], side="left")
    p[good] = (1 + exceed)/(1 + r)
    return p


def arm_lags(arm, n):
    return LAG_A if arm == ARMS[0] else n - 1


def arm_b(arm, n):
    return {96: "0.125", 192: "0.0625"}[n] if arm == ARMS[0] else "1"


def simulate(design, protocol, repetitions=REPETITIONS, draws=REFERENCE_DRAWS):
    validate_design(design)
    hypotheses, alpha, _, _ = verify_protocol(protocol)
    require(hypotheses == FAMILY and alpha == ALPHA and type(repetitions) is int
            and repetitions > 0 and type(draws) is int and draws > 0,
            "Registered v2 seven-test family or simulation inputs changed")
    lags_by_b = design["reference_distribution"]["bandwidth_lags_by_b"]
    references = {b: reference_distribution(b, lags, draws=draws) for b, lags in lags_by_b.items()}
    tail = 0.05/(2*INTERVALS)
    rows = []
    for n, phi, rho, innovation, layout in product(MONTHS, PHIS, RHOS, INNOVATIONS, NULL_LAYOUTS):
        rng = np.random.Generator(np.random.PCG64(seed_for(n, phi, rho, innovation, layout, seed=SEED)))
        effects = synthetic_effects(rng, n, phi, rho, innovation, layout, repetitions=repetitions)
        null_columns = list(range(FAMILY)) if layout == "global" else list(NULL_INDICES)
        for arm in ARMS:
            stats = bartlett_statistics(effects, arm_lags(arm, n))
            pvalues = monte_carlo_pvalues(stats, references[arm_b(arm, n)])
            rejected = holm_masks(pvalues)
            count = int(np.any(rejected[:, null_columns], axis=1).sum())
            lower, upper = exact_binomial_limits(count, repetitions, tail)
            rows.append({
                "arm": arm, "fixed_b": float(arm_b(arm, n)), "bandwidth_lags": arm_lags(arm, n),
                "months": n, "ar1_phi_assumed": phi, "cross_hypothesis_rho_assumed": rho,
                "innovation_family": innovation, "null_configuration": layout,
                "true_null_indices": null_columns, "independent_repetitions": repetitions,
                "false_family_rejections": count,
                "false_family_rate": round(count/repetitions, 6),
                "simultaneous_exact95_interval": [round(lower, 6), round(upper, 6)],
                "lower_bound_above_nominal": lower > ALPHA,
                "upper_bound_at_or_below_nominal": upper <= ALPHA,
                "undefined_statistic_count": int(np.count_nonzero(~np.isfinite(stats))),
                "shifted_false_null_any_rejections": (
                    int(np.any(rejected[:, list(SHIFTED_INDICES)], axis=1).sum())
                    if layout == "partial" else None),
            })
    require(len(rows) == INTERVALS, "Precommitted interval count changed")
    arms = {}
    for arm in ARMS:
        part = [row for row in rows if row["arm"] == arm]
        excess = sum(row["lower_bound_above_nominal"] for row in part)
        grid_upper = all(row["upper_bound_at_or_below_nominal"] for row in part)
        rates = [row["false_family_rate"] for row in part]
        power = [row["shifted_false_null_any_rejections"]/repetitions for row in part
                 if row["null_configuration"] == "partial"]
        arms[arm] = {
            "synthetic_excess_fwer_scenarios": excess,
            "synthetic_grid_upper_bounds_all_below_nominal": grid_upper,
            "synthetic_calibration_result": ("excess-rejection-detected" if excess else
                                             "grid-upper-bounds-met" if grid_upper else "inconclusive"),
            "false_family_rate_range": [min(rates), max(rates)],
            "shifted_detection_rate_range_descriptive": [round(min(power), 6), round(max(power), 6)],
        }
    return {
        "schema": SCHEMA,
        "study_design_git_blob_sha1": DESIGN_GIT_BLOB_SHA1,
        "scope": "independent-synthetic-fixed-b-research-only",
        "design_frozen_before_simulation": True,
        "simulation_seed": SEED,
        "reference_seed": REFERENCE_SEED,
        "repetitions_per_scenario": repetitions,
        "reference_draws_per_b": draws,
        "design_budget_fully_executed": repetitions == REPETITIONS and draws == REFERENCE_DRAWS,
        "interval_count": INTERVALS,
        "nominal_holm_familywise_alpha": alpha,
        "simultaneous_confidence_over_128_intervals": 0.95,
        "arms": arms,
        "candidate_approved_for_market_inference": False,
        "arm_or_bandwidth_selected_from_results": False,
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
    protocol = json.loads((ROOT/"docs/protocolo-confirmacion-integral-v2.json").read_text(encoding="utf-8"))
    report = simulate(design, protocol)
    if args.verify:
        require(report["design_budget_fully_executed"] is True
                and report["interval_count"] == INTERVALS
                and set(report["arms"]) == set(ARMS)
                and report["candidate_approved_for_market_inference"] is False
                and report["market_outcomes_read"] is False
                and report["formal_inference_enabled"] is False,
                "Fixed-b design verification failed")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, sort_keys=True))


if __name__ == "__main__":
    main()
