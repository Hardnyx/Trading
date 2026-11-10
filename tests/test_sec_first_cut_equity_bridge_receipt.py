"""Real archived MSFT bridge: audit the original SEC source keys and gates."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.historical_identity_requests import build_requests
from scripts.sec_first_cut_equity_bridge_receipt import (
    audit, SOURCE, ARTIFACT_SHA256,
)


class MsftEquityBridgeReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = build_requests()

    def test_real_original_msft_candidate_without_price_promotion(self):
        result = audit(requests=self.requests)
        self.assertEqual(result["frozen_artifact_sha256"], ARTIFACT_SHA256)
        self.assertEqual(result["historical_spy_cusip_as_filed"], "594918104")
        self.assertEqual(result["independently_dated_nport_ticker_receipts"], 1)
        self.assertEqual(result["same_symbol_debt_classes_kept_separate"], 2)
        self.assertFalse(result["historical_price_or_permanent_id_certified"])
        self.assertFalse(result["source_first_publication_independently_verified"])
        self.assertEqual(result["eligible_full_engine_cuts_added"], 0)

    def test_modified_bytes_rejected_before_any_accounting(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"sample.json"
            file.write_bytes(SOURCE.read_bytes().replace(b"594918104",b"594918105"))
            with self.assertRaisesRegex(ValueError,"differs from frozen"):
                audit(file,requests=self.requests)

    def test_adversarial_recomputed_digest_does_not_overwrite_original_identity(self):
        original=json.loads(SOURCE.read_bytes())
        for kind in ("debt", "common_stock", "ticker", "cusip", "weight", "position",
                     "late", "provider", "price", "permanent", "eligible", "fake_source"):
            row=copy.deepcopy(original)
            if kind=="debt":
                row["other_registration_classes_with_same_symbol"]=[]
            elif kind=="common_stock":
                row["issuer_common_stock_registration"]["security_class"]="debt-note"
            elif kind=="ticker":
                row["source_symbol_intersection"]="MSFT.B"
            elif kind=="cusip":
                row["spy_cusip_as_filed"]="594918105"
            elif kind=="weight":
                row["spy_weight_as_filed"]=0.9
            elif kind=="position":
                row["spy_source_position"]=182
            elif kind=="late":
                row["spy_ticker_evidence"][0]["available_after_day"]="2025-01-01"
            elif kind=="provider":
                row["vendor_instrument_id"]="fabricated"
            elif kind=="price":
                row["historical_quote_series_verified"]=True
            elif kind=="permanent":
                row["independent_historical_cik_to_cusip_permanent_mapping_verified"]=True
            elif kind=="eligible":
                row["eligible_full_engine_cuts_added"]=1
            else:
                row["spy_original_sha256"]="f"*64
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                file=Path(d)/"case.json"
                raw=(json.dumps(row,indent=2)+"\n").encode()
                file.write_bytes(raw)
                with self.assertRaises(ValueError):
                    audit(file,requests=self.requests,
                          expected_sha=hashlib.sha256(raw).hexdigest())


if __name__=="__main__":
    unittest.main()
