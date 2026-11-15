"""Admission audit of monthly full-engine captures for the v3 protocol.

Stage 1, at the origin: the capture is complete, every recorded hash is
reproduced from the archived bytes, and an RFC 3161 timestamp signed no later
than the next possible market open covers the origin record and its inputs.
Stage 2, at the 21-session horizon: every held instrument has an issuer
distribution history observed and stamped after the horizon end, so the cash
flows of the hypothetical account can be reconstructed. This audit reads no
returns and scores nothing.
"""
import argparse
import gzip
import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = "data/confirmatory/full-engine-v2"
REQUIRED_EVIDENCE = ("market_sha256", "inputs_sha256", "model_sha256", "policy_sha256",
                     "risk_calibration_sha256", "forecast_sha256")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def earliest_open_utc(cut):
    """Earliest possible next-session open: next weekday 13:30 UTC (09:30 EDT)."""
    day = date.fromisoformat(cut) + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc)


def token_times(root=ROOT):
    """Signed time per manifest (earliest valid token) and the hashes it covers."""
    try:
        from .timestamp_evidence import AUTHORITIES, verify_token
    except ImportError:
        from timestamp_evidence import AUTHORITIES, verify_token
    out = []
    for manifest in sorted((root / "data/timestamps").glob("*.manifest.json")):
        stem = manifest.name[:-len(".manifest.json")]
        times = []
        for authority in AUTHORITIES:
            token = manifest.parent / f"{stem}.{authority}.tsr"
            if token.exists() and verify_token(manifest, token, authority, root):
                text = subprocess.run(["openssl", "ts", "-reply", "-in", str(token), "-text"],
                                      capture_output=True, text=True, check=True).stdout
                stamp = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Time stamp:"))
                times.append(datetime.strptime(stamp.replace(" GMT", ""), "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc))
        if len(times) >= 2:
            files = {r["path"]: r["sha256"] for r in json.loads(manifest.read_text(encoding="utf-8"))["files"]}
            out.append((sorted(times)[1], files))  # second-earliest: at least two authorities agree it existed
    return out


def first_stamp(path, digest, stamps):
    times = [t for t, files in stamps if files.get(path) == digest]
    return min(times) if times else None


def admit_origin(root, origin_path, stamps):
    reasons = []
    raw = (root / origin_path).read_bytes()
    capture = json.loads(gzip.decompress(raw))
    cut = capture.get("cut")
    evidence = capture.get("evidence", {})
    if any(not evidence.get(k) for k in REQUIRED_EVIDENCE):
        reasons.append("missing evidence hashes")
    proposal = json.loads(capture.get("proposal_json", "null") or "null")
    if not (isinstance(proposal, dict) and proposal.get("positions") is not None and proposal.get("trade_plan")):
        reasons.append("decision or orders missing")
    if capture.get("proposal_json") and sha(capture["proposal_json"].encode()) != evidence.get("forecast_sha256"):
        reasons.append("forecast hash not reproduced")
    if capture.get("policy_json") and sha(capture["policy_json"].encode()) != evidence.get("policy_sha256"):
        reasons.append("policy hash not reproduced")
    if capture.get("source_hashes_json") and sha(capture["source_hashes_json"].encode()) != evidence.get("model_sha256"):
        reasons.append("model hash not reproduced")
    archives = {}
    for key, field in (("input_market_archive", "market_sha256"), ("input_volatility_archive", "risk_calibration_sha256")):
        rel = f"{CAPTURES}/{capture.get(key)}"
        path = root / rel
        if not path.exists():
            reasons.append(f"{key} not archived")
            continue
        archived = path.read_bytes()
        archives[rel] = sha(archived)
        if sha(gzip.decompress(archived)) != evidence.get(field):
            reasons.append(f"{key} bytes do not reproduce {field}")
    deadline = earliest_open_utc(cut) if cut else None
    stamped = {}
    for rel, digest in {origin_path: sha(raw), **archives}.items():
        when = first_stamp(rel, digest, stamps)
        stamped[rel] = when.isoformat() if when else None
        if when is None:
            reasons.append(f"{rel} has no independent timestamp")
        elif deadline and when > deadline:
            reasons.append(f"{rel} stamped after the next possible open")
    return {"origin": origin_path, "cut": cut, "admitted": not reasons, "reasons": reasons,
            "deadline_utc": deadline.isoformat() if deadline else None, "stamped_utc": stamped,
            "held_symbols": sorted(p["symbol"] for p in (proposal or {}).get("positions", []) if p.get("symbol") != "CASH")}


def horizon_end(cut, sessions=21):
    day, count = date.fromisoformat(cut), 0
    while count < sessions:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day


def cashflows_ready(root, admission, stamps, today=None):
    """Stage 2: issuer distribution histories observed after the horizon end and stamped."""
    end = horizon_end(admission["cut"])
    if (today or date.today()) <= end:
        return {"ready": False, "reason": f"horizon ends {end.isoformat()}"}
    missing = []
    for symbol in admission["held_symbols"]:
        folder = root / "data/distributions/histories" / symbol
        ok = False
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            data = json.loads(path.read_text(encoding="utf-8"))
            observed = datetime.fromisoformat(data["observed_at"]).date()
            rel = path.relative_to(root).as_posix()
            if observed > end and first_stamp(rel, sha(path.read_bytes()), stamps):
                ok = True
                break
        if not ok:
            missing.append(symbol)
    return {"ready": not missing, "missing_distribution_sources": missing, "horizon_end": end.isoformat()}


def audit(root=ROOT, today=None):
    stamps = token_times(root)
    base = root / CAPTURES / "origins"
    origins = sorted(base.glob("*.json.gz")) if base.exists() else []
    rows = []
    for path in origins:
        row = admit_origin(root, path.relative_to(root).as_posix(), stamps)
        if row["admitted"]:
            row["cashflows"] = cashflows_ready(root, row, stamps, today)
        rows.append(row)
    return {"schema": "v3-origin-admission-v1", "origins": len(rows), "admitted": sum(r["admitted"] for r in rows),
            "rows": rows, "scores_read": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(audit(), indent=1))


if __name__ == "__main__":
    main()
