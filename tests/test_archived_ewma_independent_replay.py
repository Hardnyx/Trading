"""Independent, deterministic EWMA risk arithmetic and archive rejection tests."""
import copy
from datetime import date, timedelta
import math
import unittest

from scripts.archived_ewma_independent_replay import (
    aligned_returns, audit, check_matrix, check_origin, joint_ewma_covariance,
)


def synthetic_origin():
    cut = "2024-12-31"
    d = date(2024, 12, 31)
    dates = []
    while len(dates) < 80:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d -= timedelta(days=1)
    dates.reverse()
    def asset(symbol, phase):
        history = []
        for i, session in enumerate(dates):
            price = 100 * math.exp(.0002 * i + .015 * math.sin(i / 9 + phase))
            history.append({"date": session, "adj_close": price})
        return {"symbol": symbol, "history": history}
    spy = asset("SPY", 0)
    other = asset("ABC", 1)
    return {
        "cut": cut, "snapshot": {"price_as_of": cut,
                                 "assets": [other, spy]},
    }


def synthetic_record(origin):
    symbols = ["ABC", "SPY", "CASH"]
    assets = [*origin["snapshot"]["assets"],
              {"symbol": "CASH", "history": [
                  {"date": r["date"], "adj_close": 1.0}
                  for r in origin["snapshot"]["assets"][1]["history"]]}]
    days, columns = aligned_returns(assets, origin["cut"])
    cov = joint_ewma_covariance(columns, .94)
    return {"cut": origin["cut"], "prepared": {
        "symbols": symbols, "covariance": cov,
        "observations": len(days), "calibration_end": days[-1],
        "factor_covariance": {"available": True},
        "annual_volatility": [
            {"symbol": symbol, "value": math.sqrt(cov[i][i])}
            for i, symbol in enumerate(symbols)],
    }, "proposal": {"settings": {"lambda": .94, "volatilityMode": "ewma",
                                 "volatilityData": None}}}


class ArchivedEwmaReplayTests(unittest.TestCase):
    def test_reconstructed_covariance_respects_log_return_basis_and_cash(self):
        origin = synthetic_origin()
        result = check_origin(origin, synthetic_record(origin))
        self.assertEqual(result["common_return_intervals"], 79)
        self.assertEqual(result["symbols"], 3)
        self.assertTrue(result["reconstructed_from_archived_adjusted_prices"])
        self.assertFalse(result["causal_parameters_certified"])
        self.assertEqual(result["maximum_absolute_covariance_discrepancy"], 0)

    def test_sample_covariance_60_seed_and_offdiag_shrink(self):
        a = [(.01 if i % 2 else -.01) for i in range(60)]
        b = [2 * r for r in a]
        annual = joint_ewma_covariance([a, b], .94)
        expected_var = 252 * (60 * .01 ** 2 / 59)
        self.assertAlmostEqual(annual[0][0], expected_var, places=12)
        self.assertAlmostEqual(annual[0][1], expected_var * 2 * .95, places=12)
        extended = joint_ewma_covariance([a + [.03], b + [-.02]], .94)
        self.assertAlmostEqual(extended[0][0], .94 * annual[0][0] +
                               .06 * .03 ** 2 * 252, places=12)
        self.assertAlmostEqual(extended[0][1], .94 * annual[0][1] +
                               .06 * .03 * -.02 * 252 * .95, places=12)

    def test_tampered_covariance_is_rejected(self):
        origin = synthetic_origin()
        result = synthetic_record(origin)
        result["prepared"]["covariance"][0][1] += .02
        with self.assertRaisesRegex(ValueError, "differs from independent"):
            check_origin(origin, result)

    def test_future_price_and_reordered_prices_fail_closed(self):
        origin = synthetic_origin()
        record = synthetic_record(origin)
        origin["snapshot"]["assets"][0]["history"][-1]["date"] = "2025-01-01"
        with self.assertRaisesRegex(ValueError, "future dated"):
            check_origin(origin, record)
        origin = synthetic_origin()
        record = synthetic_record(origin)
        origin["snapshot"]["assets"][0]["history"][-1]["date"] = "2024-01-01"
        with self.assertRaisesRegex(ValueError, "Nonmonotone"):
            check_origin(origin, record)

    def test_missing_cash_or_spy_cannot_be_silently_aligned(self):
        origin = synthetic_origin()
        record = synthetic_record(origin)
        origin["snapshot"]["assets"] = origin["snapshot"]["assets"][:1]
        with self.assertRaisesRegex(ValueError, "benchmark"):
            check_origin(origin, record)
        origin = synthetic_origin()
        record = synthetic_record(origin)
        record["prepared"]["symbols"][0] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "Prepared symbol"):
            check_origin(origin, record)

    def test_frozen_archives_match_independent_covariance(self):
        report = audit()
        self.assertEqual(report["schema"], "archived-ewma-independent-replay-v1")
        self.assertTrue(report["numeric_risk_replay_passed"])
        self.assertEqual(len(report["cuts"]), 2)
        self.assertEqual(report["historical_model_parameters_certified"], 0)
        self.assertEqual(report["full_engine_eligible_cuts"], 0)
        self.assertTrue(all(row["common_return_intervals"] >= 20
                            for row in report["cuts"]))


if __name__ == "__main__":
    unittest.main()
