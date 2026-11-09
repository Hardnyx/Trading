"""Reconstruct public SPY filing membership without inferring an investable universe.

Reparse the frozen SEC originals across the 48 scheduled development cuts,
enumerate disclosed CUSIPs and filing-to-filing changes, and keep original
ticker observations separate from instrument/price bindings. No current
constituents, realized returns, or trading outcomes are consulted.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
import gzip
import hashlib
import json
import math
from pathlib import Path

if __package__:
    from .historical_identifiers import build_report, cusip_valid
    from .historical_sources import canonical
    from .historical_parameter_audit import load as load_pilot
else:
    from historical_identifiers import build_report, cusip_valid
    from historical_sources import canonical
    from historical_parameter_audit import load as load_pilot

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_DIR = "data/historical/provider-inputs-v1"
IDENTIFIER_DIR = "data/historical/identifier-sources-v1"
IDENTIFIER_ARCHIVE = "data/historical/identifier-observations-v1/observations.json.gz"
IDENTIFIER_COVERAGE = "data/historical/identifier-observations-v1/coverage.json"
FROZEN_PROTOCOL = "docs/protocolo-replay-integral-v1.json"
FIRST_CUT = "2024-12-31"
OUTPUT = "out/historical-spy-membership-audit-v1.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def source_row(row):
    """Use only original filing membership and as-of ticker observations."""
    cusip = row["cusip"]
    ticker = row.get("ticker_observation")
    require(row.get("price_instrument_binding") is None,
            "Retrospective price binding was promoted into source membership")
    require(type(row.get("weight")) in (float, int) and
            math.isfinite(row["weight"]), "Nonfinite source membership weight")
    require(ticker is None or (row.get("identifier_status") == "explicit-ticker-observed" and
            isinstance(ticker.get("source_ticker"), str) and bool(ticker["source_ticker"])),
            "Unverified source ticker injected")
    require(not ticker or all(receipt["raw_sha256"] and
            receipt["available_after_day"] for receipt in ticker.get("evidence", [])),
            "Missing original ticker evidence")
    return cusip_valid(cusip), ticker["source_ticker"] if ticker else None


def summarize_cut(row):
    """Report one decision date, with no extension of stale SEC filings."""
    cut, spy = row["cut"], row["spy_source"]
    date.fromisoformat(cut)
    status = spy["status"]
    require(status in ("source-available", "stale-or-invalid-source", "no-prior-public-record"),
            "Unrecognized SPY source eligibility")
    if status != "source-available":
        require(not row.get("positions") and row["mapped_positive_weight"] == 0,
                "Blocked historical cut gained unverified holdings")
        return {"cut": cut, "status": "blocked-no-fresh-public-spy-holdings",
                "spy_source_status": status, "spy_accession": spy.get("accession"),
                "as_of": spy.get("as_of"), "available_after_day": spy.get("available_after_day"),
                "positive_positions": 0, "valid_cusip_positions": 0,
                "distinct_valid_cusips": 0, "original_explicit_ticker_positions": 0,
                "positive_weight": None, "valid_cusip_weight": None,
                "explicit_ticker_weight": None, "security_price_identifiers_verified": 0}
    require(spy["available_after_day"] < cut and spy["as_of"] <= cut and
            0 <= (date.fromisoformat(cut)-date.fromisoformat(spy["as_of"])).days <= 120,
            "SEC filing not public/fresh at historical decision")
    require(isinstance(spy.get("accession"), str) and spy["accession"],
            "Missing original SPY accession")
    positive = []
    bad_cusip = 0
    ticker_weight = 0.0
    valid_weight = 0.0
    for p in row["positions"]:
        valid, ticker = source_row(p)
        if p["weight"] <= 0:
            continue
        if ticker:
            observation = p["ticker_observation"]
            require(observation["as_of"] <= cut and observation["evidence"] and
                    all(e["available_after_day"] < cut for e in observation["evidence"]),
                    "Look-ahead in SPY position ticker evidence")
            ticker_weight += p["weight"]
        if valid:
            valid_weight += p["weight"]
        else:
            bad_cusip += 1
        positive.append({"cusip": p["cusip"], "ticker": ticker,
                         "weight": p["weight"], "valid": valid})
    require(positive, "No positive SPY source positions")
    total = sum(p["weight"] for p in positive)
    require(.65 <= total <= 1.05, "Implausible SPY positive source weight")
    require(math.isclose(ticker_weight, row["mapped_positive_weight"],
                         rel_tol=0, abs_tol=1e-10),
            "Original ticker weight differs from frozen identifier audit")
    unique_cusips = {p["cusip"] for p in positive if p["valid"]}
    require(all(p["valid"] for p in positive if p["cusip"] in unique_cusips),
            "CUSIP validity changed within source")
    return {
        "cut": cut, "status": "source-backed-spy-membership-only",
        "spy_source_status": status, "spy_accession": spy["accession"],
        "as_of": spy["as_of"], "available_after_day": spy["available_after_day"],
        "positive_positions": len(positive),
        "valid_cusip_positions": len(positive)-bad_cusip,
        "distinct_valid_cusips": len(unique_cusips),
        "invalid_or_missing_cusip_positions": bad_cusip,
        "duplicate_valid_cusip_positions": len(positive)-bad_cusip-len(unique_cusips),
        "original_explicit_ticker_positions": sum(bool(p["ticker"]) for p in positive),
        "positive_weight": total, "valid_cusip_weight": valid_weight,
        "explicit_ticker_weight": ticker_weight,
        "security_price_identifiers_verified": 0,
    }


def filing_transitions(matrix):
    """Changes between distinct *disclosed SPY snapshots*, not issuer events."""
    transitions = []
    previous_cusips = None
    previous_accession = None
    previous_as_of = None
    for row in matrix:
        if row["spy_source"]["status"] != "source-available":
            continue
        accession = row["spy_source"]["accession"]
        if accession == previous_accession:
            continue
        members = {p["cusip"] for p in row["positions"]
                   if p["weight"] > 0 and cusip_valid(p["cusip"])}
        if previous_cusips is not None:
            transitions.append({
                "from_accession": previous_accession,
                "to_accession": accession,
                "from_as_of": previous_as_of,
                "to_as_of": row["spy_source"]["as_of"],
                "first_publicly_used_at_cut": row["cut"],
                "newly_disclosed_cusips": sorted(members - previous_cusips),
                "no_longer_disclosed_cusips": sorted(previous_cusips - members),
                "interpretation": "SPY filing difference only; not listings, delistings or a trading universe",
            })
        previous_cusips, previous_accession = members, accession
        previous_as_of = row["spy_source"]["as_of"]
    return transitions


def pilot_overlap(row, pilot_symbols):
    """Compare literal ticker strings, never equate them to vendor price IDs."""
    require(row["cut"] == FIRST_CUT and row["spy_source"]["status"] == "source-available",
            "Pilot overlap requires the original first-cut SPY filing")
    require(isinstance(pilot_symbols, list) and len(pilot_symbols) == len(set(pilot_symbols)),
            "Duplicate pilot symbols")
    by_ticker = defaultdict(set)
    by_weight = defaultdict(float)
    for p in row["positions"]:
        if p["weight"] <= 0 or not cusip_valid(p["cusip"]):
            continue
        ticker = p.get("ticker_observation")
        if ticker and ticker["evidence"] and ticker["as_of"] <= row["cut"] and all(
                e["available_after_day"] < row["cut"] for e in ticker["evidence"]):
            key = ticker["source_ticker"]
            by_ticker[key].add(p["cusip"])
            by_weight[(key, p["cusip"])] += p["weight"]
    unambiguous = {symbol: next(iter(cusips)) for symbol, cusips in by_ticker.items()
                   if len(cusips) == 1}
    matched = sorted(s for s in pilot_symbols if s in unambiguous)
    ambiguous = sorted(s for s in pilot_symbols if len(by_ticker.get(s, set())) > 1)
    missing = sorted(set(pilot_symbols)-set(matched)-set(ambiguous))
    return {
        "sample": "retrospective-current-catalogue-scoped-pilot",
        "cut": FIRST_CUT, "pilot_stock_symbols": len(pilot_symbols),
        "exact_public_ticker_string_matches": len(matched),
        "ambiguous_ticker_string_matches": len(ambiguous),
        "no_exact_public_spy_ticker_observation": len(missing),
        "candidate_matched_spy_weight": sum(by_weight[(s, unambiguous[s])] for s in matched),
        "pilot_unmatched_symbols": missing,
        "pilot_ambiguous_symbols": ambiguous,
        "ticker_string_match_is_not_verified_security_identity": True,
        "historical_universe_certified": False,
    }


def build_result(matrix, pilot_symbols, provenance):
    require(matrix and [x["cut"] for x in matrix] == sorted(set(x["cut"] for x in matrix)),
            "Historical review calendar is incomplete or unordered")
    cuts = [summarize_cut(row) for row in matrix]
    source_cut = next((row for row in matrix if row["cut"] == FIRST_CUT), None)
    require(source_cut is not None, "First candidate absent from historical calendar")
    transitions = filing_transitions(matrix)
    fresh = [r for r in cuts if r["status"] == "source-backed-spy-membership-only"]
    return {
        "schema": "historical-spy-membership-audit-v1",
        "source_provenance": provenance,
        "first_candidate_cut": FIRST_CUT,
        "study_cuts": len(cuts),
        "fresh_public_spy_holdings_cuts": len(fresh),
        "blocked_or_stale_spy_holdings_cuts": len(cuts)-len(fresh),
        "distinct_filing_transitions": len(transitions),
        "cut_summaries": cuts,
        "filing_transitions": transitions,
        "first_cut_pilot_ticker_overlap": pilot_overlap(source_cut, pilot_symbols),
        "price_vendor_identity_certified": False,
        "continuous_historical_universe_certified": False,
        "issuer_delisting_events_verified": False,
        "full_engine_eligible_cuts": 0,
        "production_eligible": False,
        "predictive_validation": "not-established",
        "next_evidence": [
            "per-cut licensed permanent CUSIP/provider-instrument price binding",
            "delisted and acquired issuers outside surviving current catalogue",
            "original historical execution prices, split and distribution event vintages",
            "complete as-of tradable US universe rather than SPY fund disclosures",
        ],
    }


def audit(root=ROOT):
    root = Path(root)
    raw = (root / IDENTIFIER_ARCHIVE).read_bytes()
    archived = json.loads(gzip.decompress(raw))
    reconstructed = build_report(root / PROVIDER_DIR, root / IDENTIFIER_DIR)
    require(archived == reconstructed,
            "SEC-derived original membership archive cannot be independently reproduced")
    compact = json.loads((root / IDENTIFIER_COVERAGE).read_bytes())
    require({k: v for k, v in archived.items() if k != "matrix"} ==
            {k: v for k, v in compact.items() if k != "matrix"} and
            [{k: v for k, v in row.items() if k != "positions"}
             for row in archived["matrix"]] == compact["matrix"],
            "Compact published membership coverage differs from frozen original positions")
    protocol = json.loads((root / FROZEN_PROTOCOL).read_bytes())
    require([row["cut"] for row in archived["matrix"]] == protocol["expected_cuts"],
            "Pre-registered historical decision calendar changed")
    require(not archived["identifier_audit"]["missing_documents"] and
            not archived["identifier_audit"]["missing_discoveries"] and
            not archived["identifier_audit"]["collection_errors"],
            "Original identifier source inventory incomplete")
    pilot_protocol, summary, bundle, full = load_pilot(root)
    require(summary["certified_full_engine_cuts"] == 0 and
            pilot_protocol["sample_role"] == "previously-inspected-development-history",
            "Pilot was promoted to full-engine historical certification")
    pilot_origins = [o for o in bundle["origins"] if o["cut"] == FIRST_CUT]
    require(len(pilot_origins) == 1 and
            pilot_origins[0]["snapshot"]["price_as_of"] == FIRST_CUT,
            "Missing frozen first-cut pilot snapshot")
    stock_symbols = [a["symbol"] for a in pilot_origins[0]["snapshot"]["assets"]
                     if a["type"] == "stock"]
    return build_result(archived["matrix"], stock_symbols, {
        "source_market_commit": archived["source_market_commit"],
        "provider_manifest_sha256": archived["provider_manifest_sha256"],
        "identifier_manifest_sha256": archived["identifier_audit"]["manifest_sha256"],
        "archived_observations_sha256": sha256(raw),
        "original_identifier_documents_verified": archived["identifier_audit"]["verified_documents"],
        "raw_sec_nport_reparsed": True,
        "archive_matches_independent_derivation": True,
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Fail on source mismatch without output")
    parser.add_argument("--output", default=OUTPUT)
    options = parser.parse_args(argv)
    result = audit()
    if not options.verify:
        output = Path(options.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print(json.dumps({
        "study_cuts": result["study_cuts"],
        "fresh_public_spy_holdings_cuts": result["fresh_public_spy_holdings_cuts"],
        "distinct_filing_transitions": result["distinct_filing_transitions"],
        "pilot_stock_symbols": result["first_cut_pilot_ticker_overlap"]["pilot_stock_symbols"],
        "exact_public_ticker_string_matches": result["first_cut_pilot_ticker_overlap"]["exact_public_ticker_string_matches"],
        "full_engine_eligible_cuts": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
