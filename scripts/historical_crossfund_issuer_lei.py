"""Cross-check original SPY CUSIP/issuer-LEI hints against dated iShares N-PORT.

Reparse original SEC bytes, including filings without original tickers. Cross-fund
agreement is NOT issuer-certified security-master identity, an as-of vendor
price mapping, tradability, or evidence of predictive skill.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_identifiers import (FUNDS, MARKET_COMMIT, PROTOCOL,
                                         original_url, parse_observations, value)
    from .historical_sources import canonical, local_tag, sha
    from .historical_spy_issuer_lei import (ROOT, SCHEMA as SPY_SCHEMA, review,
                                           valid_lei)
    from .historical_vendor_identity import valid_cusip
else:
    from audit_historical_inputs import read_record
    from historical_identifiers import (FUNDS, MARKET_COMMIT, PROTOCOL,
                                        original_url, parse_observations, value)
    from historical_sources import canonical, local_tag, sha
    from historical_spy_issuer_lei import ROOT, SCHEMA as SPY_SCHEMA, review, valid_lei
    from historical_vendor_identity import valid_cusip

SCHEMA = "historical-original-crossfund-issuer-lei-review-v1"
SOURCE = "data/historical/identifier-sources-v1"
CUT = "2024-12-31"
MAX_HOLDINGS_AGE_DAYS = 120
COLUMNS = (
    "source_position", "cusip", "original_spy_name", "weight", "cut",
    "spy_issuer_lei_as_filed", "spy_issuer_lei_hint", "crossfund_status",
    "crossfund_corroborated_issuer_lei", "other_original_funds_observed",
    "other_funds_with_valid_lei", "other_fund_accessions",
    "other_fund_original_sha256", "spy_original_sha256",
    "permanent_security_identity_certified", "historical_prices_verified",
)


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def eligible_pointers(manifest, cut=CUT, maximum_age=MAX_HOLDINGS_AGE_DAYS):
    """Select one latest public original per source fund at a frozen cut."""
    require(manifest.get("protocol") == PROTOCOL and
            manifest.get("source_market_commit") == MARKET_COMMIT and
            manifest.get("funds") == FUNDS and
            manifest.get("collection_complete") is True and
            manifest.get("errors") == [], "Historical N-PORT source collection incomplete")
    require(cut == CUT and maximum_age == MAX_HOLDINGS_AGE_DAYS,
            "Historical cutoff and source-age contract are frozen")
    candidates = defaultdict(list)
    for pointer in manifest.get("documents", []):
        fund = pointer.get("fund")
        require(fund in FUNDS and
                isinstance(pointer.get("as_of"), str) and
                isinstance(pointer.get("available_after_day"), str),
                "Malformed source pointer")
        observed = date.fromisoformat(pointer["as_of"])
        first_public = date.fromisoformat(pointer["available_after_day"])
        age = (date.fromisoformat(cut) - observed).days
        if 0 <= age <= maximum_age and first_public < date.fromisoformat(cut):
            candidates[fund].append(pointer)
    selected = []
    for fund in sorted(FUNDS):
        options = candidates.get(fund, [])
        if not options:
            continue
        latest = max(p["as_of"] for p in options)
        choices = [p for p in options if p["as_of"] == latest]
        require(len(choices) == 1,
                "Ambiguous amendments at latest available fund holdings date")
        selected.append(choices[0])
    require(len({p["fund"] for p in selected}) == len(selected),
            "Fund observations must not be duplicated")
    return selected


def original_fund_rows(root, pointer):
    """Inspect holdings even when the fund reports no explicit ticker."""
    path = Path(root) / SOURCE
    record, raw = read_record(path, pointer)
    fund, accession = pointer["fund"], pointer["accession"]
    require(record.get("protocol") == PROTOCOL and
            record.get("kind") == "sec-nport-identifiers" and
            record.get("fund") == fund and
            record.get("filing") == pointer.get("filing") and
            record.get("source_url") == original_url(accession) and
            record.get("raw_sha256") == pointer.get("raw_sha256"),
            "Original fund source identity or receipt differs")
    parsed = parse_observations(raw, fund, pointer["filing"])
    require(sha(canonical(parsed)) == pointer["normalized_sha256"] and
            parsed["as_of"] == pointer["as_of"] and
            parsed["available_after_day"] == pointer["available_after_day"] and
            len(parsed["observations"]) == pointer["explicit_observations"] and
            parsed["rejected"] == pointer["rejected"],
            "Original fund observations cannot be reproduced")
    xml = ET.fromstring(raw)
    results = []
    for item in xml.iter():
        if local_tag(item) != "invstOrSec":
            continue
        if (value(item, "assetCat") != "EC" or
                value(item, "curCd") != "USD" or
                value(item, "payoffProfile") != "Long"):
            continue
        cusip = value(item, "cusip")
        if not valid_cusip(cusip):
            continue
        lei_nodes = [node for node in item if local_tag(node) == "lei"]
        require(len(lei_nodes) <= 1,
                "Multiple direct issuer LEIs in original fund holding")
        raw_lei = (lei_nodes[0].text or "").strip() if lei_nodes else ""
        results.append({
            "cusip": cusip,
            "issuer_lei_as_filed": raw_lei,
            "valid_original_issuer_lei": raw_lei if valid_lei(raw_lei) else "",
            "fund": fund,
            "accession": accession,
            "original_sha256": pointer["raw_sha256"],
            "holdings_as_of": pointer["as_of"],
            "available_after_day": pointer["available_after_day"],
        })
    return results


def compare(spy, other_positions, documents):
    """Reconcile literal identifier statements without choosing a conflicting key."""
    require(spy.get("schema") == SPY_SCHEMA and spy.get("cut") == CUT and
            spy.get("permanent_security_identity_certified") is False and
            spy.get("full_engine_eligible_cuts_added") == 0,
            "Original SPY identifier contract was promoted or changed")
    valid_positions = [p for p in spy["position_rows"] if valid_cusip(p["cusip"])]
    require(len(valid_positions) == spy["valid_original_cusip_positions"] and
            len(spy["position_rows"]) == spy["total_positive_sec_positions"] and
            len({p["source_position"] for p in spy["position_rows"]}) ==
            spy["total_positive_sec_positions"],
            "Original SPY position denominator changed")
    selected = {(d["fund"], d["accession"]): d for d in documents}
    require(len(selected) == len(documents), "Duplicate fund original source")
    by_cusip = defaultdict(list)
    for obs in other_positions:
        require((obs["fund"], obs["accession"]) in selected and
                obs["original_sha256"] == selected[(obs["fund"], obs["accession"])]["raw_sha256"] and
                obs["holdings_as_of"] == selected[(obs["fund"], obs["accession"])]["as_of"] and
                obs["available_after_day"] == selected[(obs["fund"], obs["accession"])]["available_after_day"] and
                obs["available_after_day"] < CUT and
                valid_cusip(obs["cusip"]) and
                (not obs["valid_original_issuer_lei"] or
                 (valid_lei(obs["valid_original_issuer_lei"]) and
                  obs["valid_original_issuer_lei"] == obs["issuer_lei_as_filed"])),
                "Cross-fund row contradicts original proof or cutoff")
        by_cusip[obs["cusip"]].append(obs)
    output = []
    counts = Counter()
    for position in valid_positions:
        cusip = position["cusip"]
        evidence = by_cusip.get(cusip, [])
        fund_names = sorted({v["fund"] for v in evidence})
        valid = sorted({v["valid_original_issuer_lei"] for v in evidence
                        if v["valid_original_issuer_lei"]})
        corroborated = ""
        if not evidence:
            status = "no-other-original-fund-observation"
        elif len(valid) > 1:
            status = "conflicting-original-fund-issuer-leis"
        elif not valid:
            status = "other-original-fund-lei-unavailable"
        elif not position["issuer_lei_hint"]:
            status = "other-fund-lei-without-spy-issuer-lei"
        elif valid[0] != position["issuer_lei_hint"]:
            status = "conflicting-spy-and-other-fund-issuer-lei"
        else:
            status = "original-fund-issuer-lei-agrees"
            corroborated = valid[0]
        counts[status] += 1
        output.append({
            "source_position": position["source_position"],
            "cusip": cusip,
            "original_spy_name": position["original_spy_name"],
            "weight": position["weight"],
            "cut": CUT,
            "spy_issuer_lei_as_filed": position["original_issuer_lei_as_filed"],
            "spy_issuer_lei_hint": position["issuer_lei_hint"],
            "crossfund_status": status,
            "crossfund_corroborated_issuer_lei": corroborated,
            "other_original_funds_observed": ";".join(fund_names),
            "other_funds_with_valid_lei": ";".join(sorted({v["fund"] for v in evidence
                                                   if v["valid_original_issuer_lei"]})),
            "other_fund_accessions": ";".join(sorted({v["accession"] for v in evidence})),
            "other_fund_original_sha256": ";".join(sorted({v["original_sha256"] for v in evidence})),
            "spy_original_sha256": spy["spy_original_sha256"],
            "permanent_security_identity_certified": False,
            "historical_prices_verified": False,
        })
    return {
        "schema": SCHEMA,
        "cut": CUT,
        "spy_original_accession": spy["spy_original_accession"],
        "spy_original_sha256": spy["spy_original_sha256"],
        "total_positive_sec_positions": spy["total_positive_sec_positions"],
        "valid_original_cusip_positions": len(valid_positions),
        "invalid_original_cusip_positions": spy["invalid_original_cusip_positions"],
        "original_fund_documents_reparsed": len(documents),
        "original_fund_positions_read": len(other_positions),
        "original_fund_source_receipts": [{
            "fund": ptr["fund"], "accession": ptr["accession"],
            "as_of": ptr["as_of"], "available_after_day": ptr["available_after_day"],
            "raw_sha256": ptr["raw_sha256"],
        } for ptr in documents],
        "crossfund_status_counts": dict(sorted(counts.items())),
        "crossfund_lei_agreement_positions": counts["original-fund-issuer-lei-agrees"],
        "crossfund_conflict_positions": (counts["conflicting-original-fund-issuer-leis"] +
                                         counts["conflicting-spy-and-other-fund-issuer-lei"]),
        "position_rows": output,
        "crossfund_sources_are_other_original_funds_not_issuer_or_vendor_master": True,
        "permanent_security_identity_certified": False,
        "vendor_historical_publication_verified": False,
        "historical_prices_or_corporate_actions_verified": False,
        "full_engine_eligible_cuts_added": 0,
        "predictive_validation": "not-established",
    }


def review_crossfund(root=ROOT):
    """Reopen all selected original source bytes; do not read derived LEI CSVs."""
    root = Path(root)
    original = review(root)
    manifest = json.loads((root / SOURCE / "manifest.json").read_bytes())
    chosen = eligible_pointers(manifest)
    require(chosen, "No admissible original fund documents before cutoff")
    observations = []
    for pointer in chosen:
        observations.extend(original_fund_rows(root, pointer))
    return compare(original, observations, chosen)


def queue_csv(report):
    require(report.get("schema") == SCHEMA and
            report.get("permanent_security_identity_certified") is False and
            report.get("full_engine_eligible_cuts_added") == 0,
            "Cross-fund statement cannot be promoted")
    rows = report["position_rows"]
    require(len(rows) == report["valid_original_cusip_positions"],
            "Cross-fund queue lost SPY positions")
    rows = sorted(rows, key=lambda r: (-r["weight"], r["source_position"]))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--csv", help="Write public source-only CUSIP and issuer-LEI comparisons")
    parser.add_argument("--report", help="Write aggregate source-only provenance report")
    args = parser.parse_args(argv)
    result = review_crossfund()
    if not args.verify:
        if args.csv:
            dest = Path(args.csv)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(queue_csv(result), encoding="utf-8")
        if args.report:
            dest = Path(args.report)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps({k: v for k, v in result.items() if k != "position_rows"},
                                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "cut", "total_positive_sec_positions", "valid_original_cusip_positions",
        "invalid_original_cusip_positions", "original_fund_documents_reparsed",
        "original_fund_positions_read", "crossfund_status_counts",
        "crossfund_lei_agreement_positions", "crossfund_conflict_positions",
        "full_engine_eligible_cuts_added")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
