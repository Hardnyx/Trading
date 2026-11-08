"""Fail-closed regression tests for the first historical-cut provenance audit."""
import copy
import json
from pathlib import Path
import unittest

from scripts.first_cut_source_audit import ROOT, OUTPUT, audit, build_triage, load_inputs


class FirstCutSourceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = load_inputs(ROOT)

    def test_published_triage_reproduces_from_frozen_evidence(self):
        generated = audit(ROOT)
        published = json.loads((ROOT / OUTPUT).read_text(encoding="utf-8"))
        self.assertEqual(generated, published)
        self.assertEqual(generated["candidate_cut"], "2024-12-31")
        self.assertEqual(generated["counts"], {
            "verified_sources": 2, "blocked": 12, "certified_components": 0})
        self.assertEqual(generated["independent_blockers"],
                         ["historical_identifiers", "historical_model_parameters"])
        self.assertFalse(generated["full_engine_replay_ready"])
        self.assertFalse(generated["causal_cut_certified"])

    def test_rejects_conflicting_identifier_lineage(self):
        data = copy.deepcopy(self.inputs)
        data["prices"]["identifier_audit"]["manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Identifier hash disagreement"):
            build_triage(data)

    def test_rejects_later_or_reclassified_spy_filing(self):
        data = copy.deepcopy(self.inputs)
        first = data["inventory"]["candidate_cut"]
        for row in data["readiness"]["matrix"]:
            if row["cut"] == first:
                row["spy_holdings_source"]["available_after_day"] = "2025-01-15"
        with self.assertRaisesRegex(ValueError, "SPY source mismatch"):
            build_triage(data)

    def test_rejects_current_price_identity_promotion(self):
        data = copy.deepcopy(self.inputs)
        data["prices"]["continuous_price_identity_verified"] = True
        with self.assertRaisesRegex(ValueError, "Historical instrument certification changed"):
            build_triage(data)

    def test_rejects_silent_origins_exclusion(self):
        data = copy.deepcopy(self.inputs)
        data["prices"]["matrix"].pop()
        with self.assertRaisesRegex(ValueError, "Missing, duplicated or reordered origin"):
            build_triage(data)

    def test_rejects_status_claim_not_supported_by_preflight(self):
        data = copy.deepcopy(self.inputs)
        row = next(x for x in data["inventory"]["components"]
                   if x["component"] == "historical_identifiers")
        row["status"] = "verified-source"
        row["blockers"] = []
        with self.assertRaisesRegex(ValueError, "historical_identifiers evidence changed"):
            build_triage(data)

    def test_rejects_invented_complete_cut(self):
        data = copy.deepcopy(self.inputs)
        data["plan"]["summary"]["full_engine_eligible_cuts"] = 1
        with self.assertRaisesRegex(ValueError, "Unreviewed full-engine results"):
            build_triage(data)


if __name__ == "__main__":
    unittest.main()
