"""Guard against duplicate permanent keys across historical CUSIP and ISIN imports.

The original SEC N-PORT position is the accounting unit. A vendor key assigned
to distinct source identifiers is quarantined rather than merged. Neither
this audit nor separate vendor reconciliations certify point-in-time prices.
"""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

if __package__:
    from .historical_foreign_isin_requests import (
        build_requests as build_foreign_requests, request_hash as foreign_hash,
    )
    from .historical_foreign_isin_vendor_identity import (
        read_foreign_evidence, reconcile as reconcile_foreign,
    )
    from .historical_identity_requests import build_requests as build_original
    from .historical_sec_alternate_identity import (
        audit as audit_alternates, isin_valid,
    )
    from .historical_vendor_identity import (
        read_evidence as read_cusip_evidence, reconcile as reconcile_cusip,
        request_hash as cusip_hash, valid_cusip,
    )
else:
    from historical_foreign_isin_requests import (
        build_requests as build_foreign_requests, request_hash as foreign_hash,
    )
    from historical_foreign_isin_vendor_identity import (
        read_foreign_evidence, reconcile as reconcile_foreign,
    )
    from historical_identity_requests import build_requests as build_original
    from historical_sec_alternate_identity import audit as audit_alternates, isin_valid
    from historical_vendor_identity import (
        read_evidence as read_cusip_evidence, reconcile as reconcile_cusip,
        request_hash as cusip_hash, valid_cusip,
    )

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "historical-cross-namespace-identity-gate-v1"
TEMPLATE = "out/historical-cross-namespace-identity-template-v1.json"
REPORT = "out/historical-cross-namespace-identity-private-v1.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-10)


def source_contract(original, foreign):
    """Verify every invalid-CUSIP position against the same original SEC filing."""
    cut = original["cut"]
    require(foreign["schema"] == "historical-foreign-isin-requests-v1" and
            foreign["cut"] == cut and
            foreign["source_original_sha256"] == original["spy_original_sha256"] and
            foreign["source_accession"] == original["spy_original_accession"] and
            foreign["public_available_after_day"] < cut and
            foreign["source_vendor_id_certified"] is False and
            foreign["original_cusip_corrected"] is False and
            foreign["full_engine_eligible_cuts"] == 0 and
            original["full_engine_replay_ready"] is False,
            "Original SEC provenance or retrospective source contract changed")
    positions = {item["source_position"]: item for item in original["requests"]}
    require(len(positions) == len(original["requests"]) and
            len(positions) == original["counts"]["positive_positions"] and
            all(type(k) is int and p["weight"] > 0 and
                p.get("vendor_instrument_id") is None and
                p["vendor_price_series_verified"] is False
                for k, p in positions.items()) and
            close(sum(p["weight"] for p in positions.values()),
                  original["positive_spy_weight"]),
            "Original SEC positive positions or weights changed")
    invalid = {k for k, p in positions.items() if not valid_cusip(p["cusip"])}
    mapped = {}
    for request in foreign["requests"]:
        isin = request["original_isin"]
        references = request["source_positions"]
        require(isin_valid(isin) and not isin.startswith("US") and
                request["decision_cut"] == cut and
                request["spy_accession"] == original["spy_original_accession"] and
                request["original_sec_sha256"] == original["spy_original_sha256"] and
                request["source_identity_role"] ==
                "original-foreign-isin-vendor-enquiry-only" and
                isinstance(references, list) and references == sorted(set(references)) and
                references and all(type(i) is int and i in invalid and i not in mapped
                                   for i in references) and
                close(sum(positions[i]["weight"] for i in references),
                      request["reported_spy_weight"]),
                "Foreign ISIN references overlap or change original SEC positions")
        for pos in references:
            mapped[pos] = isin
    unresolved = set()
    for row in foreign["unresolved"]:
        pos = row["source_position"]
        require(type(pos) is int and pos in invalid and pos not in mapped and
                pos not in unresolved and
                row["cusip_as_reported"] == positions[pos]["cusip"] and
                close(row["reported_spy_weight"], positions[pos]["weight"]) and
                row["spy_accession"] == original["spy_original_accession"] and
                row["decision_cut"] == cut,
                "Unresolved ISIN position differs from original SEC")
        unresolved.add(pos)
    require(set(mapped) | unresolved == invalid and
            len(mapped) == foreign["foreign_isin_request_positions"] and
            len(unresolved) == foreign["unresolved_identifier_positions"] and
            len(foreign["requests"]) == foreign["distinct_foreign_isin_requests"] and
            len({r["original_isin"] for r in foreign["requests"]}) ==
            len(foreign["requests"]) and
            foreign["original_invalid_cusip_positions"] == len(invalid) and
            close(sum(positions[i]["weight"] for i in invalid),
                  foreign["source_spy_weight"]) and
            close(sum(positions[i]["weight"] for i in mapped),
                  foreign["foreign_isin_request_weight"]) and
            close(sum(positions[i]["weight"] for i in unresolved),
                  foreign["unresolved_identifier_weight"]),
            "Foreign ISIN coverage does not reconcile to all invalid SEC CUSIPs")
    return positions, mapped, unresolved


def template(original, foreign):
    positions, mapped, unresolved = source_contract(original, foreign)
    return {
        "protocol": PROTOCOL,
        "cut": original["cut"],
        "spy_accession": original["spy_original_accession"],
        "spy_original_sha256": original["spy_original_sha256"],
        "cusip_request_sha256": cusip_hash(original),
        "foreign_isin_request_sha256": foreign_hash(foreign),
        "positive_spy_positions": len(positions),
        "positive_spy_weight": original["positive_spy_weight"],
        "valid_cusip_positions": len(positions) - len(mapped) - len(unresolved),
        "foreign_isin_positions": len(mapped),
        "unresolved_invalid_cusip_positions": len(unresolved),
        "original_source_reconciled": True,
        "vendor_rows_received": 0,
        "cross_namespace_identity_certified": False,
        "historical_prices_certified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def combine(original, foreign, cusip_report, isin_report):
    """Retain each original position once and quarantine shared native keys."""
    positions, mapped, unresolved = source_contract(original, foreign)
    require(cusip_report["protocol"] == "historical-vendor-identity-reconciliation-v1" and
            isin_report["schema"] == "historical-foreign-isin-vendor-reconciliation-v1" and
            cusip_report["cut"] == isin_report["cut"] == original["cut"] and
            cusip_report["request_sha256"] == cusip_hash(original) and
            isin_report["request_sha256"] == foreign_hash(foreign) and
            isin_report["source_original_sha256"] == original["spy_original_sha256"] and
            cusip_report["historical_public_availability_certified"] is False and
            cusip_report["historical_prices_and_actions_certified"] is False and
            cusip_report["full_engine_replay_ready"] is False and
            isin_report["historical_security_master_certified"] is False and
            isin_report["historical_prices_certified"] is False and
            isin_report["full_engine_eligible_cuts"] == 0,
            "Vendor reports mismatch frozen original SEC requests or certification gates")
    cusip_positions = {}
    for row in cusip_report["positions"]:
        pos = row["source_position"]
        require(type(pos) is int and pos in positions and pos not in cusip_positions and
                row["cusip"] == positions[pos]["cusip"] and
                close(row["weight"], positions[pos]["weight"]) and
                row["historical_availability_certified"] is False and
                row["price_history_verified"] is False and
                row["production_eligible"] is False,
                "CUSIP vendor position contradicts original SEC or claims certification")
        key = row["candidate_security_key"]
        require(bool(key) == (row["status"] == "retrospective-identity-candidate"),
                "CUSIP provider key does not match retrospective status")
        if pos in mapped or pos in unresolved:
            require(key is None and row["status"] == "no-provider-evidence",
                    "Invalid original CUSIP was promoted through the CUSIP importer")
        cusip_positions[pos] = row
    require(set(cusip_positions) == set(positions),
            "CUSIP vendor report omits original SEC positions")

    foreign_positions = {}
    for row in isin_report["positions"]:
        isin = row["original_isin"]
        linked = row["source_positions"]
        require(isinstance(linked, list) and linked and linked == sorted(set(linked)) and
                all(mapped.get(pos) == isin and pos not in foreign_positions
                    for pos in linked) and
                close(row["reported_spy_weight"],
                      sum(positions[pos]["weight"] for pos in linked)) and
                row["historical_public_availability_certified"] is False and
                row["original_price_vintage_verified"] is False and
                row["production_eligible"] is False,
                "Foreign vendor row changes source positions or claims certification")
        key = row["candidate_security_key"]
        require(bool(key) == (row["status"] ==
                              "retrospective-foreign-identity-candidate"),
                "Foreign provider key does not match retrospective status")
        for pos in linked:
            foreign_positions[pos] = row
    require(set(foreign_positions) == set(mapped),
            "Foreign vendor report omits a requested original SEC position")

    rows = []
    key_owners = defaultdict(set)
    for pos, orig in sorted(positions.items()):
        if pos in unresolved:
            domain, source_id = "ISIN", None
            status, key, source_hashes = "unresolved-original-foreign-isin", None, []
        elif pos in mapped:
            vendor = foreign_positions[pos]
            domain, source_id = "ISIN", mapped[pos]
            status, key = vendor["status"], vendor["candidate_security_key"]
            source_hashes = vendor["source_hashes"]
        else:
            vendor = cusip_positions[pos]
            domain, source_id = "CUSIP", orig["cusip"]
            status, key = vendor["status"], vendor["candidate_security_key"]
            source_hashes = vendor["source_hashes"]
        reference = (domain, source_id) if source_id is not None else None
        if key is not None:
            require(all(key.get(k) for k in ("namespace", "provider_instrument_id",
                                             "exchange_mic", "security_type")),
                    "Incomplete permanent provider identity key")
            provider_key = (key["namespace"], key["provider_instrument_id"])
            key_owners[provider_key].add(reference)
        else:
            provider_key = None
        rows.append({
            "source_position": pos, "original_cusip": orig["cusip"],
            "source_identity_namespace": domain, "original_source_identifier": source_id,
            "source_spy_weight": orig["weight"], "individual_vendor_status": status,
            "candidate_security_key": key, "source_hashes": source_hashes,
            "_provider_key": provider_key, "_source_reference": reference,
        })
    collisions = {key: owners for key, owners in key_owners.items()
                  if len(owners) > 1}
    weight_by_status = Counter()
    count_by_status = Counter()
    for row in rows:
        if row["_provider_key"] in collisions:
            row["cross_source_status"] = "shared-provider-key-quarantined"
            row["candidate_security_key"] = None
        elif row["candidate_security_key"] is not None:
            row["cross_source_status"] = "retrospective-cross-source-candidate"
        else:
            row["cross_source_status"] = "no-admissible-cross-source-candidate"
        status = row["cross_source_status"]
        count_by_status[status] += 1
        weight_by_status[status] += row["source_spy_weight"]
        del row["_provider_key"]
        del row["_source_reference"]
        row["historical_public_availability_certified"] = False
        row["historical_price_vintage_verified"] = False
        row["full_engine_eligible"] = False
    require(len(rows) == len(positions) and
            close(sum(weight_by_status.values()), original["positive_spy_weight"]),
            "Cross-source reconciliation lost original SEC source weight")
    return {
        **template(original, foreign),
        "schema": "historical-cross-namespace-private-reconciliation-v1",
        "cusip_vendor_manifest_sha256": cusip_report["vendor_manifest_sha256"],
        "foreign_isin_vendor_manifest_sha256": isin_report["vendor_manifest_sha256"],
        "cusip_vendor_rows": cusip_report["vendor_rows"],
        "foreign_isin_vendor_rows": isin_report["vendor_rows"],
        "source_position_count_by_status": dict(sorted(count_by_status.items())),
        "source_spy_weight_by_status": dict(sorted(weight_by_status.items())),
        "distinct_permanent_key_collisions": len(collisions),
        "collision_references": [
            {"namespace": key[0], "provider_instrument_id": key[1],
             "original_identifiers": sorted([
                 {"namespace": item[0], "identifier": item[1]}
                 for item in owners
             ], key=lambda item: (item["namespace"], item["identifier"]))}
            for key, owners in sorted(collisions.items())
        ],
        "positions": rows,
        "vendor_rows_received": cusip_report["vendor_rows"] + isin_report["vendor_rows"],
        "cross_namespace_identity_certified": False,
        "historical_prices_certified": False,
        "full_engine_eligible_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=TEMPLATE)
    parser.add_argument("--cusip-evidence-dir", help="Local licensed CUSIP evidence")
    parser.add_argument("--isin-evidence-dir", help="Local licensed foreign-ISIN evidence")
    parser.add_argument("--private-report", default=REPORT)
    args = parser.parse_args(argv)
    require(bool(args.cusip_evidence_dir) == bool(args.isin_evidence_dir),
            "Both local evidence directories must be supplied for cross-source matching")
    original = build_original(ROOT)
    foreign = build_foreign_requests(audit_alternates(ROOT))
    pub = template(original, foreign)
    target = Path(args.template)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(pub, indent=2) + "\n", encoding="utf-8")
    if args.cusip_evidence_dir:
        c_rows, c_proof, c_manifest = read_cusip_evidence(
            args.cusip_evidence_dir, original)
        f_rows, f_proof, f_manifest = read_foreign_evidence(
            args.isin_evidence_dir, foreign)
        cusip_report = reconcile_cusip(original, c_rows, c_proof, c_manifest)
        isin_report = reconcile_foreign(foreign, f_rows, f_proof, f_manifest)
        combined = combine(original, foreign, cusip_report, isin_report)
        private = Path(args.private_report)
        private.parent.mkdir(parents=True, exist_ok=True)
        private.write_text(json.dumps(combined, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "distinct_permanent_key_collisions": combined["distinct_permanent_key_collisions"],
            "source_position_count_by_status": combined["source_position_count_by_status"],
            "full_engine_eligible_cuts": 0,
        }, sort_keys=True))
    else:
        print(json.dumps({
            "positive_spy_positions": pub["positive_spy_positions"],
            "valid_cusip_positions": pub["valid_cusip_positions"],
            "foreign_isin_positions": pub["foreign_isin_positions"],
            "vendor_rows_received": 0, "full_engine_eligible_cuts": 0,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
