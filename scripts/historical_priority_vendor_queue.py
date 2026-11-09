"""Bind the missing-SPY-position request queue to the frozen SEC vendor contract.

The ranking uses original SPY weights, not realized returns. This code never
invents a vendor identifier or promotes retrospective evidence into a causal
historical security master. Licensed exports remain local.
"""
import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path

if __package__:
    from .historical_identity_requests import build_requests
    from .historical_spy_membership_audit import audit as audit_membership
    from .historical_vendor_identity import read_evidence, reconcile, request_hash, valid_cusip
else:
    from historical_identity_requests import build_requests
    from historical_spy_membership_audit import audit as audit_membership
    from historical_vendor_identity import read_evidence, reconcile, request_hash, valid_cusip

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "historical-spy-priority-vendor-queue-v1"
COLUMNS = (
    "priority_rank", "cusip", "reported_spy_weight", "original_ticker_hints",
    "source_positions", "spy_accession", "spy_holdings_as_of",
    "public_available_after_day", "decision_cut",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-10)


def build_queue(requests, membership):
    """Crosscheck the reverse-coverage gap against each original SEC request."""
    cut = requests["cut"]
    require(membership["schema"] == "historical-spy-membership-audit-v1" and
            membership["first_candidate_cut"] == cut and
            membership["price_vendor_identity_certified"] is False and
            membership["full_engine_eligible_cuts"] == 0,
            "Invalid source-membership contract or historical eligibility")
    origin = next((r for r in membership["cut_summaries"]
                   if r["cut"] == cut), None)
    require(origin is not None and
            origin["status"] == "source-backed-spy-membership-only" and
            origin["spy_accession"] == requests["spy_original_accession"] and
            origin["available_after_day"] < cut and origin["as_of"] <= cut,
            "SEC public filing is not identical to the identity request")
    provenance = membership["source_provenance"]
    require(provenance["source_market_commit"] == requests["source_market_commit"] and
            provenance["provider_manifest_sha256"] == requests["source_manifest_sha256"] and
            provenance["identifier_manifest_sha256"] == requests["identifier_manifest_sha256"] and
            provenance["archived_observations_sha256"] == requests["identifier_archive_sha256"],
            "Original SEC source hashes or frozen universe changed")
    overlap = membership["first_cut_pilot_ticker_overlap"]
    require(overlap["cut"] == cut and overlap["historical_universe_certified"] is False and
            overlap["requests_are_research_only"] is True and
            close(requests["positive_spy_weight"], overlap["historical_positive_spy_weight"]),
            "Source SPY portfolio weight or research status changed")
    originals = {r["source_position"]: r for r in requests["requests"]}
    require(len(originals) == len(requests["requests"]) and
            all(r["weight"] > 0 and
                r.get("vendor_instrument_id") is None and
                r["vendor_price_series_verified"] is False and
                r["original_price_vintage_verified"] is False
                for r in originals.values()),
            "Original SEC requests are duplicated or silently vendor-enriched")
    require(len(originals) == origin["positive_positions"],
            "Original SPY positive source positions changed")

    priority = overlap["priority_vendor_identity_requests"]
    require(len(priority) == overlap["distinct_valid_cusips_not_covered_by_pilot"] and
            len({r["cusip"] for r in priority}) == len(priority),
            "Omitted CUSIP priority queue is duplicated or incomplete")
    rows = []
    seen_positions = set()
    for rank, item in enumerate(priority, 1):
        cusip = item["cusip"]
        require(valid_cusip(cusip) and
                item["price_identifier_verified"] is False and
                item["reason"] == "source-disclosed-spy-position-not-in-retrospective-pilot",
                "Priority item falsely asserts a verified price identity")
        positions = item["source_positions"]
        require(isinstance(positions, list) and positions == sorted(set(positions)) and
                positions and all(type(p) is int and p in originals for p in positions) and
                seen_positions.isdisjoint(positions),
                "Priority positions duplicated or missing from original SEC requests")
        seen_positions.update(positions)
        sourced = [originals[p] for p in positions]
        require(all(p["cusip"] == cusip for p in sourced) and
                close(sum(p["weight"] for p in sourced), item["reported_positive_weight"]) and
                sorted({p["original_ticker_observation"] for p in sourced
                        if p["original_ticker_observation"]}) == item["original_source_tickers"],
                "Priority weight, CUSIP or original ticker changed")
        require(rank == 1 or
                (rows[-1]["reported_spy_weight"] > item["reported_positive_weight"] or
                 (close(rows[-1]["reported_spy_weight"], item["reported_positive_weight"]) and
                  rows[-1]["cusip"] < cusip)),
                "Priority order no longer follows original SPY weights and CUSIP ties")
        rows.append({
            "priority_rank": rank, "cusip": cusip,
            "reported_spy_weight": item["reported_positive_weight"],
            "original_ticker_hints": item["original_source_tickers"],
            "source_positions": positions,
            "spy_accession": origin["spy_accession"],
            "spy_holdings_as_of": origin["as_of"],
            "public_available_after_day": origin["available_after_day"],
            "decision_cut": cut,
        })
    excluded_invalid = overlap["source_invalid_cusip_positions_not_covered_by_pilot"]
    require(len(seen_positions) + excluded_invalid ==
            overlap["source_positive_positions_not_covered_by_pilot"],
            "Historical SPY omitted position count does not reconcile")
    selected_weight = sum(r["reported_spy_weight"] for r in rows)
    omitted_total = overlap["source_spy_weight_not_covered_by_pilot"]
    require(selected_weight <= omitted_total + 1e-10 and
            selected_weight >= -1e-10, "Historical missing-SPY weight mismatch")
    return {
        "protocol": PROTOCOL, "cut": cut,
        "source_market_commit": requests["source_market_commit"],
        "spy_accession": origin["spy_accession"],
        "spy_original_sha256": requests["spy_original_sha256"],
        "sec_request_sha256": request_hash(requests),
        "identifier_archive_sha256": requests["identifier_archive_sha256"],
        "priority_cusips": len(rows),
        "original_positive_positions": len(originals),
        "source_positive_spy_weight": requests["positive_spy_weight"],
        "omitted_source_spy_weight": omitted_total,
        "omitted_valid_cusip_weight": selected_weight,
        "omitted_invalid_or_missing_cusip_weight": omitted_total-selected_weight,
        "omitted_invalid_or_missing_cusip_positions": excluded_invalid,
        "priority_requests": rows,
        "ordering": "descending-original-SPY-position-weight-then-CUSIP",
        "vendor_identifiers_received": False,
        "historical_security_master_certified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def template_csv(queue):
    """The CSV asks for vendor data and contains no provider-returned identifiers."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in queue["priority_requests"]:
        writer.writerow({**item,
                         "original_ticker_hints": ";".join(item["original_ticker_hints"]),
                         "source_positions": ";".join(str(x) for x in item["source_positions"])})
    return output.getvalue()


def summarize_reconciliation(queue, vendor_report):
    """Join status by original SEC position; never distribute private identifiers."""
    require(vendor_report["cut"] == queue["cut"] and
            vendor_report["request_sha256"] == queue["sec_request_sha256"] and
            vendor_report["full_engine_replay_ready"] is False,
            "Vendor reconciliation does not match original SEC request")
    origin_positions = {p["source_position"]: p for p in vendor_report["positions"]}
    require(len(origin_positions) == len(vendor_report["positions"]) and
            len(origin_positions) == queue["original_positive_positions"],
            "Incomplete or duplicate full vendor source-position reconciliation")
    counts = Counter()
    weights = Counter()
    for priority in queue["priority_requests"]:
        positions = [origin_positions.get(pos) for pos in priority["source_positions"]]
        require(all(p is not None and p["cusip"] == priority["cusip"]
                    for p in positions), "Source position or CUSIP changed in vendor crosswalk")
        states = {p["status"] for p in positions}
        require(len(states) == 1, "One historical CUSIP received conflicting vendor states")
        status = next(iter(states))
        require(all(p["historical_availability_certified"] is False and
                    p["price_history_verified"] is False and
                    p["production_eligible"] is False for p in positions),
                "Vendor crosswalk promoted unverified historical source")
        counts[status] += 1
        weights[status] += priority["reported_spy_weight"]
    require(close(sum(weights.values()), queue["omitted_valid_cusip_weight"]),
            "Vendor priority weight total changed")
    return {
        "protocol": "historical-spy-priority-vendor-reconciliation-v1",
        "cut": queue["cut"],
        "sec_request_sha256": queue["sec_request_sha256"],
        "vendor_manifest_sha256": vendor_report["vendor_manifest_sha256"],
        "priority_cusips": len(queue["priority_requests"]),
        "status_counts_by_distinct_cusip": dict(sorted(counts.items())),
        "source_spy_weight_by_status": dict(sorted(weights.items())),
        "all_matches_are_retrospective": True,
        "historical_security_master_certified": False,
        "price_series_certified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default="out/historical-priority-vendor-requests-v1.csv")
    parser.add_argument("--summary", default="out/historical-priority-vendor-requests-v1.json")
    parser.add_argument("--evidence-dir", help="Private export directory for the existing vendor contract")
    parser.add_argument("--local-report", default="out/historical-priority-vendor-reconciliation-v1.json")
    args = parser.parse_args(argv)
    requests = build_requests(ROOT)
    membership = audit_membership(ROOT)
    queue = build_queue(requests, membership)
    for name, data in [(args.template, template_csv(queue)),
                       (args.summary, json.dumps({k: v for k, v in queue.items()
                                                  if k != "priority_requests"},
                                                 indent=2) + "\n")]:
        output = Path(name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(data, encoding="utf-8")
    if args.evidence_dir:
        rows, provenance, manifest_hash = read_evidence(args.evidence_dir, requests)
        vendor = reconcile(requests, rows, provenance, manifest_hash)
        private = summarize_reconciliation(queue, vendor)
        output = Path(args.local_report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(private, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"priority_cusips": queue["priority_cusips"],
                          "retrospective_vendor_statuses": private["status_counts_by_distinct_cusip"],
                          "historical_security_master_certified": False}, sort_keys=True))
    else:
        print(json.dumps({
            "priority_cusips": queue["priority_cusips"],
            "omitted_valid_cusip_weight": round(queue["omitted_valid_cusip_weight"], 8),
            "vendor_identifiers_received": False,
            "full_engine_eligible_cuts": 0,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
