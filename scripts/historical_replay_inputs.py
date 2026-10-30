"""Materialize verified ALFRED vintages for each frozen account-review cut.

This is a source-provenance adapter, not a portfolio backtest. It never
substitutes current macro values for missing historical records.
"""
import argparse
import gzip
import json
from pathlib import Path
import subprocess

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_sources import (MARKET_COMMIT, PROTOCOL, ROOT, SERIES,
        account_origins, canonical, sha, validate_macro_record)
else:
    from audit_historical_inputs import read_record
    from historical_sources import (MARKET_COMMIT, PROTOCOL, ROOT, SERIES,
        account_origins, canonical, sha, validate_macro_record)


def materialize_macro_inputs(root, cuts, definitions=SERIES):
    root = Path(root)
    manifest_path = root / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    names = [definition[0] for definition in definitions]
    if (manifest.get("protocol") != PROTOCOL or
            manifest.get("cuts") != cuts or
            manifest.get("series_ids") != names):
        raise ValueError("Source protocol, calendar or series set has changed")
    if not cuts or cuts != sorted(set(cuts)):
        raise ValueError("Historical cuts must be nonempty, unique and ordered")

    per_cut = {}
    for cut in cuts:
        rows = {}
        for definition in definitions:
            name = definition[0]
            pointer = manifest.get("macro", {}).get(cut, {}).get(name)
            if not isinstance(pointer, dict) or pointer.get("status") != "available":
                raise ValueError(f"Missing historical provider input: {cut}/{name}")
            record, _ = read_record(root, pointer)
            source = validate_macro_record(record, definition, cut)
            if source["known_by_day"] >= cut or source["vintage_date"] >= cut:
                raise ValueError("Historical vintage is not prior to the decision cut")
            if source["history"][-1]["date"] > source["known_by_day"]:
                raise ValueError("Historical series contains a future observation")
            if pointer.get("vintage_day") != source["vintage_date"]:
                raise ValueError("Source pointer vintage mismatch")
            if pointer.get("last_observation") != source["date"]:
                raise ValueError("Source pointer observation mismatch")
            if pointer.get("observations") != len(source["history"]):
                raise ValueError("Source pointer series length mismatch")
            rows[name] = {
                "id": name,
                "source_id": source["source_id"],
                "unit": source["unit"],
                "date": source["date"],
                "value": source["value"],
                "previous": source["previous"],
                "yoy": source["yoy"],
                "history": source["history"],
                "provider": source["provider"],
                "known_by_day": source["known_by_day"],
                "vintage_date": source["vintage_date"],
                "vintage_mode": source["vintage_mode"],
                "source_url": source["source_url"],
                "source_sha256": source["source_sha256"],
                "archive_sha256": pointer["sha256"],
                "retrieved_at": source["retrieved_at"]
            }
        per_cut[cut] = rows

    return {
        "protocol": "historical-macro-replay-inputs-v1",
        "source_protocol": PROTOCOL,
        "source_market_commit": manifest.get("source_market_commit"),
        "manifest_sha256": sha(original_manifest),
        "cuts": cuts,
        "series_ids": names,
        "verified_records": len(cuts) * len(names),
        "macro": per_cut,
        "historical_macro_source_verified": True,
        "historical_universe_verified": False,
        "historical_constituent_mapping_verified": False,
        "historical_bond_profiles_verified": False,
        "full_model_replay_ready": False,
        "production_eligible": False,
        "predictive_validation": "not-established",
        "note": "Reconstructed official provider vintages; downloaded later, not prospective observations or a certified whole-portfolio backtest"
    }


def write_bundle(bundle, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(bundle) + b"\n"
    output.write_bytes(gzip.compress(payload, mtime=0))
    return {"path": str(output), "sha256": sha(output.read_bytes()),
            "verified_records": bundle["verified_records"],
            "full_model_replay_ready": bundle["full_model_replay_ready"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/historical/provider-inputs-v1")
    parser.add_argument("--output", default="out/historical-macro-inputs-v1.json.gz")
    args = parser.parse_args()
    market = json.loads(subprocess.check_output(
        ["git", "show", MARKET_COMMIT + ":dist/data/market.json"], cwd=ROOT))
    result = materialize_macro_inputs(args.input, account_origins(market))
    print(json.dumps(write_bundle(result, args.output), sort_keys=True))
