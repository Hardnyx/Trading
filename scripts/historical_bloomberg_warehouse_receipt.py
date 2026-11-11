"""Reopen locally archived Bloomberg-v4 PIT source bytes for an SEC stage audit.

Offline research-only receipt. The v4 SQLite store and raw originals stay local;
this verifies local integrity and recorded value/time pointers, not Bloomberg's
independent publication time, security-master truth, or full replay eligibility.
"""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

if __package__:
    from .historical_bloomberg_asof_replay import verify_asof_selection
else:
    from historical_bloomberg_asof_replay import verify_asof_selection

MAX_RAW_BYTES = 50_000_000
HASH = re.compile(r"[0-9a-f]{64}\Z")
LOCATOR = re.compile(r"/records/(0|[1-9][0-9]*)/value\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def instant(value):
    require(isinstance(value, str), "Missing original timestamp")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(at.utcoffset() is not None, "Unzoned original timestamp")
        return at
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid original timestamp") from error


def pointer(document, path):
    """Read an RFC6901 pointer; never interpret pointers as filesystem paths."""
    require(isinstance(path, str) and path.startswith("/") and len(path) <= 500,
            "Invalid original JSON pointer")
    node = document
    for raw_part in path[1:].split("/"):
        require("~" not in raw_part.replace("~0", "").replace("~1", ""),
                "Invalid original JSON pointer escape")
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            require(re.fullmatch(r"0|[1-9][0-9]*", part) is not None,
                    "Invalid original JSON array index")
            index = int(part)
            require(index < len(node), "Original JSON array index outside document")
            node = node[index]
        elif isinstance(node, dict):
            require(part in node, "Original JSON pointer not found")
            node = node[part]
        else:
            raise ValueError("Original JSON pointer encounters scalar")
    return node


def verify_stage(stage, warehouse_root):
    """Verify *all* returned stage records against v4's immutable local receipts.

    The source store may be retrospective: success never independently proves
    that a Bloomberg response existed at its asserted historical timestamp.
    This does not reproduce the collector's as_of selection or price calendar.
    """
    require(isinstance(stage, dict) and stage.get("schema") == "bloomberg-trading-stage-v1",
            "Not a Bloomberg v4 stage")
    rows = stage.get("normalized_asof_records")
    require(isinstance(rows, list) and len(rows) <= 1_000_000,
            "Missing or oversized stage records")
    cited = stage.get("source_hashes")
    require(isinstance(cited, list) and
            all(isinstance(item, str) and HASH.fullmatch(item) for item in cited),
            "Malformed Bloomberg stage source citations")
    root = Path(warehouse_root).resolve(strict=True)
    require(root.is_dir(), "Bloomberg warehouse directory is missing")
    database = root / "warehouse.sqlite3"
    require(database.is_file(), "Bloomberg v4 warehouse database is missing")
    # A read-only SQLite connection never creates or migrates the warehouse.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    sources = {}
    originals = set()
    observed = Counter()
    try:
        connection.execute("BEGIN")

        def reopen(raw_hash):
            require(isinstance(raw_hash, str) and HASH.fullmatch(raw_hash) is not None,
                    "Invalid source content digest")
            if raw_hash in sources:
                return sources[raw_hash]
            found = connection.execute(
                "SELECT path, retrieved_at, synthetic FROM raw_sources WHERE raw_hash=?",
                (raw_hash,)).fetchone()
            require(found is not None and found["synthetic"] == 0,
                    "Original Bloomberg raw source missing or synthetic")
            expected = root / "raw" / (raw_hash + ".json")
            require(expected.is_file() and expected.resolve() == Path(found["path"]).resolve(),
                    "Warehouse source path differs from its archived content address")
            require(expected.stat().st_size <= MAX_RAW_BYTES,
                    "Archived Bloomberg raw source exceeds verification limit")
            raw = expected.read_bytes()
            require(sha256(raw) == raw_hash, "Archived Bloomberg raw source SHA256 mismatch")
            document = json.loads(raw)
            sources[raw_hash] = (document, found["retrieved_at"])
            return sources[raw_hash]

        for row in rows:
            require(isinstance(row, dict) and row.get("quality_class") == "VERIFIED_PIT" and
                    row.get("synthetic") is False,
                    "Stage contains an unverified or synthetic source record")
            record_id = sha256(canonical(row))
            require(observed[record_id] == 0, "Repeated stage record")
            observed[record_id] += 1
            stored = connection.execute(
                "SELECT record_json, raw_hash, quality_class, synthetic, retrieved_at "
                "FROM pit_records WHERE record_id=?", (record_id,)).fetchone()
            require(stored is not None and
                    canonical(json.loads(stored["record_json"])) == canonical(row) and
                    stored["raw_hash"] == row.get("raw_hash") and
                    stored["quality_class"] == row["quality_class"] and
                    stored["synthetic"] == 0 and
                    instant(stored["retrieved_at"]) == instant(row.get("retrieved_at")),
                    "Stage record is not an unchanged v4 warehouse observation")
            document, retrieval = reopen(row["raw_hash"])
            require(isinstance(document, dict) and
                    document.get("schema") == "pit-source-document-v1" and
                    document.get("synthetic") is False and
                    instant(document.get("retrieved_at")) == instant(row["retrieved_at"]) == instant(retrieval),
                    "Archived PIT interchange document or retrieval clock changed")
            proof = row.get("evidence")
            require(isinstance(proof, dict), "Missing bound original evidence")
            locator = proof.get("value_locator")
            require(isinstance(locator, str) and LOCATOR.fullmatch(locator) is not None and
                    canonical(pointer(document, locator)) == canonical(row.get("value")),
                    "PIT import value locator differs from archived interchange")
            records = document.get("records")
            index = int(LOCATOR.fullmatch(locator).group(1))
            require(isinstance(records, list) and index < len(records) and
                    isinstance(records[index], dict), "Original PIT import row is missing")
            exported = records[index]
            for field in ("dataset_id", "security_id", "field", "value", "observation_date",
                          "published_at", "first_available_at", "source_document_id", "vintage_id",
                          "valid_from", "valid_until", "unit", "currency", "adjusted_basis"):
                # The interchange may omit fields having dataclass defaults.
                if field in exported:
                    require(canonical(exported[field]) == canonical(row.get(field)),
                            "Archived interchange field differs from selected warehouse record")
            require(all(isinstance(proof.get(k), str) and proof[k] for k in (
                    "original_document_sha256", "original_value_pointer",
                    "original_publication_pointer", "original_availability_pointer")),
                    "Original provider document evidence pointers missing")
            original_hash = proof["original_document_sha256"]
            original, _ = reopen(original_hash)
            require(canonical(pointer(original, proof["original_value_pointer"])) ==
                    canonical(row.get("value")), "Original provider value differs from imported value")
            require(instant(pointer(original, proof["original_publication_pointer"])) ==
                    instant(row.get("published_at")) and
                    instant(pointer(original, proof["original_availability_pointer"])) ==
                    instant(row.get("first_available_at")),
                    "Original provider publication or availability differs from imported claim")
            originals.add(original_hash)
        require(set(cited).issubset({item["raw_hash"] for item in rows}),
                "Stage source citations are not supported by its selected records")
        asof_receipt = verify_asof_selection(connection, stage)
    except (sqlite3.Error, OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid or unreadable Bloomberg v4 warehouse evidence") from error
    finally:
        connection.close()
    return {
        "warehouse_stage_records_verified": len(rows),
        "warehouse_source_files_reopened": len(sources),
        "warehouse_original_documents_reopened": len(originals),
        "unchanged_stage_records_bound_to_local_warehouse": True,
        "original_value_and_timestamp_pointers_rechecked": True,
        **asof_receipt,
        "original_vendor_publication_independently_authenticated": False,
        "live_vendor_entitlement_or_execution_verified": False,
        "full_engine_eligible_cuts_added": 0,
    }
