"""First-cut as-of snapshot: share basis, sectors, profiles and leak checks, stubbed sources."""
import datetime as dt
import unittest

from scripts import first_cut_snapshot as fs


def ts(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp()) + 14 * 3600


CHART = {"chart": {"result": [{
    "meta": {"currency": "USD", "regularMarketPrice": 70, "currentTradingPeriod": {"regular": {"end": 1}}},
    "timestamp": [ts("2024-12-30"), ts("2024-12-31"), ts("2025-07-01")],
    "indicators": {"quote": [{"close": [100.0, 102.0, 7.0], "open": [99.0, 101.0, 6.9], "high": [1, 1, 1],
                              "low": [1, 1, 1], "volume": [1500, 3000, 45000]}],
                   "adjclose": [{"adjclose": [6.0, 6.5, 7.0]}]},
    "events": {"splits": {"a": {"date": ts("2025-06-10"), "numerator": 15, "denominator": 1},
                          "b": {"date": ts("2021-07-20"), "numerator": 4, "denominator": 1}},
               "dividends": {"x": {"date": ts("2024-12-01"), "amount": 0.1},
                             "y": {"date": ts("2025-03-01"), "amount": 0.1}}}}], "error": None}}

TABLE = """<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th>
<th>Headquarters Location</th><th>Date added</th><th>CIK</th><th>Founded</th></tr>{}</table>"""
ROW = "<tr><td>{}</td><td>Co {}</td><td>{}</td><td>x</td><td>x</td><td>2000-01-01</td><td>{:010d}</td><td>1900</td></tr>"


class SnapshotTests(unittest.TestCase):
    def test_restated_chart_is_in_the_cut_share_basis_without_later_rows(self):
        body, later = fs.restate_chart(CHART, "2024-12-31")
        result = body["chart"]["result"][0]
        self.assertEqual(later, 15)
        self.assertEqual(len(result["timestamp"]), 2)
        self.assertEqual(result["indicators"]["quote"][0]["close"], [1500.0, 1530.0])
        self.assertEqual(result["indicators"]["quote"][0]["volume"], [100.0, 200.0])
        adj = result["indicators"]["adjclose"][0]["adjclose"]
        self.assertAlmostEqual(adj[1] / adj[0], 6.5 / 6.0)
        self.assertEqual([round(d["amount"], 6) for d in result["events"]["dividends"].values()], [1.5])
        self.assertEqual(list(result["events"]["splits"]), ["b"])
        self.assertNotIn("regularMarketPrice", result["meta"])

    def test_sectors_come_from_the_list_revision_and_unlisted_members_are_reported(self):
        rows = "".join(ROW.format(f"S{i}", i, "Energy", 1000 + i) for i in range(449))
        rows += ROW.format("BRK.B", "B", "Financials", 1067983)
        by_cik, by_symbol = fs.sector_index(TABLE.format(rows).encode())
        self.assertEqual(by_cik[1067983], "Financials")
        self.assertEqual(by_symbol["BRK-B"], "Financials")
        binding = {"positions": [{"status": "verified", "symbol": "BRK-B", "cusip": "1", "weight": .1},
                                 {"status": "verified", "symbol": "GONE", "cusip": "2", "weight": .01},
                                 {"status": "no-public-series", "symbol": None, "cusip": "3", "weight": .01}]}
        fundamentals = {"members": [{"cusip": "1", "cik": 1067983, "entity": "Berkshire"},
                                    {"cusip": "2", "cik": 5, "entity": "Gone"}]}
        specs, excluded = fs.member_specs(binding, fundamentals, by_cik, by_symbol)
        self.assertEqual(specs, [("BRK-B", "Berkshire", "Financiero", 1067983, 0.04, 15)])
        self.assertEqual([e["symbol"] for e in excluded], ["GONE"])

    def test_older_list_revisions_with_other_columns_are_read(self):
        old = """<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>SEC filings</th><th>GICS Sector</th>
<th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date first added</th><th>CIK</th><th>Founded</th></tr>{}</table>"""
        row = "<tr><td>{}</td><td>Co</td><td>reports</td><td>{}</td><td>x</td><td>x</td><td>2000</td><td>{:010d}</td><td>1900</td></tr>"
        rows = "".join(row.format(f"S{i}", "Utilities", 2000 + i) for i in range(450))
        by_cik, by_symbol = fs.sector_index(old.format(rows).encode())
        self.assertEqual((by_cik[2003], by_symbol["S3"]), ("Utilities", "Utilities"))

    def test_bond_profiles_map_to_the_engine_schema(self):
        import json, tempfile, pathlib
        data = {"funds": {"TIP": {"status": "parsed", "captured_at": "2024-12-20T00:00:00+00:00", "archive_url": "u",
                                  "raw_sha256": "h", "profile": {
                                      "effective_duration_years": {"value": 6.54, "as_of": "2024-12-19"},
                                      "yield_to_maturity": {"value": .0432, "as_of": "2024-12-19"},
                                      "real_yield": {"value": .0195, "as_of": "2024-12-19"},
                                      "expense_ratio": {"value": .0018, "as_of": None}}},
                          "BAD": {"status": "failed", "profile": {}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "p.json"
            path.write_text(json.dumps(data))
            out = fs.bond_profiles(path)
        self.assertEqual(list(out), ["TIP"])
        self.assertTrue(out["TIP"]["inflationLinked"])
        self.assertEqual(out["TIP"]["observed_at"], "2024-12-20T00:00:00+00:00")
        self.assertEqual((out["TIP"]["duration"], out["TIP"]["date"], out["TIP"]["expenseRatio"]), (6.54, "2024-12-19", .0018))

    def test_future_leaks_are_named(self):
        asset = {"history": [{"date": "2024-12-31"}], "filings": [{"filing_date": "2025-02-01"}],
                 "financials": {"eps": {"filed": "2024-10-30", "period_end": "2024-09-30"}, "history": []}}
        self.assertEqual(fs.future_leaks(asset, "2024-12-31"), ["filings"])


if __name__ == "__main__":
    unittest.main()


class KnowledgeTests(unittest.TestCase):
    def test_retrieval_after_the_cut_is_dated_at_the_cut_close_and_kept(self):
        asset = {"price_observed_at": "2026-11-15T05:00:00+00:00",
                 "financials": {"earnings_history": {"observed_at": "2026-11-15T05:01:00+00:00"}},
                 "bond_profile": {"observed_at": "2024-12-22T13:18:15+00:00"}}
        fs.known_at_cut(asset, "2024-12-31")
        self.assertEqual(asset["price_observed_at"], "2024-12-31T21:00:00+00:00")
        self.assertEqual(asset["price_retrieved_at"], "2026-11-15T05:00:00+00:00")
        self.assertEqual(asset["financials"]["earnings_history"]["retrieved_at"], "2026-11-15T05:01:00+00:00")
        self.assertEqual(asset["bond_profile"]["observed_at"], "2024-12-22T13:18:15+00:00")
