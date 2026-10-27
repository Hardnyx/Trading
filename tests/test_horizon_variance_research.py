"""Varianza a horizonte: la reversión gana cuando la varianza vuelve a su nivel."""
from datetime import date, timedelta
import math
import unittest

import numpy as np

from scripts.horizon_variance_research import evaluate, horizon_forecasts


def history(seed=3, n=900):
    rng = np.random.default_rng(seed)
    close, rows, day = 100.0, [], date(2023, 1, 2)
    for t in range(n):
        # Short volatility bursts that decay: the flat EWMA overreacts to them.
        sigma = 0.04 if t % 120 < 6 else 0.01
        close *= math.exp(rng.normal(0, sigma))
        rows.append({"date": (day + timedelta(days=t)).isoformat(), "adj_close": close})
    return rows


class HorizonVarianceTests(unittest.TestCase):
    def test_forecasts_share_the_same_known_information(self):
        train = np.r_[np.full(499, 0.01), 0.2]
        flat, reverting, centre = horizon_forecasts(train, 63)
        self.assertGreater(flat, reverting)  # a fresh spike decays toward the long-run level
        calm = horizon_forecasts(np.random.default_rng(1).normal(0, 0.01, 500), 63)
        self.assertAlmostEqual(calm[0] / calm[1], 1, delta=0.4)
        self.assertAlmostEqual(horizon_forecasts(train, 1, persistence=0.99)[1],
                               horizon_forecasts(train, 1)[0], places=12)

    def test_reversion_beats_flat_ewma_after_decaying_bursts(self):
        report = evaluate([{"history": history()}], horizons=(63,), persistences=(0.99,))
        row = report[0]
        self.assertGreater(row["observations"], 3)
        self.assertGreater(row["mean_gain_flat_minus_reverting"], 0)


if __name__ == "__main__":
    unittest.main()
