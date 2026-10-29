"""Filed TTM signal reconstruction and dependent IC diagnostics; research only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

try:
    from . import refresh_data as collector
except ImportError:
    import refresh_data as collector

download, ttm, periodic_form = collector.download, collector.ttm, collector.periodic_form

ROOT = Path(__file__).resolve().parents[1]
TAG = "EarningsPerShareDiluted"
UNIT = "USD/shares"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eps_at(asset, rows, origin, snapshot_cut):
    """Run the live TTM extractor, with strict date lag and conflict/split guards.

    Today's split-adjusted closes need EPS in today's share units. Historical
    splits also retain the production guard against components on mixed bases.
    No original API vintage or acceptance timestamp is claimed.
    """
    cutoff = (date.fromisoformat(origin) - timedelta(days=1)).isoformat()
    known = [r for r in rows if r.get("filed", "9999") <= cutoff
             and r.get("end", "9999") <= cutoff and r.get("form") and periodic_form(r["form"])]
    record = ttm({TAG: {"units": {UNIT: known}}}, [TAG], cutoff, UNIT)
    if not record or record["method"] != "TTM":
        return None, "missing_ttm_or_fy_fallback"
    for component in record["components"]:
        versions = [r for r in known if all(r.get(k) == component.get(k) for k in ("start", "end", "filed"))]
        if len({r["val"] for r in versions}) != 1:
            return None, "conflicting_selected_period"
    if record["value"] <= 0:
        return None, "nonpositive_ttm"
    if (date.fromisoformat(origin) - date.fromisoformat(record["period_end"])).days > 550:
        return None, "stale_ttm"
    splits = asset.get("splits", [])
    if any(not isinstance(s.get("ratio"), (float, int)) or not math.isfinite(s["ratio"]) or s["ratio"] <= 0 for s in splits):
        return None, "invalid_split"
    latest = max((s["date"] for s in splits if s["date"] <= origin and s["ratio"] != 1), default=None)
    if latest and any(c["filed"] < latest for c in record["components"]):
        return None, "mixed_historical_share_basis"
    divisor = math.prod(s["ratio"] for s in splits if origin < s["date"] <= snapshot_cut)
    # Keep original component values; never label the rebased result as an
    # original filing value. Their arithmetic reconstructs reported_value.
    return {**record, "reported_value": record["value"], "value": record["value"] / divisor,
            "future_split_divisor": divisor, "information_cutoff": cutoff}, None


def prepare(snapshot, sources):
    benchmark = next(a for a in snapshot["assets"] if a["symbol"] == "SPY")
    dates = sorted(r["date"] for r in benchmark["history"] if r["date"] <= snapshot["price_as_of"])
    ends = {day[:7]: i for i, day in enumerate(dates)}
    origins, exclusions = [], Counter()
    assets = [a for a in snapshot["assets"] if a.get("type") == "stock"]
    for i in ends.values():
        if i < 250 or i + 21 >= len(dates):
            continue
        day = dates[i]
        facts = []
        for asset in assets:
            source = sources.get(asset["symbol"])
            if source is None:
                exclusions["missing_companyfacts"] += 1
                continue
            record, reason = eps_at(asset, source["rows"], day, snapshot["price_as_of"])
            if reason:
                exclusions[reason] += 1
            else:
                facts.append({"symbol": asset["symbol"], "eps": record})
        origins.append({"origin": day, "outcomes": {str(h): dates[i+h] for h in (21, 63, 252) if i+h < len(dates)}, "facts": facts})
    return {"method": "filed-ttm-signal-reconstruction-v1", "price_cut": snapshot["price_as_of"],
            "origins": origins, "exclusions": dict(exclusions), "sources": sources,
            "current_universe_stocks": len(assets), "original_vintages_verified": False,
            "production_eligible": False}


def correlation(x, y, ranks=False):
    if len(x) < 3:
        return None
    a, b = np.asarray(x, float), np.asarray(y, float)
    if ranks:
        a, b = rankdata(a), rankdata(b)
    if not np.isfinite(a).all() or not np.isfinite(b).all() or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def dependent_interval(values, months, block, draws=2000):
    """Moving calendar-month blocks, no flattening across missing origins."""
    if len(values) < 2 * block or any(b-a != 1 for a, b in zip(months, months[1:])):
        return None
    a, rng = np.asarray(values, float), np.random.default_rng(20261029)
    means = []
    for _ in range(draws):
        starts = rng.integers(0, len(a)-block+1, math.ceil(len(a)/block))
        means.append(float(np.concatenate([a[k:k+block] for k in starts])[:len(a)].mean()))
    return [float(v) for v in np.quantile(means, [.025, .975])]


def summarize(replay, minimum_stocks=30):
    measured, summaries = [], []
    for origin in replay["origins"]:
        for horizon, maturity in origin["outcomes"].items():
            rows = [r for r in origin["observations"] if horizon in r["outcomes"]]
            if len(rows) < minimum_stocks:
                continue
            realized = [r["outcomes"][horizon]["residual_log_return"] for r in rows]
            standardized = [r["outcomes"][horizon]["standardized_residual"] for r in rows]
            signal, value = [r["signal"] for r in rows], [r["earnings_yield"] for r in rows]
            score = [r["score"] for r in rows]
            metrics = {"ttm_rank_ic": correlation(signal, realized, True),
                       "earnings_yield_rank_ic": correlation(value, realized, True),
                       "score_standardized_pearson_ic": correlation(score, standardized),
                       "signal_standardized_rank_ic": correlation(signal, standardized, True)}
            if any(v is None for v in metrics.values()):
                continue
            metrics["rank_ic_difference_vs_yield"] = metrics["ttm_rank_ic"] - metrics["earnings_yield_rank_ic"]
            measured.append({"origin": origin["origin"], "maturity": maturity,
                             "horizon_sessions": int(horizon), "stocks": len(rows), **metrics})
    for h in (21, 63, 252):
        rows = [r for r in measured if r["horizon_sessions"] == h]
        if not rows:
            continue
        months = [int(r["origin"][:4])*12+int(r["origin"][5:7]) for r in rows]
        block = math.ceil(h/21)
        metrics = {}
        for name in ("ttm_rank_ic", "earnings_yield_rank_ic", "rank_ic_difference_vs_yield",
                     "score_standardized_pearson_ic", "signal_standardized_rank_ic"):
            values = [r[name] for r in rows]
            metrics[name] = {"mean": float(np.mean(values)), "median": float(np.median(values)),
                             "month_block_95_interval": dependent_interval(values, months, block)}
        # A disjoint subset is a sensitivity to overlap, not independent stocks.
        disjoint, last_end = [], ""
        for r in rows:
            if r["origin"] >= last_end:
                disjoint.append(r); last_end = r["maturity"]
        summaries.append({"horizon_sessions": h, "origins": len(rows), "first_origin": rows[0]["origin"],
                          "last_origin": rows[-1]["origin"], "block_months": block,
                          "minimum_stocks": min(r["stocks"] for r in rows),
                          "maximum_stocks": max(r["stocks"] for r in rows), "metrics": metrics,
                          "nonoverlapping_origin_count": len(disjoint),
                          "nonoverlapping_mean_rank_ic": float(np.mean([r["ttm_rank_ic"] for r in disjoint]))})
    return {"status": "reconstructed_ttm_signal_only", "production_eligible": False,
            "automatic_promotion": False,
            "inference": {"bootstrap_draws": 2000, "seed": 20261029,
                          "scope": "Descriptive pointwise moving-block intervals; no multiple-testing correction or certification with few independent annual origins"},
            "original_vintages_verified": False, "historical_universe_verified": False,
            "exact_live_signal": False, "exact_valuation_function": True,
            "as_of": replay["price_cut"], "summary": summaries, "origin_metrics": measured,
            "input_market_sha256": replay["input_market_sha256"], "input_facts_sha256": replay["input_facts_sha256"],
            "replay_source_hashes": replay["source_hashes"], "exclusions": replay["exclusions"],
            "limitations": ["Current companyfacts extraction, not original historical API vintages or verified filing timestamps",
                            "Strict prior-calendar-day filing lag; no same-day information is admitted",
                            "Current selected universe, present catalogue growth/multiples and corporate-action classification",
                            "Today's adjusted price and ex-date dividend series; no original dividend vintage or executable strategy",
                            "Actual valuation/market-exposure functions; not the full confidence/holdings-neutralized anchor",
                            "Rank IC is not the Pearson skill coefficient; even Pearson diagnostics do not calibrate the live coefficient",
                            "Monthly overlapping outcomes; moving blocks are approximate, few disjoint annual origins",
                            "No fitted parameter, parameter search, production promotion, or financial-risk certification"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect", "summarize"))
    parser.add_argument("--market", type=Path, default=ROOT / "dist/data/market.json")
    parser.add_argument("--input", type=Path, default=ROOT / "out/ttm-signal-replay.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    if args.command == "summarize":
        result = summarize(json.loads(args.input.read_text()))
        result["replay_sha256"] = digest(args.input)
        output = args.output or ROOT / "out/ttm-signal-summary.json"
    else:
        if args.cache_dir:
            collector.CACHE = args.cache_dir
        market, sources, errors = json.loads(args.market.read_text()), {}, []
        assets = [a for a in market["assets"] if a.get("type") == "stock" and a.get("cik")]
        lower = min(r["date"] for a in market["assets"] for r in a["history"])[:4]+"-01-01"
        def fetch(cik):
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
            try:
                raw = download(url, f"sec-{cik}.json", max_age=24*3600, sec=True)
                rows = json.loads(raw).get("facts", {}).get("us-gaap", {}).get(TAG, {}).get("units", {}).get(UNIT, [])
                # Archive all versions used for this frozen price window, not
                # just the chosen value. Full-response hash is also retained.
                rows = [r for r in rows if r.get("filed", "9999") <= market["price_as_of"]
                        and r.get("end", "") >= lower]
                return {"cik": cik, "url": url,
                    "observed_at": datetime.fromtimestamp((collector.CACHE/f"sec-{cik}.json").stat().st_mtime, timezone.utc).isoformat(),
                    "full_response_sha256": hashlib.sha256(raw).hexdigest(), "rows": rows}
            except Exception as error:
                return {"error": type(error).__name__, "http_status": getattr(error, "code", None)}
        # Independent responses can overlap in flight. The shared SEC lock in
        # download still spaces request starts by >=0.6 s across all workers.
        ciks = list(dict.fromkeys(int(a["cik"]) for a in assets))
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = dict(zip(ciks, executor.map(fetch, ciks)))
        for asset in assets:
            response = responses[int(asset["cik"])]
            if "error" in response:
                errors.append({"symbol": asset["symbol"], **response})
                print(json.dumps(errors[-1]), flush=True)
            else:
                sources[asset["symbol"]] = response
                print(json.dumps({"symbol": asset["symbol"], "eps_versions": len(response["rows"])}), flush=True)
        result = prepare(market, sources)
        result.update(input_market_sha256=digest(args.market), download_errors=errors)
        output = args.output or ROOT / "out/ttm-signal-facts.json"
    result["analysis_source_sha256"] = digest(__file__)
    result["collector_source_sha256"] = digest(collector.__file__)
    result["protocol_sha256"] = digest(ROOT/"docs/protocolo-senal-ttm-0.35.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))+"\n")
    print(json.dumps({k: v for k, v in result.items() if k in ("status", "summary", "download_errors", "exclusions")}))
    if args.command == "collect" and sum(bool(s["rows"]) for s in result["sources"].values()) < 30:
        raise RuntimeError("Insufficient companyfacts coverage; exclusions preserved")
    if args.command == "summarize" and not result["summary"]:
        raise RuntimeError("No evaluable cross-section; not a successful validation")


if __name__ == "__main__":
    main()
