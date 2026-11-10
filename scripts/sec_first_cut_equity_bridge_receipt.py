"""Verify the real first-cut Microsoft equity-class source intersection.

This report records a dated research *candidate*: the SEC 10-Q's common-stock
registration and a separate N-PORT CUSIP/ticker observation. It never
certifies a permanent CIK/CUSIP mapping, tradable price or predictive claim.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

if __package__:
    from .historical_identity_requests import build_requests
    from .historical_vendor_identity import request_hash, valid_cusip
    from .historical_sec_fsd_intake import require
else:
    from historical_identity_requests import build_requests
    from historical_vendor_identity import request_hash, valid_cusip
    from historical_sec_fsd_intake import require

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"data/historical/sec-first-cut-msft-equity-bridge-v1.json"
OBSERVATION = ROOT/"data/historical/sec-first-cut-original-source-observation-v1.json"
PRIMARY = ROOT/"data/historical/sec-first-cut-primary-inline-review-v1.json"
SCHEMA = "sec-first-cut-original-equity-bridge-audit-v1"
ARTIFACT_SHA256 = "0c689aa0573a7b945c6b210509549b77edc3daf6401d8fe5caa40ef91d4ba3bf"


def audit(source=SOURCE, *, expected_sha=ARTIFACT_SHA256, requests=None):
    raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == expected_sha,
            "Real SEC equity bridge differs from frozen workflow artifact")
    report = json.loads(raw)
    obs = json.loads(OBSERVATION.read_bytes())
    primary = json.loads(PRIMARY.read_bytes())
    req = requests if requests is not None else build_requests()
    original = obs["source_provenance"]["original_edgar_filing"]
    require(report["schema"] ==
            "sec-first-cut-issuer-equity-cross-source-candidate-v1"
            and report["cut"] == req["cut"] == "2024-12-31"
            and report["original_msft_10q_accession"] == original["accession"]
            and report["original_msft_10q_sha256"] == original["sha256"]
            and report["issuer_cik_as_filed"] == original["cik"] == "789019"
            and report["original_msft_primary_filename"] ==
                primary["original_primary_filename"]
            and report["original_msft_primary_sha256"] ==
                primary["original_primary_sha256"]
            and report["issuer_original_acceptance_utc"] ==
                primary["original_header_accepted_utc"]
            and datetime.fromisoformat(report["issuer_original_acceptance_utc"]) <
                datetime.fromisoformat(obs["cut"].replace("Z","+00:00")),
            "Original SEC 10-Q filing identity is inconsistent or postcut")
    common = report["issuer_common_stock_registration"]
    require(common == {
        "class_title_as_filed": "Common stock, $0.00000625 par value per share",
        "trading_symbol_as_filed": "MSFT",
        "exchange_as_filed": "Nasdaq",
        "security_class": "common-stock",
    }, "SEC issuer ticker must refer to the exact common-stock class")
    notes = report["other_registration_classes_with_same_symbol"]
    require(notes == [
        {"class_title_as_filed":"3.125% Notes due 2028",
         "trading_symbol_as_filed":"MSFT","exchange_as_filed":"Nasdaq",
         "security_class":"debt-note"},
        {"class_title_as_filed":"2.625% Notes due 2033",
         "trading_symbol_as_filed":"MSFT","exchange_as_filed":"Nasdaq",
         "security_class":"debt-note"},
    ] and report["ticker_not_a_unique_security_identifier"] is True,
            "Ticker-only merge would confuse Microsoft common stock with debt")
    require(report["spy_original_accession"] == req["spy_original_accession"]
            and report["spy_original_sha256"] == req["spy_original_sha256"]
            and report["spy_historical_request_sha256"] == request_hash(req),
            "Original SPY and dated identifier requests no longer reproduce")
    candidates = [x for x in req["requests"]
                  if x["original_ticker_observation"] == "MSFT"]
    require(len(candidates) == 1,
            "The original N-PORT MSFT observation is missing or ambiguous")
    row = candidates[0]
    require(report["spy_source_position"] == row["source_position"] == 181
            and report["spy_cusip_as_filed"] == row["cusip"] == "594918104"
            and valid_cusip(row["cusip"])
            and report["spy_weight_as_filed"] == row["weight"]
            and report["spy_issuer_name_as_filed"] == row["original_spy_name"]
            and row["weight"] > 0
            and row["vendor_instrument_id"] is None
            and row["vendor_price_series_verified"] is False
            and row["original_price_vintage_verified"] is False
            and row["production_eligible"] is False,
            "Original SPY position changed or claims a vendor/price binding")
    receipts = report["spy_ticker_evidence"]
    require(receipts == row["ticker_receipts"] and receipts == [{
        "fund":"ILCB",
        "accession":"0001752724-24-295861",
        "as_of":"2024-10-31",
        "available_after_day":"2024-12-30",
        "original_sha256":
            "7f5ecc21bbec25448de1ea0606d5b99cf6928ba98ad3fe398fd3d29088187cbc",
    }] and all(r["as_of"] <= r["available_after_day"] < req["cut"]
               for r in receipts),
            "Ticker evidence must remain the pre-cut original ILCB N-PORT")
    require(report["source_symbol_intersection"] == "MSFT"
            and report["source_link_status"] ==
                "retrospective-original-source-equity-candidate"
            and report["independent_historical_cik_to_cusip_permanent_mapping_verified"] is False
            and report["vendor_instrument_id"] is None
            and report["historical_quote_series_verified"] is False
            and report["delisting_and_corporate_actions_verified"] is False
            and report["universe_or_portfolio_replay_eligible"] is False
            and report["eligible_full_engine_cuts_added"] == 0
            and report["confirmatory_origins_added"] == 0
            and report["predictive_validation"] == "not-established",
            "Original symbol intersection must never certify a trade or model")
    return {
        "schema": SCHEMA, "cut": req["cut"],
        "frozen_artifact_sha256": digest,
        "spy_original_accession": req["spy_original_accession"],
        "issuer_original_accession": original["accession"],
        "ticker": "MSFT",
        "historical_spy_cusip_as_filed": row["cusip"],
        "historical_spy_weight_as_filed": row["weight"],
        "independently_dated_nport_ticker_receipts": len(receipts),
        "issuer_common_stock_class_verified_in_original_10q": True,
        "same_symbol_debt_classes_kept_separate": len(notes),
        "historical_price_or_permanent_id_certified": False,
        "source_first_publication_independently_verified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args(argv)
    result=audit()
    if args.verify:
        require(result["same_symbol_debt_classes_kept_separate"]==2 and
                result["historical_price_or_permanent_id_certified"] is False
                and result["eligible_full_engine_cuts_added"]==0,
                "Historical ticker is not an eligible security price identity")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
