"""Compute Gaussian AR(1) power requirements for the frozen seven-test family.

An analytical sensitivity study, not a power guarantee for empirical Trading
scores. The score standard deviation and AR(1) parameters are treated as known
oracle inputs. No observed returns, forecasts or future labels are loaded.
"""
import argparse
import json
from math import isfinite, sqrt
from pathlib import Path

from scipy.stats import norm

try:
    from scripts.confirmatory_familywise_bootstrap import verify_protocol, require
except ModuleNotFoundError:
    from confirmatory_familywise_bootstrap import verify_protocol, require

SCHEMA = "confirmatory-gaussian-power-feasibility-v1"
MONTHS = (96, 192, 360)
PHIS = (0.0, 0.3, 0.6, 0.85)
EFFECTS_SD = (0.1, 0.25, 0.5)
TARGET_POWER = 0.8
MAX_MONTHS = 50000


def valid_scalar(value):
    return type(value) in (int, float) and isfinite(value)


def sum_variance(n, phi):
    """Exact variance of the sum of n stationary unit-variance Gaussian AR1s."""
    require(type(n) is int and n >= 1 and valid_scalar(phi) and 0 <= phi < 1,
            "Invalid Gaussian AR1 sample length or autocorrelation")
    if phi == 0:
        return float(n)
    # Sum_{k=1}^{n-1} (n-k)*phi**k, closed form without an O(n) loop.
    result = n + 2*phi*((n-1)-n*phi+phi**n)/(1-phi)**2
    require(result > 0 and isfinite(result), "Invalid Gaussian AR1 sum variance")
    return result


def gaussian_power(n, phi, effect_sd, alpha, family=7):
    """Lower-bound power of individual Holm rejection via its first threshold.

    Known sigma, known phi, one-sided normal test and normal alternative are
    assumed. Probability of crossing alpha/m is a lower bound on power to
    reject that hypothesis after full Holm step-down, if p-values are valid.
    """
    require(valid_scalar(effect_sd) and effect_sd >= 0
            and valid_scalar(alpha) and 0 < alpha < 1
            and type(family) is int and family >= 1,
            "Invalid Gaussian power configuration")
    return float(norm.sf(norm.isf(alpha/family) - effect_sd*n/sqrt(sum_variance(n, phi))))


def minimum_detectable_effect(n, phi, alpha, target_power=TARGET_POWER, family=7):
    """Minimum positive mean advantage in unconditional monthly SD units."""
    require(valid_scalar(alpha) and 0 < alpha < 1 and
            type(family) is int and family >= 1 and
            valid_scalar(target_power) and alpha/family < target_power < 1,
            "Target power must exceed nominal first-step rejection rate")
    return float((norm.isf(alpha/family) + norm.isf(1-target_power))
                 *sqrt(sum_variance(n, phi))/n)


def months_for_power(phi, effect_sd, alpha, target_power=TARGET_POWER,
                     family=7, max_months=MAX_MONTHS):
    """Find minimal n using the exact finite-n AR1 sum variance.

    Returns None when the prespecified search ceiling is insufficient, rather
    than inventing a feasible confirmation horizon.
    """
    require(valid_scalar(effect_sd) and effect_sd > 0
            and type(max_months) is int and max_months >= 1,
            "Positive hypothetical effect and month ceiling required")
    if gaussian_power(max_months, phi, effect_sd, alpha, family) < target_power:
        return None
    low, high = 1, max_months
    while low < high:
        mid = (low+high)//2
        if gaussian_power(mid, phi, effect_sd, alpha, family) >= target_power:
            high = mid
        else:
            low = mid+1
    return low


def evaluate(protocol):
    family, alpha, draws, blocks = verify_protocol(protocol)
    require(protocol["multiplicity"]["alpha"] == .05 and
            family == 7 and alpha == .05 and draws == 10000 and blocks == (12, 24),
            "Seven-test frozen confirmatory family was modified")
    economic = protocol["economic_effect_thresholds"]
    require(economic.get("status") == "unjustified-power-not-established" and
            all(economic.get(k) is None for k in
                ("return_mse", "ranking_ic", "net_economic_value")),
            "Economic effects must not be inferred from hypothetical SD units")
    rows = []
    for phi in PHIS:
        for n in MONTHS:
            v = sum_variance(n, phi)
            entry = {
                "months": n,
                "monthly_ar1_phi_assumed": phi,
                "effective_independent_months_oracle": round(n*n/v, 6),
                "monthly_sd_for_effect": "assumed-known-unit",
                "min_effect_sd_for_80pct_first_holm_step_power": round(
                    minimum_detectable_effect(n, phi, alpha, TARGET_POWER, family), 6),
                "power_by_hypothetical_effect_sd": {
                    f"{effect:.2f}": round(gaussian_power(n, phi, effect, alpha, family), 6)
                    for effect in EFFECTS_SD
                },
            }
            rows.append(entry)
    requirements = [
        {"monthly_ar1_phi_assumed": phi,
         "effect_monthly_sd_assumed": effect,
         "minimum_months_for_80pct_first_step_power": months_for_power(
             phi, effect, alpha, TARGET_POWER, family)}
        for phi in PHIS for effect in EFFECTS_SD
    ]
    return {
        "schema": SCHEMA,
        "scope": "analytical-Gaussian-AR1-sensitivity-only",
        "family_count": family,
        "nominal_familywise_alpha": alpha,
        "first_holm_step_alpha": alpha/family,
        "target_individual_power": TARGET_POWER,
        "monthly_standard_deviation_known": "assumed-for-analytic-oracle-only",
        "ar1_phi_known": "assumed-for-analytic-oracle-only",
        "familywise_power_not_estimated": True,
        "real_market_effect_thresholds_registered": False,
        "bootstrap_calibration_repaired": False,
        "market_data_read": False,
        "registered_v2_modified": False,
        "formal_inference_enabled": False,
        "trading_predictive_validation": "not-established",
        "max_months_hypothetical_search": MAX_MONTHS,
        "rows": rows,
        "requirements": requirements,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root/"docs/protocolo-confirmacion-integral-v2.json")
                          .read_text(encoding="utf-8"))
    result = evaluate(protocol)
    if args.verify:
        require(len(result["rows"]) == len(MONTHS)*len(PHIS)
                and len(result["requirements"]) == len(PHIS)*len(EFFECTS_SD)
                and all(row["effective_independent_months_oracle"] <= row["months"]
                        for row in result["rows"])
                and result["formal_inference_enabled"] is False
                and result["real_market_effect_thresholds_registered"] is False,
                "Gaussian power sensitivity failed reproducibility checks")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n",
                               encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows", "requirements")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
