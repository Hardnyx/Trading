"""Audit the immutable four-row SEC FSD extract captured from a real ZIP.

The extract preserves the complete original JSON artifact. It does not restore
the original FSD ZIP and cannot prove first publication or a historical PIT
snapshot. This is a development-only source receipt for the MSFT 2024-12 cut.
"""
import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

try:
    from scripts.historical_sec_fsd_intake import as_filed_acceptance, require
except ModuleNotFoundError:
    from historical_sec_fsd_intake import as_filed_acceptance, require

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/historical/sec-first-cut-fsd-extract-v1.json"
OBSERVATION = ROOT / "data/historical/sec-first-cut-original-source-observation-v1.json"
EXTRACT_SHA256 = "464019f23f683c8e65d7b85554ef9d121c12f3882a0d8d27f59ba4c49838f6c5"
SCHEMA = "historical-sec-fsd-frozen-research-extract-audit-v1"


def audit(source=SOURCE, observation=OBSERVATION, *,
          expected_hash=EXTRACT_SHA256):
    """Check the full saved original FSD JSON, fields, and excluded rows."""
    raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == expected_hash,
            "Frozen SEC research extract differs from original workflow artifact")
    record = json.loads(raw)
    reference = (json.loads(Path(observation).read_bytes())
                 if isinstance(observation, (str, Path)) else observation)
    fsd = reference["source_provenance"]["original_fsd_zip"]
    edgar = reference["source_provenance"]["original_edgar_filing"]
    accepted = reference["accepted_eastern"]
    require(
        record.get("schema") == "historical-sec-fsd-research-intake-v1"
        and record.get("scope") == "retrospective-as-filed-research-only"
        and record.get("quarter_archive") == "2024q4"
        and record.get("archive_file_name") == "2024q4.zip"
        and record.get("archive_sha256") == fsd["sha256"]
        and record.get("cutoff_utc") == "2024-12-31T21:00:00+00:00"
        and record.get("requested_ciks") == [edgar["cik"]]
        and record.get("requested_tags") == ["NetIncomeLoss"]
        and record.get("selected_submission_count") == 1
        and record.get("selected_fact_count") == 4
        and record.get("segments_column_present_in_num") is True
        and record.get("excluded_target_submissions_after_cutoff") == 0
        and record.get("excluded_target_nonfinancial_forms") == 1
        and record.get("source_official_page") == fsd["url"].rsplit("/", 1)[0]
            .replace("/files/dera/data/financial-statement-data-sets",
                     "/dera/data/financial-statement-data-sets.html"),
        "Frozen SEC research extract has unreviewed source or selection metadata")
    submissions = record.get("submissions")
    require(isinstance(submissions, list) and len(submissions) == 1,
            "Exactly one selected original MSFT accession is required")
    sub = submissions[0]
    require(sub.get("adsh") == edgar["accession"]
            and sub.get("cik") == edgar["cik"]
            and sub.get("company_name_as_filed") == "MICROSOFT CORP"
            and sub.get("form") == "10-Q"
            and sub.get("form_is_amendment") is False
            and sub.get("filed_day_reported") == "2024-10-30"
            and sub.get("fiscal_period_end_reported") == "2024-09-30"
            and sub.get("accepted_eastern_as_filed") == accepted["fsd_as_reported"]
            and sub.get("accepted_utc") == "2024-10-30T20:07:00+00:00"
            and sub.get("instance") == "msft-20240930_htm.xml"
            and sub.get("edgar_submission_folder") ==
                edgar["url"].rsplit("/", 1)[0] + "/"
            and sub.get("original_filing_bytes_verified") is False
            and sub.get("first_publication_independently_verified") is False,
            "Frozen FSD accession is inconsistent with original observed source")
    reported = as_filed_acceptance(sub["accepted_eastern_as_filed"])
    original = as_filed_acceptance(accepted["original_edgar_header"])
    require(reported < original and
            (original-reported).total_seconds() < 60 and
            original <= datetime.fromisoformat(record["cutoff_utc"]),
            "FSD reported minute must not be promoted to EDGAR original acceptance")
    facts = record.get("facts")
    expected = reference["selected_numeric_facts"]["rows"]
    require(isinstance(facts, list) and len(facts) == len(expected) == 4,
            "Frozen FSD facts count differs from observed source")
    compared = []
    for row, observed in zip(facts, expected):
        require(row.get("adsh") == edgar["accession"]
                and row.get("cik") == edgar["cik"]
                and row.get("accepted_utc") == sub["accepted_utc"]
                and row.get("form") == "10-Q"
                and row.get("amendment") is False
                and row.get("tag") == "NetIncomeLoss"
                and row.get("version") == "us-gaap/2024"
                and row.get("ddate") == observed["period_end"]
                and row.get("qtrs") == 1
                and row.get("uom") == "USD"
                and row.get("coreg") == ""
                and row.get("segments") == observed["segment"]
                and row.get("segments_column_present") is True
                and row.get("value_decimal_as_filed") == observed["value_decimal"]
                and row.get("footnote_as_filed") == ""
                and row.get("consolidated_unsegmented_candidate") is
                    (observed["segment"] == "")
                and row.get("ready_for_historical_valuation") is False
                and Decimal(row["value_decimal_as_filed"]).is_finite(),
                "Frozen SEC FSD numeric row differs from captured original")
        compared.append((row["ddate"], row["segments"], row["value_decimal_as_filed"]))
    require(len(set(compared)) == 4,
            "Frozen SEC FSD extract contains duplicate rows")
    for field in (
        "ticker_identity_or_security_master_certified",
        "original_filing_publication_independently_verified",
        "quarterly_extract_available_at_historical_cutoff_proven",
        "filer_accounting_tag_semantics_reconciled",
        "fundamentals_and_quality_component_certified",
    ):
        require(record.get(field) is False,
                "FSD retrospective extraction cannot claim historical certification")
    require(record.get("eligible_full_engine_cuts_added") == 0
            and record.get("confirmatory_origins_added") == 0
            and record.get("predictive_validation") == "not-established",
            "Research source cannot add confirmation origins")
    return {
        "schema": SCHEMA,
        "fsd_extract_sha256": digest,
        "source_fsd_zip_sha256_reported": fsd["sha256"],
        "original_fsd_zip_bytes_available_for_this_check": False,
        "original_fsd_zip_reextracted_in_this_check": False,
        "source_submissions": 1,
        "selected_derived_facts": 4,
        "unsegmented_derived_facts": 2,
        "derived_dimensions_excluded_from_consolidated_count": 2,
        "frozen_source_artifact_bytes_match": True,
        "original_filing_publication_independently_verified": False,
        "historical_point_in_time_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    result = audit()
    if args.verify:
        require(result["frozen_source_artifact_bytes_match"] is True
                and result["historical_point_in_time_certified"] is False
                and result["eligible_full_engine_cuts_added"] == 0,
                "SEC FSD artifact is not eligible for confirmation")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
