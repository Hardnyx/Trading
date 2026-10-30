import copy
from datetime import date, timedelta
import unittest

from scripts.account_inputs import account_origins, prepare_account_inputs


def fixture():
    day, end, history = date(2022, 1, 3), date(2023, 2, 3), []
    while day <= end:
        if day.weekday() < 5:
            history.append({"date": day.isoformat(), "adj_close": 100, "close": 100})
        day += timedelta(days=1)
    market = {"price_as_of": end.isoformat(), "assets": [
        {"symbol": "SPY", "type": "etf", "history": history},
        {"symbol": "A", "type": "stock", "splits": []}]}
    archived = {"price_cut": end.isoformat(), "sources": {"A": {"rows": [
        {"start": "2022-01-01", "end": "2022-12-31", "filed": "2023-01-15",
         "val": 5, "form": "10-K", "accn": "test"}]}}}
    return market, archived


class AccountInputs(unittest.TestCase):
    def test_review_does_not_require_twenty_one_future_sessions(self):
        market, archived = fixture()
        result = prepare_account_inputs(market, archived)
        self.assertEqual(result["origins"][-1]["origin"], "2023-01-31")
        self.assertEqual(result["origins"][-1]["facts"][0]["eps"]["value"], 5)
        self.assertLess(len([r for r in market["assets"][0]["history"] if r["date"] > "2023-01-31"]), 21)
        self.assertTrue(all(r["origin"][:7] < "2023-02" for r in result["origins"]))

    def test_missing_sources_keep_the_review_and_its_denominator(self):
        market, archived = fixture()
        archived["sources"] = {}
        result = prepare_account_inputs(market, archived)
        self.assertEqual([r["origin"] for r in result["origins"]], account_origins(market))
        self.assertTrue(all(r["facts"] == [] for r in result["origins"]))
        self.assertEqual(result["exclusions"]["missing_companyfacts"], len(result["origins"]))

    def test_later_filings_and_prices_do_not_rewrite_old_facts(self):
        market, archived = fixture()
        original = prepare_account_inputs(market, archived)
        later = copy.deepcopy(archived)
        later["sources"]["A"]["rows"].append(dict(later["sources"]["A"]["rows"][0], filed="2023-02-01", val=999))
        self.assertEqual(prepare_account_inputs(market, later)["origins"], original["origins"])
        market["assets"][0]["history"][0]["adj_close"] = 99999
        self.assertEqual(prepare_account_inputs(market, archived)["origins"], original["origins"])

    def test_ambiguous_calendar_and_mismatched_cut_are_rejected(self):
        market, archived = fixture()
        market["assets"][0]["history"].append(market["assets"][0]["history"][-1])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            prepare_account_inputs(market, archived)
        archived["price_cut"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "Mismatched"):
            prepare_account_inputs(market, archived)
