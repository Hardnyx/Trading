"""Prepare dated CUSIP-to-price-identifier evidence requests from original SEC filings.

The output requests missing vendor instrument IDs; it never fills those IDs
from present-day tickers or certifies historical price series. Reports and
original source archives must agree before any request is emitted.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

if __package__:
    from .audit_historical_inputs import read_record
    from .first_cut_source_audit import ROOT, audit
    from .historical_identifiers import parse_observations
    from .historical_sources import canonical, parse_nport, sha
else:
    from audit_historical_inputs import read_record
    from first_cut_source_audit import ROOT, audit
    from historical_identifiers import parse_observations
    from historical_sources import canonical, parse_nport, sha

PROVIDER_DIR = "data/historical/provider-inputs-v1"
IDENTIFIER_DIR = "data/historical/identifier-sources-v1"
OBSERVATIONS = "data/historical/identifier-observations-v1/observations.json.gz"
COVERAGE = "data/historical/identifier-observations-v1/coverage.json"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def ensure_original_position(original, annotated):
    """A derived position may add evidence, but may not edit SEC facts."""
    for field in ("cusip", "name", "title", "symbol", "weight"):
        require(original.get(field) == annotated.get(field),
                "Annotated position changed original SPY " + field)
    require(annotated.get("price_instrument_binding") is None,
            "Ticker observation was silently promoted to vendor instrument identity")


def evidence_before_cut(receipt, cut):
    require(isinstance(receipt, dict) and receipt.get("available_after_day", "9999") < cut,
            "Original identifier filing was not available before the decision")
    require(receipt.get("raw_sha256") and receipt.get("source_url") and
            receipt.get("fund") and receipt.get("accession"),
            "Incomplete original identifier receipt")


def verified_documents(root, evidence):
    """Reparse only the N-PORT filings cited by this cut; fail on any mismatch."""
    directory = root / IDENTIFIER_DIR
    manifest = json.loads((directory / "manifest.json").read_bytes())
    pointers = {(ptr["fund"], ptr["accession"]): ptr for ptr in manifest["documents"]}
    require(len(pointers) == len(manifest["documents"]), "Duplicate SEC source document")
    parsed = {}
    for key in sorted(set((e["fund"], e["accession"]) for e in evidence)):
        require(key in pointers, "Cited SEC identifier filing absent from manifest")
        pointer = pointers[key]
        record, raw = read_record(directory, pointer)
        result = parse_observations(raw, pointer["fund"], pointer["filing"])
        require(sha(canonical(result)) == pointer["normalized_sha256"],
                "SEC identifier derivation changed")
        require(record["source_url"] == evidence_url(key) and
                result["as_of"] == pointer["as_of"] and
                result["available_after_day"] == pointer["available_after_day"],
                "SEC identifier filing provenance changed")
        parsed[key] = {"positions": result["observations"], "pointer": pointer}
    return parsed


def evidence_url(key):
    fund, accession = key
    from_path = accession.replace("-", "")
    return "https://www.sec.gov/Archives/edgar/data/1100663/" + from_path + "/primary_doc.xml"


def build_requests(root=ROOT):
    root = Path(root)
    triage = audit(root)
    cut = triage["candidate_cut"]
    compact = json.loads((root / COVERAGE).read_bytes())
    archive = (root / OBSERVATIONS).read_bytes()
    original = json.loads(gzip.decompress(archive))
    require({key: value for key, value in original.items() if key != "matrix"} ==
            {key: value for key, value in compact.items() if key != "matrix"},
            "Original SEC identifier bundle differs from published report")
    require([{key: value for key, value in row.items() if key != "positions"}
             for row in original["matrix"]] == compact["matrix"],
            "Origin-level identity coverage differs from archived positions")
    origin = next(row for row in original["matrix"] if row["cut"] == cut)
    require(origin["spy_source"]["status"] == "source-available" and
            origin["spy_source"]["accession"] == triage["evidence_at_cut"]["spy_accession"],
            "Selected SPY filing differs from source triage")

    provider_dir = root / PROVIDER_DIR
    provider = json.loads((provider_dir / "manifest.json").read_bytes())
    pointers = [ptr for ptr in provider["sec"]["documents"]
                if ptr["accession"] == origin["spy_source"]["accession"]]
    require(len(pointers) == 1, "SPY filing is absent or ambiguous")
    pointer = pointers[0]
    record, raw = read_record(provider_dir, pointer)
    normalized = parse_nport(raw, record["filing"])
    require(normalized == pointer["normalized"] and
            normalized["as_of"] == origin["spy_source"]["as_of"], "Original SPY filing changed")
    positions = normalized["positions"]
    annotated = origin["positions"]
    require(len(positions) == len(annotated), "Archived SPY position count changed")

    receipts = []
    for pos in annotated:
        ticker = pos.get("ticker_observation")
        if ticker is not None:
            require(ticker["source_ticker"] and
                    ticker["as_of"] <= cut and ticker["evidence"],
                    "Ticker observation lacks dated original evidence")
            for receipt in ticker["evidence"]:
                evidence_before_cut(receipt, cut)
                require(receipt["available_after_day"] < cut and
                        ticker["as_of"] <= cut, "Look-ahead in identifier source")
                receipts.append(receipt)
    docs = verified_documents(root, receipts)
    output = []
    status_counts = Counter()
    linked_weight = 0
    for index, (sec, pos) in enumerate(zip(positions, annotated)):
        ensure_original_position(sec, pos)
        if sec["weight"] <= 0:
            continue
        cusip = sec["cusip"]
        ticker = pos.get("ticker_observation")
        status_counts[pos["identifier_status"]] += 1
        proof = []
        if ticker:
            require(pos["identifier_status"] == "explicit-ticker-observed",
                    "Inconsistent ticker observation status")
            for receipt in ticker["evidence"]:
                doc = docs[(receipt["fund"], receipt["accession"])]
                p = doc["pointer"]
                require(receipt["raw_sha256"] == p["raw_sha256"] and
                        receipt["available_after_day"] == p["available_after_day"] and
                        receipt["source_url"] == evidence_url((receipt["fund"], receipt["accession"])) and
                        any(o["cusip"] == cusip and
                            o["source_ticker"] == ticker["source_ticker"]
                            for o in doc["positions"]),
                        "Original SEC identifier observation cannot be reproduced")
                proof.append({"fund": receipt["fund"], "accession": receipt["accession"],
                              "as_of": p["as_of"], "available_after_day": p["available_after_day"],
                              "original_sha256": p["raw_sha256"]})
            linked_weight += sec["weight"]
        else:
            require(pos["identifier_status"] != "explicit-ticker-observed",
                    "Ticker status claims original evidence that is absent")
        output.append({
            "source_position": index, "cusip": cusip,
            "original_spy_name": sec["name"], "weight": sec["weight"],
            "original_ticker_observation": ticker["source_ticker"] if ticker else None,
            "ticker_receipts": proof,
            "identifier_status": pos["identifier_status"],
            "vendor_instrument_id": None,
            "vendor_price_series_verified": False,
            "original_price_vintage_verified": False,
            "production_eligible": False,
        })
    require(abs(linked_weight - origin["mapped_positive_weight"]) < 1e-10,
            "SEC position weights do not reconcile to original identifier coverage")
    require(not any(p["vendor_instrument_id"] is not None for p in output),
            "Request export must not invent vendor instrument IDs")
    return {
        "protocol": "historical-instrument-identity-requests-v1",
        "cut": cut, "source_market_commit": triage["source_chain"]["market_commit"],
        "source_manifest_sha256": triage["source_chain"]["provider_manifest_sha256"],
        "identifier_manifest_sha256": triage["source_chain"]["identifier_manifest_sha256"],
        "identifier_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "spy_original_accession": pointer["accession"],
        "spy_original_sha256": pointer["raw_sha256"],
        "source_role": "historical-identity-data-collection-request-not-a-vendor-match",
        "counts": {"positive_positions": len(output), "with_explicit_ticker": sum(
            p["original_ticker_observation"] is not None for p in output),
            "without_explicit_ticker": sum(p["original_ticker_observation"] is None for p in output),
            "original_source_documents_reparsed": len(docs),
            "status_counts": dict(sorted(status_counts.items()))},
        "positive_spy_weight": sum(p["weight"] for p in output),
        "explicit_ticker_weight": linked_weight,
        "requests": output, "full_engine_replay_ready": False, "production_eligible": False,
        "predictive_validation": "not-established",
        "next_evidence": "Historical permanent vendor instrument ID, historical CUSIP/security binding, exchange and currency, validity dates, split/event history, original response and provider vintage; original ticker alone is insufficient",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="out/historical-identity-requests-v1.json.gz")
    args = parser.parse_args(argv)
    result = build_requests(ROOT)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress(canonical(result) + b"\n", mtime=0))
    print(json.dumps({"cut": result["cut"], **result["counts"],
                      "explicit_ticker_weight": round(result["explicit_ticker_weight"], 6),
                      "full_engine_replay_ready": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
