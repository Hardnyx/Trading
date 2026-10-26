import json
import gzip
from pathlib import Path
import tempfile
import unittest
from scripts.etf_holdings import parse_fund, enrich_holdings, EQUITY_ETFS

class HoldingsTests(unittest.TestCase):
    payload={"ticker":"SPY","holdings_as_of":"2026-10-22",
             "source_layer":"issuer","holdings":{
                 "AAPL":7.7,"NVDA":7.8,"MSFT":5.9,"AMZN":3.7,
                 "GOOGL":2.8,"BRK.B":2.0,"OTH":70}}
    def test_percentage_conversion_with_timestamp(self):
        r=parse_fund(self.payload,"SPY","2026-10-23","2026-10-26T09:00:00Z")
        self.assertAlmostEqual(sum(row["weight"] for row in r["positions"]),.999)
        self.assertEqual(r["positions"][0]["symbol"],"OTH")
        self.assertEqual(r["observed_at"],"2026-10-26T09:00:00Z")
    def test_no_backfill_of_future_holdings_date(self):
        p={**self.payload,"holdings_as_of":"2026-10-24"}
        with self.assertRaises(ValueError):
            parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
    def test_preserve_first_observation_across_repeated_current_snapshots(self):
        old=parse_fund(self.payload,"SPY","2026-10-23","2026-10-25T01:00:00Z")
        assets=[{"symbol":"SPY","type":"etf"}]
        result=enrich_holdings(assets,{"SPY":{"holdings":old}},
            "2026-10-23","2026-10-26T01:00:00Z",
            lambda *_:json.dumps(self.payload).encode("utf-8"))
        self.assertEqual(result["downloaded"],1)
        self.assertEqual(assets[0]["holdings"]["observed_at"],old["observed_at"])
    def test_small_short_cash_line_does_not_hide_long_equity_positions(self):
        p={**self.payload,"holdings":{**self.payload["holdings"],"CASH":-.2}}
        r=parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
        self.assertAlmostEqual(r["excluded_short_weight"],.002)
        self.assertAlmostEqual(r["all_equity_weight"],.999)
        p={**self.payload,"holdings":{**self.payload["holdings"],"CASH":-10}}
        with self.assertRaises(ValueError):
            parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")

    def test_foreign_exchange_tickers_are_not_dropped_silently(self):
        p={**self.payload,"holdings":{"7203.JP":65,"NOVO-B.CO":20,"TM":10}}
        r=parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
        self.assertEqual(len(r["positions"]),3)
        self.assertAlmostEqual(r["covered_weight"],.95)

    def test_reject_wrong_source_and_holdings(self):
        p={**self.payload,"source_layer":"unknown"}
        with self.assertRaises(ValueError):
            parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
        p={**self.payload,"holdings":{"AAA":120}}
        with self.assertRaises(ValueError):
            parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
    def test_previous_used_on_network_failure(self):
        old=parse_fund(self.payload,"SPY","2026-10-23","2026-10-25T01:00:00Z")
        assets=[{"symbol":"SPY","type":"etf"}]
        def unavailable(*_):raise TimeoutError("source unavailable")
        result=enrich_holdings(assets,{"SPY":{"holdings":old}},
            "2026-10-23","2026-10-26T01:00:00Z",unavailable)
        self.assertEqual(result["retained"],1)
        self.assertEqual(assets[0]["holdings"],old)
    def test_source_corrections_remain_separate_archive_files(self):
        with tempfile.TemporaryDirectory() as folder:
            assets=[{"symbol":"SPY","type":"etf"}]
            first_bytes=json.dumps(self.payload).encode()
            enrich_holdings(assets,{},"2026-10-23","2026-10-26T09:00:00Z",
                            lambda *_:first_bytes,archive_dir=folder)
            old=assets[0]["holdings"]
            altered={**self.payload,"holdings":{
                **self.payload["holdings"],"AAPL":7.6,"OTH":70.1}}
            next_bytes=json.dumps(altered).encode()
            second=[{"symbol":"SPY","type":"etf"}]
            enrich_holdings(second,{"SPY":{"holdings":old}},
                "2026-10-23","2026-10-26T10:00:00Z",
                lambda *_:next_bytes,archive_dir=folder)
            self.assertEqual(len(list(Path(folder).rglob("SPY-*.json.gz"))),2)
            self.assertNotEqual(old["source_sha256"],second[0]["holdings"]["source_sha256"])
            self.assertEqual(second[0]["holdings"]["observed_at"],"2026-10-26T10:00:00Z")

    def test_historical_request_does_not_enrich_without_live_fetch(self):
        assets=[{"symbol":"SPY","type":"etf"}]
        result=enrich_holdings(assets,{},"2026-10-23",
            "2026-10-26T01:00:00Z",lambda *_:b"{}")
        self.assertEqual(result["downloaded"],0)
        self.assertEqual(len(result["errors"]),1)

    def test_expanded_equity_catalog_is_included_and_five_hundred_rows_are_retained(self):
        self.assertTrue({"VUG","SCHD","XBI","IBB","KWEB","EWT"}<=EQUITY_ETFS)
        p={**self.payload,"holdings":{f"STK{i}":.2 for i in range(500)}}
        r=parse_fund(p,"SPY","2026-10-23","2026-10-26T09:00:00Z")
        self.assertEqual(len(r["positions"]),500)
        self.assertAlmostEqual(r["covered_weight"],1)

    def test_same_date_revisions_preserve_both_original_provider_responses(self):
        revised={**self.payload,"holdings":{**self.payload["holdings"],"AAPL":6.7}}
        assets=[{"symbol":"SPY","type":"etf"}]
        with tempfile.TemporaryDirectory() as directory:
            enrich_holdings(assets,{},"2026-10-23","2026-10-25T01:00:00Z",
                lambda *_:json.dumps(self.payload).encode(),archive_dir=directory)
            old=assets[0]["holdings"]
            enrich_holdings(assets,{"SPY":{"holdings":old}},"2026-10-23",
                "2026-10-26T01:00:00Z",lambda *_:json.dumps(revised).encode(),
                archive_dir=directory)
            files=list(Path(directory).rglob("*.json.gz"))
            self.assertEqual(len(files),2)
            self.assertNotEqual(old["source_sha256"],assets[0]["holdings"]["source_sha256"])
            self.assertEqual({json.loads(gzip.decompress(p.read_bytes()))["holdings"]["AAPL"]
                              for p in files},{7.7,6.7})

    def test_provider_regression_cannot_replace_a_newer_holdings_record(self):
        old=parse_fund(self.payload,"SPY","2026-10-23","2026-10-25T01:00:00Z")
        earlier={**self.payload,"holdings_as_of":"2026-06-30"}
        assets=[{"symbol":"SPY","type":"etf"}]
        result=enrich_holdings(assets,{"SPY":{"holdings":old}},"2026-10-23",
            "2026-10-26T01:00:00Z",lambda *_:json.dumps(earlier).encode())
        self.assertEqual(assets[0]["holdings"],old)
        self.assertEqual(result["retained"],1)

if __name__=="__main__":unittest.main()
