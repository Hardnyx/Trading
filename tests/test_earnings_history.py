from copy import deepcopy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.earnings_history import annual_eps_history, annual_origins, growth_replay, replay_metrics
from scripts.earnings_growth_research import research_report
from scripts import refresh_data


def fact(year, value, publication_year=None, *, accn=None, form="10-K"):
    published = publication_year or year + 1
    return {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": value,
            "filed": f"{published}-02-15", "form": form,
            "accn": accn or f"0000000001-{published % 100:02d}-000001"}


def history(rows, cutoff="2026-10-27"):
    facts = {"EarningsPerShareDiluted": {"units": {"USD/shares": rows}}}
    return annual_eps_history(facts, 1, cutoff, "2026-10-27T18:00:00+00:00")


def long_history():
    return history([r for year in range(2013, 2026) for r in
                    [fact(year, 10 * 1.1 ** (year - 2013)),
                     fact(year - 1, 10 * 1.1 ** (year - 2014), year + 1)]])


class AnnualEarningsEvidence(unittest.TestCase):
    def test_versions_are_kept_and_conflicting_contexts_and_future_facts_are_excluded(self):
        rows = [fact(2024, 10), fact(2024, 1, 2026), fact(2024, 999, 2027),
                fact(2024, 1000, form="DEF 14A"), fact(2023, 7), fact(2023, 8)]
        before = deepcopy(rows)
        result = history(rows)
        self.assertEqual(rows, before)
        self.assertEqual([r["value"] for r in result["records"]], [10, 1])
        self.assertEqual(result["conflicting_periods_excluded"], 1)
        self.assertFalse(result["original_vintages_verified"])
        self.assertTrue(all("/Archives/edgar/data/1/" in r["source_url"] for r in result["records"]))

    def test_split_comparison_uses_both_figures_from_target_filing(self):
        rows = [fact(2023, 100), fact(2022, 90, 2024),
                fact(2024, 11), fact(2023, 10, 2025)]
        replay = growth_replay(history(rows))
        outcome = replay["outcomes"][0]
        self.assertEqual(outcome["origin_eps_at_origin"], 100)
        self.assertEqual(outcome["origin_eps_in_target_filing"], 10)
        self.assertAlmostEqual(outcome["actual_growth"], .1)
        self.assertEqual(replay["status"], "research_only_reconstructed")
        self.assertFalse(replay["production_eligible"])

    def test_missing_comparator_never_mixes_accessions(self):
        result = growth_replay(history([fact(2023, 100), fact(2024, 11)]))
        self.assertEqual(result["annual_origins"], 2)
        self.assertEqual(result["nonpositive_or_missing_comparator"], 2)
        self.assertEqual(result["outcomes"], [])

    def test_later_restating_filings_do_not_rewrite_first_annual_origin(self):
        rows = [fact(2023, 10), fact(2022, 9, 2024),
                fact(2023, 999, 2025, form="10-K/A"),
                fact(2024, 12), fact(2023, 10, 2025)]
        origins = annual_origins(history(rows))
        self.assertEqual(origins[0]["eps"], 10)
        self.assertEqual(origins[0]["filed"], "2024-02-15")

    def test_future_data_cannot_change_earlier_prediction_training_or_band(self):
        before = growth_replay(long_history())
        revised = long_history()
        for row in revised["records"]:
            if row["filed"] > "2022-02-15":
                row["value"] *= 100 if row["period_end"] >= "2023-12-31" else .01
        after = growth_replay(revised)
        old = {r["origin_filed"]: r for r in before["outcomes"]}
        for row in after["outcomes"]:
            if row["origin_filed"] <= "2022-02-15":
                original = old[row["origin_filed"]]
                self.assertEqual(row["candidate"], original["candidate"])
                self.assertEqual(row["band_log90"], original["band_log90"])
                if row["candidate"]["training_latest_filing"]:
                    self.assertLessEqual(row["candidate"]["training_latest_filing"], row["origin_filed"])
                else:
                    self.assertEqual(row["candidate"]["training_observations"], 0)
                self.assertGreater(row["outcome_filed"], row["origin_filed"])

    def test_bands_need_previously_matured_errors_and_metrics_use_paired_rows(self):
        replay = growth_replay(long_history(), .05)
        self.assertIsNone(replay["outcomes"][0]["band_log90"])
        for row in replay["outcomes"]:
            if row["band_log90"] is not None:
                self.assertGreaterEqual(row["band_calibration_observations"], 5)
        metrics = replay_metrics(replay["outcomes"])
        self.assertEqual(metrics["shrinkage"]["observations"], len(replay["outcomes"]))
        self.assertEqual(metrics["paired_with_last_growth"]["observations"],
                         sum("last_growth" in r["predictions"] for r in replay["outcomes"]))
        self.assertLess(metrics["last_growth"]["mae"], 1e-10)
        self.assertGreater(metrics["empirical_band90"]["observations"], 0)

    def test_losses_are_counted_but_do_not_produce_growth_from_negative_eps(self):
        result = growth_replay(history([fact(2023, -2), fact(2022, 1, 2024),
                                       fact(2024, -1), fact(2023, -2, 2025)]))
        self.assertEqual(result["nonpositive_or_missing_comparator"], 2)
        self.assertIsNone(result["latest_candidate"])
        self.assertEqual(result["outcomes"], [])

    def test_financial_collector_retains_dated_history_from_existing_response(self):
        raw = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {"units": {
            "USD/shares": [fact(2024, 11), fact(2023, 10, 2025)]}}}}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(refresh_data, "CACHE", Path(directory)), \
                patch.object(refresh_data, "download", return_value=json.dumps(raw).encode()) as download:
            result = refresh_data.financials(1, "2026-10-27")
        self.assertEqual(download.call_count, 1)
        self.assertEqual(len(result["earnings_history"]["records"]), 2)
        self.assertEqual(result["earnings_history"]["through_filing_date"], "2026-10-27")

    def test_report_never_counts_reconstructed_outcomes_as_prospective(self):
        snapshot = {"generated_at": "2026-10-27T18:00:00+00:00", "assets": [
            {"symbol": "TEST", "type": "stock", "financials": {"earnings_history": long_history()}},
            {"symbol": "MISSING", "type": "stock"}]}
        report = research_report(snapshot, "a" * 64)
        self.assertGreater(report["reconstructed_outcomes"], 0)
        self.assertEqual(report["prospective_outcomes"], 0)
        self.assertFalse(report["production_eligible"])
        self.assertEqual(report["stocks_with_history"], 1)
