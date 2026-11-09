"""Fetch an explicitly listed SEC original into ignored local research storage.

Requires SEC_USER_AGENT with a contact email. A successful retrieval proves
only that the bytes were obtained and the filing header matches a published
source lead, NOT that the same bytes were available at the historical cut.
No market forecasts, account holdings or return labels are consumed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, urlopen

try:
    from scripts.historical_sec_original_filing import parse_original, require
    from scripts.historical_sec_fsd_intake import as_filed_acceptance
except ModuleNotFoundError:
    from historical_sec_original_filing import parse_original, require
    from historical_sec_fsd_intake import as_filed_acceptance

ROOT = Path(__file__).resolve().parents[1]
LEADS = ROOT/"data/historical/sec-first-cut-original-source-leads-v1.json"
SCHEMA = "historical-sec-original-acquisition-receipt-v1"
MAX_BYTES = 64 * 1024 * 1024


def validate_agent(agent):
    """SEC requires an identifiable requester with contact information."""
    require(isinstance(agent, str) and 10 <= len(agent) <= 200
            and "\n" not in agent and "\r" not in agent
            and re.search(r"(?<!\S)[^@\s]+@[^@\s]+\.[^@\s]+", agent)
            and "example.com" not in agent.lower(),
            "SEC_USER_AGENT must identify a real contact; no agent is logged")
    return agent


def select_lead(manifest, accession):
    require(isinstance(manifest, dict) and
            manifest.get("schema") ==
            "historical-sec-first-cut-original-source-leads-v1" and
            manifest.get("predictive_validation") == "not-established" and
            manifest.get("eligible_full_engine_cuts_added") == 0 and
            isinstance(manifest.get("sources"), list),
            "Source lead manifest cannot assert market eligibility")
    rows = [row for row in manifest["sources"]
            if isinstance(row, dict) and row.get("accession") == accession]
    require(len(rows) == 1, "Unregistered or duplicate SEC accession")
    item = rows[0]
    require(re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
            and re.fullmatch(r"[0-9]{1,10}", item.get("cik", "")),
            "Invalid registered EDGAR identifiers")
    prefix = ("https://www.sec.gov/Archives/edgar/data/"
              f'{int(item["cik"])}/{accession.replace("-", "")}/')
    require(item["full_submission_url"] == prefix+accession+".txt"
            and item["index_url"] == prefix+accession+"-index.html"
            and item["form"] in ("10-K", "10-Q", "10-K/A", "10-Q/A")
            and item["accepted_eastern"] and item["filed_date"]
            and item["original_full_submission_sha256"] is None
            and item["original_full_submission_bytes_obtained"] is False
            and item["first_publication_independently_verified"] is False,
            "SEC source lead URL or unverified state changed")
    return item


def get_original(url, *, user_agent, opener=urlopen, maximum=MAX_BYTES):
    validate_agent(user_agent)
    require(url.startswith("https://www.sec.gov/Archives/edgar/data/")
            and url.endswith(".txt") and not re.search(r"[\s?#]", url),
            "SEC origin URL outside the allowlist")
    request = Request(url, headers={
        "User-Agent": user_agent,
        "Accept": "text/plain,application/octet-stream",
        "Accept-Encoding": "identity",
    })
    with opener(request, timeout=90) as resp:
        require(getattr(resp, "status", None) == 200
                and resp.geturl() == url,
                "SEC original response is not an exact success from the official URL")
        size_text = resp.headers.get("Content-Length")
        if size_text:
            require(size_text.isdigit() and 40 <= int(size_text) <= maximum,
                    "SEC original advertised size exceeds safety limit")
        parts, total = [], 0
        while True:
            part = resp.read(1024*1024)
            if not part:
                break
            total += len(part)
            require(total <= maximum, "SEC original response exceeds safety limit")
            parts.append(part)
        raw = b"".join(parts)
        require(len(raw) >= 40 and
                (not size_text or len(raw) == int(size_text)),
                "SEC original response length mismatch")
        return raw, {
            "http_date": resp.headers.get("Date"),
            "http_last_modified": resp.headers.get("Last-Modified"),
            "content_type": resp.headers.get("Content-Type"),
        }


def acquire(manifest, accession, output_dir, *, user_agent, opener=urlopen,
            observed_at=None):
    lead = select_lead(manifest, accession)
    raw, http = get_original(lead["full_submission_url"],
                             user_agent=user_agent, opener=opener)
    header = parse_original(raw, accession)
    require(header["cik"] == str(int(lead["cik"]))
            and header["form"] == lead["form"]
            and header["filed"] == lead["filed_date"].replace("-", "")
            and header["accepted_eastern"] == lead["accepted_eastern"],
            "Original SEC bytes disagree with registered official index metadata")
    expected = lead["full_submission_size_bytes_reported_in_index"]
    require(type(expected) is int and 40 <= expected <= MAX_BYTES
            and len(raw) == expected,
            "Original SEC submission differs from official indexed file length")
    now = observed_at or datetime.now(timezone.utc)
    require(isinstance(now, datetime) and now.tzinfo is not None,
            "Acquisition instant must be timezone-aware")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir/(accession+".txt")
    receipt_path = target_dir/(accession+".receipt.json")
    require(not target.exists() and not receipt_path.exists(),
            "Existing original or receipt must not be overwritten")
    receipt = {
        "schema": SCHEMA,
        "accession": accession,
        "cik": str(int(lead["cik"])),
        "source_url": lead["full_submission_url"],
        "index_url": lead["index_url"],
        "retrieved_utc": now.astimezone(timezone.utc).isoformat(),
        "original_sha256": hashlib.sha256(raw).hexdigest(),
        "original_bytes": len(raw),
        "indexed_bytes_match": True,
        "original_header_matches_official_index_lead": True,
        "http_date_at_retrieval": http["http_date"],
        "http_last_modified_as_reported": http["http_last_modified"],
        "http_content_type_as_reported": http["content_type"],
        "first_publication_independently_verified": False,
        "numeric_xbrl_facts_reconciled": False,
        "original_fsd_zip_reconciled": False,
        "historical_instrument_identity_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }
    # Only write after response, source identity, bytes and receipt are validated.
    try:
        with tempfile.NamedTemporaryFile(
                dir=target_dir, prefix=accession+".", suffix=".part",
                delete=False) as tmp:
            temporary = Path(tmp.name)
            tmp.write(raw)
        require(hashlib.sha256(temporary.read_bytes()).hexdigest()
                == receipt["original_sha256"],
                "Original bytes changed during local write")
        temporary.replace(target)
        receipt_path.write_text(json.dumps(receipt, indent=2)+"\n",
                                encoding="utf-8", errors="strict")
    except Exception:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=LEADS)
    p.add_argument("--accession", required=True)
    p.add_argument("--out-dir", type=Path, default=ROOT/"out/sec-originals")
    args = p.parse_args(argv)
    # out/ is ignored in Git, unlike the tracked historical datasets.
    ignored = (ROOT/"out").resolve()
    require(args.out_dir.resolve().is_relative_to(ignored),
            "Original SEC bytes must remain in ignored out/ local storage")
    agent = validate_agent(os.environ.get("SEC_USER_AGENT"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = acquire(manifest, args.accession, args.out_dir, user_agent=agent)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
