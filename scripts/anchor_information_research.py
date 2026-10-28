"""Reconstructed monthly rank IC; annual EPS proxy, never live calibration."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[1]


def known_annual_eps(asset, origin, snapshot_cut):
    """Only filed annual facts; rebase units to the provider's split-adjusted prices."""
    known = [r for r in (asset.get("financials", {}).get("earnings_history") or {}).get("records", [])
             if r.get("filed", "9999") <= origin and r.get("period_end", "9999") <= origin
             and r.get("form") in ("10-K", "10-K/A", "20-F", "20-F/A")]
    if not known:
        return None
    period = max(r["period_end"] for r in known)
    known = [r for r in known if r["period_end"] == period]
    filed = max(r["filed"] for r in known)
    latest = [r for r in known if r["filed"] == filed]
    if len({r["value"] for r in latest}) != 1:
        return None
    row = latest[0]
    if (date.fromisoformat(origin) - date.fromisoformat(period)).days > 550:
        return None
    eps = row["value"]
    for split in asset.get("splits", []):
        if filed < split["date"] <= snapshot_cut:
            ratio = split.get("ratio")
            if not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio <= 0:
                return None
            eps /= ratio
    return {"eps": eps, "filed": filed, "period_end": period, "source_url": row.get("source_url")}


def rank_correlation(x, y):
    if len(x) < 3:
        return None
    a, b = rankdata(x), rankdata(y)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def block_interval(values, block=12, draws=1000):
    """Moving month blocks retain overlapping-horizon dependence."""
    a = np.asarray(values, float)
    if len(a) < 2 * block:
        return None
    random = np.random.default_rng(20261028)
    means = []
    for _ in range(draws):
        pieces = [a[start:start+block] for start in random.integers(0, len(a)-block+1, math.ceil(len(a)/block))]
        means.append(float(np.concatenate(pieces)[:len(a)].mean()))
    return [float(v) for v in np.quantile(means, [.025, .975])]


def evaluate(snapshot, horizons=(21, 63, 252), minimum_stocks=30):
    cut = snapshot["price_as_of"]
    benchmark = next(a for a in snapshot["assets"] if a["symbol"] == "SPY")
    market = {r["date"]: r["adj_close"] for r in benchmark["history"] if r["date"] <= cut}
    dates = sorted(market)
    month_ends = {}
    for i, day in enumerate(dates):
        month_ends[day[:7]] = i
    stocks = [a for a in snapshot["assets"] if a.get("type") == "stock"]
    prices = {a["symbol"]: {r["date"]: r for r in a["history"] if r["date"] <= cut} for a in stocks}
    origins, excluded = [], Counter()
    for i in month_ends.values():
        if i < 252:
            continue
        day = dates[i]
        for horizon in horizons:
            if i+horizon >= len(dates):
                continue
            end = dates[i+horizon]
            rows = []
            for asset in stocks:
                fact = known_annual_eps(asset, day, cut)
                if not fact or fact["eps"] <= 0:
                    excluded["missing_or_nonpositive_annual_eps"] += 1
                    continue
                history = prices[asset["symbol"]]
                p, q = history.get(day), history.get(end)
                if not p or not q:
                    excluded["missing_origin_or_outcome"] += 1
                    continue
                assumptions = asset.get("assumptions", {})
                growth, multiple, H = (assumptions.get(k) for k in ("growth", "multiple", "horizon"))
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (growth, multiple, H)) or multiple <= 0 or H <= 0:
                    continue
                current_pe = p["close"] / fact["eps"]
                share = 1 - .5 ** (H / 10)
                signal = (1+growth) * math.exp(math.log(multiple/current_pe)*share/H) - 1
                common = [d for d in dates[i-252:i+1] if d in history]
                if len(common) < 200:
                    continue
                stock_r = np.diff(np.log([history[d]["adj_close"] for d in common]))
                market_r = np.diff(np.log([market[d] for d in common]))
                variance = float(np.var(market_r))
                beta = float(np.mean((stock_r-stock_r.mean())*(market_r-market_r.mean())) / variance) if variance else 0
                realized = math.log(q["adj_close"] / p["adj_close"])
                residual = realized - beta * math.log(market[end] / market[day])
                rows.append({"symbol": asset["symbol"], "filed": fact["filed"], "eps": fact["eps"],
                             "signal": signal, "earnings_yield": 1/current_pe, "residual_return": residual})
            if len(rows) < minimum_stocks:
                continue
            for model, key in [("annual_building_block_proxy", "signal"), ("earnings_yield", "earnings_yield")]:
                ic = rank_correlation([r[key] for r in rows], [r["residual_return"] for r in rows])
                if ic is not None:
                    origins.append({"origin": day, "maturity": end, "horizon_sessions": horizon,
                                    "model": model, "stocks": len(rows), "rank_ic": ic, "observations": rows})
    summary = []
    for h in horizons:
        for model in ("annual_building_block_proxy", "earnings_yield"):
            values = [r["rank_ic"] for r in origins if r["horizon_sessions"] == h and r["model"] == model]
            if values:
                summary.append({"horizon_sessions": h, "model": model, "origins": len(values),
                                "mean_rank_ic": float(np.mean(values)), "median_rank_ic": float(np.median(values)),
                                "share_positive": float(np.mean(np.array(values) > 0)),
                                "month_block_95_interval": block_interval(values)})
    return {"status": "reconstructed_annual_proxy_only", "production_eligible": False,
            "original_vintages_verified": False, "historical_universe_verified": False,
            "exact_live_signal": False, "as_of": cut, "summary": summary, "origins": origins,
            "exclusions": dict(excluded), "current_universe_stocks": len(stocks),
            "limitations": "Current selected universe and provider histories; annual rather than original TTM EPS; current catalogue growth/multiples held fixed, no historical dividends. Filing filters do not certify original vintages. Splits rebase units, not economic returns. Not an estimate that may replace the live IC of 0.05."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", type=Path, default=ROOT / "dist/data/market.json")
    parser.add_argument("--output", type=Path, default=ROOT / "out/anchor-information-research.json")
    args = parser.parse_args()
    raw = args.market.read_bytes()
    report = evaluate(json.loads(raw))
    report["source_snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=1) + "\n")
    print(json.dumps({"status": report["status"], "production_eligible": False, "summary": report["summary"]}))


if __name__ == "__main__":
    main()
