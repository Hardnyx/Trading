"""Prospective preregistration guards; software tests never assert economic skill."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from scripts.prospective_study_registry import (
    read_contract, check_contract, inspect, candidate_preflight, utc
)


def candidate():
    return {"schema":"full-engine-first-capture-v2",
        "study":"full-engine-prospective-registration-v2","role":"new-full-engine-only",
        "cut":"2026-11-30","month":"2026-11",
        "issued_at":"2026-11-30T22:00:00Z",
        "market_collected_at":"2026-11-30T21:15:00Z",
        "engine_version":"0.35.0","price_kernel_version":"1.0.0",
        "horizons_sessions":[21,63,252],"calibration_end":"2026-11-30",
        "optimizer_executed":True,"orders_recorded":True,
        "evidence":{k:"a"*64 for k in ("market_sha256","inputs_sha256",
            "model_sha256","policy_sha256","risk_calibration_sha256","forecast_sha256")},
        "realized_returns":None,"scoring":None,"future_outcomes":None}


class ProspectiveStudyRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg, cls.old = read_contract()

    def test_real_registry_excludes_old_cuts_and_signal_seals(self):
        r = inspect()
        self.assertEqual(r["prior_development_cuts_excluded"],48)
        self.assertGreaterEqual(r["prior_signal_seals_excluded"],2)
        self.assertEqual(r["eligible_mature_months"],0)
        self.assertEqual(r["minimum_eligible_mature_months"],96)
        self.assertFalse(r["minimum_economic_effects_registered"])
        self.assertFalse(r["formal_inference_allowed"])

    def test_cli_verify_runs_and_reports_zero_confirmatory_origins(self):
        repo = Path(__file__).resolve().parents[1]
        output = subprocess.check_output(
            [sys.executable, str(repo / "scripts/prospective_study_registry.py"),
             "--verify"], cwd=repo, text=True)
        report = json.loads(output)
        self.assertEqual(report["prior_development_cuts_excluded"], 48)
        self.assertEqual(report["eligible_mature_months"], 0)
        self.assertFalse(report["formal_inference_allowed"])

    def test_exact_original_tests_and_family_preserved(self):
        self.assertTrue(check_contract(self.reg,self.old))
        self.assertEqual(len(self.reg["primary_tests"]),7)

    def test_cannot_shrink_history_or_resampling(self):
        for key in ("minimum_mature_eligible_months","minimum_contiguous_months_for_largest_block"):
            reg=copy.deepcopy(self.reg)
            reg["sampling"][key]=48
            with self.assertRaisesRegex(ValueError,"96-month"):
                check_contract(reg,self.old)
        reg=copy.deepcopy(self.reg)
        reg["bootstrap"]["block_lengths_months"]=[12]
        with self.assertRaisesRegex(ValueError,"block inference"):
            check_contract(reg,self.old)

    def test_prior_and_signal_only_records_are_rejected(self):
        c=candidate()
        self.assertFalse(candidate_preflight(c,self.reg)["confirmatory_eligible"])
        c["cut"]="2026-11-06"
        with self.assertRaisesRegex(ValueError,"precedes registration"):
            candidate_preflight(c,self.reg)
        c=candidate()
        c["role"]="monthly-complete-stock-signal-v1"
        with self.assertRaisesRegex(ValueError,"Signal-only"):
            candidate_preflight(c,self.reg)

    def test_future_inputs_and_scores_cannot_enter_first_capture(self):
        for change,pattern in (
            ({"market_collected_at":"2026-12-01T00:00:00Z"},"Source/issuance"),
            ({"calibration_end":"2026-12-02"},"Future risk"),
            ({"future_outcomes":{"realized":1}},"Realized outcomes"),
            ({"engine_version":"0.36.0"},"Unregistered model"),
            ({"orders_recorded":False},"orders not captured")):
            c=candidate()
            c.update(change)
            with self.assertRaisesRegex(ValueError,pattern):
                candidate_preflight(c,self.reg)

    def test_cannot_fabricate_effect_sizes_or_open_family(self):
        for key,field,value,pattern in (
            ("economic_effect_thresholds","return_mse",0.1,"Unjustified"),
            ("activation","formal_inference_enabled",True,"silently activated"),
            ("multiplicity","alpha",0.1,"multiplicity"),
        ):
            reg=copy.deepcopy(self.reg)
            reg[key][field]=value
            with self.assertRaisesRegex(ValueError,pattern):
                check_contract(reg,self.old)

    def test_return_target_cannot_drop_arithmetic_log_distinction(self):
        reg=copy.deepcopy(self.reg)
        reg["forecast_target"]="arithmetic total return in USD including distributions"
        with self.assertRaisesRegex(ValueError,"Model/publishing eligibility"):
            check_contract(reg,self.old)

    def test_parent_cannot_be_reclassified_as_independent(self):
        old=copy.deepcopy(self.old)
        old["independent_holdout"]["registered"]=True
        with self.assertRaisesRegex(ValueError,"reclassified"):
            check_contract(self.reg,old)

    def test_naive_timestamp_is_not_accepted(self):
        with self.assertRaisesRegex(ValueError,"Timezone required"):
            utc("2026-11-30T18:00:00","capture")


if __name__=="__main__":
    unittest.main()
