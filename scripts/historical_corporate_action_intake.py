"""Intake dated corporate actions for private historical raw-close evidence.

Event dates, document dates and native instrument keys must be independently
corroborated before using actions in trading, returns or cash-flow replay.
Only unadjusted splits and dividends are parsed; all other event types remain
explicit blockers instead of being silently dropped from the denominator.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import io
import json
import math
from pathlib import Path
import re

if __package__:
    from .historical_foreign_isin_requests import build_requests as foreign_requests
    from .historical_identity_cross_namespace_gate import template as identity_template
    from .historical_identity_requests import build_requests as original_requests
    from .historical_raw_price_intake import (
        ROOT, assess_prices, candidate_requests, evidence_identity,
        read_price_sources,
    )
    from .historical_sec_alternate_identity import audit as alternate_audit
    from .historical_sources import canonical, iso, sha
    from .historical_vendor_identity import local_file
else:
    from historical_foreign_isin_requests import build_requests as foreign_requests
    from historical_identity_cross_namespace_gate import template as identity_template
    from historical_identity_requests import build_requests as original_requests
    from historical_raw_price_intake import (
        ROOT, assess_prices, candidate_requests, evidence_identity,
        read_price_sources,
    )
    from historical_sec_alternate_identity import audit as alternate_audit
    from historical_sources import canonical, iso, sha
    from historical_vendor_identity import local_file

SCHEMA = "historical-corporate-action-sources-v1"
PUBLIC_TEMPLATE = "out/historical-corporate-action-request-v1.json"
PRIVATE_TEMPLATE = "out/historical-private-corporate-action-manifest-v1.json"
PRIVATE_REPORT = "out/historical-private-corporate-action-reconciliation-v1.json"
COLUMNS = (
    "id_namespace", "provider_instrument_id", "exchange_mic",
    "quote_currency", "event_id", "event_type", "announced_on",
    "record_as_of", "ex_date", "pay_date", "split_new_shares",
    "split_old_shares", "cash_per_share", "cash_currency",
)
TYPES = frozenset({
    "SPLIT", "CASH_DIVIDEND", "SPECIAL_CASH_DIVIDEND",
    "STOCK_DIVIDEND", "SPINOFF", "MERGER", "DELISTING",
})
CASH_TYPES = frozenset({"CASH_DIVIDEND", "SPECIAL_CASH_DIVIDEND"})
UNSUPPORTED = TYPES - CASH_TYPES - {"SPLIT"}
MAX_FILE_BYTES = 30_000_000
MAX_ROWS = 200_000
# A missing ex-date bar or a long gap cannot verify a trading session.
# This is a conservative diagnostic guard, not an exchange-calendar certificate.
MAX_PRIOR_SESSION_GAP_DAYS = 7


def require(ok, detail):
    if not ok:
        raise ValueError(detail)


def private_template(cross, price_report):
    require(cross["schema"] == "historical-cross-namespace-private-reconciliation-v1"
            and price_report["schema"] == "historical-private-raw-price-intake-v1"
            and cross["cut"] == price_report["cut"]
            and price_report["identity_report_sha256"] == sha(canonical(cross))
            and price_report["full_engine_eligible_cuts"] == 0
            and price_report["original_publication_vintages_verified"] is False,
            "Private price and identity reports do not share frozen source hashes")
    return {
        "protocol": SCHEMA,
        "cut": cross["cut"],
        "identity_report_sha256": sha(canonical(cross)),
        "raw_price_report_sha256": sha(canonical(price_report)),
        "exports": [],
    }


def parse_actions(raw, snapshot_as_of, cut):
    require(isinstance(raw, bytes) and len(raw) <= MAX_FILE_BYTES,
            "Invalid or oversized corporate-action CSV")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Corporate-action source must be UTF-8") from error
    reader = csv.DictReader(io.StringIO(content, newline=""))
    require(reader.fieldnames is not None and
            len(reader.fieldnames) == len(set(reader.fieldnames)) and
            set(reader.fieldnames) == set(COLUMNS),
            "Corporate-action CSV columns differ from contract")
    records = []
    for line, row in enumerate(reader, 2):
        require(None not in row and all(v is not None for v in row.values()),
                f"Malformed corporate-action CSV row {line}")
        item = {field: value.strip() for field, value in row.items()}
        require(re.fullmatch(r"[A-Z][A-Z0-9_-]{1,30}", item["id_namespace"]) and
                re.fullmatch(r"[A-Za-z0-9_.:/-]{2,100}",
                             item["provider_instrument_id"]) and
                re.fullmatch(r"[A-Z0-9]{4}", item["exchange_mic"]) and
                re.fullmatch(r"[A-Z]{3}", item["quote_currency"]) and
                re.fullmatch(r"[A-Za-z0-9_.:/-]{2,100}", item["event_id"]),
                f"Invalid security or corporate event key at row {line}")
        kind = item["event_type"]
        require(kind in TYPES, f"Unsupported event type at row {line}")
        announced = iso(item["announced_on"])
        asof = iso(item["record_as_of"])
        ex_date = iso(item["ex_date"])
        require(announced <= ex_date and announced <= asof <= snapshot_as_of <= cut,
                f"Future or late-announced corporate action at row {line}")
        require(ex_date <= cut, f"Future effective event excluded at row {line}")
        if item["pay_date"]:
            pay_date = iso(item["pay_date"])
            require(pay_date >= ex_date,
                    f"Payment date precedes ex-date at row {line}")
        else:
            pay_date = None
        if kind == "SPLIT":
            require(not any(item[field] for field in
                            ("pay_date", "cash_per_share", "cash_currency")),
                    f"Split must not claim a cash dividend at row {line}")
            try:
                new, old = (float(item["split_new_shares"]),
                            float(item["split_old_shares"]))
            except ValueError as error:
                raise ValueError(f"Invalid split ratio at row {line}") from error
            require(all(math.isfinite(n) and 0 < n <= 1_000_000 for n in (new, old)),
                    f"Invalid split share ratio at row {line}")
            item["split_ratio"] = new / old
            item["cash_per_share"] = None
        elif kind in CASH_TYPES:
            require(not item["split_new_shares"] and
                    not item["split_old_shares"] and pay_date is not None and
                    item["cash_currency"] == item["quote_currency"],
                    f"Cash dividend fields or currency mismatch at row {line}")
            try:
                cash = float(item["cash_per_share"])
            except ValueError as error:
                raise ValueError(f"Invalid cash dividend at row {line}") from error
            require(math.isfinite(cash) and cash > 0,
                    f"Invalid positive cash dividend at row {line}")
            item["cash_per_share"] = cash
            item["split_ratio"] = None
        else:
            require(not any(item[field] for field in
                            ("split_new_shares", "split_old_shares",
                             "cash_per_share", "cash_currency", "pay_date")),
                    f"Unsupported event may not declare interpreted cash or split at row {line}")
            item["cash_per_share"] = None
            item["split_ratio"] = None
        item["pay_date"] = pay_date
        records.append(item)
    require(len(records) <= MAX_ROWS, "Corporate-action export has too many rows")
    return records


def read_event_sources(directory, cross, price_report):
    """Private manifest binds exact security-master and raw-price source hashes."""
    root = Path(directory)
    manifest_bytes = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    baseline = private_template(cross, price_report)
    require(all(manifest.get(k) == v for k, v in baseline.items() if k != "exports"),
            "Action export not bound to frozen price and security-master reports")
    exports = manifest.get("exports")
    require(isinstance(exports, list) and 0 < len(exports) <= 25,
            "No dated corporate-action exports supplied")
    rows, receipts = [], []
    paths = set()
    for ref in exports:
        require(isinstance(ref, dict), "Invalid action source pointer")
        relative = ref.get("path")
        require(isinstance(relative, str) and relative not in paths,
                "Duplicate action export path")
        paths.add(relative)
        raw = local_file(root, relative).read_bytes()
        require(re.fullmatch(r"[0-9a-f]{64}", ref.get("sha256", "")) is not None
                and sha(raw) == ref["sha256"],
                "Action export SHA256 mismatch")
        require(all(isinstance(ref.get(k), str) and ref[k].strip()
                    for k in ("provider", "source_reference")),
                "Action provider provenance missing")
        snapshot = iso(ref.get("snapshot_as_of"))
        require(snapshot <= cross["cut"], "Action export uses a post-cut snapshot")
        require(ref.get("temporal_basis") in
                ("retrospective_asof_export", "contemporaneous_archive"),
                "Action temporal basis not declared")
        retrieved = ref.get("retrieved_at")
        try:
            when = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
            require(when.utcoffset() is not None, "Action retrieval needs timezone")
            when = when.astimezone(timezone.utc)
        except (TypeError, AttributeError, ValueError) as error:
            raise ValueError("Invalid corporate-action retrieval timestamp") from error
        require(when.date().isoformat() >= snapshot,
                "Retrieval predates declared action snapshot")
        parsed = parse_actions(raw, snapshot, cross["cut"])
        rows.extend(parsed)
        receipts.append({
            "sha256": ref["sha256"], "provider": ref["provider"],
            "source_reference": ref["source_reference"],
            "snapshot_as_of": snapshot, "retrieved_at": when.isoformat(),
            "temporal_basis": ref["temporal_basis"],
            "row_count": len(parsed),
            "independent_contemporaneous_proof": False,
        })
    return rows, receipts, sha(manifest_bytes)


def reconcile_actions(cross, prices, rows, receipts, manifest_sha, raw_bars):
    """Match events to original raw bars; never create payments or adjusted prices."""
    base = private_template(cross, prices)
    # Reject a substituted price report or a different set of raw bar originals.
    rebuilt = assess_prices(
        cross, raw_bars, prices["source_receipts"],
        prices["price_manifest_sha256"],
    )
    require(canonical(rebuilt) == canonical(prices),
            "Corporate events require the exact reported raw-price observations")
    raw_sessions = defaultdict(dict)
    for bar in raw_bars:
        key = (bar["id_namespace"], bar["provider_instrument_id"])
        raw_sessions[key][bar["session_date"]] = bar["raw_close"]
    candidates = candidate_requests(cross)
    owners = {(x["id_namespace"], x["provider_instrument_id"]): x
              for x in candidates}
    prices_by_key = {(x["id_namespace"], x["provider_instrument_id"]): x
                     for x in prices["positions"]}
    require(len(owners) == prices["requested_unique_security_keys"] and
            set(owners) == set(prices_by_key),
            "Price archive does not represent the same original security keys")
    seen_events, events_by_key, date_groups = set(), defaultdict(list), defaultdict(set)
    for event in rows:
        key = (event["id_namespace"], event["provider_instrument_id"])
        require(key in owners, "Corporate action has no cross-source security candidate")
        owner = owners[key]
        require(event["exchange_mic"] == owner["exchange_mic"] and
                event["quote_currency"] == owner["quote_currency"],
                "Corporate action has inconsistent listing or quote currency")
        identity = key + (event["event_id"],)
        require(identity not in seen_events, "Duplicate corporate event ID")
        seen_events.add(identity)
        events_by_key[key].append(event)
        date_groups[key + (event["event_type"], event["ex_date"])].add(event["event_id"])
    counts = Counter()
    observed_key_statuses = Counter()
    per_key = []
    for request in candidates:
        key = (request["id_namespace"], request["provider_instrument_id"])
        events = sorted(events_by_key[key], key=lambda e: (e["ex_date"], e["event_id"]))
        price = prices_by_key[key]
        has_prices = price["raw_bar_count"] > 0
        if not events:
            observed_key_statuses["no-event-row-not-proof-of-event-absence"] += 1
        else:
            observed_key_statuses["one-or-more-reported-events"] += 1
        labels, bridges = [], []
        sessions = raw_sessions[key]
        for event in events:
            ex_day = event["ex_date"]
            prior_days = [day for day in sessions if day < ex_day]
            prior = max(prior_days) if prior_days else None
            before = sessions.get(prior) if prior else None
            on_ex_day = sessions.get(ex_day)
            gap = ((date.fromisoformat(ex_day) -
                    date.fromisoformat(prior)).days if prior else None)
            # Prices here remain raw, retrospective and unlicensed for deployment.
            # No actual cash payment or dividend-adjusted series is constructed.
            bracketed = (
                before is not None and on_ex_day is not None and
                gap <= MAX_PRIOR_SESSION_GAP_DAYS
            )
            bridge = {
                "prior_observed_session": prior, "ex_date": ex_day,
                "calendar_days_between_observed_sessions": gap,
                "prior_raw_close": before, "ex_date_raw_close": on_ex_day,
                "ex_date_bracket_observed": bracketed,
                "unadjusted_price_change": (
                    on_ex_day / before - 1 if bracketed else None),
                "split_neutral_price_change": (
                    on_ex_day * event["split_ratio"] / before - 1
                    if bracketed and event["event_type"] == "SPLIT" else None),
                "cash_payment_created": False,
                "historical_price_vintage_authenticated": False,
            }
            group = key + (event["event_type"], ex_day)
            if len(date_groups[group]) > 1:
                state = "conflicting-event-type-and-ex-date"
            elif event["record_as_of"] > ex_day:
                state = "post-effective-event-record-quarantined"
            elif event["event_type"] in UNSUPPORTED:
                state = "uninterpreted-reorganization-or-delisting"
            elif not has_prices:
                state = "no-raw-price-history-for-action"
            elif event["event_type"] in CASH_TYPES and event["pay_date"] > cross["cut"]:
                state = "unsettled-cash-payment-at-cut"
            elif not bracketed:
                state = "missing-ex-date-raw-price-bracket"
            else:
                state = "retrospective-event-candidate"
            labels.append(state)
            bridges.append(bridge)
            counts[state] += 1
        per_key.append({
            **request,
            "raw_price_status": price["status"],
            "source_event_count": len(events),
            "event_statuses": dict(sorted(Counter(labels).items())),
            "event_refs": [
                {"event_id": event["event_id"], "event_type": event["event_type"],
                 "announced_on": event["announced_on"],
                 "ex_date": event["ex_date"], "pay_date": event["pay_date"],
                 "record_as_of": event["record_as_of"],
                 "event_status": state,
                 "raw_price_bridge": bridge}
                for event, state, bridge in zip(events, labels, bridges)
            ],
            "independently_authenticated": False,
            "cashflows_reconciled": False,
            "price_adjustments_authorized": False,
            "production_eligible": False,
        })
    require(sum(x["source_event_count"] for x in per_key) == len(rows),
            "Corporate action report lost original event observations")
    return {
        "schema": "historical-corporate-action-reconciliation-v1",
        "cut": cross["cut"],
        "identity_report_sha256": base["identity_report_sha256"],
        "raw_price_report_sha256": base["raw_price_report_sha256"],
        "action_manifest_sha256": manifest_sha,
        "receipt_count": len(receipts),
        "source_receipts": receipts,
        "raw_event_count": len(rows),
        "event_status_counts": dict(sorted(counts.items())),
        "security_key_event_coverage": dict(sorted(observed_key_statuses.items())),
        "absence_of_reported_events_certified": False,
        "session_calendar_verified": False,
        "source_positive_spy_positions": cross["positive_spy_positions"],
        "source_spy_weight": cross["positive_spy_weight"],
        "unique_security_keys": len(candidates),
        "positions": per_key,
        "corporate_actions_certified": False,
        "historical_cashflow_dates_verified": False,
        "price_adjustment_pipeline_enabled": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=PUBLIC_TEMPLATE)
    parser.add_argument("--cusip-evidence-dir")
    parser.add_argument("--isin-evidence-dir")
    parser.add_argument("--price-evidence-dir")
    parser.add_argument("--event-evidence-dir")
    parser.add_argument("--private-manifest", default=PRIVATE_TEMPLATE)
    parser.add_argument("--private-report", default=PRIVATE_REPORT)
    args = parser.parse_args(argv)
    have_identity = bool(args.cusip_evidence_dir) and bool(args.isin_evidence_dir)
    require(bool(args.cusip_evidence_dir) == bool(args.isin_evidence_dir) and
            (not args.price_evidence_dir or have_identity) and
            (not args.event_evidence_dir or
             (have_identity and args.price_evidence_dir)),
            "Corporate-action intake requires both identity extracts and raw prices")
    original = original_requests(ROOT)
    foreign = foreign_requests(alternate_audit(ROOT))
    public = identity_template(original, foreign)
    public.update({
        "schema": "historical-corporate-action-request-v1",
        "corporate_action_types_requested": sorted(TYPES),
        "expected_price_basis": "unadjusted-per-share-exchange-close",
        "vendor_actions_received": 0,
        "historical_actions_certified": False,
        "full_engine_eligible_cuts": 0,
    })
    p = Path(args.template)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    if not args.price_evidence_dir:
        print(json.dumps({
            "positive_spy_positions": public["positive_spy_positions"],
            "vendor_actions_received": 0, "full_engine_eligible_cuts": 0,
        }, sort_keys=True))
        return
    cross = evidence_identity(original, foreign, args.cusip_evidence_dir,
                              args.isin_evidence_dir)
    bars, price_receipts, price_manifest = read_price_sources(
        args.price_evidence_dir, cross)
    price_report = assess_prices(cross, bars, price_receipts, price_manifest)
    template = private_template(cross, price_report)
    destination = Path(args.private_manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
    if args.event_evidence_dir:
        events, event_receipts, digest = read_event_sources(
            args.event_evidence_dir, cross, price_report)
        report = reconcile_actions(cross, price_report, events,
                                   event_receipts, digest, bars)
        target = Path(args.private_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "raw_event_count": report["raw_event_count"],
            "event_status_counts": report["event_status_counts"],
            "full_engine_eligible_cuts": 0,
        }, sort_keys=True))
    else:
        print(json.dumps({
            "raw_price_rows": price_report["raw_price_rows"],
            "vendor_actions_received": 0, "full_engine_eligible_cuts": 0,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
