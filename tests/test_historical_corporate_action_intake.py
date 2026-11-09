"""Corporate-event as-of and cash-flow guards using synthetic private extracts."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_corporate_action_intake import (
    COLUMNS, private_template, parse_actions, read_event_sources,
    reconcile_actions,
)
from tests.test_historical_raw_price_intake import identity_report
from scripts.historical_raw_price_intake import assess_prices


def raw(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def event(kind="CASH_DIVIDEND", **kwargs):
    defaults = {
        "id_namespace": "FIGI", "provider_instrument_id": "BBG001",
        "exchange_mic": "XNAS", "quote_currency": "USD",
        "event_id": "action-001", "event_type": kind,
        "announced_on": "2024-11-01", "record_as_of": "2024-11-02",
        "ex_date": "2024-11-15", "pay_date": "2024-12-15",
        "split_new_shares": "", "split_old_shares": "",
        "cash_per_share": "0.25", "cash_currency": "USD",
    }
    if kind == "SPLIT":
        defaults.update(pay_date="", split_new_shares="2", split_old_shares="1",
                        cash_per_share="", cash_currency="")
    if kind in {"MERGER", "SPINOFF", "DELISTING", "STOCK_DIVIDEND"}:
        defaults.update(pay_date="", split_new_shares="", split_old_shares="",
                        cash_per_share="", cash_currency="")
    defaults.update(kwargs)
    return defaults


def bar():
    return {
        "id_namespace": "FIGI", "provider_instrument_id": "BBG001",
        "exchange_mic": "XNAS", "quote_currency": "USD",
        "session_date": "2024-12-31", "raw_close": 100.,
        "record_as_of": "2024-12-31",
        "price_basis": "unadjusted-per-share-exchange-close",
    }


def fixture():
    cross = identity_report()
    # One raw price record is enough to identify the candidate but not to certify returns.
    raw_bars = [
        {**bar(), "session_date": "2024-11-14", "record_as_of": "2024-11-14",
         "raw_close": 100.},
        {**bar(), "session_date": "2024-11-15", "record_as_of": "2024-11-15",
         "raw_close": 99.75},
        bar(),
    ]
    prices = assess_prices(cross, raw_bars, [], "e"*64)
    return cross, prices, raw_bars


class CorporateActionIntakeTests(unittest.TestCase):
    def test_cash_dividend_ex_and_payment_are_distinct(self):
        rows = parse_actions(raw([event()]), "2024-12-31", "2024-12-31")
        self.assertEqual(rows[0]["cash_per_share"], .25)
        cross, prices, bars = fixture()
        report = reconcile_actions(cross, prices, rows, [], "f"*64, bars)
        self.assertEqual(report["event_status_counts"],
                         {"retrospective-event-candidate": 1})
        self.assertFalse(report["historical_cashflow_dates_verified"])
        self.assertEqual(report["full_engine_eligible_cuts"], 0)

    def test_split_is_share_ratio_not_cash(self):
        rows = parse_actions(raw([event("SPLIT")]), "2024-12-31", "2024-12-31")
        self.assertEqual(rows[0]["split_ratio"], 2.)
        self.assertIsNone(rows[0]["cash_per_share"])
        with self.assertRaisesRegex(ValueError, "Split must not claim"):
            parse_actions(raw([event("SPLIT", cash_per_share="1")]),
                          "2024-12-31", "2024-12-31")

    def test_late_publication_future_event_and_wrong_cash_are_blocked(self):
        cases = [
            event(record_as_of="2025-01-01"),
            event(announced_on="2025-01-01"),
            event(ex_date="2025-01-01"),
            event(pay_date="2024-11-01"),
            event(cash_currency="GBP"),
            event(cash_per_share="0"), event(cash_per_share="-0.2"),
            event(cash_per_share="nan"), event(cash_per_share="inf"),
            event("SPLIT", split_old_shares="0"),
            event("SPLIT", split_new_shares="-2"),
            event("SPLIT", split_old_shares="nan"),
            event("MERGER", cash_per_share="10"),
        ]
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    parse_actions(raw([row]), "2024-12-31", "2024-12-31")

    def test_unsupported_events_are_preserved_as_blockers(self):
        cross, prices, bars = fixture()
        rows = parse_actions(raw([event("SPINOFF")]), "2024-12-31", "2024-12-31")
        report = reconcile_actions(cross, prices, rows, [], "a"*64, bars)
        self.assertEqual(report["event_status_counts"],
                         {"uninterpreted-reorganization-or-delisting": 1})
        self.assertEqual(report["raw_event_count"], 1)
        self.assertFalse(report["price_adjustment_pipeline_enabled"])

    def test_future_payment_cannot_be_backfilled_as_realized_cash(self):
        cross, prices, bars = fixture()
        rows = parse_actions(raw([event(pay_date="2025-01-15")]),
                             "2024-12-31", "2024-12-31")
        report = reconcile_actions(cross, prices, rows, [], "a"*64, bars)
        self.assertEqual(report["event_status_counts"],
                         {"unsettled-cash-payment-at-cut": 1})

    def test_conflicting_same_day_events_quarantined_and_duplicate_id_rejected(self):
        cross, prices, bars = fixture()
        r1, r2 = event(), event(event_id="action-002", cash_per_share="1.75")
        rows = parse_actions(raw([r1, r2]), "2024-12-31", "2024-12-31")
        report = reconcile_actions(cross, prices, rows, [], "a"*64, bars)
        self.assertEqual(report["event_status_counts"],
                         {"conflicting-event-type-and-ex-date": 2})
        with self.assertRaisesRegex(ValueError, "Duplicate corporate event ID"):
            reconcile_actions(cross, prices, rows[:1] * 2, [], "a"*64, bars)

    def test_event_not_in_security_master_or_wrong_exchange_rejected(self):
        cross, prices, bars = fixture()
        rows = parse_actions(raw([event(provider_instrument_id="UNKNOWN")]),
                             "2024-12-31", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "no cross-source"):
            reconcile_actions(cross, prices, rows, [], "a"*64, bars)
        rows = parse_actions(raw([event(exchange_mic="XLON")]),
                             "2024-12-31", "2024-12-31")
        with self.assertRaisesRegex(ValueError, "listing or quote"):
            reconcile_actions(cross, prices, rows, [], "a"*64, bars)

    def test_no_price_history_never_claims_action_coverage(self):
        cross = identity_report()
        prices = assess_prices(cross, [], [], "b"*64)
        rows = parse_actions(raw([event()]), "2024-12-31", "2024-12-31")
        report = reconcile_actions(cross, prices, rows, [], "a"*64, [])
        self.assertEqual(report["event_status_counts"],
                         {"no-raw-price-history-for-action": 1})
        self.assertEqual(report["source_positive_spy_positions"], 3)

    def test_original_bytes_hashes_and_price_contract_are_required(self):
        cross, prices, bars = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_bytes = raw([event()])
            (root / "actions.csv").write_bytes(source_bytes)
            ref = {
                "path": "actions.csv",
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "provider": "synthetic", "source_reference": "unit-test",
                "snapshot_as_of": "2024-12-31",
                "retrieved_at": "2026-11-09T02:00:00Z",
                "temporal_basis": "retrospective_asof_export",
            }
            manifest = {**private_template(cross, prices), "exports": [ref]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            rows, sources, digest = read_event_sources(root, cross, prices)
            self.assertEqual(len(rows), 1)
            self.assertFalse(sources[0]["independent_contemporaneous_proof"])
            self.assertEqual(len(digest), 64)
            manifest["raw_price_report_sha256"] = "a"*64
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "not bound"):
                read_event_sources(root, cross, prices)
            manifest["raw_price_report_sha256"] = private_template(cross, prices)[
                "raw_price_report_sha256"]
            ref["snapshot_as_of"] = "2025-01-01"
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "post-cut"):
                read_event_sources(root, cross, prices)
            ref["snapshot_as_of"] = "2024-12-31"
            (root / "actions.csv").write_bytes(source_bytes + b"\n")
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                read_event_sources(root, cross, prices)


    def test_post_effective_records_remain_quarantined(self):
        cross, prices, bars = fixture()
        rows = parse_actions(raw([event(record_as_of="2024-11-20")]),
                             "2024-12-31", "2024-12-31")
        outcome = reconcile_actions(cross, prices, rows, [], "f"*64, bars)
        self.assertEqual(outcome["event_status_counts"],
                         {"post-effective-event-record-quarantined": 1})
        self.assertFalse(outcome["historical_cashflow_dates_verified"])

    def test_event_requires_original_bar_on_ex_date_and_nearby_prior_session(self):
        cross, prices, bars = fixture()
        row = parse_actions(raw([event()]), "2024-12-31", "2024-12-31")
        without_ex = [b for b in bars if b["session_date"] != "2024-11-15"]
        rebuilt = assess_prices(cross, without_ex, [], "e"*64)
        outcome = reconcile_actions(cross, rebuilt, row, [], "f"*64, without_ex)
        self.assertEqual(outcome["event_status_counts"],
                         {"missing-ex-date-raw-price-bracket": 1})
        self.assertFalse(outcome["positions"][0]["event_refs"][0][
            "raw_price_bridge"]["ex_date_bracket_observed"])
        # A gap of over seven calendar days cannot establish the prior session.
        distant = [{**b, "session_date": "2024-11-01",
                    "record_as_of": "2024-11-01"}
                   if b["session_date"] == "2024-11-14" else b for b in bars]
        rebuilt = assess_prices(cross, distant, [], "e"*64)
        outcome = reconcile_actions(cross, rebuilt, row, [], "f"*64, distant)
        self.assertEqual(outcome["event_status_counts"],
                         {"missing-ex-date-raw-price-bracket": 1})

    def test_split_raw_price_bridge_does_not_create_total_return(self):
        cross, _, bars = fixture()
        bars = [{**b, "raw_close": 50.}
                if b["session_date"] == "2024-11-15" else b for b in bars]
        prices = assess_prices(cross, bars, [], "e"*64)
        rows = parse_actions(raw([event("SPLIT")]), "2024-12-31", "2024-12-31")
        result = reconcile_actions(cross, prices, rows, [], "a"*64, bars)
        ref = result["positions"][0]["event_refs"][0]
        self.assertEqual(ref["event_status"], "retrospective-event-candidate")
        self.assertAlmostEqual(ref["raw_price_bridge"]["split_neutral_price_change"], 0.)
        self.assertEqual(ref["raw_price_bridge"]["unadjusted_price_change"], -.5)
        self.assertFalse(ref["raw_price_bridge"]["cash_payment_created"])
        self.assertFalse(result["price_adjustment_pipeline_enabled"])

    def test_substituted_raw_bars_or_prices_fail_even_with_correct_event_hash(self):
        cross, prices, bars = fixture()
        rows = parse_actions(raw([event()]), "2024-12-31", "2024-12-31")
        changed = [dict(b) for b in bars]
        changed[0]["raw_close"] = 888.
        with self.assertRaisesRegex(ValueError, "exact reported raw-price"):
            reconcile_actions(cross, prices, rows, [], "f"*64, changed)
        changed_report = {**prices, "raw_price_rows": 999}
        with self.assertRaisesRegex(ValueError, "exact reported raw-price"):
            reconcile_actions(cross, changed_report, rows, [], "f"*64, bars)

    def test_zero_event_rows_do_not_certify_no_actions(self):
        cross, prices, bars = fixture()
        result = reconcile_actions(cross, prices, [], [], "a"*64, bars)
        self.assertEqual(result["security_key_event_coverage"],
                         {"no-event-row-not-proof-of-event-absence": 2})
        self.assertFalse(result["absence_of_reported_events_certified"])
        self.assertEqual(result["full_engine_eligible_cuts"], 0)

    def test_public_sec_template_does_not_require_private_data(self):
        from scripts.historical_identity_requests import build_requests
        from scripts.historical_foreign_isin_requests import build_requests as foreign
        from scripts.historical_sec_alternate_identity import audit
        from scripts.historical_identity_cross_namespace_gate import template
        original = build_requests()
        result = template(original, foreign(audit()))
        self.assertEqual(result["positive_spy_positions"], 504)
        self.assertEqual(result["foreign_isin_positions"], 26)
        self.assertEqual(result["vendor_rows_received"], 0)


if __name__ == "__main__":
    unittest.main()
