import copy
import unittest
from scripts.ttm_signal_research import eps_at, dependent_interval, summarize


def fact(start, end, filed, value):
    return {"start": start, "end": end, "filed": filed, "val": value,
            "form": "10-Q", "accn": "0000000001-24-000001"}


class TTMSignalResearch(unittest.TestCase):
    def setUp(self):
        self.rows = [fact("2022-01-01", "2022-12-31", "2023-02-01", 10),
                     fact("2023-01-01", "2023-06-30", "2023-08-01", 7),
                     fact("2022-01-01", "2022-06-30", "2023-08-01", 4)]

    def test_future_and_same_day_filing_cannot_change_old_ttm(self):
        original, _ = eps_at({}, self.rows, "2023-08-31", "2026-10-28")
        self.assertEqual(original["value"], 13)
        amended = self.rows + [fact("2023-01-01", "2023-06-30", "2023-08-31", 999),
                               fact("2023-01-01", "2023-06-30", "2024-02-01", 9999)]
        self.assertEqual(eps_at({}, amended, "2023-08-31", "2026-10-28")[0], original)
        self.assertEqual(eps_at({}, amended, "2023-09-01", "2026-10-28")[0]["value"], 1005)

    def test_ambiguous_selected_fact_rejected_in_both_array_orders(self):
        rows = self.rows + [dict(self.rows[-1], val=999)]
        for ordered in (rows, list(reversed(rows))):
            self.assertEqual(eps_at({}, ordered, "2023-08-31", "2026-10-28"),
                             (None, "conflicting_selected_period"))

    def test_share_units_rebase_without_rewriting_evidence_and_mixed_bases_blocked(self):
        before = copy.deepcopy(self.rows)
        asset = {"splits": [{"date": "2024-06-10", "ratio": 10}]}
        result, reason = eps_at(asset, self.rows, "2023-08-31", "2026-10-28")
        self.assertIsNone(reason)
        self.assertEqual(result["value"], 1.3)
        self.assertEqual(result["reported_value"], 13)
        self.assertEqual(result["components"][0]["val"], 10)
        self.assertEqual(self.rows, before)
        asset["splits"][0]["date"] = "2023-06-10"
        self.assertEqual(eps_at(asset, self.rows, "2023-08-31", "2026-10-28")[1], "mixed_historical_share_basis")

    def test_fy_fallback_is_not_silently_called_current_ttm(self):
        rows = self.rows[:2]  # Missing comparable YTD.
        self.assertEqual(eps_at({}, rows, "2023-08-31", "2026-10-28")[1], "missing_ttm_or_fy_fallback")

    def test_block_intervals_respect_calendar_gaps_and_small_temporal_samples(self):
        self.assertIsNone(dependent_interval([.1]*23, list(range(23)), 12))
        self.assertIsNone(dependent_interval([.1]*24, list(range(23))+[24], 12))
        for bound in dependent_interval([.1]*24, list(range(24)), 12, draws=20):
            self.assertAlmostEqual(bound, .1)

    def test_paired_reference_uses_identical_outcomes_and_does_not_promote_ic(self):
        observations = [{"signal": k, "earnings_yield": k, "score": k,
                         "outcomes": {"252": {"residual_log_return": k, "standardized_residual": k}}} for k in range(35)]
        replay = {"price_cut": "2026-10-28", "origins": [{"origin": "2024-01-31", "outcomes": {"252": "2025-01-31"},
                  "observations": observations}], "input_market_sha256": "x", "input_facts_sha256": "y", "source_hashes": {}, "exclusions": {}}
        report = summarize(replay)
        self.assertEqual(report["summary"][0]["metrics"]["rank_ic_difference_vs_yield"]["mean"], 0)
        self.assertFalse(report["production_eligible"])
        self.assertFalse(report["exact_live_signal"])
        self.assertIsNone(report["summary"][0]["metrics"]["ttm_rank_ic"]["month_block_95_interval"])


if __name__ == "__main__":
    unittest.main()
