"""Adversarial tests for dated historical risk-fit evidence intake."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_risk_fit_intake import validate, template


def write_json(root, name, obj):
    raw = (json.dumps(obj, sort_keys=True) + "\n").encode()
    (root / name).write_bytes(raw)
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}


def fixture(root):
    raw = b"archived synthetic source, not a historical price"
    (root / "source.bin").write_bytes(raw)
    source_sha = hashlib.sha256(raw).hexdigest()
    policy = {
        "schema": "risk-fit-policy-v1", "model": "ewma",
        "policy_id": "development-fixed-2026",
        "selected_at": "2026-11-08T13:00:00Z",
        "selection_data_end": "2024-12-30",
        "selection_mode": "fixed", "all_trials_recorded": False,
    }
    training = {
        "schema": "risk-fit-training-v1", "cut": "2024-12-31",
        "observations": [
            {"instrument_id": "FIGI:TEST1", "observation_date": d,
             "label_end": d, "known_at": f"{d}T21:10:00Z",
             "source_sha256": source_sha}
            for d in ("2024-12-27", "2024-12-30")]
    }
    policy_ref = write_json(root, "policy.json", policy)
    training_ref = write_json(root, "training.json", training)
    fit = {
        "schema": "risk-fit-result-v1", "cut": "2024-12-31",
        "model": "ewma", "policy_sha256": policy_ref["sha256"],
        "training_sha256": training_ref["sha256"],
        "fitted_at": "2026-11-08T13:02:00Z", "observations": 2,
        "parameters": {"lambda": 0.94}
    }
    fit_ref = write_json(root, "fit.json", fit)
    manifest = {
        "schema": "historical-risk-fit-intake-v1", "cut": "2024-12-31",
        "decision_at": "2024-12-31T21:30:00Z",
        "retrieved_at": "2026-11-08T14:00:00Z",
        "temporal_basis": "retrospective_reconstruction",
        "source_reference": "synthetic-unittest",
        "policy": policy_ref, "training": training_ref, "fit": fit_ref,
        "sources": [{
            "path": "source.bin", "sha256": source_sha,
            "provider": "synthetic", "claimed_available_at": "2024-12-30T21:15:00Z",
            "collected_at": "2026-11-08T13:30:00Z",
            "temporal_basis": "retrospective_reconstruction",
        }]
    }
    write_json(root, "manifest.json", manifest)
    return manifest, policy, training, fit


class RiskFitIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest, self.policy, self.training, self.fit = fixture(self.root)

    def change(self, name, payload):
        ref = write_json(self.root, name + ".json", payload)
        self.manifest[name] = ref
        if name == "policy":
            self.fit["policy_sha256"] = ref["sha256"]
            self.manifest["fit"] = write_json(self.root, "fit.json", self.fit)
        elif name == "training":
            self.fit["training_sha256"] = ref["sha256"]
            self.manifest["fit"] = write_json(self.root, "fit.json", self.fit)
        write_json(self.root, "manifest.json", self.manifest)

    def check(self):
        return validate(self.root, "2024-12-31")

    def test_valid_reconstruction_does_not_certify_historical_parameter(self):
        result = self.check()
        self.assertEqual(result["training_rows"], 2)
        self.assertEqual(result["distinct_instruments"], 1)
        self.assertFalse(result["policy_claims_pre_cut_selection"])
        self.assertFalse(result["fit_claims_pre_cut_execution"])
        self.assertFalse(result["historical_model_parameters_certified"])
        self.assertFalse(result["full_engine_replay_ready"])
        self.assertFalse(result["fit_recomputed_from_original_inputs"])
        self.assertEqual(template("2024-12-31")["sources"], [])

    def test_future_known_training_row_rejected(self):
        self.training["observations"][0]["known_at"] = "2025-01-02T14:00:00Z"
        self.change("training", self.training)
        with self.assertRaisesRegex(ValueError, "future-known"):
            self.check()

    def test_future_label_rejected_even_when_observation_is_old(self):
        self.training["observations"][0]["label_end"] = "2025-01-21"
        self.change("training", self.training)
        with self.assertRaisesRegex(ValueError, "Unmatured"):
            self.check()

    def test_invalid_utc_offset_and_premarket_decision_rejected(self):
        self.manifest["decision_at"] = "2024-12-31T15:30:00Z"
        write_json(self.root, "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "post-close"):
            self.check()
        self.manifest["decision_at"] = "2024-12-31T16:30:00"
        write_json(self.root, "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "Timezone missing"):
            self.check()

    def test_rejects_checksum_tampering(self):
        (self.root / "source.bin").write_bytes(b"mutated")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.check()

    def test_fit_must_bind_exact_policy_and_training_bytes(self):
        self.policy["policy_id"] = "mutated but manifest updated"
        self.manifest["policy"] = write_json(self.root, "policy.json", self.policy)
        write_json(self.root, "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "Fit does not bind"):
            self.check()

    def test_refuses_unsafe_source_path_and_missing_source_binding(self):
        self.manifest["sources"][0]["path"] = "../leak.bin"
        write_json(self.root, "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.check()
        self.manifest["sources"][0]["path"] = "source.bin"
        self.training["observations"][0]["source_sha256"] = "0"*64
        self.change("training", self.training)
        with self.assertRaisesRegex(ValueError, "absent original"):
            self.check()

    def test_rejects_duplicated_instrument_day(self):
        self.training["observations"][1]["observation_date"] = "2024-12-27"
        self.training["observations"][1]["label_end"] = "2024-12-27"
        self.change("training", self.training)
        with self.assertRaisesRegex(ValueError, "Duplicate training"):
            self.check()

    def test_rejects_future_policy_selection_data_and_untracked_trials(self):
        self.policy["selection_data_end"] = "2025-01-02"
        self.change("policy", self.policy)
        with self.assertRaisesRegex(ValueError, "Look-ahead"):
            self.check()
        self.policy["selection_data_end"] = "2024-12-30"
        self.policy["all_trials_recorded"] = True
        self.change("policy", self.policy)
        with self.assertRaisesRegex(ValueError, "exhaustive"):
            self.check()

    def test_rejects_nonfinite_or_mismatched_fit(self):
        self.fit["parameters"]["lambda"] = float("nan")
        self.manifest["fit"] = write_json(self.root, "fit.json", self.fit)
        write_json(self.root, "manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            self.check()


if __name__ == "__main__":
    unittest.main()
