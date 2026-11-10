"""Source-lineage and look-ahead regression tests for archived pilot parameters."""
import copy
import unittest

from scripts.historical_parameter_audit import (
    audit, build_report, load, validate_origin, invariant_policy_fingerprint,
)


class HistoricalParameterAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol, cls.summary, cls.bundle, cls.full = load()

    def test_real_archives_reconcile_without_historical_policy_claim(self):
        report = audit()
        self.assertEqual(report["cut_count"], 2)
        self.assertEqual([r["cut"] for r in report["cuts"]],
                         ["2024-12-31", "2025-04-30"])
        self.assertFalse(report["production_eligible"])
        self.assertEqual(report["historical_model_parameters_verified"], 0)
        policy = report["retrospective_fixed_policy_audit"]
        self.assertTrue(policy["policy_equal_across_development_cuts"])
        self.assertTrue(policy["engine_version_equal_across_development_cuts"])
        self.assertFalse(policy["historically_pre_registered_policy"])
        self.assertFalse(policy["historical_training_source_independently_certified"])
        self.assertEqual(policy["full_engine_eligible_cuts_added"], 0)
        self.assertEqual(len(policy["policy_fingerprint_sha256"]), 64)
        for cut in report["cuts"]:
            self.assertFalse(cut["risk_parameter_policy_predefined_at_cut"])
            self.assertFalse(cut["training_history_source_is_historical_vendor_vintage"])
            self.assertFalse(cut["historical_model_parameters_certified"])
            self.assertEqual(cut["engine_calibration_end"], cut["cut"])
            self.assertEqual(cut["risk_policy"]["volatilityMode"], "ewma")
            self.assertEqual(cut["registered_request_seed"], self.protocol["seed"])
            self.assertEqual(len(cut["registered_request_sha256"]), 64)

    def test_compact_review_cannot_substitute_request_receipt(self):
        summary = copy.deepcopy(self.summary)
        summary["results"][0]["request_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "receipt mismatch: request_sha256"):
            build_report(self.protocol, summary, self.bundle, self.full)

    def test_compact_review_cannot_substitute_engine_snapshot_receipt(self):
        summary = copy.deepcopy(self.summary)
        summary["results"][0]["engine_snapshot_json_sha256"] = "0" * 64
        with self.assertRaisesRegex(
                ValueError, "receipt mismatch: engine_snapshot_json_sha256"):
            build_report(self.protocol, summary, self.bundle, self.full)

    def test_compact_review_cannot_substitute_stored_snapshot_receipt(self):
        summary = copy.deepcopy(self.summary)
        summary["results"][0]["stored_snapshot_sha256"] = "0" * 64
        with self.assertRaisesRegex(
                ValueError, "receipt mismatch: stored_snapshot_sha256"):
            build_report(self.protocol, summary, self.bundle, self.full)

    def test_full_results_cannot_substitute_request_receipt(self):
        full = copy.deepcopy(self.full)
        full["results"][0]["request_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "receipt mismatch: request_sha256"):
            build_report(self.protocol, self.summary, self.bundle, full)

    def test_effective_simulation_seed_must_match_registered_request(self):
        full = copy.deepcopy(self.full)
        full["results"][0]["proposal"]["settings"]["seed"] = self.protocol["seed"] + 1
        with self.assertRaisesRegex(ValueError, "seed differs from registered"):
            build_report(self.protocol, self.summary, self.bundle, full)

    def test_future_training_price_fails_before_replay(self):
        origin = copy.deepcopy(self.bundle["origins"][0])
        origin["snapshot"]["assets"][0]["history"][-1]["date"] = "2025-01-02"
        with self.assertRaisesRegex(ValueError, "Nonmonotone or missing-cut"):
            validate_origin(origin, self.full["results"][0],
                            self.summary["results"][0], self.protocol)

    def test_future_macro_vintage_fails_before_replay(self):
        origin = copy.deepcopy(self.bundle["origins"][0])
        origin["snapshot"]["macro"][0]["vintage_date"] = origin["cut"]
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            validate_origin(origin, self.full["results"][0],
                            self.summary["results"][0], self.protocol)

    def test_origin_fitted_after_cut_is_rejected(self):
        full = copy.deepcopy(self.full)
        full["results"][0]["prepared"]["calibration_end"] = "2025-01-02"
        with self.assertRaisesRegex(ValueError, "Risk fit calibration"):
            build_report(self.protocol, self.summary, self.bundle, full)

    def test_2026_policy_cannot_be_promoted_to_contemporaneous(self):
        p = copy.deepcopy(self.protocol)
        p["registered_on"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "registration was historically"):
            build_report(p, self.summary, self.bundle, self.full)

    def test_pilot_selection_must_reproduce_frozen_rule(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["schedule"][0]["selected"] = True
        with self.assertRaisesRegex(ValueError, "Pilot selection schedule"):
            build_report(self.protocol, self.summary, bundle, self.full)

    def test_distinct_cut_policy_changes_are_not_presented_as_one_fixed_policy(self):
        full = copy.deepcopy(self.full)
        first = full["results"][0]["proposal"]["settings"]["lambda"]
        full["results"][1]["proposal"]["settings"]["lambda"] = (
            first + 0.05 if first < 0.9 else first - 0.05
        )
        with self.assertRaisesRegex(
                ValueError, "policy changed between historical cuts"):
            build_report(self.protocol, self.summary, self.bundle, full)

    def test_model_version_cannot_drift_across_development_cuts(self):
        full = copy.deepcopy(self.full)
        full["results"][1]["proposal"]["model_version"] = "99.0.0"
        summary = copy.deepcopy(self.summary)
        summary["results"][1]["decision"]["model_version"] = "99.0.0"
        with self.assertRaisesRegex(
                ValueError, "policy changed between historical cuts"):
            build_report(self.protocol, summary, self.bundle, full)

    def test_risk_factor_estimator_observation_count_must_match(self):
        summary = copy.deepcopy(self.summary)
        summary["results"][0]["risk"]["factor_covariance"]["observations"] = (
            summary["results"][0]["risk"]["observations"] - 1
        )
        with self.assertRaisesRegex(ValueError, "risk fit method or observation"):
            build_report(self.protocol, summary, self.bundle, self.full)

    def test_policy_audit_refuses_2026_policy_reclassified_as_pre_cut(self):
        audits = audit()["cuts"]
        protocol = copy.deepcopy(self.protocol)
        protocol["registered_on"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "registration must postdate"):
            invariant_policy_fingerprint(audits, protocol)

    def test_current_volatility_file_cannot_enter_historical_settings(self):
        full = copy.deepcopy(self.full)
        full["results"][0]["proposal"]["settings"]["volatilityData"] = {"source": "current"}
        with self.assertRaisesRegex(ValueError, "Current volatility data"):
            build_report(self.protocol, self.summary, self.bundle, full)


if __name__ == "__main__":
    unittest.main()
