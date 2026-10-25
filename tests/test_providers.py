import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.parse

from scripts import data_providers as providers
from scripts import refresh_data as collector


OBSERVED = "2026-10-24T18:00:00+00:00"
CUTOFF = "2026-10-24"


class ProviderInputs(unittest.TestCase):
    def test_public_fred_exports_work_without_a_key_and_are_identified_as_observed_current_data(self):
        request = Mock(return_value='\ufeffobservation_date,CPIAUCSL\n2010-01-01,50\n2025-08-01,100\n2026-08-01,102\n2026-09-01,.\n2026-11-01,999\n'.encode())
        result = providers.fred_csv_series(request, providers.FRED_SERIES[0], CUTOFF, OBSERVED)
        self.assertEqual(result["value"], 102)
        self.assertAlmostEqual(result["yoy"], 0.02)
        self.assertEqual(result["vintage_mode"], "observed_current")
        self.assertEqual(len(result["history"]), 2)
        self.assertNotIn("api_key", request.call_args.args[0])
        request.reset_mock()
        with self.assertRaisesRegex(providers.ProviderError, "histórico"):
            providers.fred_csv_series(request, providers.FRED_SERIES[0], "2025-01-01", OBSERVED)
        request.assert_not_called()

    def test_fred_uses_the_requested_vintage_and_omits_missing_future_or_unavailable_observations(self):
        request = Mock(return_value=json.dumps({"observations": [
            {"date": "2025-08-01", "value": "100"},
            {"date": "2026-07-01", "value": "101"},
            {"date": "2026-08-01", "value": "102"},
            {"date": "2026-09-01", "value": "."},
            {"date": "2026-10-01", "value": "999", "realtime_start": "2026-11-01"},
            {"date": "2026-11-01", "value": "999"},
            None,
        ]}).encode())
        result = providers.fred_series(request, providers.FRED_SERIES[0], CUTOFF, "test-key", OBSERVED)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.call_args.args[0]).query)
        self.assertEqual(query["realtime_start"], [CUTOFF])
        self.assertEqual(query["realtime_end"], [CUTOFF])
        self.assertEqual(result["date"], "2026-08-01")
        self.assertEqual(result["previous"], 101)
        self.assertAlmostEqual(result["yoy"], 0.02)
        self.assertEqual(result["vintage_date"], CUTOFF)
        self.assertNotIn("test-key", json.dumps(result))

    def test_consensus_revisions_compare_the_same_future_fiscal_period_and_keep_coverage(self):
        request = Mock(return_value=json.dumps([
            {"symbol": "TEST", "date": "2027-06-30", "epsAvg": 5, "epsLow": 4, "epsHigh": 6,
             "revenueAvg": 110, "numAnalystsEps": 7, "numAnalystsRevenue": 9, "currency": "USD", "apikey": "do-not-export"},
            {"symbol": "TEST", "date": "2025-06-30", "epsAvg": 1},
            {"symbol": "OTHER", "date": "2027-06-30", "epsAvg": 999},
            {"symbol": "TEST", "date": "2028-06-30", "epsAvg": "NaN", "revenueAvg": None},
        ]).encode())
        previous = {"observed_at": "2026-10-23T18:00:00+00:00", "periods": [
            {"period_end": "2027-06-30", "frequency": "annual", "eps_mean": 4, "revenue_mean": 100, "currency": "USD", "eps_basis": "non_gaap"},
        ]}
        result = providers.analyst_estimates(request, "TEST", CUTOFF, "test-key", OBSERVED, previous)
        self.assertEqual(len(result["periods"]), 1)
        row = result["periods"][0]
        self.assertEqual(row["eps_revision"], 1)
        self.assertEqual(row["eps_revision_pct"], 0.25)
        self.assertEqual(row["revenue_revision"], 10)
        self.assertEqual(row["eps_analysts"], 7)
        self.assertEqual(row["eps_basis"], "non_gaap")
        self.assertNotIn("do-not-export", json.dumps(result))
        self.assertNotIn("test-key", json.dumps(result))

    def test_current_consensus_is_never_requested_for_a_historical_cut(self):
        request = Mock()
        with self.assertRaisesRegex(providers.ProviderError, "histórico"):
            providers.analyst_estimates(request, "TEST", "2025-01-01", "test-key", OBSERVED)
        request.assert_not_called()
        self.assertIsNone(providers.retained_estimates({"observed_at": OBSERVED}, "2025-01-01"))

    def test_incompatible_currencies_and_future_observations_do_not_produce_revisions(self):
        request = Mock(return_value=b'[{"symbol":"TEST","date":"2027-06-30","epsAvg":5,"currency":"USD"}]')
        for observed, currency in [("2026-10-23T18:00:00Z", "EUR"), ("2026-10-24T19:00:00Z", "USD")]:
            previous = {"observed_at": observed, "periods": [{"period_end": "2027-06-30", "frequency": "annual", "eps_mean": 4, "currency": currency}]}
            result = providers.analyst_estimates(request, "TEST", CUTOFF, "test-key", OBSERVED, previous)
            self.assertNotIn("eps_revision", result["periods"][0])

    def test_missing_keys_and_provider_errors_do_not_disclose_credentials(self):
        request = Mock()
        with self.assertRaises(providers.ProviderError):
            providers.fred_series(request, providers.FRED_SERIES[0], CUTOFF, "", OBSERVED)
        request.assert_not_called()
        request.side_effect = urllib.error.HTTPError("https://example.test/?apikey=never-print", 401, "never-print", None, None)
        with self.assertRaises(providers.ProviderError) as caught:
            providers.analyst_estimates(request, "TEST", CUTOFF, "never-print", OBSERVED)
        self.assertEqual(caught.exception.code, 401)
        self.assertNotIn("never-print", str(caught.exception))
        request.side_effect = None
        request.return_value = b'{"Error Message":"invalid never-print"}'
        with self.assertRaises(providers.ProviderError) as caught:
            providers.analyst_estimates(request, "TEST", CUTOFF, "never-print", OBSERVED)
        self.assertNotIn("never-print", str(caught.exception))


class PublicationAndFallbacks(unittest.TestCase):
    def test_a_local_research_cut_does_not_replace_newer_public_market_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collector, "OUTPUT", Path(directory) / "market.json"), patch.object(collector, "RESEARCH_OUTPUT", Path(directory) / "research.json"):
            collector.OUTPUT.write_text(json.dumps({"assets": [{"symbol": "TEST", "price": 20}]}))
            collector.RESEARCH_OUTPUT.write_text(json.dumps({"assets": [{"symbol": "TEST", "price": 10, "analyst_estimates": {"observed_at": OBSERVED, "periods": []}}]}))
            result = collector.previous_snapshot()["assets"][0]
            self.assertEqual(result["price"], 20)
            self.assertEqual(result["analyst_estimates"]["observed_at"], OBSERVED)

    def test_licensed_research_stays_in_private_files_and_is_omitted_from_public_cuts(self):
        snapshot = {"schema_version": 1, "generated_at": OBSERVED, "requested_as_of": CUTOFF,
                    "price_as_of": "2026-10-23", "assets": [{"symbol": "TEST", "history": [],
                    "analyst_estimates": {"observed_at": OBSERVED, "periods": [{"eps_mean": 123.45}]}}], "macro": []}
        original = copy.deepcopy(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            public, private = folder / "dist/market.json", folder / "research/latest.json"
            collector.write_snapshot(snapshot, public, private)
            archive = collector.archive_observation(snapshot, folder / "public-archive")
            self.assertNotIn("analyst_estimates", public.read_text())
            self.assertNotIn("123.45", archive.read_text())
            self.assertEqual(json.loads(private.read_text())["assets"][0]["analyst_estimates"]["periods"][0]["eps_mean"], 123.45)
            self.assertEqual(len(list((folder / "research/snapshots").glob("*/*.json"))), 1)
        self.assertEqual(snapshot, original)

    def test_public_actions_never_download_fmp_data_even_when_a_key_exists(self):
        today = collector.dt.datetime.now(collector.UTC).date().isoformat()
        quote = {"price": 10, "price_date": today, "change": 0,
                 "history": [{"date": today, "close": 10, "adj_close": 10}]}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), \
             patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "REPOSITORY_PRIVATE": "false", "FMP_API_KEY": "never-print-test-key"}, clear=True), \
             patch.object(collector, "ROOT", Path(directory)), \
             patch.object(collector, "OUTPUT", Path(directory) / "dist/market.json"), \
             patch.object(collector, "RESEARCH_OUTPUT", Path(directory) / "research/latest.json"), \
             patch.object(collector, "ARCHIVE", Path(directory) / "snapshots"), \
             patch.object(collector, "ASSETS", [("TEST", "Test", "Sector", 1, 0.05, 20)]), \
             patch.object(collector, "expanded_universe", return_value=[]), \
             patch.object(collector, "prices", return_value=quote), \
             patch.object(collector, "financials", return_value={}), \
             patch.object(collector, "filings", return_value=[]), \
             patch.object(collector, "treasury_curves", return_value=[]), \
             patch.object(collector, "fred_csv_series", side_effect=providers.ProviderError("CSV no disponible")), \
             patch.object(collector, "bls_batch", return_value=[{"id": "CPI", "value": 1, "date": today}]), \
             patch.object(collector, "analyst_estimates") as estimates, \
             patch("sys.argv", ["refresh_data.py"]):
            collector.main()
            estimates.assert_not_called()
            saved = json.loads(collector.OUTPUT.read_text())
            self.assertEqual(next(p for p in saved["providers"] if p["id"] == "fmp")["status"], "private_required")
            self.assertNotIn("never-print-test-key", collector.OUTPUT.read_text())

    def test_source_failures_cannot_retain_prices_or_fundamentals_from_after_the_cut(self):
        old = {"TEST": {"price_date": "2026-12-01", "price": 999, "dividend_per_share": 20,
                        "history": [{"date": "2026-10-22", "close": 9}, {"date": "2026-10-23", "close": 10}, {"date": "2026-12-01", "close": 999}],
                        "financials": {"eps": {"value": 100, "period_end": "2026-09-30", "filed": "2026-11-01"}},
                        "filings": [{"filing_date": "2026-11-01"}]}}
        with patch.object(collector, "prices", side_effect=ValueError), patch.object(collector, "financials", side_effect=ValueError), patch.object(collector, "filings", side_effect=ValueError):
            asset, warnings = collector.build_asset(("TEST", "Test", "Sector", 1, 0.05, 20), CUTOFF, old)
        self.assertEqual(asset["price"], 10)
        self.assertEqual(asset["price_date"], "2026-10-23")
        self.assertIsNone(asset["financials"]["eps"])
        self.assertIsNone(asset["dividend_per_share"])
        self.assertEqual(asset["filings"], [])
        self.assertEqual(len(warnings), 3)

    def test_bls_uses_the_documented_post_payload_and_keeps_a_single_observation(self):
        payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [{"year": "2026", "period": "M09", "value": "4.1"}]}]}}
        with patch.dict(os.environ, {}, clear=True), patch.object(collector, "download", return_value=json.dumps(payload).encode()) as request:
            result = collector.bls_series("LNS14000000", "Desempleo", CUTOFF)
        self.assertEqual(request.call_args.kwargs["payload"], {"seriesid": ["LNS14000000"], "startyear": "2024", "endyear": "2026"})
        self.assertEqual(result["value"], 4.1)
        self.assertIsNone(result["previous"])


    def test_registered_bls_batch_normalizes_multiple_series_without_exposing_key(self):
        response = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
            {"seriesID": "CUSR0000SA0", "data": [
                {"year": "2026", "period": "M09", "value": "320.5"},
                {"year": "2025", "period": "M09", "value": "310.0"},
                {"year": "2026", "period": "M13", "value": "999"}]},
            {"seriesID": "LNS14000000", "data": [
                {"year": "2026", "period": "M09", "value": "4.1"}]},
        ]}}
        definitions = [collector.BLS_SERIES[0], collector.BLS_SERIES[2]]
        with patch.dict(os.environ, {"BLS_API_KEY": "never-log-this-key"}), \
             patch.object(collector, "download", return_value=json.dumps(response).encode()) as request:
            rows = collector.bls_batch(definitions, CUTOFF)
        self.assertEqual({row["id"] for row in rows}, {"CPI", "UNRATE"})
        cpi = next(row for row in rows if row["id"] == "CPI")
        self.assertAlmostEqual(cpi["yoy"], 320.5 / 310 - 1)
        self.assertEqual(cpi["date"], "2026-09-01")
        self.assertEqual(cpi["vintage_mode"], "observed_current")
        url, cache = request.call_args.args[:2]
        self.assertIn("/v2/", url)
        self.assertNotIn("never-log-this-key", url + cache)
        self.assertEqual(request.call_args.kwargs["payload"]["registrationkey"], "never-log-this-key")

    def test_bls_partial_series_and_failure_message_are_safe(self):
        definition = collector.BLS_SERIES[0]
        response = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [
            {"seriesID": "CUSR0000SA0", "data": [{"year": "2026", "period": "M09", "value": "320.5"}]}
        ]}}
        with patch.dict(os.environ, {"BLS_API_KEY": "secret"}, clear=True), \
             patch.object(collector, "download", return_value=json.dumps(response).encode()):
            rows = collector.bls_batch([definition, collector.BLS_SERIES[2]], CUTOFF)
        self.assertEqual(len(rows), 1)
        with patch.dict(os.environ, {"BLS_API_KEY": "secret"}, clear=True), \
             patch.object(collector, "download", side_effect=urllib.error.HTTPError("https://example/?key=secret", 403, "secret", None, None)):
            with self.assertRaises(providers.ProviderError) as caught:
                collector.bls_batch([definition], CUTOFF)
        self.assertNotIn("secret", str(caught.exception))
        self.assertEqual(caught.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
