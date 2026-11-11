"""Review issuer LEIs explicitly reported in the archived first-cut SPY N-PORT.

An issuer LEI identifies a legal entity, NOT a tradeable security or a
historically live FIGI/CUSIP crosswalk. This is an evidence collection queue;
it does not establish vendor availability, pricing, trading, or model skill.
"""
import argparse
from collections import Counter, defaultdict
import csv
import io
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_identity_requests import build_requests
    from .historical_sources import local_tag, parse_nport
    from .historical_vendor_identity import valid_cusip
else:
    from audit_historical_inputs import read_record
    from historical_identity_requests import build_requests
    from historical_sources import local_tag, parse_nport
    from historical_vendor_identity import valid_cusip

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "data/historical/provider-inputs-v1"
SCHEMA = "historical-spy-original-issuer-lei-review-v1"
LEI_PATTERN = re.compile(r"[A-Z0-9]{18}[0-9]{2}\Z")
COLUMNS = (
    "source_position", "cusip", "original_ticker_observation",
    "original_spy_name", "weight", "cut", "original_issuer_lei_as_filed",
    "issuer_lei_hint", "issuer_lei_status", "original_spy_accession",
    "original_spy_sha256", "original_spy_holdings_date",
    "original_spy_available_after_day",
)


def require(ok, error):
    if not ok:
        raise ValueError(error)


def valid_lei(value):
    """ISO 17442 mod-97-10 validation, without inventing a legal-entity match."""
    if not isinstance(value, str) or LEI_PATTERN.fullmatch(value) is None:
        return False
    expanded = "".join(str(ord(ch) - 55) if "A" <= ch <= "Z" else ch
                       for ch in value)
    return int(expanded) % 97 == 1


def classify_lei(raw):
    if raw == "":
        return "missing-original-issuer-lei", None
    if raw.upper() in ("N/A", "NA", "NONE", "NOT AVAILABLE", "-"):
        return "issuer-lei-not-available-as-filed", None
    if not valid_lei(raw):
        return "invalid-original-issuer-lei", None
    return "valid-original-issuer-lei-hint", raw


def review(root=ROOT, original=None):
    """Read the same original SEC filing that generated the 504 PIT requests."""
    root = Path(root)
    original = build_requests(root) if original is None else original
    require(original.get("cut") == "2024-12-31" and
            original.get("full_engine_replay_ready") is False and
            original.get("production_eligible") is False,
            "Frozen SEC first-cut request contract has changed")
    archive_dir = root / SOURCE
    manifest = json.loads((archive_dir / "manifest.json").read_bytes())
    matches = [ptr for ptr in manifest["sec"]["documents"]
               if ptr["accession"] == original["spy_original_accession"]]
    require(len(matches) == 1, "Original SEC accession is missing or ambiguous")
    pointer = matches[0]
    record, raw = read_record(archive_dir, pointer)
    normalized = parse_nport(raw, record["filing"])
    require(pointer["raw_sha256"] == original["spy_original_sha256"] and
            pointer["normalized"] == normalized and
            normalized["available_after_day"] < original["cut"] and
            normalized["as_of"] < original["cut"] and
            len(raw) <= 4_000_000 and
            b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "Archived SEC source or its historical public cutoff differs")
    document = ET.fromstring(raw)
    investments = [node for node in document.iter()
                   if local_tag(node) == "invstOrSec"]
    positions = normalized["positions"]
    require(len(investments) == len(positions),
            "Original N-PORT investment position count differs")
    positive = {pos: row for pos, row in enumerate(positions)
                if row["weight"] > 0}
    requests = original["requests"]
    require(len(requests) == len(positive) and
            len({r["source_position"] for r in requests}) == len(requests),
            "Original SEC positive position denominator differs")
    rows = []
    for request in requests:
        idx = request["source_position"]
        require(type(idx) is int and idx in positive and
                positive[idx]["cusip"] == request["cusip"] and
                positive[idx]["name"] == request["original_spy_name"] and
                math.isclose(positive[idx]["weight"], request["weight"],
                             rel_tol=0, abs_tol=1e-14) and
                request.get("vendor_instrument_id") is None and
                request.get("vendor_price_series_verified") is False,
                "SEC source position or original vendor-request status differs")
        item = investments[idx]
        lei_nodes = [part for part in item if local_tag(part) == "lei"]
        require(len(lei_nodes) <= 1,
                "More than one direct issuer LEI is reported for SEC position")
        raw_lei = (lei_nodes[0].text or "").strip() if lei_nodes else ""
        status, hint = classify_lei(raw_lei)
        rows.append({
            "source_position": idx, "cusip": request["cusip"],
            "original_ticker_observation": request["original_ticker_observation"] or "",
            "original_spy_name": request["original_spy_name"],
            "weight": request["weight"], "cut": original["cut"],
            "original_issuer_lei_as_filed": raw_lei,
            "issuer_lei_hint": hint or "", "issuer_lei_status": status,
            "original_spy_accession": pointer["accession"],
            "original_spy_sha256": pointer["raw_sha256"],
            "original_spy_holdings_date": normalized["as_of"],
            "original_spy_available_after_day": normalized["available_after_day"],
        })
    # An issuer LEI may legitimately occur on several share classes, but a
    # single CUSIP naming different entities in the same filing is ambiguous.
    by_cusip = defaultdict(set)
    for row in rows:
        if valid_cusip(row["cusip"]) and row["issuer_lei_hint"]:
            by_cusip[row["cusip"]].add(row["issuer_lei_hint"])
    conflicts = {cusip for cusip, leis in by_cusip.items() if len(leis) > 1}
    for row in rows:
        if row["cusip"] in conflicts:
            row["issuer_lei_hint"] = ""
            row["issuer_lei_status"] = "conflicting-original-issuer-lei-for-cusip"
    counts = Counter(row["issuer_lei_status"] for row in rows)
    valid_rows = [row for row in rows if valid_cusip(row["cusip"])]
    require(len(valid_rows) + sum(not valid_cusip(row["cusip"]) for row in rows)
            == len(rows) and len(rows) == len(positive),
            "Issuer LEI coverage does not reconcile to SEC originals")
    return {
        "schema": SCHEMA, "cut": original["cut"],
        "spy_original_accession": pointer["accession"],
        "spy_original_sha256": pointer["raw_sha256"],
        "spy_holdings_date": normalized["as_of"],
        "spy_public_available_after_day": normalized["available_after_day"],
        "total_positive_sec_positions": len(rows),
        "valid_original_cusip_positions": len(valid_rows),
        "invalid_original_cusip_positions": len(rows) - len(valid_rows),
        "valid_cusip_positions_with_issuer_lei_hint": sum(
            bool(r["issuer_lei_hint"]) for r in valid_rows),
        "distinct_issuer_leis_in_valid_cusip_positions": len({
            r["issuer_lei_hint"] for r in valid_rows if r["issuer_lei_hint"]}),
        "original_lei_status_counts": dict(sorted(counts.items())),
        "position_rows": rows,
        "source_role": "sec-original-issuer-identifier-hints-not-security-crosswalk",
        "permanent_security_identity_certified": False,
        "vendor_publication_independently_verified": False,
        "historical_price_or_executability_certified": False,
        "full_engine_eligible_cuts_added": 0,
        "predictive_validation": "not-established",
    }


def queue_csv(report):
    """Return only valid-CUSIP requests in weighted lookup order."""
    require(report.get("schema") == SCHEMA and
            report.get("full_engine_eligible_cuts_added") == 0 and
            report.get("permanent_security_identity_certified") is False,
            "Issuer LEI data was promoted to a security master")
    rows = [r for r in report["position_rows"] if valid_cusip(r["cusip"])]
    require(len(rows) == report["valid_original_cusip_positions"],
            "Original CUSIP request count changed")
    rows.sort(key=lambda r: (-r["weight"], r["source_position"]))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="Rebuild source evidence and print counts without writing")
    parser.add_argument("--csv", help="Write original issuer-LEI annotated valid-CUSIP queue")
    parser.add_argument("--report", help="Write source-only review JSON")
    args = parser.parse_args(argv)
    source = review()
    if not args.verify:
        if args.csv:
            target = Path(args.csv)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(queue_csv(source), encoding="utf-8")
        if args.report:
            target = Path(args.report)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({k:v for k,v in source.items()
                                          if k != "position_rows"},
                                         indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({key:source[key] for key in (
        "cut", "total_positive_sec_positions", "valid_original_cusip_positions",
        "invalid_original_cusip_positions", "valid_cusip_positions_with_issuer_lei_hint",
        "distinct_issuer_leis_in_valid_cusip_positions", "original_lei_status_counts",
        "full_engine_eligible_cuts_added")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
