"""Actual SEC JSON report artifacts: reproduce exact subset and reject inflation."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.sec_first_cut_real_numeric_subset import (
    audit, PRIMARY, EMBEDDED, PRIMARY_ARTIFACT_SHA256, EMBEDDED_ARTIFACT_SHA256,
)


class SecFirstCutRealNumericTests(unittest.TestCase):
    def test_original_two_reports_match_artifact_bytes_and_primary_values(self):
        result = audit()
        self.assertEqual(result["primary_report_sha256"], PRIMARY_ARTIFACT_SHA256)
        self.assertEqual(result["embedded_report_sha256"], EMBEDDED_ARTIFACT_SHA256)
        self.assertEqual(result["primary_exact_unsegmented_matches"], 2)
        self.assertEqual(result["embedded_exact_unsegmented_matches"], 2)
        self.assertEqual(result["excluded_segmented_derived_facts"], 2)
        self.assertFalse(result["source_first_publication_independently_verified"])
        self.assertEqual(result["eligible_full_engine_cuts_added"], 0)

    def test_mutated_original_report_bytes_fail_before_any_promotion(self):
        with tempfile.TemporaryDirectory() as d:
            altered = Path(d) / "primary.json"
            altered.write_bytes(PRIMARY.read_bytes().replace(
                b'"exact_match": 2', b'"exact_match": 3'))
            with self.assertRaisesRegex(ValueError,"byte hash differs"):
                audit(primary=altered)

    def test_false_success_and_numeric_changes_rejected_even_with_new_digest(self):
        for mode in ("amount", "status", "segment", "time", "pit", "whole"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                original = json.loads(PRIMARY.read_bytes())
                replica = json.loads(EMBEDDED.read_bytes())
                if mode == "amount":
                    original["rows"][0]["matched_original_primary_value_decimal"] = "1"
                elif mode == "status":
                    replica["comparison_counts"]["exact_literal_match"] = 4
                elif mode == "segment":
                    original["rows"][1]["comparison_status"] = "exact_match"
                elif mode == "time":
                    original["original_header_matches_derived_fsd"] = True
                elif mode == "pit":
                    replica["original_first_publication_independently_verified"] = True
                else:
                    original["full_xbrl_document_numeric_fact_set_reconciled"] = True
                left, right = Path(d)/"primary.json", Path(d)/"secondary.json"
                left.write_text(json.dumps(original,indent=2)+"\n")
                right.write_text(json.dumps(replica,indent=2)+"\n")
                lh = hashlib.sha256(left.read_bytes()).hexdigest()
                rh = hashlib.sha256(right.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    audit(primary=left,embedded=right,
                          primary_digest=lh,embedded_digest=rh)


if __name__ == "__main__":
    unittest.main()
