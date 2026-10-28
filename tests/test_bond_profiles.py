import json
import unittest
from html import escape
from scripts.bond_profiles import parse_profile

class BondProfiles(unittest.TestCase):
    def html(self, day=20261022, label="Effective Duration"):
        components = [{"containersByNameMap":{"default":{"dataPointsByNameMap":{
            "modelOad":{"value":1.78871,"asOfDate":day,"label":label},
            "fxHedgedYield":{"value":4.64,"asOfDate":day,"label":"Average Yield to Maturity"},
            "thirtyDaySecYield":{"value":4.6621,"asOfDate":day,"label":"30 Day SEC Yield"},
        }}}},{"feeDataPoints":{"expr":{"formattedValue":"0.15%"}}}]
        return "".join(f'<walrus-render-on-client componentprops="{escape(json.dumps(c), quote=True)}"></walrus-render-on-client>' for c in components)

    def test_yield_units_dates_and_expense_are_preserved(self):
        p=parse_profile(self.html(),"SHY","2026-10-23","2026-10-24T00:00:00Z")
        self.assertAlmostEqual(p['yieldToMaturity'],.0464)
        self.assertAlmostEqual(p['expenseRatio'],.0015)
        self.assertAlmostEqual(p['duration'],1.78871)
        self.assertEqual(p['date'],'2026-10-22')

    def test_future_profiles_and_changed_labels_are_rejected(self):
        with self.assertRaises(ValueError):parse_profile(self.html(20261024),"SHY","2026-10-23","2026-10-24T00:00:00Z")
        with self.assertRaises(ValueError):parse_profile(self.html(label="Different measure"),"SHY","2026-10-23","2026-10-24T00:00:00Z")

    def test_research_profile_keeps_an_explicit_issuer_source_without_changing_live_catalog(self):
        from scripts.bond_profiles import ISSUER_URLS
        source = 'https://www.ishares.com/us/products/239456/ishares-7-10-year-treasury-bond-etf'
        p = parse_profile(self.html(), 'IEF', '2026-10-23', '2026-10-24T00:00:00Z', source_url=source)
        self.assertEqual(p['source_url'], source)
        self.assertNotIn('IEF', ISSUER_URLS)

    def test_inflation_linked_profile_takes_the_real_yield(self):
        components = [{"containersByNameMap":{"default":{"dataPointsByNameMap":{
            "modelOad":{"value":6.7,"asOfDate":20261026,"label":"Effective Duration"},
            "realYield":{"value":2.65614,"asOfDate":20261026,"label":"Real Yield"},
            "weightedAvgYieldToMaturity":{"value":4.87,"asOfDate":20261026,"label":"Weighted Avg YTM"},
        }}}},{"feeDataPoints":{"expr":{"formattedValue":"0.18%"}}}]
        html = "".join(f'<walrus-render-on-client componentprops="{escape(json.dumps(c), quote=True)}"></walrus-render-on-client>' for c in components)
        p = parse_profile(html, "TIP", "2026-10-27", "2026-10-28T00:00:00Z", source_url="x")
        self.assertAlmostEqual(p["realYield"], .0265614)
        self.assertTrue(p["inflationLinked"])
        self.assertNotIn("yieldToMaturity", p)
        # A nominal fund still requires its nominal yield.
        with self.assertRaises(ValueError):
            parse_profile(html, "HYG", "2026-10-27", "2026-10-28T00:00:00Z", source_url="x")
