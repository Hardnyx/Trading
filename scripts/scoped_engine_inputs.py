"""Compile a small, explicitly retrospective input set for the actual engine."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import gzip
import json
import math
from pathlib import Path
import re
import subprocess

if __package__:
    from .historical_sources import ROOT, MARKET_COMMIT, canonical, sha
    from .historical_price_audit import build_audit
    from .audit_historical_inputs import read_record
    from .historical_identifiers import build_report as identifier_report
    from .historical_replay_inputs import materialize_macro_inputs
    from .ttm_signal_research import eps_at
else:
    from historical_sources import ROOT, MARKET_COMMIT, canonical, sha
    from historical_price_audit import build_audit
    from audit_historical_inputs import read_record
    from historical_identifiers import build_report as identifier_report
    from historical_replay_inputs import materialize_macro_inputs
    from ttm_signal_research import eps_at

PILOT_PROTOCOL = "docs/protocolo-piloto-integrado-v1.json"


def prior_day(cut):
    return (date.fromisoformat(cut) - timedelta(days=1)).isoformat()


def reconstruct_stock(original, history, source, cut, price_cut):
    eps, reason = eps_at(original, source["rows"], cut, price_cut)
    if reason:
        return None, reason
    reported = eps["reported_value"]
    eps = {k: v for k, v in eps.items() if k not in ("future_split_divisor", "reported_value")}
    # eps_at returns today's split units; production inputs here use the
    # origin's share units, matching the prepared historical close levels.
    eps["value"] = reported
    index = original.get("distribution_index") or {}
    lower = (date.fromisoformat(cut) - timedelta(days=364)).isoformat()
    if (not index.get("complete_ex_date_index") or index.get("currency") != "USD" or
            index.get("coverage_start", "9999") > lower or index.get("coverage_end", "") < cut):
        return None, "incomplete-trailing-provider-dividends"
    dividends = [r for r in index["records"] if lower <= r["ex_date"] < cut]
    if (len({r["ex_date"] for r in dividends}) != len(dividends) or
            any(type(r.get("amount_per_share")) not in (float, int) or
                not math.isfinite(r["amount_per_share"]) or r["amount_per_share"] < 0 for r in dividends)):
        return None, "invalid-trailing-dividends"
    # Both prices and quoted dividend events in the frozen provider data are
    # in the provider's final split units. This is a declared research basis.
    dividend = sum(r["amount_per_share"] for r in dividends) * history["declared_split_reversal_factor"]
    known = [r for r in source["rows"] if r.get("filed", "9999") <= prior_day(cut) and r.get("end", "9999") <= prior_day(cut)]
    filings = {(r["filed"], r["end"], r.get("form")) for r in known if r.get("form") in ("10-K", "10-Q", "20-F")}
    rows = history["history"]
    output = {k: original[k] for k in ("symbol", "name", "type", "sector", "currency", "cik", "assumptions") if k in original}
    output.update(history=rows, price=rows[-1]["close"], price_date=cut,
                  splits=[s for s in original.get("splits", []) if s["date"] <= cut],
                  dividend_per_share=dividend,
                  financials={"eps": eps, "observed_at": source["observed_at"],
                              "refresh_status": "archived-ttm-only-reconstruction", "history": []},
                  filings=[{"filing_date": f, "report_date": e, "form": t} for f, e, t in sorted(filings)],
                  historical_reconstruction={"original_financial_quality_verified": False,
                      "eps_source_sha256": source["full_response_sha256"],
                      "provider_dividend_basis_verified": False})
    return output, None


def reconstructed_holdings(origin, retrieved_at):
    counts = Counter(p["ticker_observation"]["source_ticker"] for p in origin["positions"] if p["ticker_observation"] and p["weight"] > 0)
    positions = [{"symbol": p["ticker_observation"]["source_ticker"], "weight": p["weight"]}
                 for p in origin["positions"] if p["ticker_observation"] and p["weight"] > 0
                 and counts[p["ticker_observation"]["source_ticker"]] == 1
                 and re.fullmatch(r"[A-Z0-9.-]{1,15}", p["ticker_observation"]["source_ticker"])]
    source = origin["spy_source"]
    availability = [source["available_after_day"]] + [e["available_after_day"]
        for p in origin["positions"] if p["ticker_observation"]
        for e in p["ticker_observation"]["evidence"]]
    known = (date.fromisoformat(max(availability)) + timedelta(days=1)).isoformat()
    if known > origin["cut"]:
        raise ValueError("Holdings availability after pilot origin")
    return {"as_of": source["as_of"], "positions": positions,
            "observed_at": known + "T12:00:00Z", "retrieved_at": retrieved_at,
            "observed_at_semantics": "virtual-public-availability-clock-for-research-not-capture",
            "original_capture_verified": False, "expense_ratio": None,
            "source_url": f"https://www.sec.gov/Archives/edgar/data/884394/{source['accession'].replace('-', '')}/primary_doc.xml"}


def compile_inputs(market, facts, price_report, histories, identifiers, macro, protocol, generated_at, source_retrievals):
    if market["price_as_of"] != facts["price_cut"] or protocol["source_market_commit"] != MARKET_COMMIT:
        raise ValueError("Frozen input identity mismatch")
    selection = protocol["selection"]
    candidates = sorted(r["cut"] for r in price_report["matrix"] if r["research_history_weight"] >= selection["minimum_weight"])
    selected = candidates[:selection["maximum_origins"]]
    if not selected:
        raise ValueError("No pilot origin meets the registered input-coverage rule")
    by_symbol = {a["symbol"]: a for a in market["assets"]}
    by_origin = {r["cut"]: r for r in identifiers["matrix"]}
    origins = []
    for cut in selected:
        assets, exclusions = [], Counter()
        for history in histories["origins"][cut]:
            original = by_symbol[history["symbol"]]
            source = facts["sources"].get(history["symbol"])
            if source is None or str(source.get("cik")) != str(original.get("cik")):
                exclusions["missing-or-mismatched-eps-source"] += 1
                continue
            asset, reason = reconstruct_stock(original, history, source, cut, market["price_as_of"])
            if reason:
                exclusions[reason] += 1
            else:
                assets.append(asset)
        benchmark = {k: by_symbol["SPY"][k] for k in ("symbol", "name", "type", "sector", "currency") if k in by_symbol["SPY"]}
        benchmark_history = [{k: r[k] for k in ("date", "close", "adj_close")} for r in by_symbol["SPY"]["history"] if r["date"] <= cut][-501:]
        if not benchmark_history or benchmark_history[-1]["date"] != cut:
            raise ValueError("Missing exact benchmark origin price")
        benchmark.update(history=benchmark_history, price=benchmark_history[-1]["close"], price_date=cut,
                         financials={}, dividend_per_share=None,
                         holdings=reconstructed_holdings(by_origin[cut], source_retrievals[by_origin[cut]["spy_source"]["accession"]]))
        assets.append(benchmark)
        snapshot = {"price_as_of": cut, "requested_as_of": cut, "generated_at": generated_at,
                    "assets": assets, "macro": list(macro["macro"][cut].values()), "positions": []}
        origins.append({"cut": cut, "snapshot": snapshot, "snapshot_sha256": sha(canonical(snapshot)),
                        "usable_stocks": len(assets)-1, "eps_exclusions": dict(sorted(exclusions.items()))})
    schedule = [{"cut": r["cut"], "research_history_weight": r["research_history_weight"],
                 "selected": r["cut"] in selected,
                 "reason": "selected-before-model-results" if r["cut"] in selected else
                           "outside-registered-pilot-count" if r["cut"] in candidates else "insufficient-price-input-coverage"}
                for r in price_report["matrix"]]
    return {"protocol": protocol, "generated_at": generated_at, "origins": origins, "schedule": schedule,
            "source_market_commit": MARKET_COMMIT, "canonical_market_sha256": sha(canonical(market)),
            "price_audit_sha256": sha(canonical(price_report)),
            "eps_archive_market_sha256": facts["input_market_sha256"],
            "builder_sha256": sha(Path(__file__).read_bytes()),
            "production_eligible": False, "prospective": False, "predictive_validation": "not-established"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-input", default="data/historical/provider-inputs-v1")
    parser.add_argument("--identifier-input", default="data/historical/identifier-sources-v1")
    parser.add_argument("--output", default="out/scoped-engine-inputs-v1.json.gz")
    args = parser.parse_args()
    protocol = json.loads((ROOT / PILOT_PROTOCOL).read_bytes())
    raw_market = subprocess.check_output(["git", "show", MARKET_COMMIT + ":dist/data/market.json"], cwd=ROOT)
    market = json.loads(raw_market)
    facts_bytes = (ROOT / protocol["eps_archive"]).read_bytes()
    facts = json.loads(gzip.decompress(facts_bytes))
    if sha(raw_market) != facts["input_market_sha256"]:
        raise ValueError("Archived EPS study uses a different frozen market")
    price_protocol = json.loads((ROOT / "docs/protocolo-precios-historicos-v1.json").read_bytes())
    prices, histories = build_audit(args.provider_input, args.identifier_input, market, price_protocol)
    identifiers = identifier_report(args.provider_input, args.identifier_input)
    provider_root = Path(args.provider_input)
    provider = json.loads((provider_root / "manifest.json").read_bytes())
    retrievals = {ptr["accession"]: read_record(provider_root, ptr)[0]["retrieved_at"]
                  for ptr in provider["sec"]["documents"] if ptr["form"].startswith("NPORT")}
    macro = materialize_macro_inputs(args.provider_input, [r["cut"] for r in prices["matrix"]])
    output = compile_inputs(market, facts, prices, histories, identifiers, macro, protocol, datetime.now(timezone.utc).isoformat(), retrievals)
    output["eps_archive_sha256"] = sha(facts_bytes)
    output["pilot_protocol_sha256"] = sha((ROOT / PILOT_PROTOCOL).read_bytes())
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(canonical(output)+b"\n", mtime=0))
    print(json.dumps({"origins": [{k:r[k] for k in ("cut","usable_stocks","eps_exclusions")} for r in output["origins"]], "production_eligible": False}))


if __name__ == "__main__":
    main()
