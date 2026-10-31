import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.historical_identifiers import (CIK, FUNDS, PROTOCOL, collect,
    cusip_valid, discovery_url, match_positions, original_url, parse_discovery,
    parse_observations, verified_observations, observation_pointer)
from scripts.historical_sources import archive, canonical, sha
from scripts import historical_identifiers as identifiers


FILING = {"accession": "0000000001-22-000001", "filing_date": "2022-11-25", "form": "NPORT-P"}


def source_xml(ticker="AAPL", period="2022-09-30", series=FUNDS["IVV"]):
    identity = f'<ticker value="{ticker}"/>' if ticker else '<isin value="US0378331005"/>'
    return f'''<edgarSubmission xmlns="urn:sec"><genInfo><regCik>{CIK}</regCik>
      <seriesId>{series}</seriesId><repPdDate>{period}</repPdDate></genInfo>
      <invstOrSecs><invstOrSec><name>APPLE INC</name><lei>APPLE-LEI</lei><title>Common</title>
      <cusip>037833100</cusip><identifiers>{identity}</identifiers>
      <assetCat>EC</assetCat><curCd>USD</curCd><payoffProfile>Long</payoffProfile>
      </invstOrSec></invstOrSecs></edgarSubmission>'''.encode()


def atom():
    accession = FILING["accession"]
    index = original_url(accession).replace("primary_doc.xml", accession + "-index.htm")
    return f'''<feed xmlns="http://www.w3.org/2005/Atom"><company-info><cik>{CIK}</cik></company-info>
      <entry><content><accession-number>{accession}</accession-number><filing-date>2022-11-25</filing-date>
      <filing-type>NPORT-P</filing-type><filing-href>{index}</filing-href></content></entry></feed>'''.encode()


def source(ticker="AAPL", period="2022-09-30", filed="2022-11-25"):
    filing = {**FILING, "filing_date": filed}
    return {**parse_observations(source_xml(ticker, period), "IVV", filing),
            "fund": "IVV", "accession": FILING["accession"], "source_url": original_url(FILING["accession"]),
            "raw_sha256": "test-source"}


class HistoricalIdentifiers(unittest.TestCase):
    def test_cusip_check_digit_and_share_classes_are_exact(self):
        for cusip in ["037833100", "02079K107", "02079K305", "084670702", "084670108", "G1151C101"]:
            self.assertTrue(cusip_valid(cusip), cusip)
        for cusip in ["037833101", "000000000", "AAPL", "03783310", "0378331000"]:
            self.assertFalse(cusip_valid(cusip), cusip)
        positions = [{"cusip": "02079K305", "name": "ALPHABET", "weight": .4}]
        s = source(); s["observations"][0].update(cusip="02079K107", name="ALPHABET", source_ticker="GOOG")
        self.assertIsNone(match_positions(positions, [s], "2022-11-30")[0]["ticker_observation"])

    def test_original_explicit_symbol_is_required_and_punctuation_not_guessed(self):
        n = parse_observations(source_xml(), "IVV", FILING)
        self.assertEqual(n["observations"][0]["source_ticker"], "AAPL")
        n = parse_observations(source_xml(None), "IVV", FILING)
        self.assertEqual(n["observations"], [])
        self.assertEqual(n["rejected"]["missing-or-ambiguous-explicit-ticker"], 1)
        n = parse_observations(source_xml("BRK/B"), "IVV", FILING)
        self.assertEqual(n["observations"][0]["source_ticker"], "BRK/B")

    def test_wrong_series_registrant_or_future_period_fail(self):
        variants = [source_xml(series=FUNDS["ITOT"]), source_xml().replace(str(CIK).encode(), b"1234567"),
                    source_xml(period="2022-12-31"), b"<!DOCTYPE x>" + source_xml()]
        for raw in variants:
            with self.assertRaises(ValueError):
                parse_observations(raw, "IVV", FILING)

    def test_derivatives_cash_and_invalid_identifiers_cannot_link_equities(self):
        variants = [source_xml().replace(b"<assetCat>EC", b"<assetCat>DE"),
                    source_xml().replace(b"<curCd>USD", b"<curCd>EUR"),
                    source_xml().replace(b"<payoffProfile>Long", b"<payoffProfile>Short"),
                    source_xml().replace(b"037833100", b"000000000")]
        for raw in variants:
            self.assertEqual(parse_observations(raw, "IVV", FILING)["observations"], [])

    def test_publication_and_120_day_policy_are_not_relaxed(self):
        positions = [{"cusip": "037833100", "weight": .4}]
        s = source()
        for cut in ["2022-10-31", "2022-11-29", "2023-01-31"]:
            self.assertIsNone(match_positions(positions, [s], cut)[0]["ticker_observation"])
        row = match_positions(positions, [s], "2022-11-30")[0]
        self.assertEqual(row["ticker_observation"]["source_ticker"], "AAPL")
        self.assertIsNone(row["price_instrument_binding"])
        self.assertEqual(row["weight"], .4)

    def test_future_amendments_cannot_rewrite_earlier_mapping(self):
        positions = [{"cusip": "037833100", "weight": .4}]
        original = source()
        amendment = source("NEW", filed="2022-12-15")
        row = match_positions(positions, [amendment, original], "2022-11-30")[0]
        self.assertEqual(row["ticker_observation"]["source_ticker"], "AAPL")
        row = match_positions(positions, [amendment, original], "2022-12-30")[0]
        self.assertEqual(row["identifier_status"], "conflicting-explicit-identifiers")

    def test_conflicting_tickers_or_issuer_leis_do_not_get_majority_vote(self):
        positions = [{"cusip": "037833100", "weight": .4}]
        first = source()
        for field, value in [("source_ticker", "OTHER"), ("lei", "OTHER-ISSUER")]:
            second = copy.deepcopy(first); second["observations"][0][field] = value
            result = match_positions(positions, [first, second], "2022-11-30")[0]
            self.assertEqual(result["identifier_status"], "conflicting-explicit-identifiers")
            self.assertIsNone(result["ticker_observation"])

    def test_discovery_requires_correct_company_accession_and_window(self):
        self.assertEqual(parse_discovery(atom(), "2022-05-01", "2022-11-30"), [FILING])
        self.assertEqual(parse_discovery(atom(), "2022-05-01", "2022-10-31"), [])
        for raw in [atom().replace(str(CIK).encode(), b"1234567"), atom().replace(b"-index.htm", b"-other.htm")]:
            with self.assertRaises(ValueError):
                parse_discovery(raw, "2022-05-01", "2022-11-30")

    def fixture(self, folder):
        root = Path(folder)
        raw = atom()
        source_ = {"protocol": PROTOCOL, "kind": "sec-series-atom", "source_url": discovery_url("IVV", "2022-11-30"),
                   "raw_base64": base64.b64encode(raw).decode(), "raw_sha256": sha(raw)}
        discovery, _ = archive(root, "discovery.json.gz", source_)
        raw = source_xml()
        source_ = {"protocol": PROTOCOL, "kind": "sec-nport-identifiers", "source_url": original_url(FILING["accession"]),
                   "raw_base64": base64.b64encode(raw).decode(), "raw_sha256": sha(raw), "fund": "IVV", "filing": FILING}
        pointer, _ = archive(root, "original.json.gz", source_)
        from scripts.historical_sources import MARKET_COMMIT
        manifest = {"protocol": PROTOCOL, "source_market_commit": MARKET_COMMIT, "cuts": ["2022-11-30"],
                    "funds": FUNDS, "discovery": {"IVV": discovery}, "documents": [{**pointer, "fund": "IVV", "accession": FILING["accession"],
                     "filing": FILING, **observation_pointer(parse_observations(raw, "IVV", FILING))}]}
        (root / "manifest.json").write_bytes(canonical(manifest))
        return root, manifest

    def test_reverification_uses_original_bytes_not_manifest_mapping_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            root, manifest = self.fixture(folder)
            rows, audit = verified_observations(root, ["2022-11-30"])
            self.assertEqual(rows[0]["observations"][0]["source_ticker"], "AAPL")
            self.assertEqual(audit["verified_documents"], 1)
            self.assertEqual(audit["missing_discoveries"], ["ILCB", "ISCB", "ITOT", "IYY"])
            manifest["documents"][0]["normalized_sha256"] = "FAKE"
            (root / "manifest.json").write_bytes(canonical(manifest))
            with self.assertRaisesRegex(ValueError, "original XML"):
                verified_observations(root, ["2022-11-30"])

    def test_corrupt_or_duplicate_originals_fail_and_missing_sources_remain_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root, manifest = self.fixture(folder)
            saved = (root / "original.json.gz").read_bytes()
            (root / "original.json.gz").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verified_observations(root, ["2022-11-30"])
            (root / "original.json.gz").write_bytes(saved)
            manifest["documents"] *= 2
            (root / "manifest.json").write_bytes(canonical(manifest))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                verified_observations(root, ["2022-11-30"])
            manifest["documents"] = []
            (root / "manifest.json").write_bytes(canonical(manifest))
            rows, audit = verified_observations(root, ["2022-11-30"])
            self.assertEqual(rows, [])
            self.assertEqual(len(audit["missing_documents"]), 1)

    def test_collection_reuses_first_original_and_keeps_secrets_out_of_errors(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return atom() if "browse-edgar" in url else source_xml()
        with tempfile.TemporaryDirectory() as folder, patch.object(identifiers, "FUNDS", {"IVV": FUNDS["IVV"]}), patch("builtins.print"):
            first = collect(folder, ["2022-11-30"], fetch)
            self.assertTrue(first["collection_complete"])
            pointer = first["documents"][0]
            second = collect(folder, ["2022-11-30"], fetch)
            self.assertEqual(pointer, second["documents"][0])
            self.assertEqual(sum("/Archives/" in url for url in calls), 1)
            rows, audit = verified_observations(folder, ["2022-11-30"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(audit["missing_discoveries"], [])
        def broken(url, **kwargs):
            raise RuntimeError("sentinel-private-key")
        with tempfile.TemporaryDirectory() as folder, patch.object(identifiers, "FUNDS", {"IVV": FUNDS["IVV"]}):
            result = collect(folder, ["2022-11-30"], broken)
            self.assertFalse(result["collection_complete"])
            self.assertEqual(result["errors"], [{"fund": "IVV", "kind": "RuntimeError"}])
            self.assertNotIn("sentinel-private-key", (Path(folder) / "manifest.json").read_text())


if __name__ == "__main__":
    unittest.main()
