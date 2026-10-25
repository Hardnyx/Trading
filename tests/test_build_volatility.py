import unittest
from datetime import date, timedelta
import math
from scripts.build_volatility import compact_volatility


def mock_history(n=640):
    rng=17
    close=100.
    rows=[]
    today=date(2025, 1, 1)
    for i in range(n):
        # Deterministic oscillations preserve reproducibility across runs.
        shock=.006*math.sin((i+1)*1.93)+.003*math.cos(i*.87)
        close*=math.exp(shock)
        rows.append({"date": (today+timedelta(days=i)).isoformat(),
                     "adj_close": close,"close":close})
    return rows


class ConditionalPublisherTests(unittest.TestCase):
    def test_cutoff_and_research_gate_are_explicit(self):
        history=mock_history()
        end=history[-1]["date"]
        snapshot={
            "price_as_of":end,"generated_at":end+"T22:00:00Z",
            "assets":[{"symbol":"SPY","type":"etf","history":history},
                      {"symbol":"BAD","type":"etf","history":[]}]}
        report=compact_volatility(snapshot,test_days=20,train_window=500,refit_every=10)
        self.assertEqual(report["as_of"],end)
        self.assertTrue(report["no_news_attribution"])
        self.assertEqual(report["instruments"]["BAD"]["status"],"unavailable")
        self.assertIn(report["instruments"]["SPY"]["status"],
                      {"research_only","accepted"})
        self.assertEqual(report["summary"]["evaluated"],2)
        self.assertEqual(report["instruments"]["SPY"]["fitted_through"],end)
        self.assertEqual(report["instruments"]["SPY"]["verification"]["observations"],20)
        self.assertNotIn("forecasts",report["instruments"]["SPY"])

    def test_stale_price_is_not_calibrated(self):
        history=mock_history()
        report=compact_volatility({
            "price_as_of":"2026-10-23","generated_at":"2026-10-25T00:00:00Z",
            "assets":[{"symbol":"SPY","type":"etf","history":history}]
        },test_days=20,train_window=500)
        self.assertEqual(report["instruments"]["SPY"]["status"],"unavailable")


if __name__=="__main__":
    unittest.main()
