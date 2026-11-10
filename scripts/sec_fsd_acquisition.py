"""Acquire the registered SEC 2024q4 Financial Statement Data Set.

Original bytes remain in ignored out/. Receipts do not establish historical
first publication, issuer security identity, or predictive eligibility.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile

try:
    from scripts.sec_original_acquisition import validate_agent
    from scripts.historical_sec_fsd_intake import archive_members, require
except ModuleNotFoundError:
    from sec_original_acquisition import validate_agent
    from historical_sec_fsd_intake import archive_members, require

ROOT = Path(__file__).resolve().parents[1]
QUARTER = "2024q4"
URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip"
SCHEMA = "sec-first-cut-fsd-acquisition-receipt-v1"
MAX_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED = 6 * 1024 * 1024 * 1024


def acquire(output_dir, *, quarter=QUARTER, user_agent,
            opener=urlopen, observed_at=None):
    require(quarter == QUARTER, "Only the reviewed 2024q4 FSD source is allowed")
    validate_agent(user_agent)
    folder = Path(output_dir)
    target = folder / (quarter + ".zip")
    receipt_path = folder / (quarter + ".receipt.json")
    require(not target.exists() and not receipt_path.exists(),
            "Original source or immutable receipt already exists")
    now = observed_at or datetime.now(timezone.utc)
    require(isinstance(now, datetime) and now.tzinfo is not None and
            now.utcoffset() is not None, "Acquisition requires timezone-aware time")
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        req = Request(URL, headers={
            "User-Agent": user_agent,
            "Accept": "application/zip,application/octet-stream",
            "Accept-Encoding": "identity",
        })
        length = 0
        digest = hashlib.sha256()
        with opener(req, timeout=120) as response:
            require(getattr(response, "status", None) == 200 and
                    response.geturl() == URL,
                    "Official SEC FSD source URL must return HTTP 200 without redirect")
            advertised = response.headers.get("Content-Length")
            if advertised is not None:
                require(advertised.isdigit() and
                        100 <= int(advertised) <= MAX_BYTES,
                        "Invalid SEC FSD Content-Length")
            http_date = response.headers.get("Date")
            http_modified = response.headers.get("Last-Modified")
            with tempfile.NamedTemporaryFile(dir=folder, prefix=quarter+".",
                    suffix=".part", delete=False) as output:
                temporary = Path(output.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    length += len(chunk)
                    require(length <= MAX_BYTES, "FSD source exceeds download ceiling")
                    output.write(chunk)
                    digest.update(chunk)
        require(length >= 100 and
                (advertised is None or length == int(advertised)),
                "Incomplete FSD response length")
        try:
            with ZipFile(temporary) as z:
                members = archive_members(z)
                files = [item for item in z.infolist() if not item.is_dir()]
                declared = sum(item.file_size for item in files)
                require(0 < declared <= MAX_UNCOMPRESSED and len(files) <= 100,
                        "FSD archive member sizes or count exceed safety bounds")
                require(members["sub.txt"].file_size > 0 and
                        members["num.txt"].file_size > 0,
                        "FSD original SUB/NUM tables cannot be empty")
        except BadZipFile as exc:
            raise ValueError("SEC FSD source is not a valid ZIP") from exc
        receipt = {
            "schema": SCHEMA, "quarter": quarter, "source_url": URL,
            "official_listing": "https://www.sec.gov/dera/data/financial-statement-data-sets.html",
            "retrieved_utc": now.astimezone(timezone.utc).isoformat(),
            "zip_sha256": digest.hexdigest(), "zip_bytes": length,
            "members_present": sorted(members), "declared_uncompressed_bytes": declared,
            "zip_member_payload_crc_verified": False,
            "http_date_at_retrieval": http_date,
            "http_last_modified_as_reported": http_modified,
            "original_source_historically_available_verified": False,
            "original_filing_publication_independently_verified": False,
            "historical_security_identity_certified": False,
            "eligible_full_engine_cuts_added": 0,
            "confirmatory_origins_added": 0,
            "predictive_validation": "not-established",
        }
        temporary.replace(target)
        temporary = None
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n",
                                encoding="utf-8")
        return receipt
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        receipt_path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quarter", default=QUARTER)
    parser.add_argument("--out-dir", type=Path, default=ROOT/"out/sec-fsd")
    args = parser.parse_args(argv)
    require(args.out_dir.resolve().is_relative_to((ROOT/"out").resolve()),
            "Original FSD ZIP must remain in Git-ignored out/")
    print(json.dumps(acquire(args.out_dir, quarter=args.quarter,
                             user_agent=os.environ.get("SEC_USER_AGENT")),
                     sort_keys=True))


if __name__ == "__main__":
    main()
