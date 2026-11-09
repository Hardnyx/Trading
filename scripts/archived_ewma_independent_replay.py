"""Independently reconstruct the frozen pilot's annualized joint EWMA covariance.

This reproduces risk arithmetic from the archived prices without rerunning
the optimizer or changing its decisions. It cannot certify vendor price vintages,
historical model selection, or predictive skill.
"""
import argparse
from datetime import date
import json
import math
from pathlib import Path

try:
    from .historical_parameter_audit import load, build_report
except ImportError:
    from historical_parameter_audit import load, build_report

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def returns_by_day(asset, cut):
    """Mirror dailyReturns on dated adjusted closes, rejecting bad chronology."""
    result = {}
    previous = None
    last_day = ""
    for row in asset["history"]:
        day = row["date"]
        price = row["adj_close"]
        require(isinstance(day, str) and day > last_day and day <= cut,
                "Nonmonotone or future dated risk training price")
        require(type(price) in (int, float) and math.isfinite(price) and price > 0,
                "Invalid risk training adjusted close")
        if previous is not None:
            value = math.log(price / previous)
            require(math.isfinite(value), "Nonfinite risk training log return")
            result[day] = value
        previous, last_day = price, day
    return result


def aligned_returns(assets, cut, lookback=500):
    """Preserve alignReturns date intersection and first-asset ordering."""
    require(assets and all("history" in a for a in assets), "Missing aligned assets")
    maps = [returns_by_day(a, cut) for a in assets]
    dates = sorted(d for d in maps[0] if all(d in m for m in maps[1:]))[-lookback:]
    require(len(dates) >= 20 and dates[-1] == cut,
            "Insufficient common returns or calibration does not end at cut")
    return dates, [[m[d] for d in dates] for m in maps]


def joint_ewma_covariance(columns, decay):
    """Independent Python version of risk-math.mjs; log daily, annual output."""
    require(columns and 0 < decay < 1 and
            len(columns[0]) >= 20 and
            all(len(a) == len(columns[0]) for a in columns),
            "Invalid EWMA sample or decay")
    n = len(columns)
    count = len(columns[0])
    initial = min(60, count)
    averages = [sum(a[:initial]) / initial for a in columns]
    covariance = [
        [sum((columns[i][t] - averages[i]) *
             (columns[j][t] - averages[j]) for t in range(initial)) /
         (initial - 1) for j in range(n)] for i in range(n)
    ]
    for t in range(initial, count):
        for i in range(n):
            for j in range(n):
                covariance[i][j] = (
                    decay * covariance[i][j] +
                    (1 - decay) * columns[i][t] * columns[j][t]
                )
    return [
        [covariance[i][j] * 252 * (1 if i == j else .95)
         for j in range(n)] for i in range(n)
    ]


def snapshot_assets(origin, symbols):
    snapshot = origin["snapshot"]
    originals = {a["symbol"]: a for a in snapshot["assets"]}
    require(len(originals) == len(snapshot["assets"]) and
            "SPY" in originals, "Duplicate/missing original benchmark")
    assets = []
    for symbol in symbols:
        if symbol == "CASH" and "CASH" not in originals:
            rows = [{"date": r["date"], "adj_close": 1.0}
                    for r in originals["SPY"]["history"]]
            assets.append({"symbol": "CASH", "history": rows})
        else:
            require(symbol in originals, "Prepared symbol is not in frozen snapshot")
            assets.append(originals[symbol])
    require(len(set(symbols)) == len(symbols), "Duplicate prepared risk symbol")
    return assets, originals["SPY"]


def check_matrix(observed, expected):
    n = len(expected)
    require(len(observed) == n and
            all(isinstance(row, list) and len(row) == n for row in observed),
            "Archived EWMA covariance dimensions changed")
    largest = 0.0
    for i in range(n):
        for j in range(n):
            actual, independent = observed[i][j], expected[i][j]
            require(type(actual) in (float, int) and math.isfinite(actual),
                    "Archived EWMA covariance is nonfinite")
            error = abs(actual - independent)
            largest = max(largest, error)
            require(error <= 1e-10 + 2e-9 * max(abs(actual), abs(independent)),
                    "Archived EWMA covariance differs from independent replay")
    return largest


def check_origin(origin, record):
    cut = origin["cut"]
    require(origin["snapshot"]["price_as_of"] == cut and
            record["cut"] == cut, "Origin and recorded risk cut differ")
    prepared, settings = record["prepared"], record["proposal"]["settings"]
    require(settings["volatilityMode"] == "ewma" and
            settings.get("volatilityData") is None, "GJR/hybrid risk is not the frozen pilot")
    symbols = prepared["symbols"]
    assets, spy = snapshot_assets(origin, symbols)
    days, columns = aligned_returns(assets, cut)
    require(prepared["observations"] == len(days) and
            prepared["calibration_end"] == days[-1],
            "Archived EWMA sample window or cut differs")
    has_factor = prepared["factor_covariance"].get("available") is True
    if has_factor and "SPY" not in symbols:
        factor_days, factor_columns = aligned_returns([*assets, spy], cut)
        require(len(factor_days) >= 126 and factor_days[-1] == cut,
                "Registered factor evidence lacks SPY alignment")
        expected = [row[:len(symbols)] for row in
                    joint_ewma_covariance(factor_columns, settings["lambda"])[:len(symbols)]]
        risk_basis = "joint-with-SPY"
    else:
        expected = joint_ewma_covariance(columns, settings["lambda"])
        risk_basis = "joint-with-SPY" if has_factor else "joint-fallback"
    largest = check_matrix(prepared["covariance"], expected)
    annual_vol = prepared["annual_volatility"]
    require(len(annual_vol) == len(symbols), "Missing archived annual volatilities")
    for i, row in enumerate(annual_vol):
        require(row["symbol"] == symbols[i] and
                math.isclose(row["value"], math.sqrt(max(0, expected[i][i])),
                             rel_tol=2e-9, abs_tol=1e-10),
                "Archived annual volatility does not match independent variance")
    return {
        "cut": cut,
        "symbols": len(symbols),
        "common_return_intervals": len(days),
        "calibration_end": days[-1],
        "decay": settings["lambda"],
        "risk_basis": risk_basis,
        "maximum_absolute_covariance_discrepancy": largest,
        "reconstructed_from_archived_adjusted_prices": True,
        "independent_historical_price_vintages_verified": False,
        "causal_parameters_certified": False,
    }


def audit(root=ROOT):
    protocol, summary, bundle, full = load(root)
    provenance = build_report(protocol, summary, bundle, full)
    require(provenance["historical_model_parameters_verified"] == 0 and
            provenance["cut_count"] == len(bundle["origins"]),
            "Archived provenance changed eligibility unexpectedly")
    require(len(bundle["origins"]) == len(full["results"]), "Archived origin mismatch")
    rows = [check_origin(o, r) for o, r in
            zip(bundle["origins"], full["results"])]
    return {
        "schema": "archived-ewma-independent-replay-v1",
        "source_market_commit": bundle["source_market_commit"],
        "archived_input_sha256": summary["input_file_sha256"],
        "archived_full_results_sha256": summary["full_results_sha256"],
        "scope": "retrospective-development-fixed-policy",
        "numeric_risk_replay_passed": True,
        "cuts": rows,
        "historical_model_parameters_certified": 0,
        "full_engine_eligible_cuts": 0,
        "production_eligible": False,
        "predictive_validation": "not-established",
        "limitations": [
            "archive is compiled after decisions and uses subsequently adjusted prices",
            "no original vendor price-vintage certification or ex-ante selection evidence",
            "no independent re-estimation of GJR, returns, Monte Carlo or portfolio decisions",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="Verify frozen risk arithmetic without writing files")
    parser.add_argument("--output", default="out/archived-ewma-independent-replay-v1.json")
    options = parser.parse_args(argv)
    report = audit()
    if not options.verify:
        target = Path(options.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "cuts": len(report["cuts"]), "symbols": [r["symbols"] for r in report["cuts"]],
        "numeric_risk_replay_passed": True, "historical_model_parameters_certified": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
