"""Months needed to detect economically material effects with the three-test family.

Analytic, outcome-free: thresholds come from external conventions, dispersions
from sampling theory or stated tracking-error ranges, never from Trading data.
Gaussian known-variance power at Holm's first step (alpha/3) is an optimistic
lower bound on the months a calibrated KVB test would need.
"""
import argparse
import json
from math import ceil, sqrt
from pathlib import Path

from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
ALPHA, FAMILY, POWER = 0.05, 3, 0.80


def months_needed(delta_sd, phi=0.0, alpha=ALPHA / FAMILY, power=POWER):
    """Smallest n with Gaussian one-sided power >= target for AR(1) effects."""
    z = norm.ppf(1 - alpha) + norm.ppf(power)
    n = ceil((z / delta_sd) ** 2)
    while True:
        variance = n + 2 * sum((n - k) * phi ** k for k in range(1, min(n, 400)))
        if n * delta_sd / sqrt(variance) >= z:
            return n
        n += 1


def scenarios():
    rows = []
    # Ranking IC: under no skill a monthly Spearman IC over N names has sd
    # about 1/sqrt(N-1); the model-minus-benchmark difference adds the
    # benchmark's sampling error with correlation r between the two ICs.
    for names in (100, 160):
        for corr in (0.0, 0.5):
            for extra in (0.0, 0.05):  # time variation of true IC (sd per month)
                sd = sqrt(2 * (1 - corr) / (names - 1) + extra ** 2)
                for threshold in (0.02, 0.03):
                    rows.append({"test": "ranking_ic:21", "threshold": threshold, "unit": "Spearman points per month",
                                 "assumptions": {"names": names, "ic_correlation": corr, "true_ic_sd": extra},
                                 "difference_sd": round(sd, 4), "delta_sd": round(threshold / sd, 4),
                                 "months_phi0": months_needed(threshold / sd), "months_phi03": months_needed(threshold / sd, .3)})
    # Net economic value: annual threshold over a stated annual tracking error.
    for threshold in (0.01, 0.02):
        for tracking in (0.02, 0.04, 0.06):
            delta = (threshold / 12) / (tracking / sqrt(12))
            rows.append({"test": "net_economic_value:21", "threshold": threshold, "unit": "annualized log return net of costs",
                         "assumptions": {"tracking_error_annual": tracking}, "difference_sd": round(tracking / sqrt(12), 4),
                         "delta_sd": round(delta, 4), "months_phi0": months_needed(delta), "months_phi03": months_needed(delta, .3)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/potencia-v3-familia-21.json")
    options = parser.parse_args()
    report = {"schema": "confirmatory-v3-power-feasibility-v1", "alpha_first_holm_step": ALPHA / FAMILY, "power": POWER,
              "method": "Gaussian known variance, AR(1) effects; optimistic lower bound for KVB",
              "sources": {"ranking_ic": "Grinold and Kahn, Active Portfolio Management: IC 0.05 good, 0.10 very good; increments of 0.02-0.03 are material at broad breadth",
                          "net_economic_value": "1-2% a year: the range of active management fees an investor would need to beat net",
                          "return_mse": "Campbell and Thompson (2008): monthly R2_OS of about 0.5% is economically meaningful for a mean-variance investor; its months are not computed because the dispersion of squared-error differences has no outcome-free value"},
              "rows": scenarios(), "market_outcomes_read": False, "formal_inference_enabled": False}
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    for r in report["rows"]:
        print(r["test"], r["threshold"], r["assumptions"], "dsd", r["delta_sd"], "n0", r["months_phi0"], "n.3", r["months_phi03"])


if __name__ == "__main__":
    main()
