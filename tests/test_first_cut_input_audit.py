"""H1.4 input audit: each check family rejects a crafted violation."""
import copy
import hashlib
import unittest

from scripts import first_cut_input_audit as audit

CUT = "2024-12-31"
ASSET = {"symbol": "AAA", "type": "stock", "cik": 7, "price": 30.0, "later_split_factor_undone": 1.0,
         "splits": [{"date": "2024-11-01", "ratio": 2.0}],
         "history": [{"date": "2024-09-30", "close": 50.0, "adj_close": 49.0},
                     {"date": "2024-12-31", "close": 30.0, "adj_close": 30.0}],
         "financials": {"eps": {"value": 2.0, "filed": "2024-10-30", "period_end": "2024-09-30"}},
         "price_observed_at": f"{CUT}T21:00:00+00:00"}
MARKET = {"price_as_of": CUT, "requested_as_of": CUT, "assets": [ASSET],
          "macro": [{"id": "DGS10", "unit": "%", "value": 4.6, "date": "2024-12-27", "known_by_day": "2024-12-30"},
                    {"id": "LFPR", "unit": "%", "value": 62.5, "date": "2024-11-01"}],
          "reconstruction": {"members_excluded": [{"symbol": "BBB"}]}}
VOL = {"as_of": CUT, "parameter_fit_through": CUT, "instruments": {"AAA": {"fitted_through": CUT}}}
BINDING = {"cut": CUT, "report_date": "2024-09-30", "positions": [
    {"symbol": "AAA", "cusip": "1", "status": "verified", "weight": .9, "filed_price": 100.0},
    {"symbol": "BBB", "cusip": "2", "status": "verified", "weight": .05, "filed_price": 10.0},
    {"symbol": None, "cusip": "3", "status": "no-public-series", "weight": .05}]}
FUNDAMENTALS = {"members": [{"cusip": "1", "cik": 7}, {"cusip": "2", "cik": 8}]}


class InputAuditTests(unittest.TestCase):
    def test_clean_fixture_passes_every_family(self):
        self.assertTrue(audit.availability(MARKET, VOL, CUT)["passed"])
        u = audit.universe(MARKET, BINDING, CUT)
        self.assertTrue(u["passed"])
        self.assertEqual(u["declared_exclusions"]["no_sector_in_list_revision"], ["BBB"])
        self.assertTrue(audit.identity(MARKET, BINDING, FUNDAMENTALS)["passed"])
        self.assertTrue(audit.units(MARKET)["passed"])

    def test_a_date_after_the_cut_is_rejected(self):
        market = copy.deepcopy(MARKET)
        market["assets"][0]["financials"]["eps"]["filed"] = "2025-01-30"
        self.assertEqual(audit.availability(market, VOL, CUT)["fields_after_cut"], ["assets[0].financials.eps.filed"])
        market = copy.deepcopy(MARKET)
        market["assets"][0]["price_observed_at"] = "2026-11-15T05:00:00+00:00"
        self.assertFalse(audit.availability(market, VOL, CUT)["passed"])

    def test_an_undeclared_missing_member_is_rejected(self):
        market = copy.deepcopy(MARKET)
        market["reconstruction"]["members_excluded"] = []
        self.assertEqual(audit.universe(market, BINDING, CUT)["unexplained_missing"], ["BBB"])
        market["reconstruction"]["failed"] = ["BBB"]  # no series at the cut: declared by the snapshot
        result = audit.universe(market, BINDING, CUT)
        self.assertTrue(result["passed"])
        self.assertEqual(result["declared_exclusions"]["no_price_series_at_cut"], ["BBB"])

    def test_a_price_outside_the_filed_basis_is_rejected(self):
        market = copy.deepcopy(MARKET)
        market["assets"][0]["splits"] = []
        self.assertEqual(audit.identity(market, BINDING, FUNDAMENTALS)["mismatches"][0]["check"], "filed price")

    def test_spin_off_price_adjustments_are_undone_like_splits(self):
        market = copy.deepcopy(MARKET)
        market["assets"][0]["splits"] = []
        market["assets"][0]["price_adjustments"] = [{"date": "2024-11-01", "ratio": 2.0,
                                                    "classification": "price_adjustment_not_share_split"}]
        self.assertTrue(audit.identity(market, BINDING, FUNDAMENTALS)["passed"])

    def test_units_reject_a_negative_price_and_an_out_of_range_rate(self):
        market = copy.deepcopy(MARKET)
        market["assets"][0]["history"][0]["close"] = -1
        market["macro"][0]["value"] = 46
        checks = {p["check"] for p in audit.units(market)["problems"]}
        self.assertEqual(checks, {"prices", "percent range"})
        market = copy.deepcopy(MARKET)
        market["assets"][0]["financials"]["eps"]["value"] = -40.0  # a loss above the price is real
        self.assertTrue(audit.units(market)["passed"])
        market["assets"][0]["financials"]["eps"]["value"] = 31.0  # a P/E below one is a unit error
        self.assertFalse(audit.units(market)["passed"])

    def test_engine_inputs_must_be_the_audited_bytes(self):
        sha = lambda b: hashlib.sha256(b).hexdigest()
        decision = {"market_sha256": sha(b"m"), "volatility_sha256": sha(b"v"), "engine_version": "1",
                    "status": "proposed", "positions": [{"weight": .5}, {"weight": .5}], "outcomes_read": False}
        self.assertTrue(audit.engine_inputs(b"m", b"v", decision)["passed"])
        self.assertFalse(audit.engine_inputs(b"m2", b"v", decision)["passed"])
        self.assertTrue(audit.engine_inputs(b"m", b"v", dict(decision, status="hold"))["passed"])
        self.assertFalse(audit.engine_inputs(b"m", b"v", dict(decision, status="error"))["passed"])
        # A later engine release must not invalidate an archived decision; an unrecorded engine does.
        self.assertTrue(audit.engine_inputs(b"m", b"v", dict(decision, engine_version="9.9.9"))["passed"])
        self.assertFalse(audit.engine_inputs(b"m", b"v", dict(decision, engine_version=""))["passed"])


if __name__ == "__main__":
    unittest.main()


class CloseTimeTests(unittest.TestCase):
    def test_an_archive_capture_after_the_new_york_close_is_late(self):
        market = copy.deepcopy(MARKET)
        market["price_as_of"] = market["requested_as_of"] = "2025-03-31"
        market["assets"][0]["history"] = [{"date": "2025-03-31", "close": 30.0, "adj_close": 30.0}]
        market["assets"][0]["price_observed_at"] = "2025-03-31T21:00:00+00:00"
        vol = dict(VOL, as_of="2025-03-31", parameter_fit_through="2025-03-31", instruments={})
        market["assets"][0]["bond_profile"] = {"observed_at": "2025-03-31T19:30:00+00:00", "date": "2025-03-28"}
        self.assertTrue(audit.availability(market, vol, "2025-03-31")["passed"])
        market["assets"][0]["bond_profile"]["observed_at"] = "2025-03-31T20:30:00+00:00"  # 16:30 EDT
        self.assertFalse(audit.availability(market, vol, "2025-03-31")["passed"])
