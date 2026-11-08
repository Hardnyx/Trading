"""Read-only prospective sample diagnostics, without observing realized returns.

The exact block sign test is a deliberately conservative comparator, not a
replacement for the frozen moving-block bootstrap or its inferential claims.
"""

import argparse
from math import comb, sqrt
from pathlib import Path
from statistics import NormalDist
import json

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/protocolo-confirmacion-integral-v2.json"
ORIGIN_COUNTS = (48, 96, 120, 192)
ILLUSTRATIVE_BLOCK_WIN_PROBABILITY = 0.8


def upper_binomial_tail(n, successes, p):
    """Exact P[X >= successes] for X ~ Binomial(n, p)."""
    if not isinstance(n, int) or n < 1 or not isinstance(successes, int):
        raise ValueError("n must be positive and successes an integer")
    if not 0 <= successes <= n + 1 or not 0 <= p <= 1:
        raise ValueError("Invalid binomial argument")
    return sum(comb(n, k) * p**k * (1 - p)**(n - k)
               for k in range(successes, n + 1))


def minimum_positive_blocks(blocks, threshold):
    """Smallest successful-block count passing a one-sided exact sign test."""
    if blocks < 1 or not 0 < threshold < 1:
        raise ValueError("Invalid sign-test design")
    return next((k for k in range(blocks + 1)
                 if upper_binomial_tail(blocks, k, 0.5) <= threshold), None)


def analyze(contract, origins=ORIGIN_COUNTS):
    """Check frozen choices; calculate only hypothetical sampling properties."""
    if contract.get("schema") != "full-engine-prospective-registration-v2":
        raise ValueError("Expected frozen prospective registration v2")
    family = contract["primary_tests"]
    if len(family) != 7 or len({row["id"] for row in family}) != 7:
        raise ValueError("Expected seven distinct preregistered tests")
    m = contract["multiplicity"]
    if m["method"] != "Holm step-down" or m["alpha"] != 0.05:
        raise ValueError("Registered Holm familywise alpha changed")
    lengths = contract["bootstrap"]["block_lengths_months"]
    if lengths != [12, 24]:
        raise ValueError("Registered 12/24-month blocks changed")
    if contract["sampling"]["minimum_mature_eligible_months"] != 96:
        raise ValueError("Registered operational monthly minimum changed")
    first_step = m["alpha"] / len(family)
    normal_z = (NormalDist().inv_cdf(1 - first_step)
                + NormalDist().inv_cdf(0.8))
    rows = []
    for months in origins:
        if not isinstance(months, int) or months < 1:
            raise ValueError("Origin counts must be positive integers")
        for length in lengths:
            blocks = months // length
            successes = minimum_positive_blocks(blocks, first_step) if blocks else None
            rows.append({
                "mature_months": months,
                "block_months": length,
                "nonoverlapping_blocks": blocks,
                "optimistic_normal_mde_block_sd": round(normal_z / sqrt(blocks), 3) if blocks else None,
                "exact_sign_min_one_sided_p": 2.0**(-blocks) if blocks else None,
                "sign_test_can_cross_first_holm_step": successes is not None,
                "sign_test_min_positive_blocks": successes,
                "illustrative_sign_power_at_p80": round(
                    upper_binomial_tail(blocks, successes, ILLUSTRATIVE_BLOCK_WIN_PROBABILITY), 6)
                if successes is not None else 0.0,
            })
    return {
        "schema": "prospective-design-sensitivity-v1",
        "study": contract["schema"],
        "kind": "hypothetical-design-only-no-outcomes-used",
        "formal_inference_performed": False,
        "target_power_illustrative": 0.8,
        "holm_first_step_alpha": first_step,
        "sign_test_assumption": "iid nonoverlapping block signs, null P(positive)=0.5",
        "sign_power_assumption": "iid nonoverlapping block signs, P(positive)=0.8 (illustrative, not estimated)",
        "not_the_registered_bootstrap": True,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Check immutable protocol without writing files")
    args = parser.parse_args()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    result = analyze(contract)
    if args.verify:
        row = next(x for x in result["rows"] if x["mature_months"] == 96
                   and x["block_months"] == 24)
        assert row["nonoverlapping_blocks"] == 4
        assert row["sign_test_can_cross_first_holm_step"] is False
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
