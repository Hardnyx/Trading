"""Synthetic vendor extracts for foreign SEC ISINs, including negative as-of cases."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_foreign_isin_vendor_identity import (
    EXPORT_COLUMNS, SCHEMA, foreign_state, manifest_template,
    parse_foreign_export, read_foreign_evidence, reconcile,
)
from scripts.historical_foreign_isin_requests import request_hash


def request_bundle():
    return {
        "schema": "historical-foreign-isin-requests-v1",
        "cut": "2024-12-31", "source_original_sha256": "a" * 64,
        "public_available_after_day": "2024-11-29",
        "requests": [
            {"original_isin": "GB0002634946", "source_positions": [2, 5],
             "reported_spy_weight": .07},
            {"original_isin": "US0378331005".replace("US", "GB"), "source_positions": [8],
             "reported_spy_weight": .03},
        ],
        "foreign_isin_request_positions": 3,
        "distinct_foreign_isin_requests": 2,
        "foreign_isin_request_weight": .1,
        "unresolved_identifier_positions": 0,
        "unresolved_identifier_weight": 0.,
        "source_spy_weight": .1, "original_invalid_cusip_positions": 3,
        "source_vendor_id_certified": False,
        "original_cusip_corrected": False,
        "full_engine_eligible_cuts": 0,
    }


def row(original_isin="GB0002634946", native="VENDOR-001", namespace="FIGI",
        currency="GBP", **changes):
    result = {
        "original_isin": original_isin,
        "provider_instrument_id": native, "id_namespace": namespace,
        "security_type": "COMMON_STOCK", "currency": currency,
        "exchange_mic": "XLON",
        "valid_from": "2000-01-01", "valid_to": "2030-01-01",
        "record_as_of": "2024-12-31",
    }
    result.update(changes)
    return result


def raw_csv(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def with_provenance(rows, provider="fixture", source_hash="c" * 64):
    return [{**r, "_provider": provider, "_source_sha256": source_hash} for r in rows]


class ForeignVendorIdentityTests(unittest.TestCase):
    def test_original_foreign_identity_can_match_without_usd_inference(self):
        queue = request_bundle()
        queue["requests"] = queue["requests"][:1]
        queue["distinct_foreign_isin_requests"] = 1
        queue["foreign_isin_request_positions"] = 2
        queue["foreign_isin_request_weight"] = .07
        queue["original_invalid_cusip_positions"] = 2
        queue["source_spy_weight"] = .07
        parsed = parse_foreign_export(raw_csv([row()]), "2024-12-31")
        report = reconcile(queue, with_provenance(parsed), [], "b" * 64)
        self.assertEqual(report["counts_by_distinct_isin"],
                         {"retrospective-foreign-identity-candidate": 1})
        self.assertEqual(report["positions"][0]["source_positions"], [2, 5])
        self.assertEqual(report["positions"][0]["candidate_security_key"]["quote_currency"], "GBP")
        self.assertFalse(report["positions"][0]["historical_quote_currency_and_fx_verified"])
        self.assertFalse(report["production_eligible"])

    def test_original_isin_check_digit_rejects_bad_source(self):
        with self.assertRaisesRegex(ValueError, "check digit"):
            parse_foreign_export(raw_csv([row(original_isin="GB0002634947")]),
                                 "2024-12-31")
        with self.assertRaisesRegex(ValueError, "columns changed"):
            from scripts.historical_vendor_identity import parse_export
            parse_export(raw_csv([row()]), "2024-12-31")

    def test_temporally_invalid_and_missing_metadata_do_not_pass(self):
        values = [
            (row(valid_from="2025-01-01"), "not-effective-at-cut"),
            (row(valid_from=""), "incomplete-effective-interval"),
            (row(exchange_mic=""), "missing-exchange-mic"),
            (row(currency=""), "missing-quote-currency"),
            (row(native=""), "missing-permanent-id"),
            (row(security_type="BOND"), "unsupported-security-type"),
            (row(valid_from="2024-12-15", record_as_of="2024-11-30"),
             "identity-begins-after-declared-snapshot"),
        ]
        for source, status in values:
            with self.subTest(status=status):
                self.assertEqual(foreign_state(source, "2024-12-31"), status)
        with self.assertRaisesRegex(ValueError, "invalid vendor instrument key|Partial vendor"):
            parse_foreign_export(raw_csv([row(namespace="TICKER")]), "2024-12-31")

    def test_conflicting_vendor_rows_are_not_selected(self):
        q = request_bundle()
        q["requests"] = q["requests"][:1]
        q["distinct_foreign_isin_requests"] = 1
        q["foreign_isin_request_positions"] = 2
        q["foreign_isin_request_weight"] = .07
        q["original_invalid_cusip_positions"] = 2
        q["source_spy_weight"] = .07
        report = reconcile(q, with_provenance([row(), row(native="VENDOR-002")]),
                           [], "b"*64)
        self.assertEqual(report["positions"][0]["status"], "conflicting-provider-identities")
        self.assertIsNone(report["positions"][0]["candidate_security_key"])

    def test_unrequested_isin_is_rejected_before_reconciliation(self):
        q = request_bundle()
        q["requests"] = q["requests"][:1]
        q["distinct_foreign_isin_requests"] = 1
        q["foreign_isin_request_positions"] = 2
        q["foreign_isin_request_weight"] = .07
        q["original_invalid_cusip_positions"] = 2
        q["source_spy_weight"] = .07
        with self.assertRaisesRegex(ValueError, "Unrequested ISIN"):
            reconcile(q, with_provenance([row(original_isin="US0378331005")]), [],
                      "b"*64)

    def test_private_source_hash_and_asof_must_match_original_request(self):
        q = request_bundle()
        q["requests"] = q["requests"][:1]
        q["distinct_foreign_isin_requests"] = 1
        q["foreign_isin_request_positions"] = 2
        q["foreign_isin_request_weight"] = .07
        q["original_invalid_cusip_positions"] = 2
        q["source_spy_weight"] = .07
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            raw = raw_csv([row()])
            (folder / "export.csv").write_bytes(raw)
            template = manifest_template(q)
            self.assertEqual(template["request_sha256"], request_hash(q))
            src = {
                "path": "export.csv", "sha256": hashlib.sha256(raw).hexdigest(),
                "provider": "fixture", "source_reference": "local-export",
                "snapshot_as_of": "2024-12-31",
                "retrieved_at": "2026-11-08T10:00:00Z",
                "temporal_basis": "retrospective_asof_export",
            }
            manifest = {**template, "exports": [src]}
            (folder/"manifest.json").write_text(json.dumps(manifest))
            records, provenance, digest = read_foreign_evidence(folder, q)
            self.assertEqual(len(records), 1)
            self.assertFalse(provenance[0]["historical_public_availability_certified"])
            report = reconcile(q, records, provenance, digest)
            self.assertEqual(report["positions"][0]["status"],
                             "retrospective-foreign-identity-candidate")
            manifest["request_sha256"] = "d"*64
            (folder/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "does not match"):
                read_foreign_evidence(folder, q)
            manifest["request_sha256"] = request_hash(q)
            manifest["source_original_sha256"] = "e"*64
            (folder/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Original SEC filing hash"):
                read_foreign_evidence(folder, q)
            manifest["source_original_sha256"] = "a"*64
            src["snapshot_as_of"] = "2025-01-01"
            (folder/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "later than"):
                read_foreign_evidence(folder, q)
            src["snapshot_as_of"] = "2024-12-31"
            (folder/"export.csv").write_bytes(raw+b"\n")
            (folder/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                read_foreign_evidence(folder, q)

    def test_fixture_provenance_and_zero_provider_rows_remain_unverified(self):
        q = request_bundle()
        q["requests"] = q["requests"][:1]
        q["distinct_foreign_isin_requests"] = 1
        q["foreign_isin_request_positions"] = 2
        q["foreign_isin_request_weight"] = .07
        q["original_invalid_cusip_positions"] = 2
        q["source_spy_weight"] = .07
        report = reconcile(q, [], [], "e"*64)
        self.assertEqual(report["positions"][0]["status"], "no-provider-evidence")
        self.assertFalse(report["historical_security_master_certified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)

    def test_actual_originals_yield_public_unfilled_manifest(self):
        from scripts.historical_foreign_isin_requests import build_requests
        from scripts.historical_sec_alternate_identity import audit
        q = build_requests(audit())
        template = manifest_template(q)
        self.assertEqual(q["distinct_foreign_isin_requests"], 26)
        self.assertEqual(template["exports"], [])
        self.assertEqual(template["request_sha256"], request_hash(q))
        self.assertEqual(template["source_original_sha256"], q["source_original_sha256"])


if __name__ == "__main__":
    unittest.main()
