"""Reconcile private dated foreign-ISIN vendor extracts against frozen SEC requests.

No private evidence is committed. A matched retrospective instrument key is
not certification of original availability, tradability or historical prices.
"""
import argparse
from collections import Counter, defaultdict
import csv
import io
import json
import math
from pathlib import Path

if __package__:
    from .historical_foreign_isin_requests import (
        ROOT, build_requests, request_hash,
    )
    from .historical_sec_alternate_identity import (
        audit as audit_alternates, isin_valid,
    )
    from .historical_vendor_identity import (
        ALLOWED_TYPES, COLUMNS, parse_export, read_evidence,
    )
else:
    from historical_foreign_isin_requests import ROOT, build_requests, request_hash
    from historical_sec_alternate_identity import audit as audit_alternates, isin_valid
    from historical_vendor_identity import ALLOWED_TYPES, COLUMNS, parse_export, read_evidence

SCHEMA = "historical-foreign-isin-vendor-sources-v1"
OUTPUT = "out/historical-foreign-isin-vendor-reconciliation-v1.json"
TEMPLATE = "out/historical-foreign-isin-vendor-manifest-template-v1.json"
EXPORT_COLUMNS = tuple("original_isin" if column == "cusip" else column
                       for column in COLUMNS)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_foreign_export(raw, snapshot_as_of):
    """Reuse the dated CUSIP export controls with an ISO 6166 original ISIN."""
    return parse_export(raw, snapshot_as_of, identifier_column="original_isin",
                        validator=isin_valid)


def foreign_state(row, cut):
    """Identity-only conditions: local trading currency is not forced to USD."""
    if not row["provider_instrument_id"]:
        return "missing-permanent-id"
    if row["security_type"] not in ALLOWED_TYPES:
        return "unsupported-security-type"
    if not row["currency"]:
        return "missing-quote-currency"
    if not row["exchange_mic"]:
        return "missing-exchange-mic"
    if not row["valid_from"] or not row["valid_to"]:
        return "incomplete-effective-interval"
    if not row["valid_from"] <= cut < row["valid_to"]:
        return "not-effective-at-cut"
    if row["valid_from"] > row["record_as_of"]:
        return "identity-begins-after-declared-snapshot"
    return "retrospective-foreign-identity-candidate"


def manifest_template(queue):
    """Immutable original SEC requests bound to an unfilled local export manifest."""
    return {
        "protocol": SCHEMA,
        "cut": queue["cut"],
        "request_sha256": request_hash(queue),
        "source_original_sha256": queue["source_original_sha256"],
        "exports": [],
    }


def read_foreign_evidence(directory, queue):
    """Shared source checks: manifest hash, raw bytes, as-of, retrieval and path."""
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_bytes())
    require(manifest.get("source_original_sha256") == queue["source_original_sha256"],
            "Original SEC filing hash differs from foreign-ISIN request")
    return read_evidence(
        root, queue, schema=SCHEMA, request_sha256=request_hash(queue),
        parser=parse_foreign_export,
    )


def reconcile(queue, rows, provenance, manifest_sha256):
    """Join source ISINs only; no ticker/name fallback or future model promotion."""
    require(queue["schema"] == "historical-foreign-isin-requests-v1" and
            queue["source_vendor_id_certified"] is False and
            queue["original_cusip_corrected"] is False and
            queue["full_engine_eligible_cuts"] == 0,
            "The original foreign-ISIN requests were modified or promoted")
    originals = queue["requests"]
    by_isin = {item["original_isin"]: item for item in originals}
    require(len(by_isin) == len(originals) and
            all(isin_valid(k) and not k.startswith("US") for k in by_isin),
            "Original foreign ISIN requests contain duplicates or invalid IDs")
    require(sum(len(item["source_positions"]) for item in originals) ==
            queue["foreign_isin_request_positions"] and
            math.isclose(sum(item["reported_spy_weight"] for item in originals),
                         queue["foreign_isin_request_weight"], rel_tol=0, abs_tol=1e-10),
            "Frozen SEC positions or weights changed")
    require(queue["public_available_after_day"] < queue["cut"],
            "Original filing became public only after decision")
    require(math.isclose(queue["foreign_isin_request_weight"] +
                         queue["unresolved_identifier_weight"],
                         queue["source_spy_weight"], rel_tol=0, abs_tol=1e-10),
            "Original SEC foreign ISIN denominator changed")

    evidence = defaultdict(list)
    rejected = Counter()
    for row in rows:
        isin = row["original_isin"]
        require(isin in by_isin, "Unrequested ISIN in vendor export")
        state = foreign_state(row, queue["cut"])
        if state != "retrospective-foreign-identity-candidate":
            rejected[state] += 1
        evidence[isin].append(row)

    choices = {}
    reverse = defaultdict(set)
    for isin, group in evidence.items():
        viable = [row for row in group
                  if foreign_state(row, queue["cut"]) ==
                  "retrospective-foreign-identity-candidate"]
        identities = {}
        for row in viable:
            key = (
                row["_provider"], row["id_namespace"],
                row["provider_instrument_id"], row["exchange_mic"],
                row["currency"], row["security_type"],
            )
            identities.setdefault(key, set()).add(row["_source_sha256"])
            reverse[(key[0], key[1], key[2])].add(isin)
        choices[isin] = identities

    counts = Counter()
    weights = Counter()
    positions = []
    for item in originals:
        isin = item["original_isin"]
        candidates = choices.get(isin, {})
        if not evidence[isin]:
            status = "no-provider-evidence"
        elif not candidates:
            status = "no-temporally-admissible-identity"
        elif len(candidates) > 1:
            status = "conflicting-provider-identities"
        elif any(len(reverse[key[:3]]) > 1 for key in candidates):
            status = "provider-key-shared-by-multiple-isins"
        else:
            status = "retrospective-foreign-identity-candidate"
        selected = next(iter(candidates)) if status == (
            "retrospective-foreign-identity-candidate") else None
        counts[status] += 1
        weights[status] += item["reported_spy_weight"]
        positions.append({
            "original_isin": isin,
            "source_positions": item["source_positions"],
            "reported_spy_weight": item["reported_spy_weight"],
            "status": status,
            "candidate_security_key": {
                "provider": selected[0], "namespace": selected[1],
                "provider_instrument_id": selected[2],
                "exchange_mic": selected[3], "quote_currency": selected[4],
                "security_type": selected[5],
            } if selected else None,
            "source_hashes": sorted(candidates[selected]) if selected else [],
            "historical_public_availability_certified": False,
            "historical_quote_currency_and_fx_verified": False,
            "listing_and_execution_verified": False,
            "original_price_vintage_verified": False,
            "corporate_actions_verified": False,
            "production_eligible": False,
        })
    require(sum(counts.values()) == queue["distinct_foreign_isin_requests"] and
            math.isclose(sum(weights.values()), queue["foreign_isin_request_weight"],
                         rel_tol=0, abs_tol=1e-10),
            "Foreign-ISIN reconciliation lost source weight or requests")
    return {
        "schema": "historical-foreign-isin-vendor-reconciliation-v1",
        "cut": queue["cut"], "request_sha256": request_hash(queue),
        "source_original_sha256": queue["source_original_sha256"],
        "vendor_manifest_sha256": manifest_sha256, "sources": provenance,
        "vendor_rows": len(rows),
        "counts_by_distinct_isin": dict(sorted(counts.items())),
        "source_weight_by_status": dict(sorted(weights.items())),
        "excluded_row_reasons": dict(sorted(rejected.items())),
        "positions": positions,
        "original_source_positions": queue["original_invalid_cusip_positions"],
        "requested_source_positions": queue["foreign_isin_request_positions"],
        "unresolved_source_positions": queue["unresolved_identifier_positions"],
        "unresolved_source_weight": queue["unresolved_identifier_weight"],
        "vendor_evidence_is_retrospective_only": True,
        "historical_security_master_certified": False,
        "historical_prices_certified": False,
        "full_engine_eligible_cuts": 0,
        "production_eligible": False,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=TEMPLATE,
                        help="Public SEC-bound but intentionally unfilled manifest")
    parser.add_argument("--evidence-dir", help="Local, licensed vendor export directory")
    parser.add_argument("--report", default=OUTPUT, help="Private local reconciliation JSON")
    args = parser.parse_args(argv)

    queue = build_requests(audit_alternates(ROOT))
    target = Path(args.template)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest_template(queue), indent=2) + "\n",
                      encoding="utf-8")

    if args.evidence_dir:
        rows, provenance, source_hash = read_foreign_evidence(args.evidence_dir, queue)
        report = reconcile(queue, rows, provenance, source_hash)
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "distinct_foreign_isin_requests": queue["distinct_foreign_isin_requests"],
            "reconciliation_status": report["counts_by_distinct_isin"],
            "full_engine_eligible_cuts": 0,
        }, sort_keys=True))
    else:
        print(json.dumps({
            "distinct_foreign_isin_requests": queue["distinct_foreign_isin_requests"],
            "licensed_vendor_rows": 0, "full_engine_eligible_cuts": 0,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
