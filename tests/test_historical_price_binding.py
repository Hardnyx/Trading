"""Price binding of first-cut SPY positions, with stubbed public sources."""
import unittest

from scripts import historical_price_binding as hb

FILINGS = [
    {"name": "Alpha Inc", "cusip": "111111111", "isin": "US1111111111", "units": "NS", "shares": 10, "value_usd": 1000},
    {"name": "Beta Plc", "cusip": "000000000", "isin": "IE0000000001", "units": "NS", "shares": 10, "value_usd": 500},
    {"name": "Gamma Co", "cusip": "333333333", "isin": "US3333333333", "units": "NS", "shares": 10, "value_usd": 300},
    {"name": "Cash Fund", "cusip": "444444444", "isin": None, "units": "OU", "shares": 1, "value_usd": 1},
]
ROW = {"positions": [
    {"name": "Alpha Inc", "cusip": "111111111", "weight": .4, "ticker_observation": {"source_ticker": "ALPH"}},
    {"name": "Beta Plc", "cusip": "000000000", "weight": .3, "ticker_observation": None},
    {"name": "Gamma Co", "cusip": "333333333", "weight": .2, "ticker_observation": {"source_ticker": "GAMA"}},
    {"name": "Cash Fund", "cusip": "444444444", "weight": .1, "ticker_observation": None},
]}
PRICES = {"ALPH": (50.0, 2.0), "BETA": (50.0, 1.0), "GAMA": (10.0, 1.0), "GAMX": (30.0, 1.0)}


def fetch(symbol, day):
    if symbol not in PRICES:
        raise KeyError(symbol)
    return PRICES[symbol]


def figi(id_type, value):
    return {"IE0000000001": ["BETA"], "333333333": ["GAMX"]}.get(value, [])


class PriceBindingTests(unittest.TestCase):
    def test_bindings_need_a_filed_price_match_after_undoing_later_splits(self):
        rows = hb.bind(ROW, FILINGS, "2024-09-30", fetch=fetch, figi=figi, pause=0)
        by = {r["name"]: r for r in rows}
        self.assertEqual(by["Alpha Inc"]["status"], "verified")       # 50 x 2 = 100 = 1000/10
        self.assertEqual(by["Beta Plc"]["ticker_source"], "openfigi-id_isin")  # invalid CUSIP -> ISIN
        self.assertEqual(by["Beta Plc"]["status"], "verified")
        self.assertEqual(by["Gamma Co"]["symbol"], "GAMX")             # observed ticker mismatched, FIGI rescued
        self.assertEqual(by["Cash Fund"]["status"], "no-filed-share-price")

    def test_filing_order_must_match(self):
        swapped = [FILINGS[1], FILINGS[0]] + FILINGS[2:]
        with self.assertRaises(ValueError):
            hb.bind(ROW, swapped, "2024-09-30", fetch=fetch, figi=figi, pause=0)


if __name__ == "__main__":
    unittest.main()


class CutSelectionTests(unittest.TestCase):
    def test_first_cut_keeps_its_file_and_later_cuts_are_dated(self):
        from scripts import historical_price_binding as hb
        self.assertEqual(hb.binding_path("2024-12-31").name, "first-cut.json")
        self.assertEqual(hb.binding_path("2025-06-30").name, "2025-06-30.json")

    def test_a_stale_spy_source_is_refused(self):
        import gzip, json, tempfile, pathlib
        from scripts import historical_price_binding as hb
        matrix = {"matrix": [{"cut": "2025-01-31", "positions": [], "spy_source": {"status": "stale-or-invalid-source"}},
                             {"cut": "2025-03-31", "positions": [{}], "spy_source": {"status": "source-available"}}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "o.json.gz"
            path.write_bytes(gzip.compress(json.dumps(matrix).encode()))
            self.assertEqual(hb.cut_row("2025-03-31", path)["cut"], "2025-03-31")
            with self.assertRaises(ValueError):
                hb.cut_row("2025-01-31", path)
