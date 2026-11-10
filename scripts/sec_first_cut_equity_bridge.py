"""Class-aware issuer ticker crosscheck from original SEC 10-Q and SPY N-PORT.

SEC 10-Q cover registration rows and dated N-PORT CUSIP/ticker observations
provide two independently dated source statements. Their intersection is a
retrospective research candidate, NOT a permanent CIK->CUSIP mapping,
vendor price identifier, historical execution quote or PIT certificate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

if __package__:
    from .historical_identity_requests import build_requests
    from .historical_sec_original_filing import parse_original
    from .historical_sec_numeric_concordance import primary_inline_document
    from .historical_vendor_identity import valid_cusip, request_hash
    from .historical_sec_fsd_intake import require
    from .sec_sgml_text_wrapper import unwrap_sec_xml_payload
else:
    from historical_identity_requests import build_requests
    from historical_sec_original_filing import parse_original
    from historical_sec_numeric_concordance import primary_inline_document
    from historical_vendor_identity import valid_cusip, request_hash
    from historical_sec_fsd_intake import require
    from sec_sgml_text_wrapper import unwrap_sec_xml_payload

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "data/historical/sec-first-cut-original-source-observation-v1.json"
ORIGINAL = ROOT / "out/sec-originals/0000950170-24-118967.txt"
SCHEMA = "sec-first-cut-issuer-equity-cross-source-candidate-v1"
TICKER = "MSFT"


def cell_text(node):
    return " ".join(" ".join(node.itertext()).split())


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def registered_securities(primary):
    """Require a unique 12(b) security-class table in the original XML."""
    require(type(primary) is bytes and 100 <= len(primary) <= 64*1024*1024
            and b"<!DOCTYPE" not in primary.upper()
            and b"<!ENTITY" not in primary.upper(),
            "SEC equity-class source is missing, too large or uses unsafe XML")
    document = unwrap_sec_xml_payload(primary, "XBRL").lstrip(b" \t\r\n")
    require(document.startswith(b"<"), "No original SEC inline XML document")
    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise ValueError("SEC security class table is not well-formed XML") from exc
    candidates = []
    for table in root.iter():
        if local_name(table.tag) != "table":
            continue
        rows = []
        for tr in table.iter():
            if local_name(tr.tag) != "tr":
                continue
            cells = [cell_text(td) for td in tr
                     if local_name(td.tag) in ("td", "th")]
            rows.append([x for x in cells if x])
        table_text = " ".join(" ".join(cells) for cells in rows).lower()
        if (re.search(r"title of each class", table_text) and
            re.search(r"trading symbol", table_text) and
            re.search(r"name of (?:each |the )?exchange", table_text)):
            candidates.append(rows)
    require(len(candidates) == 1,
            "Missing or ambiguous original SEC 12(b) registration table")
    rows = candidates[0]
    out = []
    for cells in rows:
        if len(cells) < 3:
            continue
        title = cells[0].strip()
        if not (re.match(r"(?i)^common stock\b", title)
                or re.search(r"(?i)\bnotes? due \d{4}\b", title)):
            continue
        require(len(cells) == 3,
                "SEC registration row has ambiguous security symbol columns")
        symbol, exchange = cells[1].strip(), cells[2].strip()
        require(re.fullmatch(r"[A-Z][A-Z0-9./-]{0,14}", symbol) is not None
                and 1 <= len(exchange) <= 60,
                "SEC registration row has invalid ticker or exchange")
        kind = "common-stock" if re.match(
            r"(?i)^common stock\b", title) else "debt-note"
        out.append({"class_title_as_filed": title,
                    "trading_symbol_as_filed": symbol,
                    "exchange_as_filed": exchange,
                    "security_class": kind})
    require(out and any(row["security_class"] == "common-stock" for row in out),
            "No independently labeled SEC common-stock registration found")
    require(len({(x["class_title_as_filed"], x["trading_symbol_as_filed"],
                  x["exchange_as_filed"]) for x in out}) == len(out),
            "Duplicated or conflicting SEC security registration rows")
    return out


def bridge(original_bytes, requests, observed):
    """Intersect exact original ticker evidence, never infer price identities."""
    lead = observed["source_provenance"]["original_edgar_filing"]
    require(type(original_bytes) is bytes and
            hashlib.sha256(original_bytes).hexdigest() == lead["sha256"]
            and len(original_bytes) == lead["bytes"]
            and observed["cut"] == requests["cut"] + "T21:00:00Z"
            and requests["counts"]["positive_positions"] == len(requests["requests"])
            and requests["full_engine_replay_ready"] is False
            and requests["production_eligible"] is False,
            "Source originals or fixed retrospective decision cut changed")
    filed = parse_original(original_bytes, lead["accession"])
    require(filed["cik"] == lead["cik"] and filed["form"] == "10-Q"
            and filed["accepted_eastern"] ==
                observed["accepted_eastern"]["original_edgar_header"]
            and datetime.fromisoformat(filed["accepted_utc"]) <=
                datetime.fromisoformat(observed["cut"].replace("Z","+00:00")),
            "Issuer identity or exact acceptance is later than decision cut")
    name, primary = primary_inline_document(original_bytes, filed["form"])
    require(name == "msft-20240930.htm", "Unexpected original SEC primary document")
    registrations = registered_securities(primary)
    equity = [r for r in registrations
              if r["security_class"] == "common-stock"
              and r["trading_symbol_as_filed"] == TICKER]
    require(len(equity) == 1,
            "MSFT may not be linked without a unique common-stock class")
    other = [r for r in registrations
             if r["trading_symbol_as_filed"] == TICKER
             and r["security_class"] != "common-stock"]
    candidates = [r for r in requests["requests"]
                  if r["original_ticker_observation"] == TICKER]
    require(len(candidates) == 1,
            "Original SPY holdings must have exactly one source MSFT ticker")
    position = candidates[0]
    require(valid_cusip(position["cusip"]) and
            position["source_position"] >= 0 and
            0 < position["weight"] < 1 and
            position["vendor_instrument_id"] is None and
            position["vendor_price_series_verified"] is False and
            position["original_price_vintage_verified"] is False and
            position["production_eligible"] is False and
            position["ticker_receipts"],
            "Historical N-PORT position or vendor identity was silently promoted")
    receipts = position["ticker_receipts"]
    require(all(receipt["available_after_day"] < requests["cut"]
                and receipt["original_sha256"] and
                receipt["fund"] and receipt["accession"]
                for receipt in receipts),
            "N-PORT ticker evidence was not available before the cut")
    return {
        "schema": SCHEMA, "cut": requests["cut"],
        "original_msft_10q_accession": lead["accession"],
        "original_msft_10q_sha256": lead["sha256"],
        "original_msft_primary_filename": name,
        "original_msft_primary_sha256": hashlib.sha256(primary).hexdigest(),
        "issuer_cik_as_filed": filed["cik"],
        "issuer_original_acceptance_utc": filed["accepted_utc"],
        "issuer_common_stock_registration": equity[0],
        "other_registration_classes_with_same_symbol": other,
        "ticker_not_a_unique_security_identifier": bool(other),
        "spy_original_accession": requests["spy_original_accession"],
        "spy_original_sha256": requests["spy_original_sha256"],
        "spy_historical_request_sha256": request_hash(requests),
        "spy_source_position": position["source_position"],
        "spy_cusip_as_filed": position["cusip"],
        "spy_weight_as_filed": position["weight"],
        "spy_issuer_name_as_filed": position["original_spy_name"],
        "spy_ticker_evidence": receipts,
        "source_symbol_intersection": TICKER,
        "source_link_status": "retrospective-original-source-equity-candidate",
        "independent_historical_cik_to_cusip_permanent_mapping_verified": False,
        "vendor_instrument_id": None,
        "historical_quote_series_verified": False,
        "delisting_and_corporate_actions_verified": False,
        "universe_or_portfolio_replay_eligible": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--output", type=Path,
                        default=ROOT/"out/sec-msft-equity-bridge-research.json")
    args = parser.parse_args(argv)
    require(args.output.resolve().is_relative_to((ROOT/"out").resolve()),
            "Original-source issuer bridge reports must remain in ignored out/")
    report = bridge(args.original.read_bytes(), build_requests(),
                    json.loads(OBSERVATION.read_bytes()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("spy_ticker_evidence",)}, sort_keys=True))


if __name__ == "__main__":
    main()
