"""Registered synthetic calibration of the three-test 21-session family (H0.3 redesign)."""
import argparse
import hashlib
import json
from math import sqrt
from pathlib import Path

import numpy as np
from scipy.stats import t as student

try:
    from .confirmatory_fixed_b_stress import bartlett_statistics, monte_carlo_pvalues
    from .confirmatory_calibration_gate import exact_binomial_limits
except ImportError:
    from confirmatory_fixed_b_stress import bartlett_statistics, monte_carlo_pvalues
    from confirmatory_calibration_gate import exact_binomial_limits

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-calibracion-familia-21-v1.json"
FAMILY, ALPHA, BURN = 3, 0.05, 256
ARMS = ("A-iid-student-t", "B-kvb-full-bandwidth")


def scenario_seed(seed, n, phi, rho, innovation, layout):
    token = f"{seed}|{n}|{phi}|{rho}|{innovation}|{layout}"
    return int.from_bytes(hashlib.sha256(token.encode("ascii")).digest()[:8], "big")


def synthetic_effects(rng, n, phi, rho, innovation, layout, repetitions, design):
    shape = (repetitions, n + BURN, FAMILY + 1)
    shocks = rng.standard_normal(shape) if innovation == "gaussian" else rng.standard_t(5, size=shape) / sqrt(5 / 3)
    last = np.zeros((repetitions, FAMILY + 1))
    effects = np.empty((repetitions, n, FAMILY + 1))
    scale = sqrt(1 - phi * phi)
    for t in range(n + BURN):
        last = phi * last + scale * shocks[:, t, :]
        if t >= BURN:
            effects[:, t - BURN, :] = last
    out = (sqrt(rho) * effects[:, :, :1] + sqrt(1 - rho) * effects[:, :, 1:]).transpose(0, 2, 1).copy()
    if layout == "partial":
        m = design["multiplicity"]
        out[:, m["shifted_false_null_indices_partial"], :] += m["shifted_effect_in_marginal_sd_units"]
    return out


def holm(p, alpha=ALPHA):
    order = np.argsort(p, axis=1, kind="stable")
    ordered = np.take_along_axis(p, order, axis=1)
    reject_sorted = np.logical_and.accumulate(ordered <= alpha / np.arange(p.shape[1], 0, -1), axis=1)
    mask = np.zeros_like(reject_sorted)
    np.put_along_axis(mask, order, reject_sorted, axis=1)
    return mask


def iid_pvalues(x):
    n = x.shape[-1]
    stat = x.mean(axis=-1) / (x.std(axis=-1, ddof=1) / sqrt(n))
    return student.sf(stat, n - 1)


def kvb_reference(seed, draws=100000, length=1200, chunk=2000):
    rng = np.random.Generator(np.random.PCG64(seed))
    values, left = [], draws
    while left:
        size = min(chunk, left)
        values.append(bartlett_statistics(rng.standard_normal((size, length)), length - 1))
        left -= size
    return np.sort(np.concatenate(values))


def simulate(design, repetitions=None, draws=100000):
    syn, cal = design["synthetic_data"], design["calibration_evaluation"]
    repetitions = repetitions or syn["repetitions_per_scenario"]
    reference = kvb_reference(syn["reference_seed"], draws=draws)
    true_null = {"global": list(range(FAMILY)), "partial": design["multiplicity"]["true_null_indices_partial"]}
    rows = []
    for n in syn["monthly_counts"]:
        for phi in syn["ar1_phi"]:
            for rho in syn["cross_hypothesis_factor_correlations"]:
                for innovation in syn["innovation_families"]:
                    for layout in syn["null_configurations"]:
                        rng = np.random.Generator(np.random.PCG64(
                            scenario_seed(syn["independent_simulation_seed"], n, phi, rho, innovation, layout)))
                        x = synthetic_effects(rng, n, phi, rho, innovation, layout, repetitions, design)
                        for arm in ARMS:
                            p = iid_pvalues(x) if arm == ARMS[0] else monte_carlo_pvalues(bartlett_statistics(x, n - 1), reference)
                            reject = holm(p)
                            false = int(np.any(reject[:, true_null[layout]], axis=1).sum())
                            lower, upper = exact_binomial_limits(false, repetitions, cal["per_tail_probability"])
                            row = {"arm": arm, "months": n, "phi": phi, "rho": rho, "innovation": innovation, "null": layout,
                                   "false_family_rejections": false, "rate": false / repetitions,
                                   "simultaneous_lower": lower, "simultaneous_upper": upper, "excess": lower > ALPHA}
                            if layout == "partial":
                                shifted = design["multiplicity"]["shifted_false_null_indices_partial"]
                                row["detection"] = float(np.any(reject[:, shifted], axis=1).mean())
                            rows.append(row)
    summary = {}
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        low = [r for r in mine if r["phi"] <= 0.3]
        summary[arm] = {"excess_scenarios": sum(r["excess"] for r in mine), "of": len(mine),
                        "excess_in_non_overlapping_design_phi_le_0_3": sum(r["excess"] for r in low), "of_design": len(low),
                        "all_upper_bounds_le_5pct_phi_le_0_3": all(r["simultaneous_upper"] <= ALPHA for r in low),
                        "rate_range": [min(r["rate"] for r in mine), max(r["rate"] for r in mine)],
                        "detection_range": [min(r["detection"] for r in mine if "detection" in r),
                                            max(r["detection"] for r in mine if "detection" in r)],
                        "excess_by_phi": {str(phi): sum(r["excess"] for r in mine if r["phi"] == phi) for phi in syn["ar1_phi"]}}
    return {"schema": "confirmatory-21-session-family-stress-v1", "repetitions": repetitions, "reference_draws": draws,
            "design_budget_fully_executed": repetitions == syn["repetitions_per_scenario"] and draws == 100000,
            "summary": summary, "rows": rows, "candidate_approved_for_market_inference": False,
            "formal_inference_enabled": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/calibracion-familia-21-v1.json")
    options = parser.parse_args()
    result = simulate(json.loads(DESIGN.read_text(encoding="utf-8")))
    options.output.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
