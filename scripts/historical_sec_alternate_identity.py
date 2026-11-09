"""Extract alternative identifiers from the *same* archived SEC SPY N-PORT filing.

Never substitute an ISIN-derived CUSIP for an original field, bind a ticker
to a provider security or certify historical investability. All candidates
remain a distinct source-correction review track.
"""
import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_sources import local_tag, parse_nport
    from .historical_spy_exception_classification import audit as audit_exceptions
    from .historical_vendor_identity import valid_cusip
else:
    from audit_historical_inputs import read_record
    from historical_sources import local_tag, parse_nport
    from historical_spy_exception_classification import audit as audit_exceptions
    from historical_vendor_identity import valid_cusip

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = "data/historical/provider-inputs-v1"
REPORT = "out/historical-sec-alternate-identity-v1.json"
CSV = "out/historical-sec-alternate-identity-v1.csv"
CSV_FIELDS = (
    "source_position", "cusip_as_reported", "reported_spy_weight",
    "explicit_isins", "invalid_isin_observations", "explicit_ticker_hints",
    "original_lei_hint", "structural_us_isin_cusip_candidate", "review_status",
    "source_accession", "source_original_sha256", "public_available_after_day",
    "decision_cut",
)
ISIN_RE = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def isin_valid(isin):
    """ISO 6166 check digit: Luhn over expanded letter/digit character string."""
    if not isinstance(isin, str) or ISIN_RE.fullmatch(isin) is None:
        return False
    expanded = "".join(str(ord(c)-55) if "A" <= c <= "Z" else c for c in isin)
    total = 0
    for index, char in enumerate(reversed(expanded)):
        doubled = int(char) * (2 if index % 2 else 1)
        total += doubled // 10 + doubled % 10
    return total % 10 == 0


def literal_identifiers(item):
    """Only explicitly tagged filing ISIN/ticker; do not use name equivalence."""
    candidates = []
    ticker = []
    for parent in item:
        if local_tag(parent) != "identifiers":
            continue
        for node in parent:
            tag = local_tag(node)
            value = node.get("value", (node.text or "").strip()).strip()
            if tag == "isin" or (tag == "other" and
                node.get("otherDesc", "").strip().lower() in ("isin", "isin code")):
                candidates.append(value)
            elif tag == "ticker" or (tag == "other" and
                 node.get("otherDesc", "").strip().lower() in ("ticker", "ticker symbol")):
                if value:
                    ticker.append(value)
    return sorted(set(candidates)), sorted(set(ticker))


def review_source(raw, positions, exceptions, accession, original_sha, public_day, cut):
    """Index by literal original position; never repair an invalid source field."""
    require(isinstance(raw, bytes) and len(raw) <= 4_000_000 and
            b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "Unsafe or oversized original filing")
    root = ET.fromstring(raw)
    items = [r for r in root.iter() if local_tag(r) == "invstOrSec"]
    require(len(items) == len(positions) and
            len({e["source_position"] for e in exceptions}) == len(exceptions),
            "Original source position count changed")
    require(public_day < cut, "Original filing was not public before cut")
    result = []
    for record in exceptions:
        index = record["source_position"]
        require(type(index) is int and 0 <= index < len(items),
                "Exception source position outside original filing")
        row = positions[index]
        require(row["weight"] > 0 and
                record["cusip_as_reported"] == row["cusip"] and
                math.isclose(record["reported_spy_weight"], row["weight"],
                             rel_tol=0, abs_tol=1e-14) and not valid_cusip(row["cusip"]),
                "Original invalid CUSIP exception was rewritten")
        original_item = items[index]
        original = {}
        for tag, key in (("cusip", "cusip"), ("name", "name"), ("title", "title")):
            value = next((n for n in original_item.iter() if local_tag(n) == tag), None)
            original[tag] = (value.text or "").strip() if value is not None else ""
            require(original[tag] == row[key], "Original SEC position identity changed")
        weight = next((n for n in original_item.iter() if local_tag(n) == "pctVal"), None)
        require(weight is not None and
                math.isclose(float(weight.text) / 100, row["weight"],
                             rel_tol=0, abs_tol=1e-14),
                "Original SEC position weight changed")
        isins, ticker_hints = literal_identifiers(original_item)
        valid_isins = [v for v in isins if isin_valid(v)]
        invalid_isins = [v for v in isins if not isin_valid(v)]
        us_cusips = sorted({v[2:11] for v in valid_isins
                            if v.startswith("US") and valid_cusip(v[2:11])})
        # Even a valid US ISIN is same-source *structural* evidence, not
        # independent issuer/share-class/security-master confirmation.
        if len(us_cusips) > 1:
            status = "ambiguous-original-us-isin-cusips"
            candidate = None
        elif len(valid_isins) > 1:
            status = "ambiguous-original-valid-isins"
            candidate = None
        elif len(us_cusips) == 1:
            status = "structural-us-isin-cusip-candidate"
            candidate = us_cusips[0]
        elif valid_isins:
            status = "original-non-us-isin-only"
            candidate = None
        elif invalid_isins:
            status = "invalid-original-isin-only"
            candidate = None
        else:
            status = "no-original-isin-observed"
            candidate = None
        lei_node = next((n for n in original_item.iter() if local_tag(n) == "lei"), None)
        lei = (lei_node.text or "").strip() if lei_node is not None else ""
        result.append({
            "source_position": index, "cusip_as_reported": row["cusip"],
            "reported_spy_weight": row["weight"],
            "explicit_isins": valid_isins,
            "invalid_isin_observations": invalid_isins,
            "explicit_ticker_hints": ticker_hints,
            "original_lei_hint": lei,
            "structural_us_isin_cusip_candidate": candidate,
            "review_status": status, "source_accession": accession,
            "source_original_sha256": original_sha,
            "public_available_after_day": public_day, "decision_cut": cut,
        })
    require(len(result) == len(exceptions) and
            len({r["source_position"] for r in result}) == len(exceptions),
            "Not every original exception was reviewed")
    return result


def audit(root=ROOT):
    root = Path(root)
    exception_report = audit_exceptions(root)
    directory = root / SOURCE_DIR
    manifest = json.loads((directory / "manifest.json").read_bytes())
    matching = [p for p in manifest["sec"]["documents"]
                if p["accession"] == exception_report["source_accession"]]
    require(len(matching) == 1, "Original SEC filing missing or ambiguous")
    pointer = matching[0]
    record, raw = read_record(directory, pointer)
    source = parse_nport(raw, record["filing"])
    require(pointer["normalized"] == source and
            pointer["raw_sha256"] == exception_report["original_source_sha256"] and
            source["available_after_day"] == exception_report["source_public_available_after_day"] and
            source["available_after_day"] < exception_report["cut"],
            "Original SEC source no longer matches classified exceptions")
    positions = review_source(raw, source["positions"], exception_report["positions"],
                              exception_report["source_accession"],
                              pointer["raw_sha256"], source["available_after_day"],
                              exception_report["cut"])
    counts = Counter(r["review_status"] for r in positions)
    weights = Counter()
    for row in positions:
        weights[row["review_status"]] += row["reported_spy_weight"]
    require(sum(counts.values()) == exception_report["invalid_or_missing_cusip_positions"] and
            math.isclose(sum(weights.values()), exception_report["original_spy_weight"],
                         rel_tol=0, abs_tol=1e-10),
            "Source alternate identifiers do not reconcile to original exceptions")
    return {
        "schema": "historical-sec-alternate-identity-review-v1",
        "cut": exception_report["cut"],
        "source_accession": pointer["accession"],
        "source_original_sha256": pointer["raw_sha256"],
        "source_public_available_after_day": source["available_after_day"],
        "original_invalid_or_missing_cusip_positions": len(positions),
        "original_spy_weight": exception_report["original_spy_weight"],
        "review_status_counts": dict(sorted(counts.items())),
        "review_status_weights": dict(sorted(weights.items())),
        "positions": positions,
        "original_cusip_rewritten": False,
        "us_isin_candidates_corroborated_by_independent_source": 0,
        "vendor_identifiers_certified": 0,
        "price_histories_certified": 0,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def csv_output(result):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in result["positions"]:
        writer.writerow({**row, "explicit_isins": ";".join(row["explicit_isins"]),
                         "invalid_isin_observations": ";".join(row["invalid_isin_observations"]),
                         "explicit_ticker_hints": ";".join(row["explicit_ticker_hints"])})
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", default=REPORT)
    parser.add_argument("--csv", default=CSV)
    args = parser.parse_args(argv)
    report = audit()
    if not args.verify:
        for name, data in [
            (args.output, json.dumps({k: v for k, v in report.items()
                                      if k != "positions"}, indent=2) + "\n"),
            (args.csv, csv_output(report)),
        ]:
            target = Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data, encoding="utf-8")
    print(json.dumps({
        "cut": report["cut"],
        "original_invalid_or_missing_cusip_positions":
            report["original_invalid_or_missing_cusip_positions"],
        "review_status_counts": report["review_status_counts"],
        "us_isin_candidates_corroborated_by_independent_source": 0,
        "full_engine_eligible_cuts": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
