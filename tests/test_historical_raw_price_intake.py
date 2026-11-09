"""Adversarial raw-close intake against synthetic historical identity candidates."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_raw_price_intake import (
    PRICE_BASIS, COLUMNS, assess_prices, candidate_requests,
    parse_bars, private_template, read_price_sources, request_csv,
)


def identity_report():
    return {
        "schema": "historical-cross-namespace-private-reconciliation-v1",
        "cut": "2024-12-31",
        "cross_namespace_identity_certified": False,
        "historical_prices_certified": False,
        "full_engine_eligible_cuts": 0,
        "vendor_rows_received": 2,
        "positive_spy_positions": 3, "positive_spy_weight": 1.,
        "positions": [
            {"source_position": 0, "source_spy_weight": .6,
             "cross_source_status": "retrospective-cross-source-candidate",
             "candidate_security_key": {
                 "namespace": "FIGI", "provider_instrument_id": "BBG001",
                 "exchange_mic": "XNAS", "security_type": "COMMON_STOCK"},
             "historical_price_vintage_verified": False, "full_engine_eligible": False},
            {"source_position": 1, "source_spy_weight": .35,
             "cross_source_status": "retrospective-cross-source-candidate",
             "candidate_security_key": {
                 "namespace": "VENDOR", "provider_instrument_id": "ID002",
                 "exchange_mic": "XLON", "security_type": "COMMON_STOCK",
                 "quote_currency": "GBP"},
             "historical_price_vintage_verified": False, "full_engine_eligible": False},
            {"source_position": 2, "source_spy_weight": .05,
             "cross_source_status": "no-admissible-cross-source-candidate",
             "candidate_security_key": None,
             "historical_price_vintage_verified": False, "full_engine_eligible": False},
        ],
    }


def row(day="2024-12-31", close="100.1", **overrides):
    data = {
        "id_namespace": "FIGI", "provider_instrument_id": "BBG001",
        "exchange_mic": "XNAS", "quote_currency": "USD",
        "session_date": day, "raw_close": close,
        "record_as_of": day, "price_basis": PRICE_BASIS,
    }
    data.update(overrides)
    return data


def csv_bytes(rows, fieldnames=COLUMNS):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


class HistoricalRawPriceIntakeTests(unittest.TestCase):
    def test_separate_identity_requests_never_reveal_unsupported_positions(self):
        report = identity_report()
        rows = candidate_requests(report)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["quote_currency"], "USD")
        self.assertEqual(rows[1]["quote_currency"], "GBP")
        self.assertIn("BBG001", request_csv(rows))
        self.assertNotIn("source_position,2", request_csv(rows))
        self.assertEqual(private_template(report)["exports"], [])
        self.assertEqual(len(private_template(report)["identity_report_sha256"]), 64)

    def test_raw_prices_are_not_return_indices_or_adjusted_closes(self):
        rows = parse_bars(csv_bytes([row()]), "2024-12-31", "2024-12-31")
        self.assertEqual(rows[0]["raw_close"], 100.1)
        with self.assertRaisesRegex(ValueError, "Adjusted"):
            parse_bars(csv_bytes([row(price_basis="adjusted-total-return")]),
                       "2024-12-31", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "columns"):
            parse_bars(csv_bytes([row()], fieldnames=COLUMNS + ("adj_close",)),
                       "2024-12-31", "2024-12-31")

    def test_future_observations_and_invalid_prices_are_rejected(self):
        cases = [
            row(day="2025-01-02"),
            row(record_as_of="2025-01-02"),
            row(close="0"), row(close="-1"), row(close="nan"),
            row(close="inf"), row(close="nonsense"),
        ]
        for record in cases:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    parse_bars(csv_bytes([record]), "2024-12-31", "2024-12-31")

    def test_retrospective_bar_rows_do_not_create_full_engine_eligibility(self):
        report = assess_prices(identity_report(), [parse_bars(
            csv_bytes([row()]), "2024-12-31", "2024-12-31")[0]], [], "a"*64)
        self.assertEqual(report["raw_price_rows"], 1)
        self.assertEqual(report["count_by_status"], {
            "insufficient-raw-price-intervals": 1,
            "no-original-price-evidence": 1,
        })
        self.assertFalse(report["original_publication_vintages_verified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)

    def test_competing_bar_versions_and_listing_mismatches_fail_closed(self):
        record = parse_bars(csv_bytes([row()]), "2024-12-31", "2024-12-31")[0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_prices(identity_report(), [record, record], [], "a"*64)
        with self.assertRaisesRegex(ValueError, "currency"):
            assess_prices(identity_report(), [{**record, "quote_currency": "GBP"}], [],
                          "a"*64)
        with self.assertRaisesRegex(ValueError, "no eligible"):
            assess_prices(identity_report(), [{**record, "provider_instrument_id": "UNKNOWN"}],
                          [], "a"*64)

    def test_provider_originals_require_hash_path_cut_and_identity_report(self):
        report = identity_report()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            raw = csv_bytes([row()])
            (folder / "bars.csv").write_bytes(raw)
            source = {
                "path": "bars.csv",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "provider": "vendor-test", "source_reference": "fixture",
                "snapshot_as_of": "2024-12-31",
                "retrieved_at": "2026-11-09T00:00:00Z",
                "temporal_basis": "retrospective_asof_export",
            }
            manifest = {**private_template(report), "exports": [source]}
            (folder / "manifest.json").write_text(json.dumps(manifest))
            rows, receipts, digest = read_price_sources(folder, report)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(digest), 64)
            self.assertFalse(receipts[0]["original_vintage_independently_authenticated"])
            manifest["identity_report_sha256"] = "f"*64
            (folder / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "not bound"):
                read_price_sources(folder, report)
            manifest["identity_report_sha256"] = private_template(report)["identity_report_sha256"]
            source["path"] = "../outside.csv"
            (folder / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                read_price_sources(folder, report)
            source["path"] = "bars.csv"
            (folder / "bars.csv").write_bytes(raw + b"\n")
            (folder / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                read_price_sources(folder, report)

    def test_raw_252_intervals_are_still_research_only(self):
        # Each date is strictly earlier than the cut; no lookahead allowed.
        from datetime import date, timedelta
        base = date(2024, 1, 1)
        records = []
        for i in range(253):
            day = (base + timedelta(days=i)).isoformat()
            records.append(parse_bars(csv_bytes([row(day=day)]),
                                      "2024-12-31", "2024-12-31")[0])
        report = assess_prices(identity_report(), records, [], "a"*64)
        self.assertEqual(report["count_by_status"]["missing-exact-cut-session-close"], 1)
        self.assertEqual(report["full_engine_eligible_cuts"], 0)


    def test_price_receipt_changes_when_close_changes_at_unchanged_dates(self):
        raw = parse_bars(csv_bytes([row()]), "2024-12-31", "2024-12-31")
        original = assess_prices(identity_report(), raw, [], "a"*64)
        changed = [dict(raw[0], raw_close=901.5)]
        modified = assess_prices(identity_report(), changed, [], "a"*64)
        self.assertNotEqual(original["positions"][0]["raw_bar_sha256"],
                            modified["positions"][0]["raw_bar_sha256"])
        self.assertEqual(original["positions"][0]["raw_bar_count"],
                         modified["positions"][0]["raw_bar_count"])
        self.assertEqual(original["positions"][0]["first_session"],
                         modified["positions"][0]["first_session"])
        self.assertEqual(original["positions"][0]["last_session"],
                         modified["positions"][0]["last_session"])
        self.assertEqual(len(original["positions"][0]["raw_bar_sha256"]), 64)
        self.assertEqual(original["full_engine_eligible_cuts"], 0)

    def test_price_receipt_digest_is_order_independent_and_captures_asof(self):
        rows = parse_bars(csv_bytes([row(day="2024-12-30"),
                                     row(day="2024-12-31")]),
                          "2024-12-31", "2024-12-31")
        report = assess_prices(identity_report(), rows, [], "a"*64)
        reversed_report = assess_prices(identity_report(), list(reversed(rows)),
                                        [], "a"*64)
        self.assertEqual(report["positions"][0]["raw_bar_sha256"],
                         reversed_report["positions"][0]["raw_bar_sha256"])
        older = [{**r, "record_as_of": "2024-12-30"}
                 if r["session_date"] == "2024-12-30" else r for r in rows]
        # The same close with different source publication evidence must not
        # reuse an identical receipt.
        newer = [{**r, "record_as_of": "2024-12-31"}
                 if r["session_date"] == "2024-12-30" else r for r in rows]
        self.assertNotEqual(assess_prices(identity_report(), older, [], "a"*64)[
            "positions"][0]["raw_bar_sha256"],
            assess_prices(identity_report(), newer, [], "a"*64)[
                "positions"][0]["raw_bar_sha256"])

    def test_public_sec_study_contract_contains_no_private_price_keys(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_foreign_isin_requests import build_requests as build_foreign
        from scripts.historical_sec_alternate_identity import audit
        from scripts.historical_identity_cross_namespace_gate import template
        result = template(build_requests(), build_foreign(audit()))
        self.assertEqual(result["positive_spy_positions"], 504)
        self.assertEqual(result["foreign_isin_positions"], 26)
        self.assertEqual(result["valid_cusip_positions"], 478)
        self.assertEqual(result["vendor_rows_received"], 0)


if __name__ == "__main__":
    unittest.main()
