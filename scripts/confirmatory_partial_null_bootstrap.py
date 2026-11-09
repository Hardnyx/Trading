"""Stress-test frozen seven-test Holm inference with a partially true synthetic null.

A known-parameter Gaussian oracle provides an exact-marginal control. The
registered centered circular block bootstrap is evaluated with all seven
jointly resampled columns. This study uses no real market observations.
"""
import argparse
import json
from math import isfinite
from pathlib import Path
import random

import numpy as np

if __package__:
    from .confirmatory_familywise_bootstrap import (
        _block_sums, gaussian_ar1_oracle_pvalues, joint_null_series,
        require, stable_seed, verify_protocol, wilson,
    )
else:
    from confirmatory_familywise_bootstrap import (
        _block_sums, gaussian_ar1_oracle_pvalues, joint_null_series,
        require, stable_seed, verify_protocol, wilson,
    )

SCHEMA = "confirmatory-partial-null-holm-v1"
MONTHS = (96, 192)
PHIS = (0.6,)
RHOS = (0.0, 0.75)
NULL_INDICES = frozenset((0, 1, 2, 3))
SHIFTED_INDICES = frozenset((4, 5, 6))
SHIFT_SD = 0.5
REPETITIONS = 128
SEED = 20261110


def holm_rejections(pvalues, alpha=0.05):
    """Return rejected indices from full Holm step-down, including ties."""
    require(len(pvalues) == 7 and 0 < alpha < 1 and
            all(isinstance(p, (float, int)) and isfinite(p) and
                0 <= p <= 1 for p in pvalues),
            "Holm requires seven finite p-values in [0,1]")
    ordered = sorted(range(7), key=lambda i: (pvalues[i], i))
    rejected = set()
    for rank, index in enumerate(ordered):
        if pvalues[index] > alpha/(7-rank):
            break
        rejected.add(index)
    return frozenset(rejected)


def joint_bootstrap_holm_rejections(columns, block, draw_indices, alpha=0.05):
    """Compute exact seven-test Holm decisions from shared bootstrap indices.

    Every column uses the same circular monthly draws. Vectorized evaluation
    keeps the registered 10,000 draws rather than approximating decisions
    with fewer draws or altering the hypothesis thresholds.
    """
    require(0 < alpha < 1, "Invalid Holm threshold")
    blocks, observed = _block_sums(columns, block)
    n = len(columns[0])
    indices = np.asarray(draw_indices)
    require(indices.ndim == 2 and indices.shape[0] > 0 and
            indices.shape[1] == n//block and
            np.issubdtype(indices.dtype, np.integer) and
            np.all((indices >= 0) & (indices < n)),
            "Bootstrap draws must be valid common circular-block indices")
    block_sums = np.asarray(blocks, dtype=np.float64)
    targets = np.asarray(observed, dtype=np.float64)
    counts = np.zeros(7, dtype=np.int64)
    for offset in range(0, indices.shape[0], 512):
        sample = indices[offset:offset+512]
        boot_totals = block_sums[:, sample].sum(axis=2)
        counts += np.count_nonzero(boot_totals >= targets[:, None], axis=1)
    pvalues = (1+counts)/(indices.shape[0]+1)
    return holm_rejections(pvalues.tolist(), alpha)


def simulate(protocol, repetitions=REPETITIONS, seed=SEED,
             months=MONTHS, phis=PHIS, rhos=RHOS):
    tests, alpha, draws, blocks = verify_protocol(protocol)
    require(tests == 7 and len(NULL_INDICES | SHIFTED_INDICES) == 7
            and not (NULL_INDICES & SHIFTED_INDICES)
            and len(NULL_INDICES) == 4 and len(SHIFTED_INDICES) == 3
            and type(repetitions) is int and repetitions > 0
            and type(seed) is int and seed >= 0
            and all(type(n) is int and n >= 96 for n in months)
            and all(n % block == 0 for n in months for block in blocks)
            and all(0 <= phi < 1 for phi in phis)
            and all(0 <= rho < 1 for rho in rhos),
            "Invalid partial-null simulation design")
    rows = []
    for n in months:
        for phi in phis:
            for rho in rhos:
                effects_rng = random.Random(
                    stable_seed(seed, n, phi, rho, "partial-effects"))
                block_rngs = {block: np.random.Generator(np.random.PCG64(
                    stable_seed(seed, n, phi, rho, "partial-bootstrap", block)))
                    for block in blocks}
                totals = {block: {
                    "false_family_rejections": 0,
                    "false_family_oracle_only": 0,
                    "false_family_bootstrap_only": 0,
                    "any_shifted_rejections": 0,
                } for block in blocks}
                oracle_errors = 0
                for _ in range(repetitions):
                    columns = joint_null_series(effects_rng, n, phi, rho, tests)
                    for index in SHIFTED_INDICES:
                        columns[index] = [value+SHIFT_SD for value in columns[index]]
                    oracle = holm_rejections(
                        gaussian_ar1_oracle_pvalues(columns, phi), alpha)
                    oracle_false = bool(oracle & NULL_INDICES)
                    oracle_errors += int(oracle_false)
                    for block in blocks:
                        draw_indices = block_rngs[block].integers(
                            0, n, size=(draws, n//block), dtype=np.int32)
                        rejected = joint_bootstrap_holm_rejections(
                            columns, block, draw_indices, alpha)
                        bootstrap_false = bool(rejected & NULL_INDICES)
                        row = totals[block]
                        row["false_family_rejections"] += int(bootstrap_false)
                        row["false_family_bootstrap_only"] += int(
                            bootstrap_false and not oracle_false)
                        row["false_family_oracle_only"] += int(
                            oracle_false and not bootstrap_false)
                        row["any_shifted_rejections"] += int(
                            bool(rejected & SHIFTED_INDICES))
                for block in blocks:
                    counts = totals[block]
                    rows.append({
                        "months": n,
                        "monthly_ar1_phi_assumed": phi,
                        "cross_test_rho_assumed": rho,
                        "block_months": block,
                        "repetitions": repetitions,
                        **counts,
                        "bootstrap_false_family_rate": round(
                            counts["false_family_rejections"]/repetitions, 6),
                        "bootstrap_wilson95": wilson(
                            counts["false_family_rejections"], repetitions),
                        "oracle_false_family_rejections": oracle_errors,
                        "oracle_false_family_rate": round(
                            oracle_errors/repetitions, 6),
                        "oracle_wilson95": wilson(oracle_errors, repetitions),
                    })
    return {
        "schema": SCHEMA,
        "status": "synthetic-partial-null-stress-only",
        "true_null_indices": sorted(NULL_INDICES),
        "shifted_false_null_indices": sorted(SHIFTED_INDICES),
        "shifted_effect_unconditional_sd_assumed": SHIFT_SD,
        "hypotheses": [test["id"] for test in protocol["primary_tests"]],
        "nominal_familywise_alpha": alpha,
        "bootstrap_draws_per_replication": draws,
        "simulation_seed": seed,
        "real_market_outcomes_used": False,
        "registered_v2_modified": False,
        "confirmatory_inference_enabled": False,
        "strong_fwer_control_not_established": True,
        "oracle_uses_known_synthetic_phi": True,
        "oracle_not_applicable_to_unknown_market_dgp": True,
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
        require(len(result["rows"]) == 8 and
                all(r["repetitions"] == REPETITIONS and
                    r["false_family_rejections"] - r["oracle_false_family_rejections"] ==
                    r["false_family_bootstrap_only"] - r["false_family_oracle_only"]
                    for r in result["rows"]) and
                result["real_market_outcomes_used"] is False and
                result["confirmatory_inference_enabled"] is False,
                "Partial-null diagnostic did not reproduce")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA, "scenarios": len(result["rows"]),
        "repetitions_per_scenario": REPETITIONS,
        "confirmatory_inference_enabled": False,
        "trading_skill": "not-established",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
