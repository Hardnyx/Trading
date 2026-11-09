"""Intake raw historical closing-price bars bound to SEC security-master candidates.

This file does not create adjusted/total returns, infer dividends or splits,
certify publication vintages, or authorize full-engine historical decisions.
Private vendor rows and native instrument keys must never be uploaded to CI.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re

if __package__:
    from .historical_foreign_isin_requests import build_requests as foreign_requests
    from .historical_foreign_isin_vendor_identity import (
        read_foreign_evidence, reconcile as reconcile_foreign,
    )
    from .historical_identity_cross_namespace_gate import (
        combine, template as identity_template,
    )
    from .historical_identity_requests import build_requests as original_requests
    from .historical_sec_alternate_identity import audit as alternate_audit
    from .historical_sources import canonical, iso, sha
    from .historical_vendor_identity import (
        local_file, read_evidence as read_cusip_evidence,
        reconcile as reconcile_cusip,
    )
else:
    from historical_foreign_isin_requests import build_requests as foreign_requests
    from historical_foreign_isin_vendor_identity import (
        read_foreign_evidence, reconcile as reconcile_foreign,
    )
    from historical_identity_cross_namespace_gate import combine, template as identity_template
    from historical_identity_requests import build_requests as original_requests
    from historical_sec_alternate_identity import audit as alternate_audit
    from historical_sources import canonical, iso, sha
    from historical_vendor_identity import (
        local_file, read_evidence as read_cusip_evidence,
        reconcile as reconcile_cusip,
    )

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "historical-raw-price-bars-v1"
PUBLIC_TEMPLATE = "out/historical-raw-price-source-request-v1.json"
PRIVATE_REQUEST = "out/historical-private-price-requests-v1.csv"
PRIVATE_MANIFEST = "out/historical-private-price-manifest-template-v1.json"
PRIVATE_REPORT = "out/historical-private-price-receipt-v1.json"
COLUMNS = (
    "id_namespace", "provider_instrument_id", "exchange_mic", "quote_currency",
    "session_date", "raw_close", "record_as_of", "price_basis",
)
REQUEST_COLUMNS = (
    "id_namespace", "provider_instrument_id", "exchange_mic", "quote_currency",
    "first_requested_session", "decision_cut", "source_positions",
    "minimum_return_intervals",
)
PRICE_BASIS = "unadjusted-per-share-exchange-close"
MIN_RETURN_INTERVALS = 252
MAX_CSV_BYTES = 40_000_000


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-10)


def evidence_identity(original, foreign, cusip_dir, isin_dir):
    """Rebuild hashes and private candidate keys directly from vendor originals."""
    c_rows, c_proof, c_manifest = read_cusip_evidence(cusip_dir, original)
    f_rows, f_proof, f_manifest = read_foreign_evidence(isin_dir, foreign)
    return combine(
        original, foreign,
        reconcile_cusip(original, c_rows, c_proof, c_manifest),
        reconcile_foreign(foreign, f_rows, f_proof, f_manifest),
    )


def candidate_requests(cross):
    """Only unambiguous cross-namespace candidates, one per original key."""
    require(cross["schema"] == "historical-cross-namespace-private-reconciliation-v1" and
            cross["cross_namespace_identity_certified"] is False and
            cross["historical_prices_certified"] is False and
            cross["full_engine_eligible_cuts"] == 0 and
            cross["vendor_rows_received"] >= 0 and
            len(cross["positions"]) == cross["positive_spy_positions"] and
            close(sum(r["source_spy_weight"] for r in cross["positions"]),
                  cross["positive_spy_weight"]),
            "Unreconciled or promoted identity input")
    groups = {}
    for row in cross["positions"]:
        key = row["candidate_security_key"]
        if key is None:
            require(row["cross_source_status"] != "retrospective-cross-source-candidate",
                    "Candidate status lost its private identity key")
            continue
        require(row["cross_source_status"] == "retrospective-cross-source-candidate" and
                row["historical_price_vintage_verified"] is False and
                row["full_engine_eligible"] is False,
                "Only unpromoted cross-source identity candidates may be priced")
        namespace, native, mic = (key["namespace"], key["provider_instrument_id"],
                                  key["exchange_mic"])
        currency = key.get("quote_currency", "USD")
        require(all(isinstance(x, str) and x for x in (namespace, native, mic, currency)) and
                re.fullmatch(r"[A-Z]{3}", currency) is not None and
                re.fullmatch(r"[A-Z0-9]{4}", mic) is not None,
                "Provider quote currency, MIC or permanent key missing")
        identifier = (namespace, native)
        if identifier in groups:
            require(groups[identifier]["exchange_mic"] == mic and
                    groups[identifier]["quote_currency"] == currency,
                    "Permanent key has incompatible listing or quote currency")
            groups[identifier]["source_positions"].append(row["source_position"])
        else:
            groups[identifier] = {
                "id_namespace": namespace, "provider_instrument_id": native,
                "exchange_mic": mic, "quote_currency": currency,
                "first_requested_session": "training-window-to-be-confirmed",
                "decision_cut": cross["cut"],
                "source_positions": [row["source_position"]],
                "minimum_return_intervals": MIN_RETURN_INTERVALS,
            }
    return sorted(groups.values(), key=lambda r: (r["id_namespace"],
                                                  r["provider_instrument_id"]))


def request_csv(requests):
    content = io.StringIO(newline="")
    writer = csv.DictWriter(content, fieldnames=REQUEST_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in requests:
        writer.writerow({
            **row,
            "source_positions": ";".join(str(i) for i in sorted(row["source_positions"])),
        })
    return content.getvalue()


def private_template(cross):
    return {
        "protocol": SCHEMA, "cut": cross["cut"],
        "identity_report_sha256": sha(canonical(cross)),
        "price_basis": PRICE_BASIS,
        "exports": [],
    }


def parse_bars(raw, snapshot, cut):
    require(isinstance(raw, bytes) and len(raw) <= MAX_CSV_BYTES,
            "Missing, oversized or invalid price CSV")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("Price source is not UTF-8") from error
    require(reader.fieldnames is not None and
            len(set(reader.fieldnames)) == len(reader.fieldnames) and
            set(reader.fieldnames) == set(COLUMNS),
            "Price CSV columns differ from raw-close contract")
    result = []
    for line, row in enumerate(reader, 2):
        require(None not in row and all(v is not None for v in row.values()),
                f"Malformed price CSV row {line}")
        item = {k: v.strip() for k, v in row.items()}
        day, asof = iso(item["session_date"]), iso(item["record_as_of"])
        require(day <= asof <= snapshot <= cut,
                f"Future price, publication or snapshot at row {line}")
        require(item["price_basis"] == PRICE_BASIS,
                f"Adjusted, total-return or unknown price basis at row {line}")
        require(re.fullmatch(r"[A-Z][A-Z0-9_-]{1,30}", item["id_namespace"]) and
                re.fullmatch(r"[A-Za-z0-9_.:/-]{2,100}", item["provider_instrument_id"]) and
                re.fullmatch(r"[A-Z0-9]{4}", item["exchange_mic"]) and
                re.fullmatch(r"[A-Z]{3}", item["quote_currency"]),
                f"Invalid native identity, MIC or currency at row {line}")
        try:
            price = float(item["raw_close"])
        except ValueError as error:
            raise ValueError(f"Invalid raw price at row {line}") from error
        require(math.isfinite(price) and price > 0,
                f"Nonpositive or nonfinite raw price at row {line}")
        result.append({**item, "raw_close": price})
    require(len(result) <= 100_000, "Price export exceeds maximum observations")
    return result


def read_price_sources(directory, cross):
    """Read private, hash-anchored originals. A claimed as-of is not proof."""
    root = Path(directory)
    raw_manifest = (root / "manifest.json").read_bytes()
    manifest = json.loads(raw_manifest)
    expected = private_template(cross)
    require(all(manifest.get(k) == v for k, v in expected.items() if k != "exports"),
            "Price evidence manifest is not bound to selected identity keys")
    exports = manifest.get("exports")
    require(isinstance(exports, list) and 0 < len(exports) <= 25,
            "Missing or excessive price exports")
    rows, receipts = [], []
    seen = set()
    for source in exports:
        require(isinstance(source, dict), "Invalid price source reference")
        relative = source.get("path")
        require(isinstance(relative, str) and relative not in seen,
                "Duplicate or missing price CSV path")
        seen.add(relative)
        raw = local_file(root, relative).read_bytes()
        require(re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")) is not None and
                sha(raw) == source["sha256"], "Price source SHA256 mismatch")
        require(all(isinstance(source.get(k), str) and source[k].strip()
                    for k in ("provider", "source_reference")),
                "Price provider identity or source reference missing")
        snapshot = iso(source.get("snapshot_as_of"))
        require(snapshot <= cross["cut"], "Future price source snapshot")
        basis = source.get("temporal_basis")
        require(basis in ("retrospective_asof_export", "contemporaneous_archive"),
                "Price export temporal provenance missing")
        retrieved = source.get("retrieved_at")
        try:
            when = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
            require(when.utcoffset() is not None, "Price retrieval time needs timezone")
            when = when.astimezone(timezone.utc)
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("Invalid price source retrieval timestamp") from error
        require(when.date().isoformat() >= snapshot, "Retrieval predates declared snapshot")
        parsed = parse_bars(raw, snapshot, cross["cut"])
        rows.extend(parsed)
        receipts.append({
            "path": relative, "sha256": source["sha256"],
            "provider": source["provider"],
            "source_reference": source["source_reference"],
            "snapshot_as_of": snapshot,
            "retrieved_at": when.isoformat(),
            "temporal_basis": basis, "rows": len(parsed),
            "original_vintage_independently_authenticated": False,
        })
    return rows, receipts, sha(raw_manifest)


def assess_prices(cross, rows, sources, manifest_sha):
    requests = candidate_requests(cross)
    by_key = {(r["id_namespace"], r["provider_instrument_id"]): r for r in requests}
    histories = defaultdict(list)
    seen = set()
    for row in rows:
        key = (row["id_namespace"], row["provider_instrument_id"])
        require(key in by_key, "Price bar has no eligible cross-source identity candidate")
        owner = by_key[key]
        require(row["exchange_mic"] == owner["exchange_mic"] and
                row["quote_currency"] == owner["quote_currency"],
                "Price bar exchange or currency differs from security-master candidate")
        require(row["session_date"] <= row["record_as_of"] <= cross["cut"],
                "Future raw-price observation")
        key_day = key + (row["session_date"],)
        require(key_day not in seen, "Duplicate or competing raw close for a session")
        seen.add(key_day)
        histories[key].append(row)
    statuses = Counter()
    result = []
    for r in requests:
        key = (r["id_namespace"], r["provider_instrument_id"])
        bars = sorted(histories[key], key=lambda x: x["session_date"])
        length = len(bars)
        if not length:
            status = "no-original-price-evidence"
        elif length - 1 < MIN_RETURN_INTERVALS:
            status = "insufficient-raw-price-intervals"
        elif bars[-1]["session_date"] != cross["cut"]:
            status = "missing-exact-cut-session-close"
        else:
            status = "retrospective-raw-close-candidate"
        statuses[status] += 1
        result.append({
            **r, "raw_bar_count": length,
            "first_session": bars[0]["session_date"] if bars else None,
            "last_session": bars[-1]["session_date"] if bars else None,
            "status": status,
            "original_publication_vintage_certified": False,
            "session_calendar_and_tradability_verified": False,
            "split_and_dividend_cashflows_verified": False,
            "historical_fx_and_executable_close_verified": False,
            "production_eligible": False,
        })
    return {
        "schema": "historical-private-raw-price-intake-v1",
        "cut": cross["cut"], "identity_report_sha256": sha(canonical(cross)),
        "price_manifest_sha256": manifest_sha, "source_receipts": sources,
        "requested_unique_security_keys": len(requests),
        "raw_price_rows": len(rows),
        "count_by_status": dict(sorted(statuses.items())),
        "positions": result,
        "source_spy_weight": cross["positive_spy_weight"],
        "original_publication_vintages_verified": False,
        "corporate_actions_and_delistings_verified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=PUBLIC_TEMPLATE)
    parser.add_argument("--cusip-evidence-dir")
    parser.add_argument("--isin-evidence-dir")
    parser.add_argument("--price-evidence-dir")
    parser.add_argument("--private-request", default=PRIVATE_REQUEST)
    parser.add_argument("--private-manifest", default=PRIVATE_MANIFEST)
    parser.add_argument("--private-report", default=PRIVATE_REPORT)
    args = parser.parse_args(argv)
    have_id = bool(args.cusip_evidence_dir) and bool(args.isin_evidence_dir)
    require(bool(args.cusip_evidence_dir) == bool(args.isin_evidence_dir) and
            (not args.price_evidence_dir or have_id),
            "Price intake requires both private identity exports")
    original = original_requests(ROOT)
    foreign = foreign_requests(alternate_audit(ROOT))
    public = identity_template(original, foreign)
    public.update({
        "schema": "historical-raw-price-source-request-v1",
        "source_role": "original-sec-positions-no-licensed-price-data",
        "required_price_basis": PRICE_BASIS,
        "minimum_return_intervals_per_price_history": MIN_RETURN_INTERVALS,
        "historical_prices_certified": False,
        "full_engine_eligible_cuts": 0,
    })
    target = Path(args.template)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(public, indent=2) + "\n", encoding="utf-8")
    if not have_id:
        print(json.dumps({"source_positive_positions": public["positive_spy_positions"],
                          "vendor_price_rows_received": 0,
                          "full_engine_eligible_cuts": 0}, sort_keys=True))
        return
    cross = evidence_identity(original, foreign, args.cusip_evidence_dir,
                              args.isin_evidence_dir)
    requests = candidate_requests(cross)
    output = Path(args.private_request)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(request_csv(requests), encoding="utf-8")
    manifest_file = Path(args.private_manifest)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(private_template(cross), indent=2) + "\n",
                             encoding="utf-8")
    if args.price_evidence_dir:
        bars, receipts, digest = read_price_sources(args.price_evidence_dir, cross)
        report = assess_prices(cross, bars, receipts, digest)
        p = Path(args.private_report)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"unique_candidates": len(requests),
                          "price_rows_received": len(bars),
                          "count_by_status": report["count_by_status"],
                          "full_engine_eligible_cuts": 0}, sort_keys=True))
    else:
        print(json.dumps({"unique_candidates": len(requests),
                          "price_rows_received": 0, "full_engine_eligible_cuts": 0},
                         sort_keys=True))


if __name__ == "__main__":
    main()
