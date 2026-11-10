"""Keep recovered SEC receipts and FSD facts separate from historical certification."""
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import unittest

from scripts.historical_sec_fsd_intake import as_filed_acceptance, require

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/historical/sec-first-cut-original-source-observation-v1.json"
LEADS = ROOT / "data/historical/sec-first-cut-original-source-leads-v1.json"


def audit(observation, lead):
    source = observation["source_provenance"]
    edgar = source["original_edgar_filing"]
    fsd = source["original_fsd_zip"]
    selected = lead["sources"][0]
    require(observation["schema"] ==
            "sec-first-cut-original-source-observation-v1"
            and observation["sample_role"] ==
            "previously-inspected-retrospective-development"
            and observation["cut"] == lead["cut"]
            and edgar["accession"] == selected["accession"]
            and edgar["cik"] == selected["cik"]
            and edgar["url"] == selected["full_submission_url"]
            and edgar["bytes"] == selected["full_submission_size_bytes_reported_in_index"],
            "Observed original does not match the reviewed SEC source lead")
    require(source["workflow_run"] == 42862554153 and
            source["extracted_fsd_json"]["artifact_sha256"] ==
            "464019f23f683c8e65d7b85554ef9d121c12f3882a0d8d27f59ba4c49838f6c5"
            and source["extracted_fsd_json"]["original_sec_zip_rows_reextracted"] is False,
            "Research extract lineage or scope changed")
    for row in (fsd, edgar):
        require(re.fullmatch("[0-9a-f]{64}", row["sha256"]) is not None
                and row["bytes"] > 100
                and row["original_file_bytes_committed"] is False
                and datetime.fromisoformat(row["retrieved_utc"]).astimezone(
                    timezone.utc).year == 2026,
                "Downloaded source receipt is incomplete or overstated")
    require(fsd["sha256"] == "9a2cbbaf39c94aa642b33d512f4def92b198d3bfd12d2267bcd27abe55b9902d"
            and edgar["sha256"] == "869604009236bade7152e0275bc940cd6f625af066d8d296ae27a9cf6477fed8",
            "Original download hashes differ from the observed receipts")
    accepted = observation["accepted_eastern"]
    reported = as_filed_acceptance(accepted["fsd_as_reported"])
    actual = as_filed_acceptance(accepted["original_edgar_header"])
    require(0 < (actual - reported).total_seconds() < 60 and
            reported.second == 0 and
            accepted["precision_relation"] == "same-minute-only-not-exact"
            and accepted["original_exact_acceptance_checked_against_research_cut"] is True
            and actual <= datetime.fromisoformat(observation["cut"]).astimezone(timezone.utc)
            and accepted["originally_public_at_cut_independently_verified"] is False,
            "FSD minute timestamp must not be promoted to exact first publication")
    facts = observation["selected_numeric_facts"]
    rows = facts["rows"]
    observed_amounts = {
        "2023-09-30": "22291000000.0000",
        "2024-09-30": "24667000000.0000",
    }
    require(facts["tag"] == "NetIncomeLoss"
            and facts["taxonomy"] == "us-gaap/2024"
            and facts["uom"] == "USD" and facts["quarters"] == 1
            and len(rows) == facts["selected_fsd_rows"] == 4
            and sum(not row["segment"] for row in rows) == facts["unsegmented_rows"] == 2
            and {(row["period_end"], row["segment"]) for row in rows} ==
            {(period, segment) for period in ("2023-09-30", "2024-09-30")
             for segment in ("", "EquityComponents=RetainedEarnings;")}
            and all(Decimal(row["value_decimal"]).is_finite() and
                    row["value_decimal"] == observed_amounts.get(row["period_end"])
                    for row in rows)
            and facts["matched_against_original_inline_document"] is False
            and facts["full_numeric_coverage_verified"] is False,
            "Research-derived SEC facts are missing, ambiguous or falsely certified")
    require(all(v is False for k, v in observation["source_review"].items()
                if k != "fsd_is_derived_not_a_vintage_of_original_filing")
            and observation["source_review"]["fsd_is_derived_not_a_vintage_of_original_filing"]
            and observation["eligible_full_engine_cuts_added"] == 0
            and observation["confirmatory_origins_added"] == 0
            and observation["predictive_validation"] == "not-established",
            "Research observations must never count as admissible origins")
    return True


class SecFirstCutObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs = json.loads(EVIDENCE.read_text())
        cls.lead = json.loads(LEADS.read_text())

    def test_original_receipts_are_retained_without_pit_promotion(self):
        self.assertTrue(audit(self.obs, self.lead))

    def test_changing_metadata_does_not_fabricate_exact_or_pit_evidence(self):
        for mutate in ("time", "hash", "acceptance", "segment", "amount", "eligibility"):
            changed = copy.deepcopy(self.obs)
            if mutate == "time":
                changed["accepted_eastern"]["original_edgar_header"] = "2024-10-30 16:08:00"
            elif mutate == "hash":
                changed["source_provenance"]["original_edgar_filing"]["sha256"] = "0"*64
            elif mutate == "acceptance":
                changed["accepted_eastern"]["originally_public_at_cut_independently_verified"] = True
            elif mutate == "segment":
                changed["selected_numeric_facts"]["rows"][1]["segment"] = ""
            elif mutate == "amount":
                changed["selected_numeric_facts"]["rows"][0]["value_decimal"] = "1.0000"
            else:
                changed["eligible_full_engine_cuts_added"] = 1
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                audit(changed, self.lead)


if __name__ == "__main__":
    unittest.main()
