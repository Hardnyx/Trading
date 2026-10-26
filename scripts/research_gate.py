"""Research-only time-of-knowledge gate for asset, event and model inputs.

A historical price is NOT the same as a historical information vintage.
Never infer what investors knew at a past cut from a current SEC/FRED/BLS API
response. For prospective tests the complete source snapshot must have been
collected before issuance; for historical replay use original dated archives.
"""
from __future__ import annotations
from datetime import datetime, date, timezone
from pathlib import Path
import json
import math
import hashlib


def instant(value):
    if not isinstance(value, str):
        raise ValueError("A timestamp with UTC timezone is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("Naive timestamp forbidden")
    return parsed.astimezone(timezone.utc)


def known_day(value, cutoff):
    if not value:
        return False
    try:
        return date.fromisoformat(str(value)[:10]) <= date.fromisoformat(cutoff)
    except ValueError:
        return False


def check_archive(archive, issued_at):
    """Returns an explicit eligibility decision; does not alter archived facts.

    Historical_request archives made today are NEVER certified vintages.
    """
    issues = []
    issued = instant(issued_at)
    observed = instant(archive["collected_at"])
    if observed > issued:
        issues.append("snapshot_collected_after_forecast")
    if archive.get("collection_mode") != "current":
        issues.append("replayed_request_not_original_vintage")
    if not known_day(archive.get("price_as_of"), issued.date().isoformat()):
        issues.append("price_cut_after_forecast")
    symbols = set()
    for asset in archive.get("assets", []):
        sym = asset.get("symbol")
        if not sym or sym in symbols:
            issues.append("duplicate_or_missing_symbol")
        symbols.add(sym)
        if not known_day(asset.get("price_date"), issued.date().isoformat()):
            issues.append(f"unavailable_price:{sym}")
        for name, fact in (asset.get("financials") or {}).items():
            if name == "history" or not isinstance(fact, dict):
                continue
            filed = fact.get("filed")
            if filed and not known_day(filed, issued.date().isoformat()):
                issues.append(f"future_filing:{sym}:{name}")
        estimates = asset.get("analyst_estimates") or {}
        if estimates and "observed_at" in estimates:
            try:
                if instant(estimates["observed_at"]) > issued:
                    issues.append(f"future_consensus:{sym}")
            except ValueError:
                issues.append(f"invalid_consensus_timestamp:{sym}")
        profile = asset.get("bond_profile") or {}
        if profile.get("observed_at"):
            try:
                if instant(profile["observed_at"]) > issued:
                    issues.append(f"future_bond_profile:{sym}")
            except ValueError:
                issues.append(f"invalid_bond_profile_timestamp:{sym}")
    for row in archive.get("macro", []):
        if row.get("observed_at"):
            try:
                if instant(row["observed_at"]) > issued:
                    issues.append(f"future_macro_download:{row.get('id')}")
            except ValueError:
                issues.append(f"invalid_macro_download:{row.get('id')}")
        if not known_day(row.get("date"), issued.date().isoformat()):
            issues.append(f"future_macro_period:{row.get('id')}")
    return {
        "eligible": len(issues) == 0,
        "issued_at": issued_at,
        "collected_at": archive["collected_at"],
        "price_cut": archive.get("price_as_of"),
        "collection_mode": archive.get("collection_mode"),
        "issues": sorted(set(issues)),
        "source_sha256": archive.get("source_snapshot_sha256"),
        "n_assets": len(symbols),
        "method": "original_archive_known_before_issuance_gate_v1",
        "warning": "A historical price series does not establish original accounting/macro vintages or delisted-universe completeness.",
    }


def audit_archives(archive_files, issued_at=None):
    rows = []
    for path in sorted(archive_files):
        entry = json.loads(Path(path).read_text(encoding="utf-8"))
        cut = issued_at or entry["collected_at"]
        result = check_archive(entry, cut)
        result["file"] = str(path)
        rows.append(result)
    return {
        "original_archives": len(rows),
        "eligible_for_selected_issuance": sum(r["eligible"] for r in rows),
        "rejected": sum(not r["eligible"] for r in rows),
        "results": rows,
        "note": "Eligibility is for the SPECIFIED issuance, not certification of fully reconstructed historical data.",
    }


def validate_event(event, forecast_issued_at=None):
    """An event registry cannot assign a retroactive forecast feature."""
    required = ("event_id", "published_at_utc", "known_at_utc", "source_url", "type")
    for field in required:
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError("Missing event field: " + field)
    published = instant(event["published_at_utc"])
    known = instant(event["known_at_utc"])
    if known < published:
        raise ValueError("News cannot be known before verified publication")
    if not event["source_url"].startswith(("https://", "http://")):
        raise ValueError("Event requires an actual source link")
    actual = event.get("actual")
    consensus = event.get("consensus")
    if actual is not None or consensus is not None:
        if not all(isinstance(v, (int, float)) and math.isfinite(v)
                   for v in (actual, consensus)):
            raise ValueError("Surprise requires numeric actual and pre-release consensus")
        if not event.get("consensus_known_at_utc"):
            raise ValueError("Consensus must carry a dated vintage")
        if instant(event["consensus_known_at_utc"]) >= published:
            raise ValueError("Post-release consensus is not an ex-ante expectation")
    usable = forecast_issued_at is None or known <= instant(forecast_issued_at)
    return {
        "event_id": event["event_id"], "published_at_utc": event["published_at_utc"],
        "known_at_utc": event["known_at_utc"],
        "event_known_before_forecast": usable,
        "surprise": actual - consensus if actual is not None else None,
        "attribution": "verified_release_not_causal_identification",
    }


def event_features(events, issued_at, symbols=None):
    """Only previously published events, never future news, become regressors."""
    names = set(symbols or [])
    old = instant(issued_at)
    out = []
    for e in events:
        v = validate_event(e, issued_at)
        affected = set(e.get("asset_ids") or [])
        if not v["event_known_before_forecast"]:
            continue
        if names and affected and not (names & affected):
            continue
        if instant(e["known_at_utc"]) > old:
            continue
        out.append(v)
    return sorted(out, key=lambda v: v["known_at_utc"])


def maturation_status(issued_at, target_date, as_of, *, original_archive=True):
    """Daily archive history cannot mature a 12-month prediction in a day."""
    issued = instant(issued_at)
    if not original_archive:
        return "unverified_origin"
    if date.fromisoformat(target_date) > date.fromisoformat(as_of):
        return "immature"
    if issued.date().isoformat() > target_date:
        return "invalid_target"
    return "eligible_for_outcome_matching"
