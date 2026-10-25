"""Pruebas del candidato GJR-GARCH-t; nunca modifica el optimizador."""
import math
import unittest
import numpy as np

from scripts.volatility_research import (
    fit_gjr_t, updated_variance, ewma_next, prices_to_returns,
    walk_forward, link_known_events, qlike,
)


def synthetic_history(n=410):
    rng = np.random.default_rng(20261025)
    variance = 1.0  # percent squared
    close = 100.
    rows = [{"date": "2025-01-01", "adj_close": close}]
    from datetime import date, timedelta
    base = date(2025, 1, 2)
    for i in range(n):
        e = float(rng.standard_t(8) * math.sqrt(6/8) * math.sqrt(variance))
        close *= math.exp(e / 100)
        rows.append({"date": (base+timedelta(days=i)).isoformat(), "adj_close": close})
        variance = .04 + .06*e**2 + (.11*e**2 if e<0 else 0) + .82*variance
    return rows


class VolatilityResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = synthetic_history()
        cls.as_of = cls.rows[-1]["date"]
        cls.dates, cls.returns = prices_to_returns(cls.rows, cls.as_of)

    def test_gjr_parameters_are_admissible_and_deterministic(self):
        a = fit_gjr_t(self.returns[:330], self.dates[329])
        b = fit_gjr_t(self.returns[:330], self.dates[329])
        self.assertTrue(a.success)
        self.assertAlmostEqual(a.omega, b.omega, places=8)
        self.assertAlmostEqual(a.alpha, b.alpha, places=8)
        self.assertGreaterEqual(a.gamma, 0)
        self.assertLess(a.persistence, 1)
        self.assertGreater(a.nu, 2)
        self.assertGreater(a.next_variance_pct2, 0)
        self.assertEqual(a.training_end, self.dates[329])

    def test_negative_shock_can_raise_variance_more_than_positive(self):
        fit = fit_gjr_t(self.returns[:330], self.dates[329])
        from dataclasses import replace
        fit = replace(fit, gamma=0.2)
        below = updated_variance(fit, 1., (fit.mean_pct-3)/100)
        above = updated_variance(fit, 1., (fit.mean_pct+3)/100)
        self.assertGreater(below, above)

    def test_symmetric_candidate_cannot_fake_negative_effect(self):
        fit = fit_gjr_t(self.returns[:330], self.dates[329], asymmetric=False)
        self.assertEqual(fit.gamma, 0)
        self.assertLess(fit.persistence, 1)

    def test_asof_retains_only_known_price_history(self):
        cutoff = self.dates[310]
        dates, returns = prices_to_returns(self.rows, cutoff)
        self.assertEqual(dates[-1], cutoff)
        self.assertEqual(len(dates), len(returns))
        changed = [dict(x) for x in self.rows]
        changed[-1]["adj_close"] *= 50
        self.assertTrue(np.array_equal(
            prices_to_returns(self.rows, cutoff)[1],
            prices_to_returns(changed, cutoff)[1],
        ))

    def test_no_causal_absolution_for_later_news(self):
        events = [{
            "event_id": "results-test", "source_url": "https://example.org/releases",
            "published_at_utc": "2026-10-24T18:00:00Z",
            "known_at_utc": "2026-10-24T18:20:00Z",
        }]
        rows = link_known_events("2026-10-24", events, "2026-10-23T23:59:59Z")
        self.assertEqual(rows[0]["classification"], "temporal_coincidence_not_causality")
        self.assertFalse(rows[0]["known_before_forecast"])
        self.assertEqual(link_known_events("2026-10-23", events, "2026-10-23T23:59:59Z"), [])

    def test_ewma_and_qlike_finite(self):
        h = ewma_next(self.returns[:300], 0)
        self.assertTrue(math.isfinite(qlike(h, 0, 0)))
        self.assertGreater(h, 0)

    def test_walk_forward_is_shadow_and_stores_all_errors(self):
        result = walk_forward(self.rows, self.as_of,
                              train_window=300, test_days=24,
                              refit_every=12)
        self.assertTrue(result["not_promoted"])
        self.assertEqual(len(result["forecasts"]), 24)
        self.assertEqual(result["out_of_sample_days"], 24)
        self.assertGreater(result["gjr_valid_days"], 0)
        self.assertTrue(all(row["predictive_error_retained"] for row in result["forecasts"]))
        self.assertTrue(all(row["gjr_parameters_trained_through"] < row["for_date"]
                            for row in result["forecasts"] if row["gjr_qlike"] is not None))
        self.assertTrue(math.isfinite(result["ewma_qlike"]))
        self.assertTrue(math.isfinite(result["gjr_qlike"]))

    def test_malformed_prices_are_rejected_not_imputed(self):
        bad = list(self.rows)
        bad[-1] = dict(bad[-1], adj_close=None)
        with self.assertRaisesRegex(ValueError, "no válido"):
            prices_to_returns(bad, self.as_of)
        with self.assertRaises(ValueError):
            prices_to_returns(self.rows+[self.rows[-1]], self.as_of)


if __name__ == "__main__":
    unittest.main()
