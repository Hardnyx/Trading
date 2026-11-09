"""Audit the frozen seven-test Holm entry threshold using synthetic monthly effects.

Under a complete global null, Holm rejects at least one hypothesis exactly
when one marginal p-value crosses alpha/7. A common block-index draw is
reused for all seven simulated test series, preserving cross-test dependence.
No observed market outcomes are loaded and the protocol is never modified.
"""
import argparse
import hashlib
import json
from math import floor, sqrt
from pathlib import Path
import random

SCHEMA = "confirmatory-joint-null-bootstrap-v1"
MONTHS = (96, 192)
AUTOCORRELATIONS = (0.0, 0.6)
CROSS_TEST_CORRELATIONS = (0.0, 0.75)
REPETITIONS = 256
SEED = 20261109


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def verify_protocol(protocol):
    require(protocol.get("schema") == "full-engine-prospective-registration-v2"
            and protocol.get("status") ==
            "registered-methodology-inactive-confirmatory-inference"
            and protocol["activation"]["formal_inference_enabled"] is False
            and protocol["activation"]["confirmatory_collection_open"] is False,
            "Registered v2 inference must remain inactive")
    tests = protocol["primary_tests"]
    require([t["id"] for t in tests] ==
            [f"{kind}:{h}" for kind in ("return_mse", "ranking_ic")
             for h in (21, 63, 252)] + ["net_economic_value:21"],
            "Registered seven-test hypothesis family changed")
    multi = protocol["multiplicity"]
    require(multi["method"] == "Holm step-down"
            and multi["alpha"] == 0.05
            and multi["direction"] == "one-sided positive advantage",
            "Registered Holm criterion changed")
    bootstrap = protocol["bootstrap"]
    require(bootstrap["block_lengths_months"] == [12, 24]
            and bootstrap["draws"] == 10000
            and bootstrap["seed"] == 20261030
            and bootstrap["minimum_complete_blocks"] == 4
            and protocol["sampling"]["minimum_mature_eligible_months"] == 96,
            "Registered block bootstrap or sampling requirement changed")
    return (len(tests), multi["alpha"], bootstrap["draws"],
            tuple(bootstrap["block_lengths_months"]))


def ar1(rng, n, phi):
    """Stationary Gaussian AR(1) with zero mean and unit variance."""
    require(n > 0 and 0 <= phi < 1, "Invalid AR(1) parameters")
    scale = sqrt(1 - phi*phi)
    last = rng.gauss(0, 1)
    values = [last]
    for _ in range(n-1):
        last = phi*last + scale*rng.gauss(0, 1)
        values.append(last)
    return values


def joint_null_series(rng, n, phi, rho, tests=7):
    """Common-factor Gaussian effects with contemporaneous correlation rho."""
    require(0 <= rho < 1 and tests == 7,
            "Invalid synthetic test correlation/family")
    common = ar1(rng, n, phi)
    shared, independent = sqrt(rho), sqrt(1-rho)
    return [
        [shared*common[t] + independent*local[t] for t in range(n)]
        for local in (ar1(rng, n, phi) for _ in range(tests))
    ]


def holm_any_reject(pvalues, alpha=0.05):
    """Under complete null, any Holm rejection starts with min(p)<=alpha/7."""
    require(len(pvalues) == 7 and 0 < alpha < 1 and
            all(0 <= p <= 1 for p in pvalues),
            "Invalid Holm family p-values")
    return min(pvalues) <= alpha / len(pvalues)


def _block_sums(columns, block):
    require(len(columns) == 7 and
            all(isinstance(col, list) and col for col in columns),
            "Seven nonempty monthly effect series are required")
    n = len(columns[0])
    require(all(len(col) == n for col in columns) and n >= 96 and
            0 < block <= n and n % block == 0,
            "Joint monthly matrix must have aligned eligible months")
    all_blocks, targets = [], []
    for col in columns:
        target = sum(col)
        centered = [x-target/n for x in col]
        extended = centered + centered[:block-1]
        prefix = [0.0]
        for value in extended:
            prefix.append(prefix[-1]+value)
        all_blocks.append(
            [prefix[i+block]-prefix[i] for i in range(n)])
        targets.append(target)
    return all_blocks, targets


def joint_bootstrap_pvalues(columns, block, draws, rng):
    """Non-stopping reference for tests; share block indices across columns."""
    n = len(columns[0])
    sums, observed = _block_sums(columns, block)
    counts = [0]*len(columns)
    for _ in range(draws):
        chosen = [rng.randrange(n) for _ in range(n//block)]
        for j, target in enumerate(observed):
            if sum(sums[j][i] for i in chosen) >= target:
                counts[j] += 1
    return [(1+count)/(draws+1) for count in counts]


def joint_first_holm_reject(columns, block, draws, rng, alpha=0.05):
    """Full-null Holm-any decision with common centered moving-block draws.

    Early non-rejection is exact: once all seven marginal exceedance counts
    exceed the first-step threshold, further draws cannot cause rejection.
    """
    require(type(draws) is int and draws >= 1 and 0 < alpha < 1,
            "Invalid registered bootstrap settings")
    blocks, observed = _block_sums(columns, block)
    n = len(columns[0])
    limit = floor((alpha/7)*(draws+1)-1)
    if limit < 0:
        return False
    eligible = [i for i, value in enumerate(observed) if value > 0]
    if not eligible:
        return False
    exceed = [0]*7
    for _ in range(draws):
        selected = [rng.randrange(n) for _ in range(n//block)]
        for j in eligible[:]:
            if sum(blocks[j][i] for i in selected) >= observed[j]:
                exceed[j] += 1
                if exceed[j] > limit:
                    eligible.remove(j)
        if not eligible:
            return False
    return bool(eligible)


def stable_seed(seed, n, phi, rho, role, block=None):
    """Derive stable scenario seeds without dependence on iteration order."""
    raw = f"{seed}|{n}|{phi:.3f}|{rho:.3f}|{role}|{block}".encode("ascii")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def wilson(k, n, z=1.96):
    """Monte Carlo uncertainty of simulated rejection rate, not market risk."""
    require(type(k) is int and type(n) is int and 0 <= k <= n and n > 0,
            "Invalid simulation rejection count")
    p = k/n
    den = 1+z*z/n
    mid = (p+z*z/(2*n))/den
    half = z/den*sqrt(p*(1-p)/n+z*z/(4*n*n))
    return [round(max(0, mid-half), 6), round(min(1, mid+half), 6)]


def simulate(protocol, repetitions=REPETITIONS, seed=SEED, months=MONTHS,
             phis=AUTOCORRELATIONS, rhos=CROSS_TEST_CORRELATIONS):
    count, alpha, draws, lengths = verify_protocol(protocol)
    require(type(repetitions) is int and repetitions > 0
            and type(seed) is int and seed >= 0
            and all(type(n) is int and n >= 96 for n in months)
            and all(n % b == 0 for n in months for b in lengths)
            and all(0 <= phi < 1 for phi in phis)
            and all(0 <= rho < 1 for rho in rhos),
            "Invalid synthetic global-null scenario grid")
    rows = []
    for n in months:
        for phi in phis:
            for rho in rhos:
                series_rng = random.Random(
                    stable_seed(seed, n, phi, rho, "effects"))
                block_rngs = {
                    b: random.Random(stable_seed(
                        seed, n, phi, rho, "bootstrap", b))
                    for b in lengths
                }
                rejected = {b: 0 for b in lengths}
                for _ in range(repetitions):
                    columns = joint_null_series(series_rng, n, phi, rho, count)
                    for b in lengths:
                        rejected[b] += joint_first_holm_reject(
                            columns, b, draws, block_rngs[b], alpha)
                for b in lengths:
                    k = rejected[b]
                    rows.append({
                        "months": n,
                        "block_months": b,
                        "monthly_ar1_phi_assumed": phi,
                        "cross_test_rho_assumed": rho,
                        "synthetic_tests": count,
                        "null_repetitions": repetitions,
                        "familywise_any_rejections": k,
                        "familywise_null_rejection_rate": round(
                            k/repetitions, 6),
                        "monte_carlo_wilson95": wilson(k, repetitions),
                    })
    return {
        "schema": SCHEMA,
        "scope": "seven-correlated-synthetic-effects-under-complete-global-null",
        "trading_outcomes_read": False,
        "real_market_effects_used": False,
        "confirmatory_collection_open": False,
        "formal_inference_enabled": False,
        "strong_fwer_control_not_established": True,
        "family_test_names": [t["id"] for t in protocol["primary_tests"]],
        "assumed_dgp": "stationary equicorrelated Gaussian common-factor AR1 effects",
        "not_economic_power_or_actual_seven_hypothesis_scores": True,
        "nominal_holm_familywise_alpha": alpha,
        "bootstrap_draws_per_replication": draws,
        "bootstrap_rule": "centered circular 12/24-month blocks; shared months for seven tests",
        "simulation_seed": seed,
        "rows": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root/"docs/protocolo-confirmacion-integral-v2.json")
                          .read_text(encoding="utf-8"))
    result = simulate(protocol)
    if args.verify:
        require(len(result["rows"]) == 16 and
                all(r["null_repetitions"] == REPETITIONS
                    for r in result["rows"]) and
                result["trading_outcomes_read"] is False and
                result["formal_inference_enabled"] is False,
                "Joint global-null calibration did not reproduce")
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA, "scenarios": len(result["rows"]),
        "null_repetitions_per_scenario": REPETITIONS,
        "formal_inference_enabled": False,
        "trading_skill": "not-established",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
