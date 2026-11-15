"""Apply the registered gate test of bond duration from the yield-curve slope."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

try:
    from .valuation_anchor_oos import load
    from .fund_laboratory import read_folder
    from .fund_v2_acceptance import drawdown_stats
except ImportError:
    from valuation_anchor_oos import load
    from fund_laboratory import read_folder
    from fund_v2_acceptance import drawdown_stats

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-duracion-curva-v1.json"


def monthly_series(design):
    rows = load()
    bills = {r["date"][:7]: float(r["value"]) / 100 for r in read_folder(ROOT / "data/history/macro/TB3MS")
             if r["value"] not in ("", ".")}
    first, last = design["period"]["first_month"], design["period"]["last_month"]
    out = []
    for i in range(len(rows) - 1):
        m = rows[i]["date"][:7]
        if not (first <= m <= last) or m not in bills:
            continue
        y0, y1 = rows[i]["gs10"] / 100, rows[i + 1]["gs10"] / 100
        duration = (1 - (1 + y0 / 2) ** -20) / y0
        equity = (rows[i + 1]["price"] + rows[i]["dividend"] / 12) / rows[i]["price"] - 1
        out.append({"month": m, "bond": y0 / 12 - duration * (y1 - y0), "bill": bills[m] / 12,
                    "signal": y0 > bills[m], "equity": equity})
    return out


def sleeves(series, cost=0.0005):
    rule, always, held = [], [], None
    for row in series:
        choice = "bond" if row["signal"] else "bill"
        r = row[choice] - (cost if held is not None and choice != held else 0.0)
        held = choice
        rule.append(r)
        always.append(row["bond"])
    return np.array(rule), np.array(always)


def bootstrap_p(diff, draws, seed, block=12):
    n, observed = len(diff), float(diff.mean())
    rng = np.random.default_rng(seed)
    means = np.empty(draws)
    for k in range(draws):
        idx, pos = np.empty(n, dtype=int), rng.integers(n)
        for j in range(n):
            if j and rng.random() < 1 / block:
                pos = rng.integers(n)
            idx[j] = pos % n
            pos += 1
        means[k] = diff[idx].mean()
    return float(np.mean(means - observed >= observed))


def path(returns):
    return list(np.cumprod(np.concatenate([[1.0], 1 + np.asarray(returns)])))


def sharpe(r, bills):
    x = np.asarray(r) - np.asarray(bills)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(12))


def run(design):
    series = monthly_series(design)
    rule, always = sleeves(series)
    bills = np.array([r["bill"] for r in series])
    months = [series[0]["month"]] + [r["month"] for r in series]
    diff = rule - always
    p = bootstrap_p(diff, 10000, 20261115)
    dd_rule = drawdown_stats(path(rule), months, "months")
    dd_always = drawdown_stats(path(always), months, "months")
    mean_diff = float(diff.mean() * 12)
    verdict = ("not-supported" if mean_diff <= 0 else
               "supported" if p < .05 and dd_rule["max_drawdown"] >= dd_always["max_drawdown"] else "inconclusive")
    sub = {}
    for label, (a, b) in {"1937-1979": ("1937-01", "1979-12"), "1980-2018": ("1980-01", "2018-12")}.items():
        idx = [k for k, r in enumerate(series) if a <= r["month"] <= b]
        sub[label] = {"annualized_difference": round(float(diff[idx].mean() * 12), 4),
                      "sharpe_rule": round(sharpe(rule[idx], bills[idx]), 4), "sharpe_always": round(sharpe(always[idx], bills[idx]), 4)}
    mix = {}
    for name, sleeve in (("rule", rule), ("always", always)):
        total = [.70 * s["equity"] + .25 * b for s, b in zip(series, sleeve)]
        mix[name] = {"annualized_return": round(float(np.prod(1 + np.array(total)) ** (12 / len(total)) - 1), 4),
                     "max_drawdown": round(drawdown_stats(path(total), months, "months")["max_drawdown"], 4)}
    return {"schema": "duration-curve-gate-result-v1", "months": len(series),
            "months_in_bills": int(sum(not r["signal"] for r in series)),
            "annualized_difference": round(mean_diff, 4), "bootstrap_p_one_sided": round(p, 4),
            "annualized_return": {"rule": round(float(np.prod(1 + rule) ** (12 / len(rule)) - 1), 4),
                                  "always": round(float(np.prod(1 + always) ** (12 / len(always)) - 1), 4)},
            "sharpe_over_bills": {"rule": round(sharpe(rule, bills), 4), "always": round(sharpe(always, bills), 4)},
            "max_drawdown": {"rule": round(dd_rule["max_drawdown"], 4), "always": round(dd_always["max_drawdown"], 4)},
            "subperiods": sub, "mix_70_25_5_descriptive": mix, "verdict": verdict, "limits": design["limits"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/duracion-curva-1937-2018.json")
    options = parser.parse_args()
    result = run(json.loads(DESIGN.read_text(encoding="utf-8")))
    options.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
