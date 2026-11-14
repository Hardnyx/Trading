"""Registered acceptance tests T3 (long history) and T4 (ETF era) for fondo-v2."""
import argparse
import json
import math
from pathlib import Path

try:
    from .price_risk_oos_inputs import adjusted_history
    from .valuation_anchor_oos import load
except ImportError:
    from price_risk_oos_inputs import adjusted_history
    from valuation_anchor_oos import load

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/fondo-v2-registro.json"
MIXES = {"70/25/5": (0.70, 0.25, 0.05), "60/40": (0.60, 0.40, 0.0), "100/0": (1.0, 0.0, 0.0)}


def simulate(returns, weights, threshold, cost=0.0):
    """Drift-rebalanced path; returns values, rebalance count and total cost."""
    holdings, value, values, trades, paid = list(weights), 1.0, [1.0], 0, 0.0
    for step in returns:
        holdings = [h * (1 + r) for h, r in zip(holdings, step)]
        value = sum(holdings)
        current = [h / value for h in holdings]
        if max(abs(c - w) for c, w in zip(current, weights)) > threshold + 1e-12:
            traded = sum(abs(c - w) for c, w in zip(current, weights)) / 2 * value
            value -= traded * cost
            paid += traded * cost
            holdings = [w * value for w in weights]
            trades += 1
        values.append(value)
    return values, trades, paid


def drawdown_stats(values, dates, unit):
    peak, peak_i, worst, worst_i, worst_peak = values[0], 0, 0.0, 0, 0
    for i, v in enumerate(values):
        if v > peak:
            peak, peak_i = v, i
        if v / peak - 1 < worst:
            worst, worst_i, worst_peak = v / peak - 1, i, peak_i
    recover = next((i for i in range(worst_i, len(values)) if values[i] >= values[worst_peak]), None)
    return {"max_drawdown": worst, "peak": dates[worst_peak], "trough": dates[worst_i],
            f"{unit}_to_recover_from_peak": None if recover is None else recover - worst_peak}


def quantile(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def t3(design):
    rows = load()
    index = {r["date"][:7]: i for i, r in enumerate(rows)}
    start, end = index["1900-01"], index["2018-12"]
    steps, dates = [], [rows[start]["date"][:7]]
    for i in range(start, end):
        equity = (rows[i + 1]["price"] + rows[i]["dividend"] / 12) / rows[i]["price"] - 1
        y0, y1 = rows[i]["gs10"] / 100, rows[i + 1]["gs10"] / 100
        duration = (1 - (1 + y0 / 2) ** -20) / y0
        steps.append((equity, y0 / 12 - duration * (y1 - y0), 0.0))
        dates.append(rows[i + 1]["date"][:7])
    out = {}
    for name, weights in MIXES.items():
        values, trades, _ = simulate(steps, weights, 0.05)
        years = {}
        for d, v in zip(dates, values):
            years.setdefault(d[:4], []).append(v)
        calendar = {y: vs[-1] / prev[-1] - 1 for (y, vs), (_, prev) in zip(list(years.items())[1:], list(years.items())[:-1])}
        rolling = [values[i + 12] / values[i] - 1 for i in range(len(values) - 12)]
        monthly = [values[i + 1] / values[i] - 1 for i in range(len(values) - 1)]
        mean = sum(monthly) / len(monthly)
        worst_year = min(calendar, key=calendar.get)
        out[name] = {"annualized_return": values[-1] ** (12 / (len(values) - 1)) - 1,
                     "annualized_volatility": math.sqrt(sum((m - mean) ** 2 for m in monthly) / (len(monthly) - 1) * 12),
                     "worst_calendar_year": [worst_year, calendar[worst_year]],
                     "median_12m": quantile(rolling, .5), "p05_12m": quantile(rolling, .05),
                     "share_of_negative_12m": sum(r < 0 for r in rolling) / len(rolling),
                     "rebalances_per_year": trades / ((len(values) - 1) / 12), **drawdown_stats(values, dates, "months")}
        post = dates.index("1946-01")
        out[name]["descriptive_post_1946"] = drawdown_stats(values[post:], dates[post:], "months")
    return {"period": "1900-01 to 2018-12", "assets": "S&P composite total return, 10-year Treasury by duration approximation, cash at zero",
            "results": out}


def t4(design):
    symbols = ["VTI", "VXUS", "AGG"]
    series = {s: {r["date"]: r["adj_close"] for r in adjusted_history(s, "2100-01-01")} for s in symbols}
    dates = sorted(set.intersection(*(set(v) for v in series.values())))
    dates = [d for d in dates if d >= "2011-02-01"]
    steps = [tuple(series[s][dates[i]] / series[s][dates[i - 1]] - 1 for s in symbols) + (0.0,) for i in range(1, len(dates))]
    weights = tuple(design["strategic_weights"][s] for s in symbols) + (design["strategic_weights"]["CASH"],)
    values, trades, paid = simulate(steps, weights, 0.05, cost=0.0007)
    # Comparator: same weights rebalanced at each month end, no costs.
    holdings, monthly_values = list(weights), [1.0]
    for i, step in enumerate(steps, start=1):
        holdings = [h * (1 + r) for h, r in zip(holdings, step)]
        value = sum(holdings)
        if i < len(dates) - 1 and dates[i][:7] != dates[i + 1][:7]:
            holdings = [w * value for w in weights]
        monthly_values.append(value)
    diff = [values[i + 1] / values[i] - monthly_values[i + 1] / monthly_values[i] for i in range(len(values) - 1)]
    m = sum(diff) / len(diff)
    years = (len(dates) - 1) / 252
    tracking = math.sqrt(sum((d - m) ** 2 for d in diff) / (len(diff) - 1) * 252)
    cost_per_year = paid / years
    result = {"period": f"{dates[0]} to {dates[-1]}", "years": years,
              "annualized_return": values[-1] ** (1 / years) - 1,
              "comparator_annualized_return": monthly_values[-1] ** (1 / years) - 1,
              "tracking_error_annualized": tracking, "rebalances": trades, "rebalances_per_year": trades / years,
              "cost_per_year_of_initial_capital": cost_per_year, **drawdown_stats(values, dates, "sessions")}
    accept = design["acceptance_tests"]["T4_etf_era"]["acceptance"]
    result["acceptance"] = {accept[0]: tracking <= 0.015, accept[1]: trades / years <= 6, accept[2]: cost_per_year <= 0.001}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/fondo-v2-aceptacion.json")
    options = parser.parse_args()
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    report = {"schema": "fondo-v2-acceptance-v1", "T3_long_history": t3(design), "T4_etf_era": t4(design)}
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report, indent=1)[:4000])


if __name__ == "__main__":
    main()
