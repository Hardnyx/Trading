import datetime as dt
import html
import json
import unittest
from unittest.mock import patch

from scripts.distributions import parse_issuer_history, parse_monthly_schedule, price_distribution_index


def issuer_page(pay=20261105, amount="0.24"):
    columns=[]
    for name,label,value in [("recordDate","Record Date",20261102),
      ("exDate","Ex-Date",20261102),("payableDate","Payable Date",pay),
      ("totalDistribution","Total Distribution",amount)]:
        columns.append({"name":name,"label":label,"value":[value]})
    payload=html.escape(json.dumps({"distributionTableData":columns}),quote=True)
    return '<walrus-render-on-client componentprops="'+payload+'"></walrus-render-on-client>'


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


if __name__=='__main__':unittest.main()
