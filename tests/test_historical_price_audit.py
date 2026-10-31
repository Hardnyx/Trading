import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import base64

from scripts.historical_price_audit import (nport_marks, point_check, prepare_trailing_history,
    validate_asset, split_factor, build_audit, write_audit)
from scripts.historical_sources import MARKET_COMMIT, archive, canonical, sha


def protocol(market=None):
    value = {"protocol": "historical-price-unit-audit-v1", "source_market_commit": MARKET_COMMIT,
             "comparison_tolerance": {"absolute_usd": .01, "relative": .0001},
             "minimum_return_intervals": 2, "maximum_return_intervals": 4,
             "scope": "Synthetic test, not validation"}
    if market is not None:
        value["canonical_market_sha256"] = sha(canonical(market))
    return value


def asset():
    return {"symbol": "AAA", "type": "stock", "currency": "USD", "price_date": "2022-12-30", "splits": [],
            "history": [{"date": d, "close": c, "adj_close": c*.9} for d, c in [
                ("2022-10-31", 100), ("2022-11-01", 101), ("2022-11-30", 105), ("2022-12-30", 107)]]}


def xml():
    return b'''<root><invstOrSec><cusip>037833100</cusip><assetCat>EC</assetCat><curCd>USD</curCd>
    <units>NS</units><payoffProfile>Long</payoffProfile><fairValLevel>1</fairValLevel>
    <balance>10</balance><valUSD>1000</valUSD></invstOrSec></root>'''


class HistoricalPriceAudit(unittest.TestCase):
    def test_original_mark_is_per_share_fair_value_not_adjusted_close(self):
        marks = nport_marks(xml())
        self.assertEqual(marks["037833100"]["reported_per_share_mark"], 100)
        a = asset(); a["history"][0]["adj_close"] = 20
        r = point_check(a, marks["037833100"], "2022-10-31", a["price_date"], protocol())
        self.assertEqual(r["status"], "point-compatible")
        self.assertFalse(r["reference_is_exchange_close_certified"])
        self.assertEqual(r["reference_quantity"], 10)

    def test_non_share_units_currency_level_and_quantity_do_not_become_stock_prices(self):
        for raw in [xml().replace(b"<units>NS", b"<units>NC"), xml().replace(b"<curCd>USD", b"<curCd>EUR"),
                    xml().replace(b"<fairValLevel>1", b"<fairValLevel>2"), xml().replace(b"<balance>10", b"<balance>0")]:
            self.assertTrue(nport_marks(raw)["037833100"]["reason"])
        duplicate = xml().replace(b"</root>", xml()[6:-7] + b"</root>")
        self.assertEqual(nport_marks(duplicate)["037833100"]["reason"], "multiple-original-positions-for-cusip")

    def test_declared_future_split_is_inverted_and_not_dividends(self):
        a = asset()
        for row in a["history"]:
            row["close"] /= 10; row["adj_close"] /= 10
        a["splits"] = [{"date": "2022-12-15", "ratio": 10}]
        mark = nport_marks(xml())["037833100"]
        r = point_check(a, mark, "2022-10-31", a["price_date"], protocol())
        self.assertEqual(r["status"], "point-compatible")
        self.assertEqual(r["restored_point_close"], 100)
        self.assertEqual(r["declared_split_reversal_factor"], 10)
        self.assertFalse(r["corporate_actions_authoritatively_verified"])

    def test_fixed_tolerance_does_not_accept_a_large_price_discrepancy(self):
        a = asset(); a["history"][0]["close"] = 100.009
        mark = nport_marks(xml())["037833100"]
        self.assertEqual(point_check(a, mark, "2022-10-31", a["price_date"], protocol())["status"], "point-compatible")
        a["history"][0]["close"] = 100.011
        self.assertEqual(point_check(a, mark, "2022-10-31", a["price_date"], protocol())["status"], "point-price-discrepancy")

    def test_missing_reference_date_is_not_replaced_by_a_previous_close(self):
        a = asset()
        result = point_check(a, nport_marks(xml())["037833100"], "2022-10-30", a["price_date"], protocol())
        self.assertEqual(result["status"], "missing-exact-reference-date")

    def test_non_share_adjustments_block_reconstruction_even_if_ratio_looks_like_split(self):
        a = asset(); a["price_adjustments"] = [{"date": "2022-12-15", "ratio": 1.061}]
        result = point_check(a, nport_marks(xml())["037833100"], "2022-10-31", a["price_date"], protocol())
        self.assertEqual(result["status"], "unreconciled-future-non-share-adjustment")
        with self.assertRaisesRegex(ValueError, "non-share-event"):
            prepare_trailing_history(a, "2022-11-30", a["price_date"], protocol())

    def test_common_origin_units_preserve_all_returns_and_exclude_future_rows(self):
        a = asset(); b = copy.deepcopy(a)
        for row in b["history"]:
            row["close"] /= 20; row["adj_close"] /= 20
        b["splits"] = [{"date": "2022-12-01", "ratio": 10}, {"date": "2022-12-15", "ratio": 2}]
        x = prepare_trailing_history(a, "2022-11-30", a["price_date"], protocol())
        y = prepare_trailing_history(b, "2022-11-30", b["price_date"], protocol())
        for p, q in zip(x["history"], y["history"]):
            self.assertEqual(p["date"], q["date"])
            for key in ("close", "adj_close"):
                self.assertAlmostEqual(p[key], q[key], places=10)
        self.assertEqual(y["history"][-1]["date"], "2022-11-30")
        self.assertFalse(y["production_eligible"])
        before = copy.deepcopy(y)
        b["history"][-1]["close"] = 999999
        self.assertEqual(before, prepare_trailing_history(b, "2022-11-30", b["price_date"], protocol()))

    def test_split_on_origin_uses_post_split_units_and_reverse_split_compounds(self):
        a = asset(); a["splits"] = [{"date": "2022-11-30", "ratio": 2}, {"date": "2022-12-15", "ratio": .1}]
        self.assertAlmostEqual(split_factor(a, "2022-11-30", a["price_date"]), .1)
        self.assertAlmostEqual(split_factor(a, "2022-10-31", a["price_date"]), .2)

    def test_invalid_or_duplicate_events_and_missing_origin_fail_closed(self):
        base = asset()
        for mutate in [lambda a:a["history"].reverse(), lambda a:a["history"].append(a["history"][-1]),
                       lambda a:a.update(splits=[{"date":"2022-11-15","ratio":float("inf")}]),
                       lambda a:a.update(splits=[{"date":"2023-01-01","ratio":2}]),
                       lambda a:a.update(splits=[{"date":"2022-11-15","ratio":2}]*2)]:
            a = copy.deepcopy(base); mutate(a)
            with self.assertRaises(ValueError):validate_asset(a, base["price_date"])
        with self.assertRaisesRegex(ValueError, "origin-price"):
            prepare_trailing_history(base, "2022-11-29", base["price_date"], protocol())
        with self.assertRaisesRegex(ValueError, "insufficient"):
            prepare_trailing_history(base, "2022-11-01", base["price_date"], protocol())

    def test_audit_retains_exclusions_weights_and_never_certifies_the_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); raw = xml()
            ptr, _ = archive(root, "spy.json.gz", {"raw_base64":base64.b64encode(raw).decode(), "raw_sha256":sha(raw)})
            manifest = {"sec":{"documents":[{**ptr,"form":"NPORT-P","accession":"test"}]}}
            (root/"manifest.json").write_bytes(canonical(manifest))
            row = {"cusip":"037833100","name":"AAA","weight":.4,
                   "ticker_observation":{"source_ticker":"AAA","as_of":"2022-10-31","evidence":[]}}
            ids = {"provider_manifest_sha256":sha(canonical(manifest)),"resolver_sha256":"test", "identifier_audit":{},
                   "matrix":[{"cut":"2022-11-30","spy_source":{"status":"source-available","accession":"test","as_of":"2022-10-31"},
                              "positions":[row,{**row,"cusip":"02079K305","weight":.6,"ticker_observation":None}], "mapped_positive_weight":.4}]}
            market = {"price_as_of":"2022-12-30","assets":[asset()]}
            with patch("scripts.historical_price_audit.identifier_report", return_value=ids):
                report, bundle = build_audit(root, root, market, protocol(market))
            cut = report["matrix"][0]
            self.assertEqual(cut["point_compatible_weight"], .4)
            self.assertEqual(cut["research_history_weight"], .4)
            self.assertEqual(cut["status_counts"]["no-prior-explicit-ticker"], 1)
            self.assertFalse(cut["full_engine_replay_eligible"])
            self.assertFalse(bundle["production_eligible"])
            target = root / "output"
            write_audit(report, bundle, target, root/"bundle.gz")
            first = {p.name:p.read_bytes() for p in target.iterdir()}
            write_audit(report, bundle, target, root/"bundle.gz")
            self.assertEqual(first,{p.name:p.read_bytes() for p in target.iterdir()})
            ids["matrix"][0]["positions"][1]["ticker_observation"] = row["ticker_observation"]
            with patch("scripts.historical_price_audit.identifier_report", return_value=ids):
                ambiguous, _ = build_audit(root, root, market, protocol(market))
            self.assertEqual(ambiguous["matrix"][0]["status_counts"], {"ambiguous-ticker-to-multiple-cusips":2})
            with self.assertRaisesRegex(ValueError, "content mismatch"):
                build_audit(root, root, market, {**protocol(market),"canonical_market_sha256":"wrong"})


if __name__ == "__main__":
    unittest.main()
