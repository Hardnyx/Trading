"""Apply the registered gate test of volatility-based risk timing for the fund."""
import argparse
import csv
import gzip
import io
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-momento-riesgo-v1.json"


def read_series(folder):
    rows = []
    for path in sorted(Path(folder).glob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows += list(csv.DictReader(io.StringIO(handle.read())))
    return rows


def daily_inputs():
    ff = {r["date"]: (float(r["Mkt-RF"]) / 100 + float(r["RF"]) / 100, float(r["RF"]) / 100)
          for r in read_series(ROOT / "data/history/factors/ff5-daily")}
    yields = {}
    for r in read_series(ROOT / "data/history/macro/DGS10"):
        try:
            yields[r["date"]] = float(r["value"]) / 100
        except (TypeError, ValueError):
            continue
    dates, out, last = sorted(ff), [], None
    for d in dates:
        y = yields.get(d, last)
        if y is None:
            continue
        if last is not None:
            duration = (1 - (1 + last / 2) ** -20) / last
            equity, rf = ff[d]
            out.append((d, equity, last / 252 - duration * (y - last), rf))
        last = y
    return out


def simulate(days, design):
    """Monthly weights from information at each month end; daily compounding."""
    lam, cost = 0.94, 0.0007
    variance, sigmas, weights = None, [], (0.70, 0.25, 0.05)
    static, timed = (0.70, 0.25, 0.05), None
    values = {"static": 1.0, "timed": 1.0}
    holdings = {"static": list(static), "timed": list(static)}
    monthly = {"static": [], "timed": []}
    rf_month, start_value, equity_path = 0.0, dict(values), []
    first, last = design["period"]["first_month"], design["period"]["last_month"]
    for i, (d, eq, bond, rf) in enumerate(days):
        variance = eq * eq if variance is None else lam * variance + (1 - lam) * eq * eq
        in_period = first <= d[:7] <= last
        if in_period:
            for name in values:
                h = holdings[name]
                h[0] *= 1 + eq; h[1] *= 1 + bond; h[2] *= 1 + rf
                values[name] = sum(h)
            rf_month = (1 + rf_month) * (1 + rf) - 1
        month_end = i + 1 == len(days) or days[i + 1][0][:7] != d[:7]
        if not month_end:
            continue
        sigma = math.sqrt(252 * variance)
        timed_weights = static
        if len(sigmas) >= 60:
            share = min(0.90, max(0.60, 0.70 * (sum(sigmas) / len(sigmas)) / sigma))
            timed_weights = (share, 0.95 - share, 0.05)
        sigmas.append(sigma)
        if not in_period:
            continue
        for name, target in (("static", static), ("timed", timed_weights)):
            value = values[name]
            monthly[name].append(value / start_value[name] - 1 - rf_month)
            current = [h / value for h in holdings[name]]
            traded = sum(abs(c - w) for c, w in zip(current, target)) / 2 * value
            value -= traded * cost
            holdings[name] = [w * value for w in target]
            values[name] = value
        equity_path.append((d[:7], timed_weights[0]))
        start_value, rf_month = dict(values), 0.0
    return monthly, equity_path


def sharpe(x):
    x = np.asarray(x)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(12))


def bootstrap_p(a, b, draws, seed, block=12):
    a, b, n = np.asarray(a), np.asarray(b), len(a)
    observed = sharpe(a) - sharpe(b)
    rng = np.random.default_rng(seed)
    diffs = np.empty(draws)
    for k in range(draws):
        idx, pos = np.empty(n, dtype=int), rng.integers(n)
        for j in range(n):
            if j and rng.random() < 1 / block:
                pos = rng.integers(n)
            idx[j] = pos % n
            pos += 1
        diffs[k] = sharpe(a[idx]) - sharpe(b[idx])
    return observed, float(np.mean(diffs - observed >= observed))


def max_drawdown(excess_and_rf):
    value, peak, worst = 1.0, 1.0, 0.0
    for r in excess_and_rf:
        value *= 1 + r
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst


def run(design):
    days = daily_inputs()
    monthly, path = simulate(days, design)
    # Drawdowns use total returns: add RF back month by month is unnecessary for
    # the comparison; both series subtract the same RF, so excess paths are used.
    observed, p = bootstrap_p(monthly["timed"], monthly["static"], 10000, 20261114)
    dd = {k: max_drawdown(v) for k, v in monthly.items()}
    rule = design["verdict_rule"]
    if observed <= 0:
        verdict = "not-supported"
    elif p < 0.05 and dd["timed"] >= dd["static"] - 0.02:
        verdict = "supported"
    else:
        verdict = "inconclusive"
    months = [m for m, _ in path]
    sub = {}
    for label, (a, b) in {"1964-1989": ("1964-01", "1989-12"), "1990-2018": ("1990-01", "2018-12")}.items():
        idx = [i for i, m in enumerate(months) if a <= m <= b]
        sub[label] = {k: round(sharpe([monthly[k][i] for i in idx]), 4) for k in monthly}
    shares = [s for _, s in path]
    return {"schema": "risk-timing-gate-result-v1", "months": len(monthly["static"]),
            "sharpe": {k: round(sharpe(v), 4) for k, v in monthly.items()},
            "sharpe_difference": round(observed, 4), "bootstrap_p_one_sided": round(p, 4),
            "max_drawdown_excess": {k: round(v, 4) for k, v in dd.items()},
            "annualized_excess_return": {k: round(float(np.mean(v)) * 12, 4) for k, v in monthly.items()},
            "annualized_volatility": {k: round(float(np.std(v, ddof=1)) * math.sqrt(12), 4) for k, v in monthly.items()},
            "subperiod_sharpe": sub, "equity_share": {"min": min(shares), "max": max(shares),
            "mean_abs_monthly_change": round(float(np.mean(np.abs(np.diff(shares)))), 4)},
            "verdict": verdict, "verdict_rule": rule, "limits": design["limits"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/momento-riesgo-1964-2018.json")
    options = parser.parse_args()
    result = run(json.loads(DESIGN.read_text(encoding="utf-8")))
    options.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("verdict_rule", "limits")}, indent=1))


if __name__ == "__main__":
    main()
