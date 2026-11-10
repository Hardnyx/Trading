"""Reconcile SEC quarterly FSD metadata against an original EDGAR filing.

The complete accession .txt and its SEC-HEADER are required local inputs.
Matching original bytes corroborates reported filing metadata, not the first
publication timestamp, completeness of XBRL facts or historical tradability.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

try:
    from scripts.historical_sec_fsd_intake import (
        ACCESSION, SCHEMA as FSD_SCHEMA, as_filed_acceptance,
        cik_number, cutoff_timestamp, digest_file, require,
    )
except ModuleNotFoundError:
    from historical_sec_fsd_intake import (
        ACCESSION, SCHEMA as FSD_SCHEMA, as_filed_acceptance,
        cik_number, cutoff_timestamp, digest_file, require,
    )

SCHEMA = "historical-sec-original-filing-header-reconciliation-v1"
TEMPLATE_SCHEMA = "historical-sec-original-filing-request-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 200 * 1024 * 1024
FIELDS = {
    "form": rb"(?m)^[ \t]*CONFORMED SUBMISSION TYPE:[ \t]*([A-Z0-9/-]+)[ \t]*\r?$",
    "filing_day": rb"(?m)^[ \t]*FILED AS OF DATE:[ \t]*([0-9]{8})[ \t]*\r?$",
    "acceptance": rb"(?m)^[ \t]*<ACCEPTANCE-DATETIME>([0-9]{14})[ \t]*\r?$",
    "cik": rb"(?m)^[ \t]*CENTRAL INDEX KEY:[ \t]*([0-9]{1,10})[ \t]*\r?$",
}


def header_value(header, field, *, unique=True):
    values = re.findall(FIELDS[field], header)
    require(bool(values), "Original SEC-HEADER missing " + field)
    if unique:
        require(len(set(values)) == 1, "Conflicting original SEC-HEADER " + field)
    return [v.decode("ascii") for v in values]


def parse_original(raw, accession):
    """Treat complete raw EDGAR dissemination as data, never HTML markup."""
    require(type(raw) is bytes and len(raw) >= 40 and len(raw) <= MAX_BYTES,
            "Invalid original complete-filing bytes")
    require(ACCESSION.fullmatch(accession) is not None,
            "Invalid original filing accession")
    require(raw.count(b"<SEC-HEADER>") == 1 and
            raw.count(b"</SEC-HEADER>") == 1 and
            raw.index(b"<SEC-HEADER>") < raw.index(b"</SEC-HEADER>"),
            "Original filing requires a unique complete SEC-HEADER")
    require(raw.startswith(b"<SEC-DOCUMENT>") or
            raw.startswith(b"\xef\xbb\xbf<SEC-DOCUMENT>"),
            "Original archive must contain the full SEC-DOCUMENT, not an index")
    require(b"</SEC-DOCUMENT>" in raw[-4096:],
            "Truncated complete SEC-DOCUMENT submission")
    header = raw.split(b"<SEC-HEADER>", 1)[1].split(b"</SEC-HEADER>", 1)[0]
    require(len(header) <= 5 * 1024 * 1024,
            "SEC-HEADER exceeds allowable size")
    filings = re.findall(
        rb"(?m)^[ \t]*ACCESSION NUMBER:[ \t]*([0-9]{10}-[0-9]{2}-[0-9]{6})[ \t]*\r?$",
        header)
    require(filings == [accession.encode("ascii")],
            "Complete filing accession does not match the requested accession")
    acceptance = header_value(header, "acceptance")[0]
    accepted = datetime.strptime(acceptance, "%Y%m%d%H%M%S")
    local = accepted.strftime("%Y-%m-%d %H:%M:%S")
    accepted_utc = as_filed_acceptance(local)
    ciks = {cik_number(v) for v in header_value(header, "cik", unique=False)}
    require(len(ciks) == 1,
            "Multiple company CIKs in SEC header require manual filer review")
    return {
        "accession": accession,
        "cik": next(iter(ciks)),
        "form": header_value(header, "form")[0],
        "filed": header_value(header, "filing_day")[0],
        "accepted_eastern": local,
        "accepted_utc": accepted_utc.isoformat(),
        "header_has_unique_cik": True,
        "header_exact_acceptance_present": True,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_byte_count": len(raw),
    }


def reconcile(report, original_path, accession, *, archive_path=None,
              expected_original_sha256=None):
    """Fail closed on metadata conflicts and future post-cutoff amendments."""
    require(isinstance(report, dict) and report.get("schema") == FSD_SCHEMA
            and report.get("scope") == "retrospective-as-filed-research-only"
            and report.get("original_filing_publication_independently_verified") is False
            and report.get("eligible_full_engine_cuts_added") == 0
            and report.get("confirmatory_origins_added") == 0
            and isinstance(report.get("submissions"), list),
            "Input must be a non-certified original FSD intake report")
    cutoff = cutoff_timestamp(report.get("cutoff_utc"))
    selected = [r for r in report["submissions"]
                if isinstance(r, dict) and r.get("adsh") == accession]
    require(len(selected) == 1, "Exactly one included SEC accession required")
    fsd = selected[0]
    cik = cik_number(fsd["cik"])
    require(ACCESSION.fullmatch(accession) is not None and
            fsd["edgar_submission_folder"] ==
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/",
            "FSD accession or original EDGAR folder mismatch")
    require(as_filed_acceptance(fsd["accepted_eastern_as_filed"]) <= cutoff,
            "FSD submission was accepted after decision cutoff")
    path = Path(original_path)
    require(path.is_file() and path.name == accession + ".txt" and
            40 <= path.stat().st_size <= MAX_BYTES,
            "Original input must be the complete accession .txt")
    raw = path.read_bytes()
    filing = parse_original(raw, accession)
    # Keep the two official timestamps distinct. The observed quarterly
    # FSD row reports 16:07:00.0 while the original SEC-HEADER says 16:07:17.
    # A zero-second FSD value is at most a minute-resolution lead, not proof
    # that the original was accepted at the beginning of that minute.
    reported = as_filed_acceptance(fsd["accepted_eastern_as_filed"])
    original = as_filed_acceptance(filing["accepted_eastern"])
    exact_acceptance = reported == original
    minute_bucket = (
        not exact_acceptance
        and "." in fsd["accepted_eastern_as_filed"]
        and reported.second == 0 and reported.microsecond == 0
        and original.replace(second=0, microsecond=0) == reported
        and 0 < (original - reported).total_seconds() < 60
    )
    require(filing["cik"] == cik and filing["form"] == fsd["form"] and
            filing["filed"] == fsd["filed_day_reported"].replace("-", "") and
            fsd["accepted_utc"] == reported.isoformat() and
            filing["accepted_utc"] == original.isoformat() and
            (exact_acceptance or minute_bucket) and original <= cutoff,
            "Original SEC-HEADER disagrees with FSD identity, reported minute or decision cutoff")
    if expected_original_sha256 is not None:
        require(isinstance(expected_original_sha256, str) and
                HASH.fullmatch(expected_original_sha256) is not None and
                filing["raw_sha256"] == expected_original_sha256,
                "Independent supplied digest differs from original filing bytes")
    source_archive_reverified = False
    if archive_path is not None:
        archive = Path(archive_path)
        require(archive.is_file() and
                archive.name == report["archive_file_name"] and
                HASH.fullmatch(report["archive_sha256"]) is not None and
                digest_file(archive) == report["archive_sha256"],
                "FSD report does not match supplied original ZIP bytes")
        source_archive_reverified = True
    return {
        "schema": SCHEMA,
        "scope": "original-EDGAR-header-crosscheck-research-only",
        "accession": accession,
        "cik": cik,
        "original_complete_filing_url": (
            fsd["edgar_submission_folder"] + accession + ".txt"),
        "original_filing_sha256": filing["raw_sha256"],
        "original_byte_count": filing["raw_byte_count"],
        "fsd_archive_sha256": report.get("archive_sha256"),
        "fsd_original_zip_bytes_reverified": source_archive_reverified,
        "external_filing_sha256_supplied": expected_original_sha256 is not None,
        "header_form_filed_accepted_cik_accession_match": exact_acceptance,
        "header_identity_and_filed_day_match": True,
        "fsd_acceptance_minute_bucket_consistent_not_exact": minute_bucket,
        "fsd_accepted_utc_as_reported": fsd["accepted_utc"],
        "original_accepted_utc_from_sec_header": filing["accepted_utc"],
        "accepted_utc": filing["accepted_utc"],
        "information_cutoff_utc": cutoff.isoformat(),
        "original_filing_bytes_present_and_hashed": True,
        "original_filing_first_publication_independently_verified": False,
        "original_document_numeric_facts_reconciled": False,
        "historical_security_identity_certified": False,
        "past_source_vintage_availability_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def request_template():
    return {
        "schema": TEMPLATE_SCHEMA,
        "archive_url_pattern":
            "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_without_dashes}/{accession}.txt",
        "required_local_inputs": [
            "FSD extracted report from original quarterly ZIP",
            "Original accession .txt SEC-DOCUMENT file",
            "Exact historical decision instant with timezone in FSD report",
        ],
        "optional_checks": [
            "Original FSD quarterly ZIP for independent SHA-256 recheck",
            "Externally recorded original filing SHA-256",
        ],
        "sec_original_record_not_downloaded_by_template": True,
        "first_dissemination_and_numeric_reconciliation_still_required": True,
        "eligible_full_engine_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--template", type=Path)
    modes.add_argument("--original", type=Path)
    parser.add_argument("--fsd-report", type=Path)
    parser.add_argument("--accession")
    parser.add_argument("--fsd-archive", type=Path)
    parser.add_argument("--expected-original-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.template:
        require(all(v is None for v in (
            args.fsd_report, args.accession, args.fsd_archive,
            args.expected_original_sha256, args.output)),
            "Template mode cannot accept source evidence")
        result = request_template()
        out = args.template
    else:
        require(args.fsd_report is not None and args.accession is not None,
                "A FSD report and accession are required for original reconciliation")
        report = json.loads(args.fsd_report.read_text(encoding="utf-8"))
        result = reconcile(
            report, args.original, args.accession,
            archive_path=args.fsd_archive,
            expected_original_sha256=args.expected_original_sha256)
        out = args.output
    if args.verify:
        require(result["predictive_validation"] == "not-established" and
                (result.get("eligible_full_engine_cuts_added",
                            result.get("eligible_full_engine_cuts")) == 0)
                and not result.get("original_filing_first_publication_independently_verified",
                                   False),
                "Original metadata must not certify predictive evidence")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
