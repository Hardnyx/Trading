"""Recompute the Bloomberg v4 as-of row selection from raw warehouse record JSON.

Research-only complement to original-byte verification. This deliberately does
not import the collector or trust its indexed availability fields. A perfect
selection match does not authenticate publication times or confer engine rights.
"""
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import re

MAX_WAREHOUSE_RECORDS = 5_000_000
MAX_SELECTED_RECORDS = 1_000_000
INTERVAL_DATASETS = frozenset((
    "identifier_history", "index_membership_history", "security_master",
))
KEY_FIELDS = (
    "dataset_id", "security_id", "field", "observation_date", "period_end",
    "target_period", "member_id", "valid_from",
)
SEMANTIC_FIELDS = ("value", "unit", "currency", "adjusted_basis")
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def utc_instant(value):
    require(isinstance(value, str), "Missing as-of timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None, "Naive as-of timestamp")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid or naive as-of timestamp") from exc


def select_status(row, cutoff):
    """Use v4 Warehouse.as_of's eligibility rules on serialized original rows."""
    if row.get("quality_class") != "VERIFIED_PIT" or row.get("synthetic") is not False:
        return "ineligible-quality-or-synthetic"
    if row.get("value") is None:
        return "missing-value"
    available = row.get("first_available_at")
    if not available or utc_instant(available) > cutoff:
        return "missing-or-future-availability"
    for field in ("observation_date", "period_end"):
        value = row.get(field)
        if value is not None:
            require(isinstance(value, str) and
                    date.fromisoformat(value).isoformat() == value,
                    "Malformed warehouse observation date")
            if value > cutoff.date().isoformat():
                return "future-observation"
    effective = row.get("effective_at")
    if effective and utc_instant(effective) > cutoff:
        return "future-effective-event"
    if row.get("dataset_id") in INTERVAL_DATASETS:
        for field in ("valid_from", "valid_until"):
            value = row.get(field)
            if value is not None:
                require(isinstance(value, str) and
                        date.fromisoformat(value).isoformat() == value,
                        "Malformed warehouse identity interval")
        if row.get("valid_from") and row["valid_from"] > cutoff.date().isoformat():
            return "future-identity"
        if row.get("valid_until") and row["valid_until"] <= cutoff.date().isoformat():
            return "expired-identity"
    return None


def verify_asof_selection(connection, stage):
    """Fail if the stage omitted/replaced any row from the full v4 as-of set.

    Uses row JSON from every warehouse record, independent of the collector's
    SQLite as-of index, WHERE clause and stage construction. The v4 revision
    ordering rules are reproduced explicitly; source bytes are verified by a
    separate receipt auditor. This never authorizes replay of historical P&L.
    """
    require(isinstance(stage, dict) and stage.get("schema") == "bloomberg-trading-stage-v1",
            "Not a Bloomberg v4 stage")
    cutoff = utc_instant(stage.get("cutoff"))
    claimed = stage.get("normalized_asof_records")
    require(isinstance(claimed, list) and len(claimed) <= MAX_SELECTED_RECORDS,
            "Invalid Bloomberg stage record selection")
    selected = {}
    excluded = Counter()
    scanned = 0
    # Deliberately do not filter on indexed first_available_at, dataset or quality:
    # stale/mutated index columns must not hide an eligible serialized record.
    for stored in connection.execute("SELECT record_id, record_json FROM pit_records ORDER BY record_id"):
        scanned += 1
        require(scanned <= MAX_WAREHOUSE_RECORDS, "Excessive Bloomberg v4 warehouse records")
        try:
            row = json.loads(stored["record_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("Malformed Bloomberg v4 warehouse record JSON") from exc
        require(isinstance(row, dict) and isinstance(stored["record_id"], str) and
                HASH_RE.fullmatch(stored["record_id"]) and
                hashlib.sha256(canonical(row)).hexdigest() == stored["record_id"],
                "Unbound Bloomberg v4 record digest")
        status = select_status(row, cutoff)
        if status is not None:
            excluded[status] += 1
            continue
        key = tuple(row.get(k) for k in KEY_FIELDS)
        # Key JSON fields are intended to be scalars, never arrays or objects.
        require(all(isinstance(k, (str, int, float, type(None))) for k in key),
                "Non-scalar Bloomberg logical observation identity")
        order = (utc_instant(row["first_available_at"]),
                 row.get("vintage_id") or "", row.get("revision_id") or "")
        require(isinstance(order[1], str) and isinstance(order[2], str),
                "Malformed Bloomberg revision ordering fields")
        prior = selected.get(key)
        if prior is not None and prior[0] == order:
            require(all(row.get(f) == prior[1].get(f) for f in SEMANTIC_FIELDS),
                    "Conflicting Bloomberg values at identical as-of version")
        if prior is None or order > prior[0]:
            selected[key] = (order, row)
        require(len(selected) <= MAX_SELECTED_RECORDS,
                "Excessive Bloomberg selected logical observations")
    expected_rows = sorted((v[1] for v in selected.values()), key=canonical)
    require(canonical(expected_rows) == canonical(sorted(claimed, key=canonical)),
            "Bloomberg stage selection differs from independent warehouse as-of replay")
    return {
        "warehouse_asof_rows_independently_reselected": len(expected_rows),
        "warehouse_records_examined_for_asof": scanned,
        "warehouse_asof_excluded_record_counts": dict(sorted(excluded.items())),
        "stage_asof_selection_independently_recomputed": True,
        "asof_selection_source": "all-warehouse-record-json-not-sql-index",
        "vendor_publication_time_independently_authenticated": False,
        "historical_engine_replay_authorized": False,
    }
