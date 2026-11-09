"""Classify invalid CUSIP exceptions using the original public SPY N-PORT XML.

SEC asset-category tags describe fund holdings, not a verified historical
investable equity universe. This audit does not infer price identifiers, fix
invalid original CUSIPs or certify any past price/vintage.
"""
import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_identity_requests import build_requests
    from .historical_priority_vendor_queue import build_queue
    from .historical_sources import local_tag, parse_nport
    from .historical_spy_membership_audit import audit as audit_membership
    from .historical_vendor_identity import valid_cusip
else:
    from audit_historical_inputs import read_record
    from historical_identity_requests import build_requests
    from historical_priority_vendor_queue import build_queue
    from historical_sources import local_tag, parse_nport
    from historical_spy_membership_audit import audit as audit_membership
    from historical_vendor_identity import valid_cusip

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_DIR = "data/historical/provider-inputs-v1"
REPORT = "out/historical-sec-cusip-exception-review-v1.json"
CSV = "out/historical-sec-cusip-exception-review-v1.csv"
FIELDS = (
    "source_position", "cusip_as_reported", "reported_spy_weight",
    "source_name", "source_title", "source_asset_category", "source_currency",
    "source_payoff_profile", "source_issuer_type", "review_track",
    "source_accession", "public_available_after_day", "decision_cut",
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def xml_value(item, tag):
    node = next((r for r in item.iter() if local_tag(r) == tag), None)
    return ((node.text or "").strip() if node is not None else "")


def classify_xml(raw, original, exceptions, accession, public, cut):
    """Match every source row by original XML order before reading risk metadata."""
    require(isinstance(raw, bytes) and len(raw) <= 4_000_000 and
            b"<!DOCTYPE" not in raw.upper() and
            b"<!ENTITY" not in raw.upper(), "Unsafe or oversized N-PORT XML")
    root = ET.fromstring(raw)
    rows = [item for item in root.iter() if local_tag(item) == "invstOrSec"]
    require(len(rows) == len(original) and
            len({r["source_position"] for r in exceptions}) == len(exceptions),
            "Original N-PORT position count or exception references differ")
    expected = {i for i, p in enumerate(original) if p["weight"] > 0 and
                not valid_cusip(p["cusip"])}
    observed = {r["source_position"] for r in exceptions}
    require(observed == expected, "Original invalid CUSIP exception set changed")
    details = []
    for index, item in enumerate(rows):
        source = original[index]
        try:
            weight = float(xml_value(item, "pctVal")) / 100
        except (TypeError, ValueError) as error:
            raise ValueError("Original N-PORT weight is not numeric") from error
        require(math.isfinite(weight) and abs(weight-source["weight"]) <= 1e-14 and
                all(xml_value(item, key) == source[check]
                    for key, check in (("cusip", "cusip"), ("name", "name"),
                                       ("title", "title"))),
                "Original N-PORT identity or weight changed")
    for item in exceptions:
        index = item["source_position"]
        require(type(index) is int and 0 <= index < len(rows),
                "SEC exception position outside original document")
        original_item = original[index]
        require(item["cusip_as_reported"] == original_item["cusip"] and
                abs(item["reported_spy_weight"]-original_item["weight"]) <= 1e-14 and
                not valid_cusip(original_item["cusip"]),
                "SEC exception CUSIP or weight differs from original")
        row = rows[index]
        category = xml_value(row, "assetCat")
        currency = xml_value(row, "curCd")
        payoff = xml_value(row, "payoffProfile")
        issuer = xml_value(row, "issuerTyp")
        track = ("equity-like-source-identity-review"
                 if category == "EC" and currency == "USD" and payoff == "Long"
                 else "other-source-asset-classification-review")
        details.append({
            "source_position": index,
            "cusip_as_reported": original_item["cusip"],
            "reported_spy_weight": original_item["weight"],
            "source_name": original_item["name"],
            "source_title": original_item["title"],
            "source_asset_category": category or "not-reported",
            "source_currency": currency or "not-reported",
            "source_payoff_profile": payoff or "not-reported",
            "source_issuer_type": issuer or "not-reported",
            "review_track": track,
            "source_accession": accession,
            "public_available_after_day": public,
            "decision_cut": cut,
        })
    return details


def audit(root=ROOT):
    root = Path(root)
    requests = build_requests(root)
    membership = audit_membership(root)
    queue = build_queue(requests, membership)
    source_dir = root / PROVIDER_DIR
    manifest = json.loads((source_dir / "manifest.json").read_bytes())
    docs = [row for row in manifest["sec"]["documents"]
            if row["accession"] == requests["spy_original_accession"]]
    require(len(docs) == 1, "Original SEC filing pointer absent or ambiguous")
    pointer = docs[0]
    record, raw = read_record(source_dir, pointer)
    normalized = parse_nport(raw, record["filing"])
    require(pointer["raw_sha256"] == requests["spy_original_sha256"] and
            pointer["normalized"] == normalized and
            normalized["as_of"] < queue["cut"] and
            normalized["available_after_day"] < queue["cut"],
            "Original SPY filing integrity or availability differs")
    positive_original = {i: row for i, row in enumerate(normalized["positions"])
                         if row["weight"] > 0}
    require(len(positive_original) == queue["original_positive_positions"] and
            all(positive_original[p["source_position"]]["cusip"] == p["cusip"] and
                math.isclose(positive_original[p["source_position"]]["weight"], p["weight"],
                             rel_tol=0, abs_tol=1e-14) for p in requests["requests"]),
            "Original SEC requests are not identical to N-PORT positions")
    exceptions = classify_xml(raw, normalized["positions"],
                              queue["invalid_cusip_review_cases"],
                              queue["spy_accession"], normalized["available_after_day"],
                              queue["cut"])
    by_category = Counter(r["source_asset_category"] for r in exceptions)
    weight_by_category = Counter()
    track_weights = Counter()
    for row in exceptions:
        weight_by_category[row["source_asset_category"]] += row["reported_spy_weight"]
        track_weights[row["review_track"]] += row["reported_spy_weight"]
    require(len(exceptions) == queue["omitted_invalid_or_missing_cusip_positions"] and
            math.isclose(sum(weight_by_category.values()),
                         queue["omitted_invalid_or_missing_cusip_weight"],
                         rel_tol=0, abs_tol=1e-10),
            "Source asset categories do not reconcile to CUSIP exceptions")
    return {
        "schema": "historical-sec-cusip-exception-review-v1",
        "cut": queue["cut"], "source_accession": queue["spy_accession"],
        "original_source_sha256": queue["spy_original_sha256"],
        "source_public_available_after_day": normalized["available_after_day"],
        "invalid_or_missing_cusip_positions": len(exceptions),
        "original_spy_weight": queue["omitted_invalid_or_missing_cusip_weight"],
        "asset_category_counts": dict(sorted(by_category.items())),
        "asset_category_weight": dict(sorted(weight_by_category.items())),
        "review_track_weight": dict(sorted(track_weights.items())),
        "positions": exceptions,
        "classification_basis": "literal-original-SEC-NPORT-tags-not-investability-inference",
        "vendor_security_ids_verified": 0,
        "historical_equity_universe_certified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def csv_output(result):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(result["positions"])
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", default=REPORT)
    parser.add_argument("--csv", default=CSV)
    options = parser.parse_args(argv)
    result = audit()
    if not options.verify:
        for destination, value in (
            (options.output, json.dumps({k: v for k, v in result.items()
                                         if k != "positions"}, indent=2) + "\n"),
            (options.csv, csv_output(result)),
        ):
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
    print(json.dumps({
        "cut": result["cut"],
        "invalid_or_missing_cusip_positions": result["invalid_or_missing_cusip_positions"],
        "asset_category_counts": result["asset_category_counts"],
        "asset_category_weight": result["asset_category_weight"],
        "historical_equity_universe_certified": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
