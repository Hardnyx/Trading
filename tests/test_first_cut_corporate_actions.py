"""First-cut corporate actions: split kinds and early series ends, stubbed source."""
import unittest

from scripts import first_cut_corporate_actions as ca

BINDING = {"positions": [
    {"status": "verified", "symbol": "AAA", "cusip": "1", "name": "A", "weight": .5},
    {"status": "verified", "symbol": "BBB", "cusip": "2", "name": "B", "weight": .3},
    {"status": "no-public-series", "symbol": None, "cusip": "3", "name": "C", "weight": .2},
]}


def fetch(symbol, start, end):
    if symbol == "AAA":
        return {"first_day": start, "last_day": "2025-12-31", "dividends": [{"ex_date": "2025-03-01", "amount": 1}], "splits": []}
    return {"first_day": start, "last_day": "2025-06-30", "dividends": [], "splits": []}


class CorporateActionTests(unittest.TestCase):
    def test_early_series_end_and_unbound_positions_become_events(self):
        members, events = ca.collect(BINDING, "2024-12-31", "2025-12-31", fetch=fetch, pause=0)
        self.assertEqual([m["symbol"] for m in members], ["AAA", "BBB"])
        kinds = sorted(e["type"] for e in events)
        self.assertEqual(kinds, ["no-public-series-at-binding", "series-ends-in-window"])


if __name__ == "__main__":
    unittest.main()
