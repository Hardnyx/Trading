"""Audit historical-risk parameter clocks in the archived scoped-engine pilot.

Keeps the 2026 fixed research policy separate from fitted data available by
each pilot cut. A truncated series does not establish historical vendor prices,
ex-ante model selection, or eligibility for the full-engine study.
"""
import argparse
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = "data/historical/scoped-engine-pilot-v1/inputs.json.gz"
FULL = "data/historical/scoped-engine-pilot-v1/results.json.gz"
SUMMARY = "data/historical/scoped-engine-pilot-v1/report.json"
PROTOCOL = "docs/protocolo-piloto-integrado-v1.json"
OUTPUT = "out/historical-parameter-provenance-v1.json"
FIXED_FIELDS = (
    "model", "horizon", "seed", "lambda", "jumpIntensity", "jumpMean", "jumpVol",
    "driftMode", "volatilityMode", "uncertainFundamentals",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(root=ROOT):
    root = Path(root)
    p_raw = (root / PROTOCOL).read_bytes()
    protocol = json.loads(p_raw)
    summary = json.loads((root / SUMMARY).read_bytes())
    input_raw = (root / INPUT).read_bytes()
    full_raw = (root / FULL).read_bytes()
    require(summary["input_file_sha256"] == digest(input_raw),
            "Archived pilot input SHA256 mismatch")
    require(summary["full_results_sha256"] == digest(full_raw),
            "Archived pilot result SHA256 mismatch")
    require(summary["input_provenance"]["pilot_protocol_sha256"] == digest(p_raw),
            "Archived pilot protocol SHA256 mismatch")
    bundle = json.loads(gzip.decompress(input_raw))
    full = json.loads(gzip.decompress(full_raw))
    return protocol, summary, bundle, full


def known_cut(day, cut, description, strict=False):
    require(isinstance(day, str) and len(day) == 10, "Invalid date: " + description)
    try:
        normalized = date.fromisoformat(day).isoformat()
    except ValueError as error:
        raise ValueError("Invalid date: " + description) from error
    require(normalized == day and (day < cut if strict else day <= cut),
            "Look-ahead or malformed date: " + description)


def validate_origin(origin, record, risk, protocol):
    cut, snapshot = origin["cut"], origin["snapshot"]
    require(record["cut"] == risk["cut"] == cut, "Pilot cut result mismatch")
    require(snapshot["price_as_of"] == snapshot["requested_as_of"] == cut,
            "Pilot snapshot cut mismatch")
    require(snapshot["generated_at"][:10] > cut,
            "Retrospective compilation not identified")
    require(record["stored_snapshot_sha256"] == origin["snapshot_sha256"],
            "Archived pilot snapshot hash mismatch")
    require(not snapshot.get("volatility") and not snapshot.get("positions") and
            not snapshot.get("validated_opportunities"),
            "Contemporaneous risk/account information was fabricated")
    require(risk["risk"]["calibration_end"] == cut and
            record["prepared"]["calibration_end"] == cut,
            "Risk fit calibration does not end at the decision cut")
    require(risk["risk"]["observations"] == record["prepared"]["observations"] and
            risk["risk"]["observations"] > 0,
            "Risk training count mismatch")
    conditional = record["prepared"]["conditional_risk"]
    require(conditional["asOf"] == cut and
            risk["risk"]["conditional_risk"]["asOf"] == cut,
            "Conditional risk as-of mismatch")
    settings = record["proposal"]["settings"]
    require(isinstance(settings, dict), "Missing effective engine settings")
    require(settings["informationAsOf"] == settings["asOf"] == cut and
            settings["volatilityMode"] == protocol["risk_mode"] == "ewma",
            "Model risk or information cutoff mismatch")
    require(settings.get("volatilityData") is None,
            "Current volatility data used in historical replay")
    require(settings["seed"] == protocol["seed"] and
            settings["horizon"] == protocol["horizon_years"] and
            0 < settings["lambda"] < 1,
            "Unregistered or invalid fixed risk policy")
    require(not record["proposal"].get("historical_model_validated", False),
            "Unreviewed historical model certification appeared")
    require(record["proposal"]["as_of"] == cut and
            record["proposal"]["information_as_of"] == cut and
            record["proposal"]["calibration_end"] == cut,
            "Engine output time mismatch")
    history_days = []
    asset_counts = []
    require(snapshot.get("assets"), "No archived training assets")
    for asset in snapshot["assets"]:
        require(asset.get("price_date") == cut and asset.get("history"),
                "Missing historical asset price cut")
        history = asset["history"]
        days = [row["date"] for row in history]
        require(days == sorted(set(days)) and days[-1] == cut,
                "Nonmonotone or missing-cut training history")
        for day in days:
            known_cut(day, cut, asset["symbol"] + " price")
        for split in asset.get("splits", []):
            known_cut(split["date"], cut, asset["symbol"] + " split")
        if asset["type"] == "stock":
            eps = asset["financials"]["eps"]
            known_cut(eps["filed"], cut, asset["symbol"] + " EPS filing", strict=True)
            known_cut(eps["period_end"], cut, asset["symbol"] + " EPS end", strict=True)
            for component in eps["components"]:
                known_cut(component["filed"], cut, asset["symbol"] + " TTM filing", strict=True)
                known_cut(component["end"], cut, asset["symbol"] + " TTM end", strict=True)
            require(asset["historical_reconstruction"]["original_financial_quality_verified"] is False,
                    "Retrospective EPS was promoted to original financial-quality data")
        history_days.extend(days)
        asset_counts.append(len(days) - 1)
    for macro in snapshot["macro"]:
        for field in ("date", "known_by_day", "vintage_date"):
            known_cut(macro[field], cut, "macro " + macro["id"] + " " + field,
                      strict=True)
        for observation in macro["history"]:
            known_cut(observation["date"], cut, "macro " + macro["id"] + " history",
                      strict=True)
    curve = risk["risk"].get("regime_probabilities", {}).get("curve")
    if curve:
        known_cut(curve["to"], cut, "regime sample end", strict=False)
        known_cut(curve["from"], cut, "regime sample start", strict=True)
        require(curve["from"] <= curve["to"], "Regime sample inverted")
    require(record["proposal"]["model_version"] == risk["decision"]["model_version"],
            "Engine version mismatch")
    return {
        "cut": cut,
        "model_version": record["proposal"]["model_version"],
        "engine_calibration_end": record["proposal"]["calibration_end"],
        "engine_observations": risk["risk"]["observations"],
        "engine_conditional_method": risk["risk"]["conditional_risk"]["reason"],
        "source_assets": len(asset_counts),
        "stock_count": sum(asset["type"] == "stock" for asset in snapshot["assets"]),
        "minimum_asset_return_intervals": min(asset_counts),
        "maximum_asset_return_intervals": max(asset_counts),
        "risk_policy": {key: settings.get(key) for key in FIXED_FIELDS},
        "risk_parameter_policy_predefined_at_cut": False,
        "training_history_source_is_historical_vendor_vintage": False,
        "original_filing_capture_verified": False,
        "historical_model_parameters_certified": False,
        "full_engine_eligible": False,
    }


def build_report(protocol, summary, bundle, full):
    require(protocol["id"] == "scoped-production-engine-pilot-v1" and
            protocol["sample_role"] == "previously-inspected-development-history" and
            protocol["historical_model_validation"] is False and
            protocol["production_eligible"] is False and
            protocol["risk_mode"] == "ewma",
            "Unexpected pilot protocol classification")
    require(protocol["registered_on"] > "2025-04-30",
            "Pilot policy registration was historically reclassified")
    require(bundle.get("protocol") == full.get("protocol") == summary.get("protocol") == protocol,
            "Archived pilot protocol differs between artifacts")
    require(bundle["source_market_commit"] == protocol["source_market_commit"] ==
            summary["input_provenance"]["source_market_commit"],
            "Frozen historical market mismatch")
    for item in (bundle, full, summary):
        require(item.get("production_eligible") is False and
                item.get("prospective") is False and
                item.get("predictive_validation") == "not-established",
                "Archive was promoted to production/validation")
    require(summary["executed_development_cuts"] == len(bundle["origins"]) and
            summary["certified_full_engine_cuts"] == 0,
            "Development count or eligibility changed")
    require(summary["schedule"] == bundle["schedule"],
            "Pilot selection schedule changed")
    selected = [row["cut"] for row in bundle["schedule"] if row["selected"]]
    require(selected == [r["cut"] for r in bundle["origins"]] and
            selected == [r["cut"] for r in summary["results"]] and
            selected == [r["cut"] for r in full["results"]],
            "Pilot origin selection or order differs between archives")
    cutoff = protocol["selection"]["minimum_weight"]
    candidates = sorted(r["cut"] for r in bundle["schedule"]
                        if r["research_history_weight"] >= cutoff)
    require(selected == candidates[:protocol["selection"]["maximum_origins"]],
            "Pilot was selected after outcome inspection or rule changed")
    audits = []
    for origin, record, risk in zip(bundle["origins"], full["results"], summary["results"]):
        require(origin["cut"] < protocol["registered_on"],
                "Archived cut is not a retrospective fixed-policy experiment")
        audits.append(validate_origin(origin, record, risk, protocol))
    return {
        "schema": "historical-parameter-clock-audit-v1",
        "pilot_protocol": protocol["id"],
        "pilot_policy_registered_on": protocol["registered_on"],
        "cut_count": len(audits),
        "source_market_commit": bundle["source_market_commit"],
        "source_provenance": summary["input_provenance"],
        "input_file_sha256": summary["input_file_sha256"],
        "full_results_sha256": summary["full_results_sha256"],
        "report_source_classification": "retrospective-development-fixed-2026-policy",
        "cuts": audits,
        "historical_model_parameters_verified": 0,
        "production_eligible": False,
        "predictive_validation": "not-established",
        "required_next_evidence": [
            "pre-cut model policy timestamp or explicitly registered retrospective fixed policy",
            "vendor-independent original historical price and corporate-action evidence",
            "per-cut fit training inputs, executable method, parameter snapshot and hashes",
            "financial assumptions and universe selection not drawn from later surviving catalogue",
        ],
    }


def audit(root=ROOT):
    return build_report(*load(root))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=OUTPUT)
    args = parser.parse_args(argv)
    report = audit(ROOT)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "cut_count": report["cut_count"],
        "cuts": [row["cut"] for row in report["cuts"]],
        "historical_model_parameters_verified": 0,
        "production_eligible": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
