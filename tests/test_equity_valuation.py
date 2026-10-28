import json
import unittest
from html import escape
from scripts.equity_valuation import parse_valuation, enrich_equity_valuations, VALUATION_URLS


def page(symbol="EFA", pe=18.7678, day=20261026, fee="0.32%", label="P/E Ratio", product="239623"):
    components = [{"ticker": symbol, "currencyCode": "USD", "productId": product},
                  {"containersByNameMap": {"default": {"dataPointsByNameMap": {
                      "priceEarnings": {"value": pe, "asOfDate": day, "label": label}}}}},
                  {"feeDataPoints": {"expr": {"formattedValue": fee}}}]
    return "".join(f'<walrus-render-on-client componentprops="{escape(json.dumps(c), quote=True)}"></walrus-render-on-client>'
                   for c in components)


class EquityValuation(unittest.TestCase):
    def test_dated_pe_and_expense_with_identity_checks(self):
        r = parse_valuation(page(), "EFA", "2026-10-27", "2026-10-28T00:00:00Z", VALUATION_URLS["EFA"])
        self.assertAlmostEqual(r["priceEarnings"], 18.7678)
        self.assertEqual(r["date"], "2026-10-26")
        self.assertAlmostEqual(r["expenseRatio"], .0032)
        for bad in [page(symbol="EEM"), page(product="239637"), page(day=20261028), page(label="P/B Ratio"),
                    page(pe=-4), page(fee="5%")]:
            with self.assertRaises(ValueError):
                parse_valuation(bad, "EFA", "2026-10-27", "2026-10-28T00:00:00Z", VALUATION_URLS["EFA"])

    def test_first_observation_is_kept_and_prior_record_survives_failures(self):
        first = "2026-10-27T00:00:00Z"
        assets = [{"symbol": "EFA", "type": "etf"}, {"symbol": "SPY", "type": "etf"}]
        enrich_equity_valuations(assets, {}, "2026-10-27", first, lambda url, key: page().encode())
        record = assets[0]["equity_valuation"]
        self.assertNotIn("equity_valuation", assets[1])
        again = [{"symbol": "EFA", "type": "etf"}]
        enrich_equity_valuations(again, {"EFA": assets[0]}, "2026-10-28", "2026-10-28T00:00:00Z",
                                 lambda url, key: page().encode())
        self.assertEqual(again[0]["equity_valuation"]["observed_at"], first)
        def failing(url, key):
            raise TimeoutError("down")
        kept = [{"symbol": "EFA", "type": "etf"}]
        result = enrich_equity_valuations(kept, {"EFA": assets[0]}, "2026-10-28", "2026-10-28T00:00:00Z", failing)
        self.assertEqual(kept[0]["equity_valuation"], record)
        self.assertEqual(len(result["errors"]), 1)
        # A record observed after the requested cut is not reused.
        late = [{"symbol": "EFA", "type": "etf"}]
        enrich_equity_valuations(late, {"EFA": assets[0]}, "2026-10-26", "2026-10-26T00:00:00Z", failing)
        self.assertNotIn("equity_valuation", late[0])


if __name__ == "__main__":
    unittest.main()
