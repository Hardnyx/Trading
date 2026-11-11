"""Confront an offline Bloomberg v4 research stage with original SEC SPY positions.

This is a local, *retrospective* source-gap audit. It neither trusts claimed
provider timestamps independently nor exports licensed identifiers into Git.
A match never certifies permanent identity, historical execution or forecasts.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

if __package__:
    from .historical_sec_alternate_identity import isin_valid
    from .historical_bloomberg_warehouse_receipt import verify_stage
else:
    from historical_sec_alternate_identity import isin_valid
    from historical_bloomberg_warehouse_receipt import verify_stage

SCHEMA = "bloomberg-first-cut-source-reconciliation-v1"
STAGE_SCHEMA = "bloomberg-trading-stage-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
NY = ZoneInfo("America/New_York")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def instant(value):
    require(isinstance(value, str), "Missing source timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Malformed source timestamp") from error
    require(parsed.utcoffset() is not None, "Source timestamp needs timezone")
    return parsed


def day(value):
    require(isinstance(value, str), "Missing source date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Malformed source date") from error
    require(parsed.isoformat() == value, "Noncanonical source date")
    return parsed


def valid_original_cusip(value):
    """Mirror the original SEC CUSIP check; foreign ISINs follow another route."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9*@#]{8}[0-9]", value):
        return False
    if value == "000000000":
        return False
    special = {"*": 36, "@": 37, "#": 38}
    total = 0
    for i, char in enumerate(value[:8]):
        number = int(char) if char.isdigit() else (ord(char) - 55 if "A" <= char <= "Z" else special[char])
        weighted = number * (2 if i % 2 else 1)
        total += weighted // 10 + weighted % 10
    return (10 - total % 10) % 10 == int(value[8])


def stage_cutoff(stage, requested_cut):
    """Verify v4's declared cutoff and its independently canonical snapshot digest."""
    require(stage.get("schema") == STAGE_SCHEMA, "Unsupported Bloomberg stage schema")
    cutoff = instant(stage.get("cutoff"))
    cut = day(requested_cut)
    require(cutoff.astimezone(NY).date() == cut and
            cutoff.astimezone(NY).hour == 16 and
            cutoff.astimezone(NY).minute == 0 and
            cutoff.astimezone(NY).second == 0,
            "First-cut Bloomberg stage must use the NY 16:00 decision clock")
    snapshot = stage.get("snapshot")
    require(isinstance(snapshot, dict) and
            snapshot.get("requested_as_of") == requested_cut and
            snapshot.get("price_as_of") == requested_cut,
            "Stage snapshot and original SEC cut differ")
    require(stage.get("production_eligible") is False and
            stage.get("full_model_replay_ready") is False and
            stage.get("engine_dispatch_enabled") is False and
            snapshot.get("production_eligible") is False and
            snapshot.get("pit_certified") is False and
            snapshot.get("synthetic") is False,
            "Bloomberg stage cannot assert production/PIT/synthetic eligibility")
    require(stage.get("snapshot_sha256") == sha256(canonical(snapshot)),
            "Bloomberg v4 snapshot digest mismatch")
    rows = stage.get("normalized_asof_records")
    hashes = stage.get("source_hashes")
    require(isinstance(rows, list) and len(rows) <= 1_000_000 and
            isinstance(hashes, list) and all(isinstance(h, str) and HASH.fullmatch(h) for h in hashes),
            "Malformed Bloomberg source ledger")
    require(isinstance(stage.get("blockers"), list), "Missing stage blockers ledger")
    return cutoff, rows, set(hashes)


def usable(record, cutoff, cut):
    """Check declared PIT fields *without* authenticating the external provider."""
    if not isinstance(record, dict) or record.get("quality_class") != "VERIFIED_PIT" or record.get("synthetic") is not False:
        return False
    try:
        available = instant(record.get("first_available_at"))
        published = instant(record.get("published_at"))
        retrieved = instant(record.get("retrieved_at"))
        # A genuine contemporaneous archive may have been collected *before*
        # the decision cutoff. Retrieval cannot precede availability, but it
        # need not postdate the decision to be evidence of an earlier version.
        if not (published <= available <= cutoff and available <= retrieved):
            return False
        for field in ("observation_date", "period_end"):
            if record.get(field) and day(record[field]) > cut:
                return False
        # A closing price cannot be disseminated before its market session.
        # The 31-Dec-2024 first-cut close itself requires the registered
        # 16:00 New York decision clock; prior sessions still require an
        # independently verified exchange calendar for execution claims.
        if record.get("dataset_id") == "daily_prices" and record.get("field") == "close":
            observed = day(record.get("observation_date"))
            if published.astimezone(NY).date() < observed:
                return False
            if observed == cut and published < cutoff:
                return False
        if record.get("effective_at") and instant(record["effective_at"]) > cutoff:
            return False
        if record.get("dataset_id") == "identifier_history" and (
                not record.get("valid_from") or not record.get("valid_until")):
            return False
        if record.get("valid_from") and day(record["valid_from"]) > cut:
            return False
        if record.get("valid_until") and day(record["valid_until"]) <= cut:
            return False
    except (ValueError, TypeError):
        return False
    proof = record.get("evidence") or {}
    return (isinstance(proof, dict) and proof.get("semantics_verified") is True and
            bool(proof.get("availability_basis")) and bool(proof.get("availability_source")) and
            bool(proof.get("value_locator")) and bool(record.get("vintage_id")) and
            bool(record.get("source_document_id")) and bool(record.get("source_id")) and
            bool(record.get("license_scope")) and record.get("unit") not in (None, "", "unconfirmed") and
            isinstance(record.get("raw_hash"), str) and
            HASH.fullmatch(record["raw_hash"]) is not None)



def confirm_original_isin_route(requests, positions, alternate):
    """Reconcile the original SEC exceptions, never infer an ISIN from CUSIP.

    The independent path rereads the same N-PORT original, not a vendor master.
    Without that review an invalid CUSIP stays unresolved, not 'foreign'.
    """
    missing = {row["source_position"]: row for row in positions
               if not valid_original_cusip(row["cusip"])}
    if alternate is None:
        return set()
    require(alternate.get("schema") == "historical-sec-alternate-identity-review-v1" and
            alternate.get("cut") == requests["cut"] and
            alternate.get("source_accession") == requests.get("spy_original_accession") and
            alternate.get("source_original_sha256") == requests.get("spy_original_sha256") and
            alternate.get("source_public_available_after_day", "9999") < requests["cut"] and
            alternate.get("original_cusip_rewritten") is False and
            alternate.get("us_isin_candidates_corroborated_by_independent_source") == 0 and
            alternate.get("vendor_identifiers_certified") == 0,
            "SEC foreign-ISIN audit provenance differs from original CUSIP requests")
    rows = alternate.get("positions")
    require(isinstance(rows, list) and
            alternate.get("original_invalid_or_missing_cusip_positions") == len(missing) and
            len(rows) == len(missing) and
            all(isinstance(row, dict) and type(row.get("source_position")) is int
                for row in rows) and
            len({row["source_position"] for row in rows}) == len(rows),
            "SEC alternate-identifier positions do not match invalid original CUSIPs")
    for row in rows:
        require(isinstance(row, dict) and row.get("source_position") in missing,
                "Unrequested SEC foreign-ISIN source position")
        source = missing[row["source_position"]]
        isins = row.get("explicit_isins")
        require(row.get("cusip_as_reported") == source["cusip"] and
                type(row.get("reported_spy_weight")) in (int, float) and
                math.isclose(row["reported_spy_weight"], source["weight"],
                             rel_tol=0, abs_tol=1e-14) and
                row.get("source_original_sha256") == requests["spy_original_sha256"] and
                row.get("source_accession") == requests["spy_original_accession"] and
                row.get("public_available_after_day") == alternate["source_public_available_after_day"] and
                row.get("decision_cut") == requests["cut"] and
                row.get("review_status") == "original-non-us-isin-only" and
                isinstance(isins, list) and len(isins) == 1 and
                isin_valid(isins[0]) and not isins[0].startswith("US") and
                row.get("structural_us_isin_cusip_candidate") is None,
                "Original SEC foreign-ISIN route was changed or misclassified")
    return set(missing)

def audit(stage, requests, alternates=None):
    """Return a private local report; never treat the result as a Trading input."""
    cut = requests.get("cut")
    require(cut == "2024-12-31", "Only frozen first-cut SEC requests supported")
    expected = requests.get("requests")
    require(isinstance(expected, list) and expected, "Missing SEC request positions")
    positions = [r for r in expected if isinstance(r, dict)]
    require(len(positions) == len(expected) and
            len({r.get("source_position") for r in positions}) == len(positions) and
            all(isinstance(r.get("cusip"), str) and isinstance(r.get("weight"), (int, float))
                and math.isfinite(r["weight"]) and r["weight"] >= 0 for r in positions),
            "Invalid original SEC position contract")
    reviewed_isin_positions = confirm_original_isin_route(requests, positions, alternates)
    cutoff, records, cited_hashes = stage_cutoff(stage, cut)
    decision_day = day(cut)
    index = defaultdict(lambda: defaultdict(list))
    for record in records:
        if isinstance(record, dict) and usable(record, cutoff, decision_day):
            security = record.get("security_id")
            if isinstance(security, str) and security:
                index[security][(record.get("dataset_id"), record.get("field"))].append(record)
    by_cusip = defaultdict(set)
    for security, fields in index.items():
        for record in fields.get(("identifier_history", "cusip"), []):
            if isinstance(record.get("value"), str):
                by_cusip[record["value"]].add(security)
    # The 26 foreign-ISIN positions in this SPY filing do not become CUSIP
    # matches merely because a vendor happens to emit their placeholder text.
    requested_ids = {r["cusip"] for r in positions if valid_original_cusip(r["cusip"])}
    reverse = defaultdict(set)
    for cusip in requested_ids:
        for security in by_cusip[cusip]:
            reverse[security].add(cusip)

    detail = []
    counts = Counter()
    count_with_close = 0
    for original in positions:
        cusip = original["cusip"]
        securities = by_cusip.get(cusip, set())
        reason = None
        sec = None
        closes = 0
        if not valid_original_cusip(cusip):
            reason = ("original-foreign-isin-separate-vendor-route"
                      if original["source_position"] in reviewed_isin_positions else
                      "invalid-original-cusip-requires-isin-source-review")
        elif not securities:
            reason = "no-versioned-v4-cusip-record"
        elif len(securities) != 1:
            reason = "ambiguous-v4-security-identity"
        else:
            sec = next(iter(securities))
            if len(reverse[sec]) > 1:
                reason = "v4-security-key-reused-for-distinct-cusips"
            else:
                fields = index[sec]
                ticker_rows = fields.get(("identifier_history", "ticker"), [])
                tickers = {r["value"] for r in ticker_rows if isinstance(r.get("value"), str)}
                observed_ticker = original.get("original_ticker_observation")
                if not isinstance(observed_ticker, str) or not observed_ticker:
                    reason = "missing-original-sec-ticker-observation"
                elif len(tickers) != 1:
                    reason = "missing-or-ambiguous-original-v4-ticker"
                elif tickers != {observed_ticker}:
                    reason = "sec-v4-ticker-conflict"
                else:
                    metadata = fields.get(("security_master", "currency"), [])
                    currencies = {r["value"] for r in metadata}
                    mic = {r["value"] for r in fields.get(("security_master", "exchange_mic"), [])}
                    types = {r["value"] for r in fields.get(("security_master", "type"), [])}
                    if currencies != {"USD"} or types != {"stock"} or len(mic) != 1 or not re.fullmatch(r"[A-Z0-9]{4}", next(iter(mic), "")):
                        reason = "missing-usd-stock-and-exchange-mic-original-metadata"
                    else:
                        bars = fields.get(("daily_prices", "close"), [])
                        dates = defaultdict(set)
                        for bar in bars:
                            value = bar.get("value")
                            if (bar.get("adjusted_basis") == "unadjusted-causal" and
                                bar.get("currency") == "USD" and
                                isinstance(value, (int, float)) and not isinstance(value, bool) and
                                math.isfinite(value) and value > 0 and bar.get("observation_date")):
                                dates[bar["observation_date"]].add(float(value))
                        if any(len(values) != 1 for values in dates.values()):
                            reason = "conflicting-raw-close-at-identical-session"
                        elif cut not in dates:
                            reason = "no-original-raw-close-at-decision-cut"
                        else:
                            closes = len(dates)
                            count_with_close += 1
                            reason = "research-only-v4-sec-source-intersection"
        counts[reason] += 1
        detail.append({"source_position": original["source_position"], "cusip": cusip,
                       "weight": original["weight"], "status": reason,
                       "v4_security_id": sec if reason == "research-only-v4-sec-source-intersection" else None,
                       "versioned_raw_close_sessions": closes,
                       "historical_permanent_identity_certified": False,
                       "original_vendor_publication_independently_verified": False,
                       "tradable_price_history_certified": False})
    return {"schema": SCHEMA, "cut": cut,
            "sec_request_sha256": sha256(canonical({"cut": cut, "requests": positions})),
            "stage_snapshot_sha256": stage["snapshot_sha256"],
            "total_original_sec_positions": len(positions),
            "valid_original_cusip_positions": sum(valid_original_cusip(p["cusip"]) for p in positions),
            "invalid_original_cusip_positions": sum(not valid_original_cusip(p["cusip"]) for p in positions),
            "foreign_isin_positions_reconciled_to_original": len(reviewed_isin_positions),
            "original_sec_foreign_isin_route_reverified": alternates is not None,
            "total_v4_stage_records": len(records),
            "source_hashes_in_stage": len(cited_hashes),
            "counts": dict(sorted(counts.items())),
            "matched_versioned_raw_close_at_cut": count_with_close,
            "positions": detail,
            "scope": "retrospective-source-reconciliation-only",
            "licensed_source_bytes_independently_reopened": False,
            "vendor_publication_independently_verified": False,
            "permanent_identity_certified": False,
            "full_engine_eligible_cuts_added": 0,
            "production_eligible": False,
            "predictive_validation": "not-established"}


def template():
    return {"schema": "bloomberg-first-cut-source-request-v1", "cut": "2024-12-31",
            "required_v4_fields": {
                "identifier_history": ["cusip", "ticker"],
                "security_master": ["currency", "type", "exchange_mic"],
                "daily_prices": ["close"],
            },
            "price_basis": "unadjusted-causal", "currency": "USD",
            "evidence": "Original provider versions, dated availability, raw SHA256, actual source paths and verified unit semantics",
            "stage_schema": STAGE_SCHEMA,
            "must_reconcile_with_original_sec_cusip": True,
            "never_substitute_present_day_catalogue": True,
            "production_eligible": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="Write an unlicensed schema-only source request")
    parser.add_argument("--stage", help="Local Bloomberg v4 stage JSON with source references")
    parser.add_argument("--warehouse-root", help="Local v4 warehouse directory containing warehouse.sqlite3 and raw/")
    parser.add_argument("--report", default="out/historical-bloomberg-first-cut-receipt-v1.json")
    options = parser.parse_args(argv)
    require(options.template or options.stage, "Supply --template or --stage")
    if options.template:
        path = Path(options.template)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if options.stage:
        require(bool(options.warehouse_root),
                "--warehouse-root is required for stage original-byte verification")
        if __package__:
            from .historical_identity_requests import build_requests
            from .historical_sec_alternate_identity import audit as audit_alternates
        else:
            from historical_identity_requests import build_requests
            from historical_sec_alternate_identity import audit as audit_alternates
        source = Path(options.stage)
        require(source.is_file() and source.stat().st_size <= 100_000_000,
                "Missing or oversized private Bloomberg stage")
        raw = source.read_bytes()
        stage = json.loads(raw)
        receipt = verify_stage(stage, options.warehouse_root)
        request = build_requests()
        report = audit(stage, request, audit_alternates())
        report.update(receipt)
        report["licensed_source_bytes_independently_reopened"] = True
        report["stage_export_sha256"] = sha256(raw)
        destination = Path(options.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"original_positions": report["total_original_sec_positions"],
                          "research_intersections": report["matched_versioned_raw_close_at_cut"],
                          "full_engine_eligible_cuts_added": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
