"""Validate dated vendor security identifiers against archived SEC CUSIP requests.

The input is a local, hashed export. Matching an identifier does not establish
that its metadata was available at the investment date, verify execution
prices, or make an historical engine cut admissible. No private vendor export
is committed or uploaded by this script.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

if __package__:
    from .historical_identity_requests import build_requests
    from .historical_sources import canonical, iso
else:
    from historical_identity_requests import build_requests
    from historical_sources import canonical, iso

SCHEMA = "historical-vendor-identity-sources-v1"
COLUMNS = (
    "cusip", "provider_instrument_id", "id_namespace", "security_type",
    "currency", "exchange_mic", "valid_from", "valid_to", "record_as_of",
)
TEMPLATE_COLUMNS = (
    "source_position", "cusip", "original_ticker_observation",
    "original_spy_name", "weight", "cut",
)
ALLOWED_TYPES = {"COMMON_STOCK", "REIT", "ADR", "PREFERRED_STOCK"}
INVALID_NAMESPACES = {"TICKER", "SYMBOL", "NAME", "CUSIP", "ISIN"}
MAX_SOURCE_BYTES = 20_000_000


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()



def valid_cusip(cusip):
    """Check ANSI X9.6 body alphabet and the ninth Mod-10 check digit."""
    if not isinstance(cusip, str) or not re.fullmatch(r"[A-Z0-9*@#]{8}[0-9]", cusip):
        return False
    special = {"*": 36, "@": 37, "#": 38}
    total = 0
    for position, char in enumerate(cusip[:8]):
        value = int(char) if char.isdigit() else (
            ord(char) - 55 if "A" <= char <= "Z" else special[char])
        weighted = value * (2 if position % 2 else 1)
        total += weighted // 10 + weighted % 10
    # SEC may publish the all-zero placeholder; it is not a usable security ID.
    return cusip != "000000000" and (10 - total % 10) % 10 == int(cusip[-1])


def request_hash(requests):
    return sha256(canonical({"cut": requests["cut"], "requests": requests["requests"]}))


def template_csv(requests):
    """Create an extraction request, never an asserted provider crosswalk."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=TEMPLATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in requests["requests"]:
        writer.writerow({
            "source_position": row["source_position"], "cusip": row["cusip"],
            "original_ticker_observation": row["original_ticker_observation"] or "",
            "original_spy_name": row["original_spy_name"],
            "weight": row["weight"], "cut": requests["cut"],
        })
    return buffer.getvalue()


def parse_export(raw, snapshot_as_of, *, identifier_column="cusip", validator=valid_cusip):
    """Validate the unchanged dated vendor metadata for CUSIP or original ISIN."""
    require(identifier_column in ("cusip", "original_isin"), "Unsupported identifier column")
    require(len(raw) <= MAX_SOURCE_BYTES, "Source export exceeds 20 MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Export must be UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(content, newline=""))
    fields = reader.fieldnames
    require(fields is not None and len(fields) == len(set(fields)) and
            set(fields) == set(identifier_column if c == "cusip" else c for c in COLUMNS),
            "Vendor export columns changed")
    rows = []
    for number, row in enumerate(reader, start=2):
        require(None not in row and all(v is not None for v in row.values()),
                f"Malformed vendor CSV at line {number}")
        record = {k: v.strip() for k, v in row.items()}
        identifier = record[identifier_column]
        require(validator(identifier),
                f"Invalid {identifier_column.upper()} format or check digit at line {number}")
        require(record["record_as_of"] == snapshot_as_of and
                iso(record["record_as_of"]) == snapshot_as_of,
                f"Historical snapshot mismatch at line {number}")
        valid_from = record["valid_from"]
        valid_to = record["valid_to"]
        if valid_from:
            iso(valid_from)
        if valid_to:
            iso(valid_to)
        require(not valid_from or not valid_to or valid_from < valid_to,
                f"Invalid identity interval at line {number}")
        native_id = record["provider_instrument_id"]
        namespace = record["id_namespace"]
        require(bool(native_id) == bool(namespace),
                f"Partial vendor instrument key at line {number}")
        if native_id:
            require(bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{2,100}", native_id)) and
                    bool(re.fullmatch(r"[A-Z][A-Z0-9_-]{1,30}", namespace)) and
                    namespace not in INVALID_NAMESPACES,
                    f"Unstable or invalid vendor instrument key at line {number}")
        if record["currency"]:
            require(bool(re.fullmatch(r"[A-Z]{3}", record["currency"])),
                    f"Invalid currency at line {number}")
        if record["exchange_mic"]:
            require(bool(re.fullmatch(r"[A-Z0-9]{4}", record["exchange_mic"])),
                    f"Invalid exchange MIC at line {number}")
        if record["security_type"]:
            require(bool(re.fullmatch(r"[A-Z_]{2,30}", record["security_type"])),
                    f"Invalid security type at line {number}")
        rows.append(record)
    require(len(rows) <= 50000, "Source export has too many rows")
    return rows


def local_file(root, relative):
    root = Path(root).resolve()
    require(isinstance(relative, str) and not Path(relative).is_absolute(),
            "Absolute vendor archive path rejected")
    target = (root / relative).resolve()
    require(target.is_relative_to(root) and target.is_file(),
            "Vendor evidence path escaped directory or is missing")
    return target


def read_evidence(directory, requests, *, schema=SCHEMA, request_sha256=None,
                  parser=parse_export):
    """Check exact local bytes and dates, preserving retrieval vs. as-of clocks."""
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_bytes())
    expected_hash = request_hash(requests) if request_sha256 is None else request_sha256
    require(re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None,
            "Invalid request SHA256")
    require(manifest.get("protocol") == schema and
            manifest.get("cut") == requests["cut"] and
            manifest.get("request_sha256") == expected_hash,
            "Identity evidence manifest does not match frozen SEC requests")
    sources = manifest.get("exports")
    require(isinstance(sources, list) and sources, "No vendor exports supplied")
    require(len(sources) <= 25, "Too many vendor exports")
    records = []
    provenance = []
    seen_paths = set()
    for source in sources:
        require(isinstance(source, dict), "Invalid vendor source pointer")
        path = source.get("path")
        require(isinstance(path, str) and path not in seen_paths,
                "Duplicate vendor source path")
        seen_paths.add(path)
        raw = local_file(root, path).read_bytes()
        require(re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")) is not None and
                sha256(raw) == source["sha256"], "Vendor source SHA256 mismatch")
        provider = source.get("provider")
        require(isinstance(provider, str) and bool(provider.strip()) and
                bool(source.get("source_reference")), "Vendor identity/provenance missing")
        snapshot = iso(source.get("snapshot_as_of"))
        require(snapshot <= requests["cut"],
                "Vendor snapshot is later than the historical decision")
        retrieved = source.get("retrieved_at")
        try:
            instant = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
            require(instant.utcoffset() is not None, "Retrieval clock needs timezone")
            instant = instant.astimezone(timezone.utc)
        except (AttributeError, ValueError, TypeError) as error:
            raise ValueError("Invalid vendor retrieval timestamp") from error
        require(instant.date() >= date.fromisoformat(snapshot),
                "Vendor retrieval time precedes its claimed snapshot")
        basis = source.get("temporal_basis")
        require(basis in ("retrospective_asof_export", "contemporaneous_archive"),
                "Vendor snapshot temporal basis must be declared")
        # A self-described contemporaneous archive is not independently attested.
        # It remains research-only pending an external provenance audit.
        parsed = parser(raw, snapshot)
        receipt = {
            "path": path, "sha256": source["sha256"], "provider": provider,
            "source_reference": source["source_reference"],
            "snapshot_as_of": snapshot, "retrieved_at": instant.isoformat(),
            "temporal_basis": basis, "rows": len(parsed),
            "historical_public_availability_certified": False,
        }
        provenance.append(receipt)
        for row in parsed:
            records.append({**row, "_source_sha256": source["sha256"],
                            "_provider": provider})
    return records, provenance, sha256((root / "manifest.json").read_bytes())


def row_state(row, cut):
    if not row["provider_instrument_id"]:
        return "missing-permanent-id"
    if row["currency"] != "USD":
        return "non-usd-security"
    if row["security_type"] not in ALLOWED_TYPES:
        return "ineligible-security-type"
    if not row["exchange_mic"]:
        return "missing-exchange"
    if not row["valid_from"] or not row["valid_to"]:
        return "incomplete-identity-interval"
    if not row["valid_from"] <= cut < row["valid_to"]:
        return "not-effective-at-cut"
    return "retrospective-identity-candidate"


def reconcile(requests, rows, provenance, manifest_hash):
    """One-to-one CUSIP and security key constraints at the frozen cut."""
    cut = requests["cut"]
    original = requests["requests"]
    require(len({r["source_position"] for r in original}) == len(original),
            "Repeated SEC source position")
    mapping = defaultdict(list)
    for row in rows:
        mapping[row["cusip"]].append(row)
    candidates = {}
    excluded = Counter()
    for cusip, evidence in mapping.items():
        active = [row for row in evidence if row_state(row, cut) ==
                  "retrospective-identity-candidate"]
        for row in evidence:
            state = row_state(row, cut)
            if state != "retrospective-identity-candidate":
                excluded[state] += 1
        keys = {(r["id_namespace"], r["provider_instrument_id"],
                 r["exchange_mic"], r["security_type"]) for r in active}
        candidates[cusip] = (keys, active)
    reverse = defaultdict(set)
    for cusip, (keys, _) in candidates.items():
        for namespace, native, _, _ in keys:
            reverse[(namespace, native)].add(cusip)
    bindings = []
    weights = Counter()
    counts = Counter()
    for original_row in original:
        cusip = original_row["cusip"]
        keys, evidence = candidates.get(cusip, (set(), []))
        if not mapping[cusip]:
            status = "no-provider-evidence"
        elif not keys:
            status = "no-temporally-admissible-identity"
        elif len(keys) > 1:
            status = "conflicting-provider-identities"
        elif any(len(reverse[(namespace, native)]) > 1 for namespace, native, _, _ in keys):
            status = "provider-key-shared-by-multiple-cusips"
        else:
            status = "retrospective-identity-candidate"
        counts[status] += 1
        weights[status] += original_row["weight"]
        selected = next(iter(keys)) if status == "retrospective-identity-candidate" else None
        matched = [row for row in evidence if
                   (row["id_namespace"], row["provider_instrument_id"],
                    row["exchange_mic"], row["security_type"]) == selected] if selected else []
        bindings.append({
            "source_position": original_row["source_position"], "cusip": cusip,
            "weight": original_row["weight"],
            "original_ticker_observation": original_row["original_ticker_observation"],
            "status": status,
            "candidate_security_key": {
                "namespace": selected[0], "provider_instrument_id": selected[1],
                "exchange_mic": selected[2], "security_type": selected[3],
            } if selected else None,
            "source_hashes": sorted({r["_source_sha256"] for r in matched}),
            "historical_availability_certified": False,
            "price_history_verified": False, "corporate_actions_verified": False,
            "production_eligible": False,
        })
    return {
        "protocol": "historical-vendor-identity-reconciliation-v1",
        "cut": cut, "request_sha256": request_hash(requests),
        "vendor_manifest_sha256": manifest_hash,
        "sources": provenance, "vendor_rows": len(rows),
        "excluded_row_reasons": dict(sorted(excluded.items())),
        "counts": dict(sorted(counts.items())),
        "positive_weight_by_status": {k: round(v, 12) for k, v in sorted(weights.items())},
        "positions": bindings, "vendor_key_matches_are_research_only": True,
        "historical_public_availability_certified": False,
        "historical_prices_and_actions_certified": False,
        "full_engine_replay_ready": False, "production_eligible": False,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="Write SEC-derived collection request CSV")
    parser.add_argument("--evidence-dir", help="Local vendor manifest and hashed CSV exports")
    parser.add_argument("--report", default="out/historical-vendor-identity-reconciliation-v1.json")
    args = parser.parse_args(argv)
    if not args.template and not args.evidence_dir:
        parser.error("Supply --template and/or --evidence-dir")
    requests = build_requests()
    if args.template:
        target = Path(args.template)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template_csv(requests), encoding="utf-8")
    if args.evidence_dir:
        rows, provenance, manifest_hash = read_evidence(args.evidence_dir, requests)
        report = reconcile(requests, rows, provenance, manifest_hash)
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"cut": report["cut"], "counts": report["counts"],
                          "full_engine_replay_ready": False}, sort_keys=True))
    else:
        print(json.dumps({"cut": requests["cut"], "requests": len(requests["requests"]),
                          "vendor_sources_read": 0, "full_engine_replay_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
