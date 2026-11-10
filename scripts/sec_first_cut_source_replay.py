"""Check original SEC source bytes against the frozen first-cut receipts.

This verifies local file integrity, NOT SEC first-dissemination time or PIT
eligibility. It is safe to run on restored GitHub Actions cache contents.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, BadZipFile

try:
    from scripts.historical_sec_fsd_intake import archive_members, require
    from scripts.historical_sec_original_filing import parse_original
except ModuleNotFoundError:
    from historical_sec_fsd_intake import archive_members, require
    from historical_sec_original_filing import parse_original

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "data/historical/sec-first-cut-original-source-observation-v1.json"
SCHEMA = "sec-first-cut-local-original-byte-integrity-v1"


def digest_file(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def audit(fsd_zip, original_txt, fsd_receipt, original_receipt, observation):
    """Recompute both original hashes; never trust a cache-hit flag alone."""
    source = observation["source_provenance"]
    fsd = source["original_fsd_zip"]
    edgar = source["original_edgar_filing"]
    first = json.loads(Path(fsd_receipt).read_text(encoding="utf-8"))
    second = json.loads(Path(original_receipt).read_text(encoding="utf-8"))
    accession = edgar["accession"]
    require(observation["schema"] ==
            "sec-first-cut-original-source-observation-v1" and
            observation["sample_role"] ==
            "previously-inspected-retrospective-development" and
            observation["eligible_full_engine_cuts_added"] == 0 and
            observation["confirmatory_origins_added"] == 0 and
            observation["predictive_validation"] == "not-established",
            "Local source comparison requires a fixed non-confirmatory lead")
    for path, receipt, expected, schema, sha_field, size_field in (
        (fsd_zip, first, fsd, "sec-first-cut-fsd-acquisition-receipt-v1",
         "zip_sha256", "zip_bytes"),
        (original_txt, second, edgar,
         "historical-sec-original-acquisition-receipt-v1",
         "original_sha256", "original_bytes"),
    ):
        path = Path(path)
        require(path.is_file() and
                isinstance(expected["sha256"], str) and
                len(expected["sha256"]) == 64 and
                path.stat().st_size == expected["bytes"] and
                digest_file(path) == expected["sha256"],
                "Local original SEC bytes differ from the frozen source hash")
        require(receipt.get("schema") == schema and
                receipt.get("source_url") == expected["url"] and
                receipt.get(sha_field) == expected["sha256"] and
                receipt.get(size_field) == expected["bytes"] and
                receipt.get("eligible_full_engine_cuts_added") == 0 and
                receipt.get("confirmatory_origins_added") == 0 and
                receipt.get("predictive_validation") == "not-established",
                "Local original SEC receipt disagrees with source bytes")
    require(Path(fsd_zip).name == "2024q4.zip" and
            Path(original_txt).name == accession + ".txt",
            "Original source filenames were substituted")
    require(first.get("original_source_historically_available_verified") is False
            and first.get("original_filing_publication_independently_verified") is False
            and second.get("first_publication_independently_verified") is False
            and second.get("numeric_xbrl_facts_reconciled") is False
            and second.get("indexed_bytes_match") is True
            and second.get("original_header_matches_official_index_lead") is True,
            "Local receipts cannot promote source-vintage or numeric evidence")
    try:
        with ZipFile(fsd_zip) as zip_file:
            members = archive_members(zip_file)
            names = sorted(members)
            require(names == first.get("members_present")
                    and members["sub.txt"].file_size > 0
                    and members["num.txt"].file_size > 0,
                    "Original FSD ZIP structure differs from download receipt")
    except BadZipFile as exc:
        raise ValueError("Original SEC FSD ZIP is invalid") from exc
    parsed = parse_original(Path(original_txt).read_bytes(), accession)
    accepted = observation["accepted_eastern"]
    require(parsed["cik"] == edgar["cik"] and
            parsed["accepted_eastern"] == accepted["original_edgar_header"]
            and parsed["raw_sha256"] == edgar["sha256"]
            and second.get("accession") == accession
            and second.get("cik") == edgar["cik"],
            "Original EDGAR header or accession differs from the frozen lead")
    return {
        "schema": SCHEMA,
        "cut": observation["cut"],
        "accession": accession,
        "fsd_sha256": fsd["sha256"],
        "edgar_sha256": edgar["sha256"],
        "source_zip_original_bytes_verified": True,
        "source_edgar_original_bytes_verified": True,
        "sec_header_identity_and_acceptance_reverified": True,
        "source_originals_from_existing_local_files": True,
        "original_zip_member_payload_crc_verified": False,
        "original_first_publication_independently_verified": False,
        "historical_point_in_time_eligibility_verified": False,
        "original_primary_inline_document_numeric_facts_reconciled": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    record = json.loads(OBSERVATION.read_text(encoding="utf-8"))
    result = audit(
        ROOT / "out/sec-fsd/2024q4.zip",
        ROOT / "out/sec-originals/0000950170-24-118967.txt",
        ROOT / "out/sec-fsd/2024q4.receipt.json",
        ROOT / "out/sec-originals/0000950170-24-118967.receipt.json",
        record,
    )
    if args.verify:
        require(result["eligible_full_engine_cuts_added"] == 0 and
                result["historical_point_in_time_eligibility_verified"] is False,
                "Local cache verification cannot certify PIT or model skill")
    if args.output:
        require(args.output.resolve().is_relative_to((ROOT / "out").resolve()),
                "Source integrity reports must remain under ignored out/")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
