"""Synthetic finite-sample audit of the frozen prospective block-bootstrap test.

This diagnoses a single one-sided Holm-first-step test under artificial AR(1)
paired monthly effects. It never loads realized market returns, scored origins
or the trial log, and cannot determine the power of Trading's seven-test family.
"""
import argparse
from math import floor, sqrt
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/protocolo-confirmacion-integral-v2.json"
SCHEMA = "confirmatory-block-bootstrap-sensitivity-v1"
MONTHS = (96, 192)
PHIS = (0.0, 0.6)
SHIFTS = (0.0, 0.5)
REPETITIONS = 512
SEED = 20261109


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def protocol_parameters(protocol):
    require(protocol.get("schema") == "full-engine-prospective-registration-v2" and
            protocol.get("status") ==
            "registered-methodology-inactive-confirmatory-inference" and
            protocol["activation"]["formal_inference_enabled"] is False and
            protocol["activation"]["confirmatory_collection_open"] is False,
            "This audit requires inactive frozen confirmatory inference")
    tests = protocol["primary_tests"]
    require(len(tests) == 7 and len({t["id"] for t in tests}) == 7,
            "The seven-test family was modified")
    multiple = protocol["multiplicity"]
    require(multiple["method"] == "Holm step-down" and
            multiple["alpha"] == 0.05 and
            multiple["direction"] == "one-sided positive advantage",
            "Holm first-step definition changed")
    bootstrap = protocol["bootstrap"]
    require(bootstrap["block_lengths_months"] == [12, 24] and
            bootstrap["draws"] == 10000 and
            bootstrap["seed"] == 20261030 and
            bootstrap["minimum_complete_blocks"] == 4 and
            protocol["sampling"]["minimum_mature_eligible_months"] == 96,
            "The registered bootstrap or 96-month minimum changed")
    return multiple["alpha"] / len(tests), bootstrap["draws"], tuple(
        bootstrap["block_lengths_months"])


def ar1_series(rng, length, phi):
    """Stationary Gaussian AR(1) with unconditional variance one."""
    require(length > 0 and 0 <= phi < 1, "Invalid synthetic AR(1) parameters")
    innovation_scale = sqrt(1 - phi * phi)
    values = [rng.gauss(0, 1)]
    for _ in range(1, length):
        values.append(phi * values[-1] + innovation_scale * rng.gauss(0, 1))
    return values


def wilson_interval(rejected, repetitions, z=1.96):
    """Descriptive Monte Carlo uncertainty, not a predictive CI."""
    require(isinstance(repetitions, int) and repetitions > 0 and
            isinstance(rejected, int) and 0 <= rejected <= repetitions,
            "Invalid simulated rejection count")
    p = rejected / repetitions
    denominator = 1 + z*z / repetitions
    midpoint = (p + z*z / (2*repetitions)) / denominator
    half = z / denominator * sqrt(
        p*(1-p)/repetitions + z*z/(4*repetitions*repetitions))
    return [round(max(0, midpoint-half), 6),
            round(min(1, midpoint+half), 6)]


def first_step_reject(values, block, alpha, draws, rng):
    """Frozen centered circular-block one-sided p, using exact early stop.

    A rejection requires at most floor(alpha*(draws+1)-1) null exceedances.
    Once more exceedances occur, no additional draw can reverse non-rejection.
    Early stopping is computational only, not an interim evaluation of returns.
    """
    length = len(values)
    require(length > 0 and 0 < block <= length and length % block == 0 and
            0 < alpha < 1 and isinstance(draws, int) and draws >= 1,
            "Incompatible monthly bootstrap design")
    observed = sum(values) / length
    if observed <= 0:
        return False
    permitted = floor(alpha*(draws+1) - 1)
    if permitted < 0:
        return False
    centered = [v - observed for v in values]
    wrap = centered + centered[:block-1]
    prefix = [0.0]
    for v in wrap:
        prefix.append(prefix[-1] + v)
    block_sums = [prefix[i+block] - prefix[i] for i in range(length)]
    pieces = length // block
    exceedances = 0
    for _ in range(draws):
        sampled_sum = sum(block_sums[rng.randrange(length)]
                          for _ in range(pieces))
        if sampled_sum / length >= observed:
            exceedances += 1
            if exceedances > permitted:
                return False
    return (1 + exceedances) / (draws + 1) <= alpha


def simulate(protocol, repetitions=REPETITIONS, seed=SEED,
             months=MONTHS, phis=PHIS, shifts=SHIFTS):
    first_alpha, draws, blocks = protocol_parameters(protocol)
    require(type(repetitions) is int and repetitions > 0 and
            type(seed) is int and seed >= 0 and
            all(type(n) is int and n >= 96 for n in months) and
            all(0 <= phi < 1 for phi in phis) and
            all(shift >= 0 for shift in shifts) and
            all(n % block == 0 for n in months for block in blocks),
            "Invalid synthetic scenario grid")
    observations = {(n, phi, shift, block): 0 for n in months for phi in phis
                    for shift in shifts for block in blocks}
    # Two stable, independently seeded streams ensure the generator does not
    # inherit the number of resamples spent on previous synthetic samples.
    series_rng = random.Random(seed)
    bootstrap_rng = random.Random(seed + 1)
    for n in months:
        for phi in phis:
            for _ in range(repetitions):
                base = ar1_series(series_rng, n, phi)
                for shift in shifts:
                    values = [x + shift for x in base]
                    for block in blocks:
                        observations[n, phi, shift, block] += first_step_reject(
                            values, block, first_alpha, draws, bootstrap_rng)
    rows = []
    for (n, phi, shift, block), rejected in sorted(observations.items()):
        rows.append({
            "months": n,
            "block_months": block,
            "ar1_phi_assumed": phi,
            "mean_effect_in_unconditional_sd_assumed": shift,
            "simulations": repetitions,
            "reject_first_holm_step": rejected,
            "simulated_rejection_rate": round(rejected / repetitions, 6),
            "monte_carlo_wilson95": wilson_interval(rejected, repetitions),
        })
    return {
        "schema": SCHEMA,
        "status": "hypothetical-finite-sample-diagnostic-only",
        "hypotheses_evaluated": "one marginal paired-effect series against first Holm threshold",
        "not_familywise_error_or_trading_power": True,
        "no_realized_or_confirmatory_data_read": True,
        "retrospective_returns_used": False,
        "formal_inference_activated": False,
        "holm_first_step_alpha": first_alpha,
        "max_bootstrap_draws_per_repetition": draws,
        "bootstrap_resampling": "centered circular moving blocks; one-sided p; early non-rejection cutoff",
        "ar1_null": "stationary Gaussian AR1, variance one",
        "assumed_shift_units": "unconditional standard deviation of monthly effects, not an economic threshold",
        "simulation_seed": seed,
        "rows": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", help="Optional public synthetic design diagnostic JSON")
    args = parser.parse_args(argv)
    contract = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    result = simulate(contract)
    if args.verify:
        require(len(result["rows"]) == 16 and
                result["no_realized_or_confirmatory_data_read"] is True and
                all(r["simulations"] == REPETITIONS for r in result["rows"]) and
                result["formal_inference_activated"] is False,
                "Frozen synthetic design simulation did not reproduce")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n",
                          encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA, "scenarios": len(result["rows"]),
        "simulations_per_scenario": REPETITIONS,
        "nominal_first_holm_alpha": result["holm_first_step_alpha"],
        "inferential_activation": False,
        "trading_predictive_validation": "not-established",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
