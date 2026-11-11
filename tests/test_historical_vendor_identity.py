"""Negative identity and temporal provenance cases for vendor security-master intake."""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_vendor_identity import (
    COLUMNS, SCHEMA, local_file, parse_export, read_evidence, reconcile, valid_cusip,
    request_hash, row_state, template_csv, valid_cusip_collection_csv,
)


def request_bundle():
    return {"cut": "2024-12-31", "requests": [
        {"source_position": 0, "cusip": "037833100", "original_spy_name": "Issuer A",
         "original_ticker_observation": "AAA", "weight": 0.6},
        {"source_position": 1, "cusip": "594918104", "original_spy_name": "Issuer B",
         "original_ticker_observation": "BBB", "weight": 0.4},
    ]}


def example(cusip="037833100", native="BBG000B9XRY4", namespace="FIGI",
            valid_from="2000-01-01", valid_to="2030-01-01", **overrides):
    row = {
        "cusip": cusip, "provider_instrument_id": native,
        "id_namespace": namespace, "security_type": "COMMON_STOCK",
        "currency": "USD", "exchange_mic": "XNAS",
        "valid_from": valid_from, "valid_to": valid_to,
        "record_as_of": "2024-12-31",
    }
    row.update(overrides)
    return row


def with_source(rows):
    return [{**row, "_source_sha256": "a" * 64, "_provider": "fixture"} for row in rows]


def csv_bytes(rows):
    out = io.StringIO(newline="")
    w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode()


class VendorIdentityTests(unittest.TestCase):
    def test_template_contains_only_sec_requests(self):
        rows = list(csv.DictReader(io.StringIO(template_csv(request_bundle()))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cusip"], "037833100")
        self.assertNotIn("provider_instrument_id", rows[0])

    def test_operational_cusip_queue_excludes_invalid_placeholder(self):
        source = request_bundle()
        source["requests"].append({
            "source_position": 2, "cusip": "000000000",
            "original_spy_name": "Foreign original ISIN route",
            "original_ticker_observation": None, "weight": 0.25,
        })
        complete = list(csv.DictReader(io.StringIO(template_csv(source))))
        usable = list(csv.DictReader(io.StringIO(valid_cusip_collection_csv(source))))
        self.assertEqual(len(complete), 3)
        self.assertEqual(len(usable), 2)
        self.assertEqual([row["source_position"] for row in usable], ["0", "1"])
        self.assertTrue(all(valid_cusip(row["cusip"]) for row in usable))
        self.assertEqual(source["requests"][2]["cusip"], "000000000")

    def test_operational_queue_preserves_weighted_priority_and_original_positions(self):
        source = request_bundle()
        source["requests"][0]["weight"] = 0.2
        source["requests"][1]["weight"] = 0.8
        rows = list(csv.DictReader(io.StringIO(valid_cusip_collection_csv(source))))
        self.assertEqual([row["source_position"] for row in rows], ["1", "0"])
        self.assertEqual([float(row["weight"]) for row in rows], [0.8, 0.2])
        self.assertEqual(rows[0]["cut"], "2024-12-31")
        self.assertNotIn("provider_instrument_id", rows[0])

    def test_real_sec_first_cut_vendor_queue_is_exactly_478_eligible_cusips(self):
        from scripts.historical_identity_requests import build_requests
        original = build_requests()
        complete = list(csv.DictReader(io.StringIO(template_csv(original))))
        usable = list(csv.DictReader(io.StringIO(valid_cusip_collection_csv(original))))
        self.assertEqual(len(complete), 504)
        self.assertEqual(len(usable), 478)
        self.assertEqual(sum(not valid_cusip(r["cusip"]) for r in complete), 26)
        self.assertEqual(
            {int(r["source_position"]) for r in usable},
            {r["source_position"] for r in original["requests"]
             if valid_cusip(r["cusip"])},
        )
        self.assertTrue(all(float(usable[i]["weight"]) >= float(usable[i+1]["weight"])
                            for i in range(len(usable)-1)))

    def test_single_retrospective_binding_remains_noncausal(self):
        report = reconcile(request_bundle(), with_source([example()]), [], "b" * 64)
        self.assertEqual(report["counts"], {
            "no-provider-evidence": 1, "retrospective-identity-candidate": 1})
        self.assertEqual(report["positions"][0]["candidate_security_key"]["namespace"], "FIGI")
        self.assertEqual(report["positions"][0]["candidate_security_key"]["quote_currency"], "USD")
        self.assertIsNone(report["positions"][1]["candidate_security_key"])
        self.assertFalse(report["historical_public_availability_certified"])
        self.assertFalse(report["full_engine_replay_ready"])
        self.assertEqual(report, reconcile(request_bundle(), with_source([example()]), [], "b" * 64))

    def test_conflicting_cusip_bindings_fail_closed(self):
        rows = with_source([example(), example(native="BBGOTHERID2")])
        report = reconcile(request_bundle(), rows, [], "c" * 64)
        self.assertEqual(report["positions"][0]["status"], "conflicting-provider-identities")
        self.assertIsNone(report["positions"][0]["candidate_security_key"])

    def test_same_native_id_cannot_bind_two_cusips_simultaneously(self):
        rows = with_source([example(), example(cusip="594918104")])
        report = reconcile(request_bundle(), rows, [], "c" * 64)
        self.assertEqual(report["counts"], {"provider-key-shared-by-multiple-cusips": 2})
        self.assertTrue(all(p["candidate_security_key"] is None for p in report["positions"]))


    def test_unrequested_valid_cusip_cannot_poison_requested_native_key(self):
        unknown = example(cusip="02079K305")
        self.assertTrue(valid_cusip(unknown["cusip"]))
        with self.assertRaisesRegex(ValueError, "Unrequested CUSIP"):
            reconcile(request_bundle(), with_source([example(), unknown]), [],
                      "c"*64)
        with self.assertRaisesRegex(ValueError, "Unrequested CUSIP"):
            reconcile(request_bundle(), with_source([unknown]), [], "c"*64)

    def test_different_vendor_sources_cannot_silently_merge_one_cusip(self):
        first = with_source([example()])[0]
        second = {**first, "_provider": "second-vendor", "_source_sha256": "b"*64}
        report = reconcile(request_bundle(), [first, second], [], "d"*64)
        self.assertEqual(report["positions"][0]["status"],
                         "conflicting-provider-identities")
        self.assertIsNone(report["positions"][0]["candidate_security_key"])
        self.assertFalse(report["historical_public_availability_certified"])

    def test_single_vendor_source_is_retained_with_permanent_key(self):
        report = reconcile(request_bundle(), with_source([example()]), [],
                           "c"*64)
        identity = report["positions"][0]["candidate_security_key"]
        self.assertEqual(identity["provider"], "fixture")
        self.assertEqual(identity["quote_currency"], "USD")
        self.assertEqual(report["positions"][0]["source_hashes"], ["a"*64])

    def test_native_key_shared_across_provider_exports_quarantines_two_cusips(self):
        one = with_source([example()])[0]
        two = {**one, "cusip": "594918104",
               "_provider": "second-vendor", "_source_sha256": "b"*64}
        report = reconcile(request_bundle(), [one, two], [], "c"*64)
        self.assertEqual(report["counts"],
                         {"provider-key-shared-by-multiple-cusips": 2})
        self.assertTrue(all(x["candidate_security_key"] is None
                            for x in report["positions"]))

    def test_incomplete_dates_cannot_be_promoted(self):
        row = example(valid_from="")
        report = reconcile(request_bundle(), with_source([row]), [], "c" * 64)
        self.assertEqual(report["positions"][0]["status"], "no-temporally-admissible-identity")
        self.assertEqual(report["excluded_row_reasons"]["incomplete-identity-interval"], 1)

    def test_future_and_expired_intervals_are_excluded(self):
        rows = with_source([example(valid_from="2025-01-01"), example(valid_to="2024-01-01")])
        report = reconcile(request_bundle(), rows, [], "c" * 64)
        self.assertEqual(report["excluded_row_reasons"]["not-effective-at-cut"], 2)
        self.assertEqual(report["counts"]["no-temporally-admissible-identity"], 1)


    def test_forward_effective_vendor_snapshot_is_not_backfilled_at_cut(self):
        source = example(valid_from="2024-12-01", record_as_of="2024-11-30")
        parsed = parse_export(csv_bytes([source]), "2024-11-30")
        self.assertEqual(row_state(parsed[0], "2024-12-31"),
                         "identity-begins-after-declared-snapshot")
        report = reconcile(request_bundle(), with_source(parsed), [], "b"*64)
        self.assertEqual(report["counts"]["no-temporally-admissible-identity"], 1)
        self.assertEqual(report["excluded_row_reasons"][
            "identity-begins-after-declared-snapshot"], 1)
        self.assertIsNone(report["positions"][0]["candidate_security_key"])
        self.assertFalse(report["historical_public_availability_certified"])

    def test_cusip_identity_temporal_boundaries_and_missing_record_date(self):
        self.assertEqual(row_state(example(valid_from="2024-11-01",
                                           record_as_of="2024-11-30"),
                                   "2024-12-31"),
                         "retrospective-identity-candidate")
        self.assertEqual(row_state(example(valid_from="2024-12-01",
                                           record_as_of="2024-12-01"),
                                   "2024-12-31"),
                         "retrospective-identity-candidate")
        self.assertEqual(row_state(example(record_as_of="2025-01-01"),
                                   "2024-12-31"),
                         "missing-or-future-record-as-of")
        self.assertEqual(row_state(example(record_as_of=""),
                                   "2024-12-31"),
                         "missing-or-future-record-as-of")

    def test_check_digit_rejects_well_formed_wrong_cusips(self):
        self.assertTrue(valid_cusip("037833100"))
        self.assertTrue(valid_cusip("594918104"))
        self.assertTrue(valid_cusip("02079K305"))
        self.assertTrue(valid_cusip("*@#000009"))
        self.assertFalse(valid_cusip("037833101"))
        self.assertFalse(valid_cusip("594918105"))
        self.assertFalse(valid_cusip("03783310O"))
        self.assertFalse(valid_cusip("000000000"))
        with self.assertRaisesRegex(ValueError, "check digit"):
            parse_export(csv_bytes([example(cusip="037833101")]), "2024-12-31")

    def test_rejects_symbol_as_permanent_namespace(self):
        for namespace in ("TICKER", "ISIN"):
            with self.assertRaisesRegex(ValueError, "Unstable or invalid"):
                parse_export(csv_bytes([example(namespace=namespace)]), "2024-12-31")

    def test_rejects_manifest_future_source_and_altered_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = csv_bytes([example()])
            (root / "source.csv").write_bytes(raw)
            record = {"path": "source.csv", "sha256": hashlib.sha256(raw).hexdigest(),
                      "provider": "vendor-fixture", "source_reference": "fixture",
                      "snapshot_as_of": "2024-12-31", "retrieved_at": "2026-11-08T05:00:00Z",
                      "temporal_basis": "retrospective_asof_export"}
            manifest = {"protocol": SCHEMA, "cut": "2024-12-31",
                        "request_sha256": request_hash(request_bundle()),
                        "exports": [record]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            rows, sources, _ = read_evidence(root, request_bundle())
            self.assertEqual(len(rows), 1)
            self.assertFalse(sources[0]["historical_public_availability_certified"])
            record["snapshot_as_of"] = "2025-01-31"
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "later than"):
                read_evidence(root, request_bundle())
            record["snapshot_as_of"] = "2024-12-31"
            (root / "source.csv").write_bytes(raw + b"\n")
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                read_evidence(root, request_bundle())

    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Absolute"):
                local_file(tmp, "/etc/passwd")
            with self.assertRaisesRegex(ValueError, "escaped"):
                local_file(tmp, "../outside.csv")

    def test_rejects_malformed_csv_and_wrong_record_date(self):
        with self.assertRaisesRegex(ValueError, "snapshot mismatch"):
            parse_export(csv_bytes([example(record_as_of="2025-01-01")]), "2024-12-31")
        with self.assertRaisesRegex(ValueError, "Invalid identity interval"):
            parse_export(csv_bytes([example(valid_from="2025-01-01", valid_to="2024-01-01")]),
                         "2024-12-31")

    def test_currency_type_and_exchange_diagnostics(self):
        rows = [example(currency="EUR"), example(security_type="BOND"),
                example(exchange_mic="")]
        self.assertEqual([row_state(row, "2024-12-31") for row in rows], [
            "non-usd-security", "ineligible-security-type", "missing-exchange"])


if __name__ == "__main__":
    unittest.main()
