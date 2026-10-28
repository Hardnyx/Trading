import datetime as dt
import unittest
from scripts.gold_research import evaluate


class GoldResearch(unittest.TestCase):
    def test_only_mature_training_targets_enter_a_prediction(self):
        prices, real, dollar = [], [], []
        for i in range(80):
            day = (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
            prices.append({"date": day, "adj_close": 100 + i + (i % 4)})
            real.append({"date": day, "value": 2 + (i % 7) * .01})
            dollar.append({"date": day, "value": 100 + (i % 11) * .1})
        snapshot = {"price_as_of": prices[-1]["date"], "assets": [{"symbol": "GLD", "history": prices}]}
        report = evaluate(snapshot, real, dollar, step=3, train_origins=6)
        self.assertGreater(len(report["outcomes"]), 0)
        self.assertTrue(all(r["trained_through"] <= r["origin"] < r["maturity"] for r in report["outcomes"]))
        self.assertFalse(report["production_eligible"])
        self.assertEqual(evaluate(snapshot, [], [], step=3)["metrics"]["origins"], 0)
