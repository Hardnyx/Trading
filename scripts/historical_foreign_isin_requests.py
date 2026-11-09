"""Build dated foreign-ISIN requests from original invalid-CUSIP SEC equity rows.

Requests use explicit ISO 6166 identifiers from public SPY N-PORT originals,
not current tickers or derived US CUSIPs. All source rows remain in the
denominator and ambiguous sources stay on a separate correction queue.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path

if __package__:
    from .historical_sec_alternate_identity import audit as audit_alternates, isin_valid
    from .historical_sources import canonical
    from .historical_vendor_identity import valid_cusip
else:
    from historical_sec_alternate_identity import audit as audit_alternates, isin_valid
    from historical_sources import canonical
    from historical_vendor_identity import valid_cusip

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "historical-foreign-isin-requests-v1"
OUTPUT = "out/historical-foreign-isin-requests-v1.json"
CSV = "out/historical-foreign-isin-requests-v1.csv"
REVIEW = "out/historical-foreign-isin-unresolved-v1.csv"
FIELDS = (
    "priority_rank", "original_isin", "reported_spy_weight",
    "source_positions", "source_ticker_hints", "source_lei_hints",
    "spy_accession", "original_sec_sha256", "public_available_after_day",
    "decision_cut", "source_identity_role",
)
REVIEW_FIELDS = (
    "source_position", "cusip_as_reported", "reported_spy_weight",
    "explicit_isins", "review_status", "decision_cut", "spy_accession",
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-10)


def build_requests(source):
    require(source["schema"] == "historical-sec-alternate-identity-review-v1" and
            source["original_cusip_rewritten"] is False and
            source["vendor_identifiers_certified"] == 0 and
            source["full_engine_eligible_cuts"] == 0 and
            source["source_public_available_after_day"] < source["cut"] and
            len(source["positions"]) == source["original_invalid_or_missing_cusip_positions"],
            "Original foreign-ISIN source was altered or promoted")
    grouped = defaultdict(lambda: {"positions": [], "weight": 0.,
                                   "tickers": set(), "leis": set()})
    unresolved = []
    seen = set()
    for item in source["positions"]:
        position, weight = item["source_position"], item["reported_spy_weight"]
        require(type(position) is int and position not in seen and
                math.isfinite(weight) and weight > 0 and
                item["source_accession"] == source["source_accession"] and
                item["source_original_sha256"] == source["source_original_sha256"] and
                item["public_available_after_day"] == source["source_public_available_after_day"] and
                item["decision_cut"] == source["cut"] and
                not valid_cusip(item["cusip_as_reported"]) and
                item["structural_us_isin_cusip_candidate"] is None,
                "Original source position, CUSIP or provenance changed")
        seen.add(position)
        isins = item["explicit_isins"]
        qualified = (len(isins) == 1 and item["review_status"] == "original-non-us-isin-only"
                     and isin_valid(isins[0]) and not isins[0].startswith("US"))
        if qualified:
            record = grouped[isins[0]]
            record["positions"].append(position)
            record["weight"] += weight
            record["tickers"].update(item["explicit_ticker_hints"])
            if item["original_lei_hint"]:
                record["leis"].add(item["original_lei_hint"])
        else:
            unresolved.append({
                "source_position": position,
                "cusip_as_reported": item["cusip_as_reported"],
                "reported_spy_weight": weight,
                "explicit_isins": isins,
                "review_status": item["review_status"],
                "decision_cut": source["cut"],
                "spy_accession": source["source_accession"],
            })
    ordered = sorted(grouped.items(), key=lambda row: (-row[1]["weight"], row[0]))
    requests = [{
        "priority_rank": index, "original_isin": isin,
        "reported_spy_weight": info["weight"],
        "source_positions": sorted(info["positions"]),
        "source_ticker_hints": sorted(info["tickers"]),
        "source_lei_hints": sorted(info["leis"]),
        "spy_accession": source["source_accession"],
        "original_sec_sha256": source["source_original_sha256"],
        "public_available_after_day": source["source_public_available_after_day"],
        "decision_cut": source["cut"],
        "source_identity_role": "original-foreign-isin-vendor-enquiry-only",
    } for index, (isin, info) in enumerate(ordered, 1)]
    eligible_count = sum(len(row["source_positions"]) for row in requests)
    eligible_weight = sum(row["reported_spy_weight"] for row in requests)
    unresolved_weight = sum(row["reported_spy_weight"] for row in unresolved)
    require(len(seen) == eligible_count + len(unresolved) and
            close(eligible_weight + unresolved_weight, source["original_spy_weight"]),
            "Foreign ISIN request denominator no longer reconciles to 26 SEC equities")
    return {
        "schema": SCHEMA, "cut": source["cut"],
        "source_accession": source["source_accession"],
        "source_original_sha256": source["source_original_sha256"],
        "public_available_after_day": source["source_public_available_after_day"],
        "original_invalid_cusip_positions": len(seen),
        "source_spy_weight": source["original_spy_weight"],
        "foreign_isin_request_positions": eligible_count,
        "distinct_foreign_isin_requests": len(requests),
        "foreign_isin_request_weight": eligible_weight,
        "unresolved_identifier_positions": len(unresolved),
        "unresolved_identifier_weight": unresolved_weight,
        "requests": requests,
        "unresolved": unresolved,
        "source_vendor_id_certified": False,
        "original_cusip_corrected": False,
        "automatic_historical_universe_promotion": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def request_hash(result):
    """Immutable study-cut and source-filing bound future vendor evidence key."""
    return hashlib.sha256(canonical({
        "cut": result["cut"], "source_original_sha256": result["source_original_sha256"],
        "requests": result["requests"]
    })).hexdigest()


def to_csv(rows, fields):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        entry = dict(row)
        for key in ("source_positions", "source_ticker_hints",
                    "source_lei_hints", "explicit_isins"):
            if key in entry:
                entry[key] = ";".join(str(x) for x in entry[key])
        writer.writerow(entry)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", default=OUTPUT)
    parser.add_argument("--csv", default=CSV)
    parser.add_argument("--review", default=REVIEW)
    args = parser.parse_args(argv)
    result = build_requests(audit_alternates(ROOT))
    if not args.verify:
        for name, data in [
            (args.output, json.dumps({
                **{k: v for k, v in result.items() if k not in ("requests", "unresolved")},
                "request_sha256": request_hash(result),
            }, indent=2) + "\n"),
            (args.csv, to_csv(result["requests"], FIELDS)),
            (args.review, to_csv(result["unresolved"], REVIEW_FIELDS)),
        ]:
            target = Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data, encoding="utf-8")
    print(json.dumps({
        "cut": result["cut"],
        "foreign_isin_request_positions": result["foreign_isin_request_positions"],
        "distinct_foreign_isin_requests": result["distinct_foreign_isin_requests"],
        "foreign_isin_request_weight": round(result["foreign_isin_request_weight"], 8),
        "unresolved_identifier_positions": result["unresolved_identifier_positions"],
        "vendor_identities_certified": 0,
        "full_engine_eligible_cuts": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
