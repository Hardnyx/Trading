"""Verify retained real SEC primary and extracted XBRL comparison artifacts.

Both reports were produced from the same original 20,482,578-byte MSFT
accession, after verifying its frozen SHA-256. Equality of two supported
unsegmented facts is not complete financial/PIT/predictive validation.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

try:
    from scripts.historical_sec_fsd_intake import require
except ModuleNotFoundError:
    from historical_sec_fsd_intake import require

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT/"data/historical/sec-first-cut-primary-inline-review-v1.json"
EMBEDDED = ROOT/"data/historical/sec-first-cut-embedded-instance-review-v1.json"
EXTRACT = ROOT/"data/historical/sec-first-cut-fsd-extract-v1.json"
OBSERVED = ROOT/"data/historical/sec-first-cut-original-source-observation-v1.json"
PRIMARY_ARTIFACT_SHA256 = "a7ae0a28581650df14fe3e8e6c74597834fb50a1afc82f900392897430339f71"
EMBEDDED_ARTIFACT_SHA256 = "cd74033caa229009c3dacfc6ee84f947a2359eaca7e4c82892d9b657c415a631"
SCHEMA = "sec-first-cut-original-numeric-subset-audit-v1"


def load_report(path, digest):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest,
            "Original numerical comparison artifact byte hash differs")
    return json.loads(raw)


def audit(primary=PRIMARY, embedded=EMBEDDED, fsd=EXTRACT, observed=OBSERVED,
          *, primary_digest=PRIMARY_ARTIFACT_SHA256,
          embedded_digest=EMBEDDED_ARTIFACT_SHA256):
    """Retain only documented exact supported rows without claim inflation."""
    p = load_report(primary, primary_digest)
    e = load_report(embedded, embedded_digest)
    f = json.loads(Path(fsd).read_bytes())
    obs = json.loads(Path(observed).read_bytes())
    edgar = obs["source_provenance"]["original_edgar_filing"]
    accession = edgar["accession"]
    require(p["schema"] == "historical-sec-primary-inline-numeric-crosscheck-v1"
            and p["scope"] == "limited-exact-primary-inline-subset-research-only"
            and e["schema"] == "historical-sec-embedded-extracted-instance-crosscheck-v1"
            and e["scope"] == "limited-secondary-embedded-instance-research-only"
            and p["accession"] == e["accession"] == accession
            and p["original_complete_filing_sha256"] ==
                e["original_complete_submission_sha256"] == edgar["sha256"],
            "Original XBRL reports differ on source accession or original hash")
    require(p["original_primary_filename"] == "msft-20240930.htm"
            and p["original_primary_sha256"] ==
                "68ec2a74cd86fa97f190465c649867cf603ce7759692454c527449f2d69aab5f"
            and e["embedded_instance_filename"] == "msft-20240930_htm.xml"
            and e["embedded_instance_sha256"] ==
                "75523942f79ac5cfd31c86045b4d3accf036982f8db0ffb3235606ccda7c442d"
            and e["embedded_instance_found_in_same_original_submission"] is True,
            "Primary and secondary source document identities changed")
    require(p["original_header_accepted_utc"] ==
                e["original_acceptance_utc"] == "2024-10-30T20:07:17+00:00"
            and p["fsd_reported_accepted_utc"] == "2024-10-30T20:07:00+00:00"
            and p["original_header_matches_derived_fsd"] is False
            and p["original_header_fsd_minute_only_consistent"] is True
            and e["header_acceptance_exact_match"] is False
            and e["header_acceptance_minute_only_consistent"] is True,
            "Different FSD and EDGAR accepted timestamps must remain distinct")
    require(p["selected_derived_rows"] == e["selected_rows"] == 4
            and len(p["rows"]) == len(e["rows"]) == len(f["facts"]) == 4
            and p["comparison_counts"] == {
                "exact_match":2, "decimal_mismatch":0,
                "missing_in_original_subset":0, "ambiguous_original":0,
                "ineligible_derived_dimension":2,
                "unsupported_derived_tag_or_unit":0,
                "missing_derived_numeric_value":0,
            }
            and e["comparison_counts"] == {
                "exact_literal_match":2, "decimal_mismatch":0,
                "missing_in_embedded_instance":0, "ambiguous_instance":0,
                "ineligible_derived_dimension":2,
                "unsupported_derived_tag_or_unit":0,
                "missing_derived_numeric_value":0,
            },
            "Conservative original numeric review counts changed")
    compared = []
    for original, secondary, source in zip(p["rows"],e["rows"],f["facts"]):
        for row in (original, secondary):
            require(row["tag"] == source["tag"] == "NetIncomeLoss"
                    and row["version"] == source["version"] == "us-gaap/2024"
                    and row["ddate"] == source["ddate"]
                    and row["qtrs"] == source["qtrs"] == 1
                    and row["uom"] == source["uom"] == "USD"
                    and row["segments"] == source["segments"]
                    and row["coreg"] == source["coreg"] == "",
                    "Numerical comparison row keys differ from frozen FSD source")
        require(original["accession"] == accession
                and original["derived_value_decimal"] ==
                    secondary["derived_value_as_reported"] ==
                    source["value_decimal_as_filed"],
                "Numerical comparison omitted or altered the original FSD value")
        if source["segments"] == "":
            require(original["comparison_status"] == "exact_match"
                    and secondary["comparison_status"] == "exact_literal_match"
                    and original["matched_original_primary_value_decimal"] is not None
                    and secondary["embedded_value_if_unique"] is not None
                    and Decimal(original["matched_original_primary_value_decimal"]) ==
                        Decimal(secondary["embedded_value_if_unique"]) ==
                        Decimal(source["value_decimal_as_filed"]),
                    "Supported consolidated net-income match has changed")
            compared.append(source["ddate"])
        else:
            require(source["segments"] == "EquityComponents=RetainedEarnings;"
                    and original["comparison_status"] ==
                        secondary["comparison_status"] == "ineligible_derived_dimension"
                    and original["matched_original_primary_value_decimal"] is None
                    and secondary["embedded_value_if_unique"] is None,
                    "Segmented derived facts must remain excluded")
    require(compared == ["2023-09-30","2024-09-30"],
            "Two observed quarters, not four independent facts, were compared")
    for field in (
        "original_filing_publication_independently_verified",
        "historical_security_identity_certified",
    ):
        require(p[field] is False and e[field] is False,
                "Original numeric equality cannot certify source vintage or security")
    require(p["source_fsd_zip_hash_reverified"] is False
            and p["derived_fsd_rows_reproduced_from_original_zip"] is False
            and e["source_fsd_archive_bytes_reverified"] is False
            and p["full_xbrl_document_numeric_fact_set_reconciled"] is False
            and e["complete_original_numeric_fact_set_reconciled"] is False
            and e["original_primary_inline_document_numeric_facts_reconciled"] is False
            and p["eligible_full_engine_cuts_added"] ==
                e["eligible_full_engine_cuts_added"] == 0
            and p["confirmatory_origins_added"] ==
                e["confirmatory_origins_added"] == 0
            and p["predictive_validation"] ==
                e["predictive_validation"] == "not-established",
            "Narrow original-source crosscheck must not be promoted to PIT or alpha")
    return {
        "schema": SCHEMA,
        "accession": accession,
        "original_submission_sha256": edgar["sha256"],
        "primary_report_sha256": primary_digest,
        "embedded_report_sha256": embedded_digest,
        "primary_exact_unsegmented_matches": 2,
        "embedded_exact_unsegmented_matches": 2,
        "excluded_segmented_derived_facts": 2,
        "numeric_mismatches_or_ambiguities_in_supported_subset": 0,
        "original_fsd_zip_reextracted_in_this_run": False,
        "complete_original_numeric_fact_set_reconciled": False,
        "source_first_publication_independently_verified": False,
        "historical_security_master_and_prices_verified": False,
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
        require(result["primary_exact_unsegmented_matches"] == 2
                and result["complete_original_numeric_fact_set_reconciled"] is False
                and result["confirmatory_origins_added"] == 0,
                "Limited SEC comparison must remain nonconfirmatory")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
