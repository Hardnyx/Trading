import copy
import math
import unittest
from scripts.build_volatility import advance_frozen_parameters


class FrozenParameters(unittest.TestCase):
    def fixture(self):
        snapshot = {"price_as_of": "2026-10-02", "generated_at": "2026-10-02T23:00:00Z", "assets": [
            {"symbol": "AAA", "history": [{"date": "2026-09-30", "adj_close": 100},
                {"date": "2026-10-01", "adj_close": 101}, {"date": "2026-10-02", "adj_close": 102}]}]}
        fit = {"status": "accepted", "omega": .01, "alpha": .05, "gamma": .03, "beta": .9,
               "nu": 7, "mean_pct": .01, "variance_next_pct2": 1, "verification": {"observations": 126}}
        return snapshot, {"as_of": "2026-10-01", "instruments": {"AAA": fit}}

    def test_only_state_advances_and_the_archive_is_not_mutated(self):
        snapshot, frozen = self.fixture()
        original = copy.deepcopy(frozen)
        result = advance_frozen_parameters(snapshot, frozen)
        fit = result["instruments"]["AAA"]
        for key in ["omega", "alpha", "gamma", "beta", "nu", "mean_pct", "verification"]:
            self.assertEqual(fit[key], frozen["instruments"]["AAA"][key])
        self.assertNotEqual(fit["variance_next_pct2"], 1)
        error_pct = 100 * math.log(102/101) - .01
        self.assertAlmostEqual(fit["variance_next_pct2"], .01 + .05 * error_pct ** 2 + .9, places=12)
        self.assertEqual(fit["parameter_fit_through"], "2026-10-01")
        self.assertEqual(fit["fitted_through"], "2026-10-02")
        self.assertEqual(frozen, original)

    def test_wrong_month_future_origin_and_missing_prices_fail_closed(self):
        snapshot, frozen = self.fixture()
        for origin in ["2026-09-30", "2026-10-03"]:
            with self.assertRaises(ValueError):
                advance_frozen_parameters(snapshot, dict(frozen, as_of=origin))
        with self.assertRaises(ValueError):
            advance_frozen_parameters(snapshot, dict(frozen, source_market_generated_at="2026-10-03T00:00:00Z"))
        snapshot["assets"][0]["history"] = snapshot["assets"][0]["history"][:1]
        self.assertEqual(advance_frozen_parameters(snapshot, frozen)["instruments"]["AAA"]["status"], "unavailable")
