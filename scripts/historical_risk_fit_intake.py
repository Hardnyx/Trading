"""Validate local point-in-time risk-fit evidence without certifying a causal fit.

Only exact local bytes, declared clocks and sample consistency are checked.
No private source is uploaded and no historical backtest may consume this report.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "historical-risk-fit-intake-v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
NY = ZoneInfo("America/New_York")
MAX_SOURCE_BYTES = 20_000_000
MAX_TRAINING_ROWS = 100_000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def day(value, field):
    require(isinstance(value, str), "Missing " + field)
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Invalid date for " + field) from error
    require(result.isoformat() == value, "Noncanonical date for " + field)
    return result


def instant(value, field):
    require(isinstance(value, str), "Missing " + field)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid timestamp for " + field) from error
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "Timezone missing for " + field)
    return result.astimezone(timezone.utc)


def evidence_file(root, pointer):
    require(isinstance(pointer, dict) and isinstance(pointer.get("path"), str),
            "Missing evidence file path")
    relative = Path(pointer["path"])
    require(not relative.is_absolute() and ".." not in relative.parts,
            "Unsafe evidence file path")
    base = Path(root).resolve()
    target = (base / relative).resolve()
    require(target.is_relative_to(base) and target.is_file(),
            "Evidence file escaped the directory or is missing")
    require(isinstance(pointer.get("sha256"), str) and
            HEX.fullmatch(pointer["sha256"]), "Invalid evidence SHA256")
    require(target.stat().st_size <= MAX_SOURCE_BYTES, "Oversized evidence file")
    raw = target.read_bytes()
    require(digest(raw) == pointer["sha256"], "Evidence SHA256 mismatch: " + str(relative))
    return raw


def json_file(root, pointer):
    raw = evidence_file(root, pointer)
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid evidence JSON") from error
    require(isinstance(result, dict), "Evidence JSON must be an object")
    return result, digest(raw)


def validate(directory, expected_cut):
    """Audit a risk-fit receipt, never activate historical parameters."""
    cut = day(expected_cut, "candidate cut")
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_bytes())
    require(manifest.get("schema") == SCHEMA and manifest.get("cut") == expected_cut,
            "Risk evidence contract/cut mismatch")
    decision = instant(manifest.get("decision_at"), "decision_at")
    local = decision.astimezone(NY)
    require(local.date() == cut and (local.hour, local.minute) >= (16, 0),
            "Decision timestamp is not post-close on the candidate NY day")
    require(manifest.get("temporal_basis") in (
        "retrospective_reconstruction", "contemporaneous_archive"),
        "Temporal basis must be declared")
    require(isinstance(manifest.get("source_reference"), str) and
            bool(manifest["source_reference"].strip()), "Missing source reference")
    require(isinstance(manifest.get("retrieved_at"), str),
            "Missing retrieval timestamp")
    retrieval = instant(manifest["retrieved_at"], "retrieved_at")
    require(retrieval >= decision, "Evidence retrieval predates the decision cut")
    pointers = [manifest.get(key) for key in ("policy", "training", "fit")]
    require(all(isinstance(p, dict) for p in pointers), "Missing risk evidence files")
    paths = [p["path"] for p in pointers]
    require(len(set(paths)) == len(paths), "Duplicate evidence path")
    policy, policy_sha = json_file(root, manifest["policy"])
    training, training_sha = json_file(root, manifest["training"])
    fit, fit_sha = json_file(root, manifest["fit"])

    require(policy.get("schema") == "risk-fit-policy-v1" and
            isinstance(policy.get("policy_id"), str) and policy["policy_id"].strip(),
            "Missing risk fit policy")
    selected = instant(policy.get("selected_at"), "policy selected_at")
    selection_end = day(policy.get("selection_data_end"), "selection_data_end")
    require(selection_end <= cut and selected.date() >= selection_end and
            selected <= retrieval, "Look-ahead or inconsistent model selection clock")
    require(policy.get("selection_mode") in ("fixed", "nested-chronological"),
            "Unregistered model selection mode")
    require(isinstance(policy.get("model"), str) and policy["model"].strip(),
            "Missing registered model name")
    # A claim of a completed trial ledger is not evidence that every trial was registered.
    require(policy.get("all_trials_recorded") is False,
            "Cannot certify an exhaustive historical trial ledger from self-reported evidence")

    require(training.get("schema") == "risk-fit-training-v1" and
            training.get("cut") == expected_cut, "Training cut mismatch")
    observations = training.get("observations")
    require(isinstance(observations, list) and 2 <= len(observations) <= MAX_TRAINING_ROWS,
            "Invalid training observation count")
    seen = set()
    per_instrument = defaultdict(list)
    for i, row in enumerate(observations):
        require(isinstance(row, dict) and
                set(row) == {"instrument_id", "observation_date", "label_end", "known_at", "source_sha256"},
                "Unexpected risk training fields")
        identifier = row["instrument_id"]
        require(isinstance(identifier, str) and bool(identifier.strip()) and
                len(identifier) <= 128, "Invalid training instrument ID")
        observed = day(row["observation_date"], "observation_date")
        label_end = day(row["label_end"], "label_end")
        known_at = instant(row["known_at"], "training known_at")
        require(observed <= label_end <= cut and
                label_end <= known_at.astimezone(NY).date() and
                known_at <= decision, "Unmatured label or future-known training row")
        require(isinstance(row["source_sha256"], str) and
                HEX.fullmatch(row["source_sha256"]), "Invalid row source SHA256")
        key = (identifier, observed.isoformat())
        require(key not in seen, "Duplicate training instrument/session")
        seen.add(key)
        per_instrument[identifier].append(observed)

    sources = manifest.get("sources")
    require(isinstance(sources, list) and sources and len(sources) <= 25,
            "Missing or excessive original risk sources")
    source_hashes = set()
    source_receipts = []
    for source in sources:
        raw = evidence_file(root, source)
        sha = digest(raw)
        require(sha not in source_hashes, "Duplicate original risk source hash")
        source_hashes.add(sha)
        available_at = instant(source.get("claimed_available_at"), "claimed_available_at")
        collected_at = instant(source.get("collected_at"), "collected_at")
        require(available_at <= decision and
                available_at <= collected_at <= retrieval,
                "Source claimed available only after the decision or invalid collection clock")
        require(source.get("temporal_basis") in (
            "retrospective_reconstruction", "contemporaneous_archive"),
            "Unknown original source temporal basis")
        require(isinstance(source.get("provider"), str) and source["provider"].strip(),
                "Missing original source provider")
        source_receipts.append({"sha256": sha, "bytes": len(raw),
                                "temporality": source["temporal_basis"],
                                "claimed_available_at": available_at.isoformat(),
                                "collected_at": collected_at.isoformat()})
    require(all(row["source_sha256"] in source_hashes for row in observations),
            "Training references an absent original source")

    require(fit.get("schema") == "risk-fit-result-v1" and
            fit.get("cut") == expected_cut and
            fit.get("model") == policy["model"], "Risk fit/model mismatch")
    require(fit.get("policy_sha256") == policy_sha and
            fit.get("training_sha256") == training_sha,
            "Fit does not bind exact policy and training bytes")
    fitted = instant(fit.get("fitted_at"), "fitted_at")
    require(fitted >= selected and fitted <= retrieval,
            "Fit clock precedes policy selection or follows retrieval")
    require(type(fit.get("observations")) is int and
            fit["observations"] == len(observations),
            "Risk fitted sample count differs from archived training rows")
    params = fit.get("parameters")
    require(isinstance(params, dict) and params and len(params) <= 200,
            "Missing bounded risk parameters")
    for key, value in params.items():
        require(isinstance(key, str) and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", key)) and
                type(value) in (int, float) and math.isfinite(value),
                "Invalid or nonfinite risk fit parameter")

    policy_pre_cut_claim = selected <= decision
    fit_pre_cut_claim = fitted <= decision
    return {
        "schema": "historical-risk-fit-reconciliation-v1",
        "cut": expected_cut,
        "manifest_sha256": digest((root / "manifest.json").read_bytes()),
        "policy_sha256": policy_sha,
        "training_sha256": training_sha,
        "fit_sha256": fit_sha,
        "source_receipts": source_receipts,
        "training_rows": len(observations),
        "distinct_instruments": len(per_instrument),
        "first_training_day": min(v for days in per_instrument.values() for v in days).isoformat(),
        "last_training_day": max(v for days in per_instrument.values() for v in days).isoformat(),
        "declared_clocks_compatible": True,
        "policy_claims_pre_cut_selection": policy_pre_cut_claim,
        "fit_claims_pre_cut_execution": fit_pre_cut_claim,
        "historical_source_availability_independently_verified": False,
        "policy_first_publication_independently_verified": False,
        "fit_recomputed_from_original_inputs": False,
        "model_trial_inventory_independently_verified": False,
        "historical_model_parameters_certified": False,
        "full_engine_replay_ready": False,
        "production_eligible": False,
        "predictive_validation": "not-established",
        "next_evidence": [
            "independent source publication and vintage proof",
            "model source and fit code reproducibility at the cut",
            "complete historical policy/trial ledger and nested tuning when applicable",
            "original historical vendor prices, events and continuous instrument identity",
        ],
    }


def template(cut):
    return {
        "schema": SCHEMA, "cut": cut,
        "decision_at": None, "retrieved_at": None,
        "temporal_basis": "retrospective_reconstruction",
        "source_reference": None,
        "policy": {"path": "policy.json", "sha256": None},
        "training": {"path": "training.json", "sha256": None},
        "fit": {"path": "fit.json", "sha256": None},
        "sources": [],
        "instructions": "Replace null values with actual metadata, files and SHA256 hashes. Never upload licensed sources.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", help="Write a non-evidentiary manifest request")
    parser.add_argument("--evidence-dir", help="Audit local original hashes without uploading them")
    parser.add_argument("--report", default="out/historical-risk-fit-reconciliation-v1.json")
    args = parser.parse_args(argv)
    require(args.template or args.evidence_dir, "Choose --template or --evidence-dir")
    inventory = json.loads((ROOT / "data/historical/full-engine-input-audit-v1/manifest.json").read_bytes())
    cut = inventory["candidate_cut"]
    if args.template:
        output = Path(args.template)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(template(cut), indent=2) + "\n", encoding="utf-8")
    if args.evidence_dir:
        result = validate(args.evidence_dir, cut)
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"cut": cut, "training_rows": result["training_rows"],
                          "historical_model_parameters_certified": False}))
    else:
        print(json.dumps({"cut": cut, "evidence_received": False,
                          "historical_model_parameters_certified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
