import datetime as dt
import gzip
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import history_archive as h

UTC = dt.timezone.utc


def yahoo(symbol="SPY", closes=(100.0, 101.0, None, 102.0), granularity="1d", end_offset=0):
    start = int(dt.datetime(2026, 11, 2, 14, 30, tzinfo=UTC).timestamp())
    stamps = [start + 86400 * i for i in range(len(closes))]
    return json.dumps({"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "USD", "dataGranularity": granularity,
                 "currentTradingPeriod": {"regular": {"end": stamps[-1] + 6 * 3600 + end_offset}}},
        "timestamp": stamps,
        "indicators": {"quote": [{"open": list(closes), "high": list(closes), "low": list(closes),
                                  "close": list(closes), "volume": [10] * len(closes)}]},
        "events": {"dividends": {"a": {"date": stamps[1], "amount": 0.5}},
                   "splits": {"b": {"date": stamps[0], "numerator": 4, "denominator": 1}}},
    }]}}).encode()


class Prices(unittest.TestCase):
    def test_daily_rows_skip_missing_closes_and_keep_events(self):
        moment = dt.datetime(2026, 11, 8, 12, tzinfo=UTC)
        rows, events, currency = h.parse_yahoo(yahoo(), "SPY", moment)
        self.assertEqual([r[0] for r in rows], ["2026-11-02", "2026-11-03", "2026-11-05"])
        self.assertEqual(rows[-1][4], 102.0)
        self.assertEqual(events, [["2026-11-02", "split", 4.0], ["2026-11-03", "dividend", 0.5]])
        self.assertEqual(currency, "USD")

    def test_a_session_still_trading_and_wrong_payloads_are_rejected(self):
        # The last bar is today in New York and the regular session has not ended.
        moment = dt.datetime(2026, 11, 5, 18, tzinfo=UTC)
        rows, _, _ = h.parse_yahoo(yahoo(end_offset=3600), "SPY", moment)
        self.assertEqual(rows[-1][0], "2026-11-03")
        with self.assertRaises(ValueError):
            h.parse_yahoo(yahoo(symbol="QQQ"), "SPY", moment)
        with self.assertRaises(ValueError):
            h.parse_yahoo(yahoo(granularity="1mo"), "SPY", moment)


class Partitions(unittest.TestCase):
    def test_yearly_gzip_is_deterministic_and_only_changed_years_are_rewritten(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "SPY"
            rows = [["2025-12-31", 1.0], ["2026-01-02", 2.0]]
            self.assertEqual(h.write_yearly(target, ["date", "value"], rows), {"files": 2, "changed_files": 2})
            self.assertEqual(h.write_yearly(target, ["date", "value"], rows)["changed_files"], 0)
            changed = h.write_yearly(target, ["date", "value"], rows + [["2026-01-05", 3.0]])
            self.assertEqual(changed["changed_files"], 1)  # only 2026
            text = gzip.decompress((target / "2026.csv.gz").read_bytes()).decode()
            self.assertEqual(text, "date,value\n2026-01-02,2.0\n2026-01-05,3.0\n")
            # Same content compressed differently (another zlib) is not a change.
            other = gzip.compress(gzip.decompress((target / "2025.csv.gz").read_bytes()), compresslevel=1, mtime=0)
            (target / "2025.csv.gz").write_bytes(other)
            self.assertEqual(h.write_yearly(target, ["date", "value"], rows + [["2026-01-05", 3.0]])["changed_files"], 0)
            self.assertEqual((target / "2025.csv.gz").read_bytes(), other)
            # A year the source no longer publishes is removed, not kept stale.
            h.write_yearly(target, ["date", "value"], [["2026-01-02", 2.0]])
            self.assertFalse((target / "2025.csv.gz").exists())


class Sources(unittest.TestCase):
    def test_fred_csv_drops_missing_values_and_checks_the_series(self):
        raw = b"observation_date,BAA10Y\n1986-01-03,2.30\n1986-01-02,2.34\n1986-01-06,\n"
        self.assertEqual(h.parse_fred(raw, "BAA10Y"), [["1986-01-02", 2.34], ["1986-01-03", 2.3]])
        with self.assertRaises(ValueError):
            h.parse_fred(raw, "AAA10Y")

    def test_french_daily_block_only(self):
        text = ("header text\n\n,Mkt-RF,SMB,RF\n19630701,   -0.67,    0.00,    0.01\n"
                "19630702,    0.79,   -0.27,    0.01\n\n Annual Factors\n,Mkt-RF,SMB,RF\n1964,  10,  1,  3\n")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("f.csv", text)
        header, rows = h.parse_french(buffer.getvalue())
        self.assertEqual(header, ["date", "Mkt-RF", "SMB", "RF"])
        self.assertEqual(rows, [["1963-07-01", -0.67, 0.0, 0.01], ["1963-07-02", 0.79, -0.27, 0.01]])

    def test_sp500_constituents_require_the_expected_table(self):
        cells = "".join(f"<tr><td>T{i}</td><td>Co {i}</td><td>Sector</td><td>Sub</td><td>HQ</td>"
                        f"<td>2000-01-0{i % 9 + 1}</td><td>{i:010d}</td><td>1900</td></tr>" for i in range(460))
        html = ('<table id="constituents"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th>'
                '<th>GICS Sub-Industry</th><th>Headquarters Location</th><th>Date added</th><th>CIK</th>'
                f'<th>Founded</th></tr>{cells}</table>').encode()
        header, rows = h.parse_sp500(html)
        self.assertEqual(header, ["symbol", "security", "gics_sector", "date_added", "cik"])
        self.assertEqual(len(rows), 460)
        with self.assertRaises(ValueError):
            h.parse_sp500(html.replace(b'id="constituents"', b'id="other"'))


class Inventory(unittest.TestCase):
    def test_public_inventory_summarises_coverage_without_the_archive(self):
        manifest = {"revision": h.REVISION, "purpose": "x", "datasets": {
            "prices": {**h.SOURCES["prices"], "observed_at": "2026-11-08T00:00:00+00:00", "errors": [],
                       "entries": {"SPY": {"rows": 10, "first": "1993-01-29", "last": "2026-11-06", "dividends": 3, "splits": 0},
                                   "UBER": {"rows": 5, "first": "2019-05-10", "last": "2026-11-06", "dividends": 0, "splits": 0}}},
            "macro": {**h.SOURCES["macro"], "observed_at": "2026-11-08T00:00:00+00:00", "errors": ["X: down"],
                      "entries": {"DGS10": {"rows": 7, "first": "1962-01-02", "last": "2026-11-05",
                                            "frequency": "daily", "description": "d"}}},
        }}
        inv = h.inventory(manifest)
        prices = next(r for r in inv["datasets"] if r["id"] == "prices")
        self.assertEqual((prices["series"], prices["observations"], prices["first"]), (2, 15, "1993-01-29"))
        self.assertEqual((prices["dividends"], prices["before_1990"], prices["latest_start"]), (3, 0, "2019-05-10"))
        macro = next(r for r in inv["datasets"] if r["id"] == "macro")
        self.assertEqual(macro["errors"], 1)
        self.assertEqual(macro["catalog"][0]["id"], "DGS10")
        self.assertNotIn("entries", json.dumps(inv))


if __name__ == "__main__":
    unittest.main()
