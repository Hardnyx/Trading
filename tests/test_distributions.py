import datetime as dt
import html
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.distributions import (DISTRIBUTION_URLS, enrich_distributions,
    parse_issuer_history, parse_monthly_schedule, price_distribution_index)


def issuer_page(pay=20261105, amount="0.24", symbol="SHY", currency="USD"):
    columns=[]
    for name,label,value in [("recordDate","Record Date",20261102),
      ("exDate","Ex-Date",20261102),("payableDate","Payable Date",pay),
      ("totalDistribution","Total Distribution",amount)]:
        columns.append({"name":name,"label":label,"value":[value]})
    payload=html.escape(json.dumps({"distributionTableData":columns}),quote=True)
    identity=html.escape(json.dumps({"ticker":symbol,"currencyCode":currency,
      "productId":DISTRIBUTION_URLS[symbol].split('/products/')[1].split('/')[0]}),quote=True)
    return ('<walrus-render-on-client componentprops="'+identity+'"></walrus-render-on-client>'+
      '<walrus-render-on-client componentprops="'+payload+'"></walrus-render-on-client>')


def calendar_text():
    declared=[f"1-{month}-26" for month in ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]]+["29-Dec-26"]
    ex=[s.replace("1-","2-",1) for s in declared[:-1]]+["30-Dec-26"]
    paid=[s.replace("1-","5-",1) for s in declared[:-1]]+["5-Jan-27"]
    return ("October 21, 2026\nMONTHLY DISTRIBUTION — Bond and Equity Funds(b)\n"
      "DECLARATION DATE: "+" ".join(declared)+"\nEX-DATE/RECORD DATE: "+" ".join(ex)+
      "\nPAY DATE: "+" ".join(paid)+"\nAGG iShares Core U.S. Aggregate Bond ETF\n"
      "SHY iShares 1-3 Year Treasury Bond ETF\nTLT iShares 20+ Year Treasury Bond ETF\n"
      "DECLARATION DATE: 1-Jan-26\nEX-DATE/RECORD DATE: 2-Jan-26\nPAY DATE: 5-Jan-26\nBALI iShares Other Fund")


class DistributionFacts(unittest.TestCase):
    def test_issuer_table_preserves_real_dates_amount_and_first_observation(self):
        first=parse_issuer_history(issuer_page(),"SHY","2026-10-26T20:00:00Z")
        later=parse_issuer_history(issuer_page(),"SHY","2026-10-27T20:00:00Z",first)
        self.assertEqual(first['records'][0]['pay_date'],'2026-11-05')
        self.assertEqual(first['records'][0]['amount_per_share'],.24)
        self.assertEqual(later['records'][0]['observed_at'],first['records'][0]['observed_at'])
        changed=parse_issuer_history(issuer_page(amount="0.25"),"SHY","2026-10-27T20:00:00Z",first)
        self.assertEqual(changed['records'][0]['observed_at'],"2026-10-27T20:00:00Z")

    def test_distribution_source_checks_ticker_currency_and_product_identity(self):
        for page in [issuer_page(symbol="IEF"), issuer_page(currency="EUR"),
                     issuer_page().replace("239452", "239454")]:
            with self.assertRaises(ValueError):
                parse_issuer_history(page, "SHY", "2026-10-26T20:00:00Z")
        result = parse_issuer_history(issuer_page(symbol="IEF"), "IEF", "2026-10-26T20:00:00Z")
        self.assertEqual(result["symbol"], "IEF")
        self.assertEqual(result["currency"], "USD")

    def test_new_sources_archive_facts_and_retain_prior_history_on_source_failure(self):
        first = "2026-10-26T20:00:00Z"
        later = "2026-10-27T20:00:00Z"
        assets = [{"symbol": "IEF", "type": "etf"}, {"symbol": "SPY", "type": "etf"}]
        def fetch(url, key):
            if key.endswith(".pdf"):
                raise ValueError("calendar unavailable")
            return issuer_page(symbol="IEF").encode()
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "calendars"
            result = enrich_distributions(assets, {}, "2026-10-23", first, fetch, archive)
            self.assertEqual(result["requested_histories"], 1)
            self.assertEqual(result["histories"], 1)
            history = assets[0]["issuer_distributions"]
            paths = list((Path(folder)/"histories"/"IEF").glob("*.json"))
            self.assertEqual(len(paths), 1)
            original = paths[0].read_bytes()
            repeated = [{"symbol": "IEF", "type": "etf"}]
            old = {"IEF": assets[0]}
            enrich_distributions(repeated, old, "2026-10-23", later, fetch, archive)
            self.assertEqual(repeated[0]["issuer_distributions"]["records"][0]["observed_at"], first)
            self.assertEqual(paths[0].read_bytes(), original)
            def failing(url, key):
                raise ValueError("unavailable")
            restored = [{"symbol": "IEF", "type": "etf"}]
            failed = enrich_distributions(restored, old, "2026-10-23", later, failing, archive)
            self.assertEqual(failed["histories"], 0)
            self.assertEqual(restored[0]["issuer_distributions"], history)
            self.assertEqual(len(failed["errors"]), 2)

    def test_verified_treasury_history_supplies_a_dated_profile_and_retains_it_on_failure(self):
        from tests.test_bond_profiles import BondProfiles
        page = issuer_page(symbol="IEF") + BondProfiles().html()
        def fetch(url, key):
            if key.endswith('.pdf'):
                raise ValueError('calendar unavailable')
            return page.encode()
        assets = [{"symbol": "IEF", "type": "etf"}]
        result = enrich_distributions(assets, {}, "2026-10-23", "2026-10-26T20:00:00Z", fetch)
        self.assertEqual(result['profiles'], 1)
        profile = assets[0]['bond_profile']
        self.assertEqual(profile['date'], '2026-10-22')
        self.assertEqual(profile['source_sha256'], assets[0]['issuer_distributions']['source_sha256'])
        restored = [{"symbol": "IEF", "type": "etf"}]
        def failing(url, key):
            raise ValueError('unavailable')
        enrich_distributions(restored, {'IEF': assets[0]}, '2026-10-23', '2026-10-27T20:00:00Z', failing)
        self.assertEqual(restored[0]['bond_profile'], profile)

    def test_bad_payment_order_and_changed_column_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_issuer_history(issuer_page(pay=20261030),"SHY","2026-10-26T20:00:00Z")
        with self.assertRaises(ValueError):
            parse_issuer_history(issuer_page().replace('Payable Date','Wrong Date'),"SHY","2026-10-26T20:00:00Z")

    def test_monthly_calendar_matches_fund_membership_and_does_not_infer_amounts(self):
        class Page:
            def extract_text(self):return calendar_text()
        with patch('pypdf.PdfReader') as reader:
            reader.return_value.pages=[Page()]
            c=parse_monthly_schedule(b'original-pdf',['SHY','TLT','SPY'],'2026-10-26T20:00:00Z')
        self.assertEqual(c['symbols'],['SHY','TLT'])
        self.assertEqual(len(c['records']),13)
        self.assertEqual(c['published_on'],'2026-10-21')
        self.assertTrue(c['records'][-1]['conditional'])
        self.assertTrue(all(r['amount_per_share'] is None for r in c['records']))

    def test_calendar_rejects_misaligned_columns_or_future_publication(self):
        class Page:
            def __init__(self,text):self.text=text
            def extract_text(self):return self.text
        for text in [calendar_text().replace(' 5-Jan-27',''),calendar_text().replace('October 21, 2026','October 28, 2026')]:
            with patch('pypdf.PdfReader') as reader:
                reader.return_value.pages=[Page(text)]
                with self.assertRaises(ValueError):
                    parse_monthly_schedule(b'pdf',['SHY'],'2026-10-26T20:00:00Z')

    def test_price_event_index_is_a_window_of_ex_dates_not_payment_dates(self):
        timestamp=lambda day:dt.datetime.fromisoformat(day+'T12:00:00+00:00').timestamp()
        response={'meta':{'currency':'USD'},'events':{'dividends':{
          'first':{'date':timestamp('2026-11-02'),'amount':.24},
          'future':{'date':timestamp('2027-01-02'),'amount':9}}}}
        rows=[{'date':'2026-10-23'},{'date':'2026-12-01'}]
        r=price_distribution_index(response,rows,'SHY','2026-12-02T20:00:00Z')
        self.assertEqual(r['records'],[{'ex_date':'2026-11-02','amount_per_share':.24}])
        self.assertNotIn('pay_date',r['records'][0])
        self.assertEqual(r['coverage_end'],'2026-12-01')

    def test_nonfinite_quoted_distributions_do_not_become_zero_income(self):
        response={'events':{'dividends':{'bad':{'date':1793611200,'amount':float('nan')}}}}
        with self.assertRaises(ValueError):
            price_distribution_index(response,[{'date':'2026-10-23'},{'date':'2026-12-01'}],'SHY','2026-12-02T20:00:00Z')




class CreditProfileFunds(unittest.TestCase):
    def test_credit_and_inflation_linked_profiles_are_collected(self):
        from scripts.distributions import PROFILE_FUNDS, DISTRIBUTION_URLS
        self.assertTrue({"AGG", "LQD", "IGSB", "HYG", "EMB", "TIP"} <= PROFILE_FUNDS)
        self.assertTrue(PROFILE_FUNDS <= set(DISTRIBUTION_URLS))


if __name__ == "__main__":
    unittest.main()
