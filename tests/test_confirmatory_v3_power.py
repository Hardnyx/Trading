"""Outcome-free v3 power arithmetic."""
import unittest

from scripts.confirmatory_v3_power import months_needed, scenarios


class V3PowerTests(unittest.TestCase):
    def test_months_needed_matches_closed_form_without_autocorrelation(self):
        from scipy.stats import norm
        z = norm.ppf(1 - .05 / 3) + norm.ppf(.8)
        n = months_needed(.25)
        self.assertGreaterEqual(n * .25 / n ** .5, z)
        self.assertLess((n - 1) * .25 / (n - 1) ** .5, z)
        self.assertGreater(months_needed(.25, .3), n)

    def test_scenarios_never_read_market_outcomes(self):
        rows = scenarios()
        self.assertTrue(all(r["months_phi03"] >= r["months_phi0"] for r in rows))
        self.assertEqual({r["test"] for r in rows}, {"ranking_ic:21", "net_economic_value:21"})


if __name__ == "__main__":
    unittest.main()
