import unittest
from scripts.anchor_information_research import known_annual_eps, rank_correlation, block_interval


class InformationResearch(unittest.TestCase):
    def test_future_revisions_do_not_change_an_old_origin_and_split_rebasing_preserves_units(self):
        asset = {"splits": [{"date": "2024-06-10", "ratio": 10}], "financials": {"earnings_history": {"records": [
            {"period_end": "2023-12-31", "filed": "2024-02-01", "value": 10, "form": "10-K"},
            {"period_end": "2023-12-31", "filed": "2025-02-01", "value": 999, "form": "10-K"}]}}}
        result = known_annual_eps(asset, "2024-05-01", "2026-10-27")
        self.assertEqual(result["eps"], 1)
        self.assertEqual(result["filed"], "2024-02-01")
        self.assertIsNone(known_annual_eps(asset, "2023-12-31", "2026-10-27"))

    def test_ties_are_ranked_and_short_dependent_series_do_not_get_an_interval(self):
        self.assertAlmostEqual(rank_correlation([1, 1, 2, 3], [1, 1, 2, 3]), 1)
        self.assertIsNone(rank_correlation([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(block_interval([.1] * 12))
