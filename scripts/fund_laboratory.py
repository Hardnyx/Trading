"""Apply the registered fund laboratory tests L1, L2 and L3."""
import argparse
import csv
import gzip
import io
import json
import math
from pathlib import Path

from scipy.stats import t as student

try:
    from .valuation_anchor_oos import bond_realized, equity_anchor, load, score
    from .fund_v2_acceptance import drawdown_stats, simulate
except ImportError:
    from valuation_anchor_oos import bond_realized, equity_anchor, load, score
    from fund_v2_acceptance import drawdown_stats, simulate

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-laboratorio-fondo-v1.json"


def read_folder(folder):
    rows = []
    for path in sorted(Path(folder).glob("*.csv.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows += list(csv.DictReader(io.StringIO(handle.read())))
    return rows


def annualized_equity(rows, i, years):
    value = 1.0
    for k in range(12 * years):
        value *= (rows[i + k + 1]["price"] + rows[i + k]["dividend"] / 12) / rows[i + k]["price"]
    return value ** (1 / years) - 1


def r2(records):
    a = sum((r - f) ** 2 for f, _, r in records)
    b = sum((r - h) ** 2 for _, h, r in records)
    return 1 - a / b


def l1(spec):
    rows = load()
    index = {r["date"][:7]: i for i, r in enumerate(rows)}
    out = {}
    for years in spec["horizons_years"]:
        months = 12 * years
        realized = {i: annualized_equity(rows, i, years) for i in range(13, len(rows) - months)}
        variants = {
            "engine_trailing_earnings": lambda i: equity_anchor(rows, i, .06, .6),
            "descriptive_cape": lambda i: (.06 + .6 * (1 / cape(rows, i) + rows[i - 1]["cpi"] / rows[i - 13]["cpi"] - 1 - .06))
            if cape(rows, i) else None,
        }
        res = {}
        for name, anchor in variants.items():
            records = {}
            for year in range(1900, 2018 - years + 1):
                i = index[f"{year}-01"]
                known = [realized[j] for j in realized if j + months <= i]
                f = anchor(i)
                if f is not None and known:
                    records[year] = (f, sum(known) / len(known), realized[i])
            full = r2(list(records.values()))
            subs = [r2([records[y] for y in range(1900 + k, 2018 - years + 1, years) if y in records]) for k in range(years)]
            share = sum(s > 0 for s in subs) / len(subs)
            verdict = "not-supported" if full <= 0 else "supported" if share >= .8 else "inconclusive"
            res[name] = {"origins": len(records), "r2_os": round(full, 4), "nonoverlapping_subsample_r2": [round(s, 4) for s in subs],
                         "share_positive": round(share, 3), "verdict": verdict if name.startswith("engine") else "descriptive",
                         "mean_error": round(sum(r - f for f, _, r in records.values()) / len(records), 4)}
        out[f"{years}_years"] = res
    return out


def cape(rows, i):
    """Price over the 10-year average of real earnings known at t (3-month lag)."""
    j = i - 3
    if j - 119 < 0:
        return None
    real = [rows[k]["earnings"] / rows[k]["cpi"] for k in range(j - 119, j + 1)]
    return rows[i]["price"] / rows[i]["cpi"] / (sum(real) / len(real))


def l2(spec):
    rows = load()
    index = {r["date"][:7]: i for i, r in enumerate(rows)}
    bills = {r["date"][:7]: float(r["value"]) / 100 for r in read_folder(ROOT / "data/history/macro/TB3MS") if r["value"] not in ("", ".")}
    excess = {}
    for i in range(len(rows) - 12):
        m = rows[i]["date"][:7]
        if m in bills:
            excess[i] = bond_realized(rows, i) - bills[m]
    records = []
    for year in range(1937, 2019):
        i = index[f"{year}-01"]
        known = [excess[j] for j in excess if j + 12 <= i]
        records.append((str(year), (rows[i]["gs10"] / 100 - bills[rows[i]["date"][:7]]), sum(known) / len(known), excess[i]))
    s = score(records)
    verdict = "not-supported" if s["r2_os"] <= 0 else "supported" if s["p_one_sided"] < .05 else "inconclusive"
    return {"origins": s["n"], "r2_os": round(s["r2_os"], 4), "clark_west_t": round(s["clark_west_t"], 3),
            "p_one_sided": round(s["p_one_sided"], 4), "mean_error_spread": round(s["mean_error_anchor"], 4),
            "mean_error_benchmark": round(s["mean_error_benchmark"], 4), "verdict": verdict}


def monthly_inputs():
    us = {}
    for r in read_folder(ROOT / "data/history/factors/ff5-daily"):
        m = r["date"][:7]
        us[m] = us.get(m, 1.0) * (1 + (float(r["Mkt-RF"]) + float(r["RF"])) / 100)
    us = {m: v - 1 for m, v in us.items()}
    dev = {r["date"][:7]: (float(r["Mkt-RF"]) + float(r["RF"])) / 100 for r in read_folder(ROOT / "data/history/factors/developed-ex-us-monthly")}
    emg = {r["date"][:7]: (float(r["Mkt-RF"]) + float(r["RF"])) / 100 for r in read_folder(ROOT / "data/history/factors/emerging-monthly")}
    yields = {}
    for r in read_folder(ROOT / "data/history/macro/DGS10"):
        if r["value"] not in ("", "."):
            yields[r["date"][:7]] = float(r["value"]) / 100  # last day of each month wins
    months = sorted(set(us) & set(dev) & set(emg) & set(yields))
    out = []
    for a, b in zip(months, months[1:]):
        y0, y1 = yields[a], yields[b]
        duration = (1 - (1 + y0 / 2) ** -20) / y0
        out.append((b, us[b], .75 * dev[b] + .25 * emg[b], y0 / 12 - duration * (y1 - y0)))
    return out


def l3(spec):
    data = monthly_inputs()
    mixes = {"fondo-v2": (.42, .28, .25, .05), "US-only": (.70, 0.0, .25, .05)}
    out = {}
    for label, (start, end) in {"1990-2018": ("1990-07", "2018-12"), "extension": ("1990-07", data[-1][0])}.items():
        rows = [r for r in data if start <= r[0] <= end]
        dates = [rows[0][0]] + [r[0] for r in rows]
        steps = [(u, i, b, 0.0) for _, u, i, b in rows]
        res = {}
        for name, w in mixes.items():
            values, trades, _ = simulate(steps, w, .05)
            years = {}
            for d, v in zip(dates, values):
                years.setdefault(d[:4], []).append(v)
            items = list(years.items())
            calendar = {y: vs[-1] / prev[-1] - 1 for (y, vs), (_, prev) in zip(items[1:], items[:-1])}
            monthly = [values[k + 1] / values[k] - 1 for k in range(len(values) - 1)]
            mean = sum(monthly) / len(monthly)
            window = lambda a, b: drawdown_stats(values[dates.index(a):dates.index(b) + 1], dates[dates.index(a):dates.index(b) + 1], "months")
            worst = min(calendar, key=calendar.get)
            res[name] = {"annualized_return": round(values[-1] ** (12 / (len(values) - 1)) - 1, 4),
                         "annualized_volatility": round(math.sqrt(sum((m - mean) ** 2 for m in monthly) / (len(monthly) - 1) * 12), 4),
                         "worst_calendar_year": [worst, round(calendar[worst], 4)], "rebalances": trades,
                         **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in drawdown_stats(values, dates, "months").items()},
                         "drawdown_2000_2002": round(window("2000-01", "2002-12")["max_drawdown"], 4),
                         "drawdown_2007_2009": round(window("2007-01", "2009-12")["max_drawdown"], 4)}
        res["flag_intl_drawdown_worse_by_5pp"] = res["fondo-v2"]["max_drawdown"] < res["US-only"]["max_drawdown"] - .05
        out[label] = {"period": f"{dates[0]} to {dates[-1]}", **res}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/laboratorio-fondo-v1.json")
    parser.add_argument("--only", choices=["L1", "L2", "L3"], nargs="*")
    options = parser.parse_args()
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    tests = {"L1": lambda: l1(design["L1_equity_anchor_long_horizon"]), "L2": lambda: l2(design["L2_bond_duration_from_carry"]),
             "L3": lambda: l3(design["L3_international_history"])}
    report = json.loads(options.output.read_text()) if options.output.exists() else {"schema": "fund-laboratory-result-v1"}
    for key in options.only or tests:
        report[key] = tests[key]()
    options.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k in (options.only or tests)}, indent=1))


if __name__ == "__main__":
    main()
