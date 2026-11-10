"""Protect the original 2024q4 FSD subset from changes and PIT promotion."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.sec_first_cut_fsd_extract import audit, EXTRACT_SHA256, SOURCE, OBSERVATION


class SecFirstCutFsdExtractTests(unittest.TestCase):
    def test_original_artifact_hash_and_all_four_as_filed_rows(self):
        result = audit()
        self.assertEqual(result["fsd_extract_sha256"], EXTRACT_SHA256)
        self.assertEqual(result["selected_derived_facts"], 4)
        self.assertEqual(result["unsegmented_derived_facts"], 2)
        self.assertFalse(result["original_fsd_zip_reextracted_in_this_check"])
        self.assertFalse(result["historical_point_in_time_certified"])
        self.assertEqual(result["eligible_full_engine_cuts_added"], 0)

    def test_modified_original_artifact_is_rejected_by_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.json"
            path.write_bytes(SOURCE.read_bytes().replace(b"24667000000.0000",
                                                       b"24667000000.0001", 1))
            with self.assertRaisesRegex(ValueError, "differs from original"):
                audit(path)

    def test_mutated_metadata_and_outcomes_cannot_promote_frozen_extract(self):
        original = json.loads(SOURCE.read_bytes())
        expected = json.loads(OBSERVATION.read_bytes())
        for mode in ("amount", "extra", "segment", "archive", "acceptance",
                     "ready", "eligible", "confirmatory", "issuer"):
            case = copy.deepcopy(original)
            if mode == "amount":
                case["facts"][0]["value_decimal_as_filed"] = "2"
            elif mode == "extra":
                case["facts"].append(copy.deepcopy(case["facts"][0]))
            elif mode == "segment":
                case["facts"][1]["segments"] = ""
            elif mode == "archive":
                case["archive_sha256"] = "1"*64
            elif mode == "acceptance":
                case["submissions"][0]["accepted_eastern_as_filed"] = "2024-10-30 16:07:17"
            elif mode == "ready":
                case["facts"][0]["ready_for_historical_valuation"] = True
            elif mode == "eligible":
                case["eligible_full_engine_cuts_added"] = 1
            elif mode == "confirmatory":
                case["confirmatory_origins_added"] = 1
            else:
                case["submissions"][0]["cik"] = "123"
            encoded = (json.dumps(case, indent=2) + "\n").encode("utf-8")
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                file = Path(d) / "source.json"
                file.write_bytes(encoded)
                with self.assertRaises(ValueError):
                    audit(file, expected_hash=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    unittest.main()
