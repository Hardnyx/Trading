import copy
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.validation_watch import series_diagnostic, holm, review_decision, build_diagnostics, update_watch


def entry(i, hit=False, horizon=1, status="scored"):
    start = date(2025, 1, 1)+timedelta(days=i)
    return {"origin_date": start.isoformat(), "maturity_date": (start+timedelta(days=horizon)).isoformat(), "status": status,
            "kernel": {"var95_exception": hit, "crps": .02, "qlike": 1, "es_residual": 0},
            "ewma_zero_mean": {"crps": .03, "qlike": 1.1}}


class ValidationWatch(unittest.TestCase):
    def test_correlated_asset_rows_do_not_inflate_each_series_sample(self):
        a = series_diagnostic([entry(i) for i in range(10)])
        report = review_decision({"AAA": a, "BBB": a}, 1)
        self.assertEqual(a["nonoverlapping_origins"], 10)
        self.assertFalse(a["formal_coverage_ready"])
        self.assertEqual(report["verdict"], "accumulating")
        self.assertTrue(all(r["p_value"] is None for r in report["tests"]))

    def test_overlap_is_removed_and_missing_or_unissued_windows_break_transitions(self):
        self.assertEqual(series_diagnostic([entry(i, horizon=5) for i in range(12)])["nonoverlapping_origins"], 3)
        rows = [entry(0, True), entry(1, status="missing-original-outcome"), entry(2, True), entry(3)]
        d = series_diagnostic(rows)
        self.assertEqual(d["missing_outcomes"], 1)
        self.assertEqual(d["christoffersen"]["transitions"], 1)
        self.assertIsNone(d["coverage_p"])
        self.assertEqual(series_diagnostic([entry(0), entry(5, True)])["christoffersen"]["transitions"], 0)

    def test_zero_exceptions_are_not_zero_risk_or_proof_of_independence(self):
        d = series_diagnostic([entry(i) for i in range(20)])
        self.assertGreater(d["exact_binomial_95"][1], .16)
        self.assertIsNone(d["independence_p"])
        self.assertEqual(review_decision({"AAA": d}, 1)["verdict"], "not-rejected-unvalidated")

    def test_severe_coverage_rejection_requires_review_without_automatic_parameter_change(self):
        d = series_diagnostic([entry(i, i < 40) for i in range(100)])
        review = review_decision({"AAA": d}, 1)
        self.assertEqual(review["verdict"], "review-required")
        self.assertEqual(review["action"], "suspend-promotion-and-review")
        self.assertFalse(review["automatic_parameter_change"])
        self.assertFalse(review["automatic_trade_authorization"])

    def test_holm_keeps_unavailable_tests_in_the_fixed_family(self):
        adjusted = holm([{"id": "A", "p_value": .02}, {"id": "B", "p_value": None}], .025)
        self.assertAlmostEqual(adjusted[0]["holm_p"], .04)
        self.assertFalse(any(r["reject"] for r in adjusted))

    def test_monthly_alpha_budget_and_block_intervals_do_not_promote_a_model(self):
        budgets = [review_decision({}, i)["alpha"] for i in range(1, 101)]
        self.assertLess(sum(budgets), .05)
        self.assertGreater(sum(budgets), .049)
        d = series_diagnostic([entry(i, i == 3) for i in range(20)])
        self.assertAlmostEqual(d["crps_gain"], .01)
        self.assertAlmostEqual(d["qlike_gain"], .1)
        self.assertIsNotNone(d["crps_gain_block95"])

    def fixture(self):
        dates = [(date(2026, 1, 1)+timedelta(days=i)).isoformat() for i in range(6)]
        snapshot = {"price_as_of": dates[-1], "generated_at": dates[-1]+"T23:00:00Z",
                    "assets": [{"symbol": "SPY", "history": [{"date": d, "adj_close": 100} for d in dates]}]}
        forecast = {"input_price_as_of": dates[0], "issue_ny_date": dates[0], "issued_at": dates[0]+"T23:00:00Z",
                    "price_kernel_version": "1.0.0", "lead_sessions": 2,
                    "publication": {"committed_at": dates[0]+"T23:01:00Z"},
                    "records": [{"symbol": "AAA", "horizon_sessions": 1}]}
        row = entry(0)
        score = {"status": "scored", "price_kernel_version": "1.0.0", "issued_at": forecast["issued_at"],
                 "input_price_as_of": dates[0], "horizon_sessions": 1,
                 "origin_date": dates[2], "maturity_date": dates[3], "rows": [{"symbol": "AAA", **row}]}
        return snapshot, forecast, score

    def test_mature_missing_or_incompatible_score_is_not_reported_as_pending(self):
        snapshot, forecast, score = self.fixture()
        d = build_diagnostics(snapshot, [forecast], {}, "1.0.0")
        self.assertEqual(d["issues"][0]["code"], "missing-or-incompatible-mature-score")
        key = (forecast["input_price_as_of"], 1)
        score["issued_at"] = "wrong"
        self.assertTrue(build_diagnostics(snapshot, [forecast], {key: score}, "1.0.0")["issues"])

    def test_old_kernels_unverified_publications_and_late_publications_do_not_count(self):
        snapshot, forecast, score = self.fixture()
        self.assertEqual(build_diagnostics(snapshot, [forecast], {}, "new")["sealed"], 0)
        forecast["publication"] = None
        self.assertEqual(build_diagnostics(snapshot, [forecast], {}, "1.0.0")["issues"][0]["code"], "unverified-publication")
        forecast["publication"] = {"committed_at": score["origin_date"]+"T23:00:00Z"}
        self.assertEqual(build_diagnostics(snapshot, [forecast], {}, "1.0.0")["issues"][0]["code"], "nonprospective-origin")

    def test_review_is_immutable_and_preview_does_not_write_a_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);(root/"dist/data").mkdir(parents=True)
            snapshot, forecast, score = self.fixture()
            (root/"dist/data/market.json").write_text(json.dumps(snapshot))
            (root/"dist/data/simulator-validation.json").write_text('{"price_kernel_version":"1.0.0"}')
            (root/"dist/data/signal-validation.json").write_text(json.dumps({"sealed": 0, "cohorts": {}, "observed_price_as_of": snapshot["price_as_of"]}))
            directory = root/"data/simulator-validation/forecasts";directory.mkdir(parents=True)
            (directory/"2026-01-01.json.gz").write_bytes(gzip.compress(json.dumps(forecast).encode()))
            pub = {"commit": "fixture", "committed_at": forecast["publication"]["committed_at"]}
            with patch("scripts.validation_watch.publication", return_value=pub):
                update_watch(root, "2026-01-07T23:00:00Z", persist=False)
                self.assertFalse((root/"data/validation-reviews").exists())
                first = update_watch(root, "2026-01-07T23:00:00Z")
                path = root/first["review_path"];raw = path.read_bytes()
                scores = root/"data/simulator-validation/scores";scores.mkdir()
                (scores/"2026-01-01.h1.json.gz").write_bytes(gzip.compress(json.dumps(score).encode()))
                second = update_watch(root, "2026-01-08T23:00:00Z")
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(first["monthly_review"], second["monthly_review"])
                self.assertEqual(second["health"], "complete")

    def test_failed_refresh_stays_visible_until_success_and_does_not_consume_a_monthly_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);(root/"dist/data").mkdir(parents=True)
            snapshot, _, _ = self.fixture()
            (root/"dist/data/market.json").write_text(json.dumps(snapshot))
            (root/"dist/data/simulator-validation.json").write_text('{"price_kernel_version":"1.0.0","sealed":0}')
            (root/"dist/data/signal-validation.json").write_text(json.dumps({"sealed": 0, "cohorts": {}, "observed_price_as_of": snapshot["price_as_of"]}))
            failed = update_watch(root, "2026-01-07T23:00:00Z", upstream="failure")
            self.assertEqual(failed["health"], "incomplete")
            self.assertFalse((root/"data/validation-reviews").exists())
            self.assertEqual(update_watch(root, "2026-01-08T23:00:00Z")["upstream_refresh"], "failure")
            fixed = update_watch(root, "2026-01-09T23:00:00Z", upstream="success")
            self.assertEqual(fixed["health"], "complete")
            self.assertEqual(fixed["monthly_review"]["review_index"], 1)

    def test_first_mature_dates_survive_the_provider_rolling_history_window(self):
        snapshot, forecast, score = self.fixture()
        snapshot["assets"][0]["history"] = snapshot["assets"][0]["history"][4:]
        diagnostics = build_diagnostics(snapshot, [forecast], {(forecast["input_price_as_of"], 1): score}, "1.0.0")
        self.assertEqual(diagnostics["issues"], [])
        self.assertEqual(diagnostics["series"]["1|AAA"]["nonoverlapping_origins"], 1)


if __name__ == "__main__":
    unittest.main()
