"""Registro diario de riesgo: sellado prospectivo, puntuación y resumen."""
from datetime import date, timedelta
import math
import unittest
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from scipy.integrate import quad
from scipy.stats import t as student_t

from scripts.risk_ledger import (
    RISK_MODEL_VERSION, build_seal, christoffersen, kupiec, next_session_start,
    prospective_eligibility, score_seal, summarize, tail_block,
)
from scripts import risk_ledger as ledger_module


def history(n=560, end="2026-10-23", seed=7):
    rng = np.random.default_rng(seed)
    days, day = [], date.fromisoformat(end)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    close, rows = 100.0, []
    for d in reversed(days):
        close *= math.exp(rng.normal(0, .012))
        rows.append({"date": d, "close": close, "adj_close": close})
    return rows


def snapshot(rows, cut="2026-10-23", generated="2026-10-23T22:00:00Z"):
    return {"price_as_of": cut, "generated_at": generated, "assets": [
        {"symbol": "AAA", "type": "stock", "history": rows},
        {"symbol": "BBB", "type": "etf", "history": rows[:-3]},
        {"symbol": "CASH", "type": "cash", "history": []},
    ]}


def volatility(cut="2026-10-23", generated="2026-10-23T22:00:00Z", status="accepted"):
    return {"as_of": cut, "source_market_generated_at": generated,
            "training_window": 500, "instruments": {"AAA": {
                "status": status, "fitted_through": cut, "mean_pct": .05,
                "variance_next_pct2": 1.44, "nu": 6.0}}}


class RiskLedgerTests(unittest.TestCase):
    def test_issue_window_matches_the_prospective_journal(self):
        self.assertEqual(next_session_start("2026-10-23"), "2026-10-26")
        snap = {"price_as_of": "2026-10-23", "generated_at": "2026-10-25T18:00:00Z"}
        self.assertTrue(prospective_eligibility(snap, "2026-10-25T20:00:00Z")["eligible"])
        self.assertFalse(prospective_eligibility(snap, "2026-10-23T18:00:00Z")["eligible"])
        self.assertFalse(prospective_eligibility(snap, "2026-10-26T15:00:00Z")["eligible"])
        late = {**snap, "generated_at": "2026-10-26T01:00:00Z"}
        self.assertFalse(prospective_eligibility(late, "2026-10-25T20:00:00Z")["eligible"])

    def test_student_t_tail_is_unit_variance_and_matches_numeric_expected_shortfall(self):
        nu, block = 5.0, tail_block(0.0, 1.0, 5.0)
        scale = math.sqrt((nu - 2) / nu)
        q = student_t.ppf(.05, nu)
        numeric = quad(lambda x: x * student_t.pdf(x, nu), -np.inf, q)[0] / .05
        self.assertAlmostEqual(block["var95_pct"], q * scale, places=10)
        self.assertAlmostEqual(block["es95_pct"], numeric * scale, places=6)
        gaussian = tail_block(.1, 4.0, None)
        self.assertAlmostEqual(gaussian["var95_pct"], .1 - 2 * 1.6448536, places=6)
        self.assertLess(gaussian["es95_pct"], gaussian["var95_pct"])
        # Heavier tails: deeper ES at the same variance.
        self.assertLess(block["es95_pct"], tail_block(0.0, 1.0, None)["es95_pct"])

    def test_seal_requires_a_prospective_issue_and_the_same_calibration_cut(self):
        rows = history()
        snap = snapshot(rows)
        with self.assertRaises(ValueError):
            build_seal(snap, volatility(), b"m", b"v", "2026-10-26T15:00:00Z")
        with self.assertRaises(ValueError):
            build_seal(snap, volatility(generated="2026-10-22T22:00:00Z"),
                       b"m", b"v", "2026-10-24T12:00:00Z")
        seal = build_seal(snap, volatility(), b"m", b"v", "2026-10-24T12:00:00Z")
        self.assertEqual(seal["risk_model_version"], RISK_MODEL_VERSION)
        self.assertEqual(set(seal["instruments"]), {"AAA"})
        self.assertIn("BBB", seal["skipped"])  # stale close is not sealed
        aaa = seal["instruments"]["AAA"]
        self.assertEqual(aaa["selected_reference"], "gjr")
        self.assertEqual(seal["model_scope"], "statistical-references-not-page-engine")
        self.assertAlmostEqual(aaa["gjr"]["variance_pct2"], 1.44)
        self.assertGreater(aaa["ewma"]["variance_pct2"], 0)
        research = build_seal(snap, volatility(status="research_only"), b"m", b"v",
                              "2026-10-24T12:00:00Z")
        self.assertEqual(research["instruments"]["AAA"]["selected_reference"], "ewma")

    def test_scores_first_later_session_and_keeps_missing_outcomes(self):
        rows = history()
        seal = build_seal(snapshot(rows), volatility(), b"m", b"v", "2026-10-24T12:00:00Z")
        self.assertIsNone(score_seal(seal, snapshot(rows)))
        later = [dict(r) for r in rows] + [
            {"date": "2026-10-26", "adj_close": rows[-1]["adj_close"] * math.exp(-.05)},
            {"date": "2026-10-27", "adj_close": rows[-1]["adj_close"]},
        ]
        snap = snapshot(later, cut="2026-10-27")
        snap["assets"] = [a for a in snap["assets"] if a["symbol"] != "BBB"]
        seal["instruments"]["ZZZ"] = seal["instruments"]["AAA"]
        score = score_seal(seal, snap)
        row = score["instruments"]["AAA"]
        self.assertEqual(row["session"], "2026-10-26")
        self.assertAlmostEqual(row["return_pct"], -5.0, places=9)
        self.assertTrue(row["gjr"]["var95_exception"])
        self.assertAlmostEqual(row["gjr"]["z"], (-5.0 - .05) / 1.2, places=9)
        self.assertEqual(score["instruments"]["ZZZ"]["status"], "missing_outcome")

    def test_coverage_tests_and_summary_status(self):
        self.assertAlmostEqual(kupiec(5, 100)["lr"], 0.0, places=12)
        self.assertLess(kupiec(20, 100)["p_value"], .001)
        clustered = christoffersen([[False] * 40 + [True] * 5 + [False] * 40])
        spread = christoffersen([([False] * 16 + [True]) * 5])
        self.assertLess(clustered["p_value"], spread["p_value"])
        self.assertIsNone(christoffersen([[False] * 10])["lr"])
        seal = {"risk_model_version": "9.9.9", "instruments": {}}
        score = {"instruments": {"AAA": {
            "status": "scored", "return_pct": -3.0, "production": "gjr",
            "ewma": {"qlike": 1.5, "var95_exception": True, "es95_pct": -2.5},
            "gjr": {"qlike": 1.2, "var95_exception": True, "es95_pct": -3.0}}}}
        summary = summarize({"2026-10-23": seal, "2026-10-26": seal},
                            {"2026-10-23": score}, "2026-10-27T00:00:00Z")
        version = summary["versions"]["9.9.9"]
        self.assertEqual(version["status"], "accumulating")
        self.assertEqual(version["pending"], ["2026-10-26"])
        self.assertEqual(version["models"]["hybrid_reference"]["var95_exceptions"], 1)
        self.assertAlmostEqual(version["models"]["gjr"]["es95_realized_ratio"], 1.0)
        self.assertAlmostEqual(version["paired_qlike_ewma_minus_gjr"]["mean"], .3)

    def test_transient_missing_outcomes_can_complete_without_rewriting_seals_or_scores(self):
        block = tail_block(0, 1, None)
        seal = {"original_price_as_of": "2026-10-23", "risk_model_version": "1.0.0",
                "instruments": {"AAA": {"production": "ewma", "ewma": block}}}
        with TemporaryDirectory() as temp:
            root = Path(temp) / "ledger"
            root.mkdir()
            seal_file = root / "2026-10-23.json"
            seal_file.write_text(json.dumps(seal))
            original_seal = seal_file.read_bytes()
            market = Path(temp) / "market.json"
            def run(history):
                market.write_text(json.dumps({"price_as_of": "2026-10-26", "assets": [
                    {"symbol": "AAA", "history": history}]}))
                with patch.object(ledger_module, "LEDGER", root), \
                     patch("sys.argv", ["risk_ledger.py", "score", "--snapshot", str(market)]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    ledger_module.main()
            start = [{"date": "2026-10-23", "adj_close": 100}]
            run(start)
            base = root / "scores/2026-10-23.json"
            original_score = base.read_bytes()
            before = ledger_module.read_scores(root / "scores")
            pending = summarize({"2026-10-23": seal}, before, "now")["versions"]["1.0.0"]
            self.assertEqual(pending["scored_sessions"], 0)
            self.assertEqual(pending["pending_instruments"], 1)
            run(start + [{"date": "2026-10-26", "adj_close": 99}])
            after = ledger_module.read_scores(root / "scores")
            row = after["2026-10-23"]["instruments"]["AAA"]
            self.assertEqual(row["status"], "scored")
            self.assertAlmostEqual(row["return_pct"], 100 * math.log(.99))
            run(start + [{"date": "2026-10-26", "adj_close": 90}])
            self.assertEqual(ledger_module.read_scores(root / "scores")["2026-10-23"]["instruments"]["AAA"], row)
            self.assertEqual(seal_file.read_bytes(), original_seal)
            self.assertEqual(base.read_bytes(), original_score)
            self.assertEqual(len(list((root / "scores/completions").glob("*/*.json"))), 1)
            done = summarize({"2026-10-23": seal}, after, "now")["versions"]["1.0.0"]
            self.assertEqual(done["fully_scored_sessions"], 1)
            self.assertEqual(done["pending_instruments"], 0)


if __name__ == "__main__":
    unittest.main()
