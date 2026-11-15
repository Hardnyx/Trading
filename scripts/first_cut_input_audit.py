"""H1.4 input audit of the reconstructed first-cut snapshot.

Five families of checks run on the archived bytes: availability (nothing in
the snapshot or its calibration is dated, filed, ex-dated or observed after
the cut), universe (members are the price-verified SPY positions, every
other position is a declared exclusion), identity (each member's CIK and
filed N-PORT price agree with the snapshot), units (finite, positive and in
range) and engine inputs (the recorded decision was computed on exactly
these bytes with the current engine). It reads no outcome after the cut and
scores nothing; passing it does not make the cut confirmatory.
"""
import argparse
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUT = "2024-12-31"
OUT = ROOT / "data/historical/full-engine-input-audit-v1"


def report_path(cut, root=ROOT):
    """The first cut keeps its original report name; later cuts are named by date."""
    base = root / "data/historical/full-engine-input-audit-v1"
    return base / ("report.json" if cut == CUT else f"report-{cut}.json")


def audited_cuts(root=ROOT):
    return sorted(p.name[:10] for p in (root / "data/historical/first-cut-snapshot-v1").glob("????-??-??.decision.json"))
RATES = {"DFF", "DFII10", "DGS10", "DGS2", "DGS30", "DGS3MO", "DGS5", "T10YIE"}
MACRO_UNITS = {"%", "USD/hour", "index", "thousands"}
CLOSE = "T21:00:00+00:00"
TOLERANCE = 0.005


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def walk(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}" if path else key, key, value
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f"{path}[{i}]")


DATED = {"date", "filed", "period_end", "filing_date", "ex_date", "price_date", "report_date", "known_by_day",
         "vintage_date", "duration_date", "yieldToMaturity_date", "secYield_date", "realYield_date",
         "last_price_date", "fitted_through", "parameter_fit_through", "verification_as_of", "as_of",
         "coverage_end", "through_filing_date"}
OBSERVED = {"observed_at", "price_observed_at"}


def availability(market, volatility, cut):
    """Every date-like field of the market and calibration on or before the cut; observation stamps by its close."""
    late = []
    for path, key, value in [*walk(market.get("assets"), "assets"), *walk(market.get("macro"), "macro"),
                             *walk(volatility.get("instruments"), "volatility")]:
        if not isinstance(value, str):
            continue
        if key in DATED and re.match(r"\d{4}-\d\d-\d\d", value) and value[:10] > cut:
            late.append(path)
        elif key in OBSERVED and value > f"{cut}{CLOSE}":
            late.append(path)
    for key in ("price_as_of", "requested_as_of"):
        if market.get(key) != cut:
            late.append(key)
    if volatility.get("as_of") != cut or volatility.get("parameter_fit_through", cut) > cut:
        late.append("volatility.as_of")
    return {"passed": not late, "fields_after_cut": late[:50], "count": len(late)}


def universe(market, binding, cut):
    stocks = {a["symbol"]: a for a in market["assets"] if a["type"] == "stock"}
    declared = {e["symbol"] for e in market["reconstruction"]["members_excluded"]}
    verified = {p["symbol"]: p for p in binding["positions"] if p["status"] == "verified"}
    unexplained = sorted(set(verified) - set(stocks) - declared)
    extra = sorted(set(stocks) - set(verified))
    unbound = [{"cusip": p["cusip"], "name": p.get("name"), "weight": p["weight"], "status": p["status"]}
               for p in binding["positions"] if p["status"] != "verified"]
    total = sum(p["weight"] for p in binding["positions"])
    covered = sum(verified[s]["weight"] for s in stocks if s in verified)
    eps = sum(verified[s]["weight"] for s, a in stocks.items() if s in verified and (a.get("financials") or {}).get("eps"))
    return {"passed": not unexplained and not extra and binding["cut"] == cut, "members": len(stocks),
            "spy_weight_covered": round(covered / total, 6), "spy_weight_with_ttm_eps": round(eps / total, 6),
            "unexplained_missing": unexplained, "not_in_binding": extra,
            "declared_exclusions": {"unbound_positions": unbound,
                                    "unbound_weight": round(sum(u["weight"] for u in unbound) / total, 6),
                                    "no_sector_in_list_revision": sorted(declared),
                                    "eps_withheld_by_engine_guards": sorted(s for s, a in stocks.items()
                                                                            if not (a.get("financials") or {}).get("eps"))}}


def identity(market, binding, fundamentals):
    """CIK from the cut-dated fundamentals and the N-PORT filed price reproduced in the snapshot's share basis."""
    by_symbol = {p["symbol"]: p for p in binding["positions"] if p["status"] == "verified"}
    ciks = {m["cusip"]: m.get("cik") for m in fundamentals["members"]}
    report_date = binding["report_date"]
    mismatches = []
    for asset in (a for a in market["assets"] if a["type"] == "stock"):
        position = by_symbol[asset["symbol"]]
        if ciks.get(position["cusip"]) != asset["cik"]:
            mismatches.append({"symbol": asset["symbol"], "check": "cik"})
            continue
        row = next((r for r in asset["history"] if r["date"] == report_date), None)
        if row is None:
            mismatches.append({"symbol": asset["symbol"], "check": "no close on the report date"})
            continue
        # Share splits and the spin-off price adjustments the provider applies backwards to earlier closes.
        events = (asset.get("splits") or []) + (asset.get("price_adjustments") or [])
        between = math.prod(s["ratio"] for s in events if report_date < s["date"])
        difference = row["close"] * between / position["filed_price"] - 1
        if abs(difference) > TOLERANCE:
            mismatches.append({"symbol": asset["symbol"], "check": "filed price", "difference": round(difference, 6)})
    return {"passed": not mismatches, "report_date": report_date, "tolerance": TOLERANCE, "mismatches": mismatches}


def units(market):
    problems = []
    for asset in market["assets"]:
        rows = asset.get("history") or []
        if not rows or not all(finite(r["close"]) and r["close"] > 0 and finite(r["adj_close"]) and r["adj_close"] > 0
                               for r in rows):
            problems.append((asset["symbol"], "prices"))
        if any(a["date"] >= b["date"] for a, b in zip(rows, rows[1:])):
            problems.append((asset["symbol"], "dates not increasing"))
        if not finite(asset.get("later_split_factor_undone")) or asset["later_split_factor_undone"] <= 0:
            problems.append((asset["symbol"], "split factor"))
        p = asset.get("bond_profile")
        if p and not (0 <= p["duration"] <= 40 and (p.get("expenseRatio") is None or 0 <= p["expenseRatio"] <= .1)
                      and all(-.05 <= p[k] <= .2 for k in ("yieldToMaturity", "secYield", "realYield") if k in p)):
            problems.append((asset["symbol"], "bond profile range"))
        eps = ((asset.get("financials") or {}).get("eps") or {}).get("value")
        if eps is not None and not (finite(eps) and abs(eps) < asset["price"]):
            problems.append((asset["symbol"], "EPS above price"))
    for row in market["macro"]:
        if row.get("unit") not in MACRO_UNITS or not finite(row.get("value")):
            problems.append((row.get("id"), "macro unit or value"))
        elif row["unit"] == "%" and not (-5 <= row["value"] <= 30 if row["id"] in RATES else 0 <= row["value"] <= 100):
            problems.append((row["id"], "percent range"))
    return {"passed": not problems, "problems": [{"item": a, "check": b} for a, b in problems]}


def engine_inputs(market_bytes, volatility_bytes, decision, model_version):
    sha = lambda b: hashlib.sha256(b).hexdigest()
    weights = sum(p["weight"] for p in decision.get("positions", []))
    checks = {"market_bytes": decision.get("market_sha256") == sha(market_bytes),
              "volatility_bytes": decision.get("volatility_sha256") == sha(volatility_bytes),
              "engine_version": decision.get("engine_version") == model_version,
              "proposed": decision.get("status") == "proposed",
              "weights_sum_to_one": abs(weights - 1) < 1e-6, "outcomes_not_read": decision.get("outcomes_read") is False}
    return {"passed": all(checks.values()), **checks}


def model_version(root=ROOT):
    text = (root / "dist/assets/js/policy.mjs").read_text()
    return re.search(r'MODEL_VERSION = "([^"]+)"', text)[1]


def audit(cut=CUT, root=ROOT):
    base = root / "data/historical/first-cut-snapshot-v1"
    market_bytes = gzip.decompress((base / f"{cut}.json.gz").read_bytes())
    volatility_bytes = gzip.decompress((base / f"{cut}.volatility.json.gz").read_bytes())
    market, volatility = json.loads(market_bytes), json.loads(volatility_bytes)
    decision = json.loads((base / f"{cut}.decision.json").read_text())
    name = "first-cut.json" if cut == CUT else f"{cut}.json"
    binding = json.loads((root / "data/historical/price-binding-v1" / name).read_text())
    fundamentals = json.loads(gzip.decompress((root / "data/historical/first-cut-fundamentals-v1" / f"{cut}.json.gz").read_bytes()))
    checks = {"availability": availability(market, volatility, cut), "universe": universe(market, binding, cut),
              "identity": identity(market, binding, fundamentals), "units": units(market),
              "engine_inputs": engine_inputs(market_bytes, volatility_bytes, decision, model_version(root))}
    passed = all(c["passed"] for c in checks.values())
    return {
        "schema": "full-engine-first-cut-input-audit-v1", "cut": cut, "snapshot_sha256": decision["market_sha256"],
        "volatility_sha256": decision["volatility_sha256"], "checks": checks, "input_checks_passed": passed,
        "status": "inputs-pass-with-declared-exclusions" if passed else "blocked",
        "limitations": [
            "Prices are the current Yahoo revision restated to the cut's share basis, not an original vendor vintage; "
            "the unofficial endpoint grants no redistribution.",
            "Sectors come from the Wikipedia list revision in force at the cut, not from S&P's official file.",
            "The ETF list is the current engine's list, chosen after the cut.",
            "The engine, its parameters and the reference preset were developed after the cut: the decision is a "
            "development-period reconstruction and cannot be confirmatory evidence.",
            "Members bought out or delisted after the cut without a free series are excluded positions, not priced.",
        ],
        "outcomes_read": False, "confirmatory_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default=CUT)
    parser.add_argument("--verify", action="store_true", help="recompute every audited cut and compare with its report")
    options = parser.parse_args()
    if options.verify:
        for cut in audited_cuts():
            if json.loads(report_path(cut).read_text()) != audit(cut):
                raise SystemExit(f"{cut}: archived input audit does not reproduce")
            print(cut, "input audit reproduced")
        return
    report = audit(options.cut)
    report_path(options.cut).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: (v["passed"] if isinstance(v, dict) else v) for k, v in report["checks"].items()}, indent=1))
    print(report["status"])


if __name__ == "__main__":
    main()
