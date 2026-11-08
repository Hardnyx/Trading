"""Cross-check the first historical cut against frozen source audit lineage.

This is an evidence triage, not an independent replay or a full-engine
certification. File-level hashes link published reports to source manifests;
original N-PORT and ALFRED records are not re-downloaded by this command.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "protocol": "docs/protocolo-replay-integral-v1.json",
    "plan": "data/historical/replay-plan-v1/coverage.json",
    "readiness": "data/historical/provider-inputs-v1/readiness.json",
    "identifiers": "data/historical/identifier-observations-v1/coverage.json",
    "prices": "data/historical/price-reconciliation-v1/coverage.json",
    "inventory": "data/historical/full-engine-input-audit-v1/manifest.json",
}
PROVIDER_MANIFEST = "data/historical/provider-inputs-v1/manifest.json"
IDENTIFIER_MANIFEST = "data/historical/identifier-sources-v1/manifest.json"
OUTPUT = "data/historical/full-engine-input-audit-v1/triage.json"


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_inputs(root=ROOT):
    root = Path(root)
    inputs = {key: json.loads((root / path).read_bytes()) for key, path in INPUTS.items()}
    protocol = inputs["protocol"]
    preflight = inputs["plan"]
    ready = inputs["readiness"]
    ids = inputs["identifiers"]
    prices = inputs["prices"]
    provider_hash = digest((root / PROVIDER_MANIFEST).read_bytes())
    identifier_hash = digest((root / IDENTIFIER_MANIFEST).read_bytes())
    protocol_hash = digest((root / INPUTS["protocol"]).read_bytes())
    require(preflight.get("statistical_protocol_sha256") == protocol_hash, "Frozen protocol hash changed")
    for report in (preflight, ready, ids, prices):
        field = "source_manifest_sha256" if report is preflight else (
            "manifest_sha256" if report is ready else "provider_manifest_sha256")
        require(report.get(field) == provider_hash, "Provider source lineage mismatch")
    require(ids["identifier_audit"]["manifest_sha256"] == identifier_hash, "Identifier source lineage mismatch")
    require(prices["identifier_audit"]["manifest_sha256"] == identifier_hash, "Price identifier lineage mismatch")
    require(preflight["identifier_evidence"]["identifier_audit"]["manifest_sha256"] == identifier_hash,
            "Preflight identifier lineage mismatch")
    return inputs


def build_triage(inputs):
    protocol = inputs["protocol"]
    preflight = inputs["plan"]
    ready = inputs["readiness"]
    ids = inputs["identifiers"]
    prices = inputs["prices"]
    inventory = inputs["inventory"]
    cuts = protocol["expected_cuts"]
    require(len(cuts) == 48 and cuts == sorted(set(cuts)), "Unexpected frozen decision calendar")
    require(not protocol["independent_holdout"]["registered"], "Study sample classification changed")
    require(not preflight["engine_dispatch_enabled"], "Full-engine dispatch unexpectedly enabled")
    require(preflight["summary"]["full_engine_eligible_cuts"] == 0 and
            preflight["summary"]["full_engine_executed_cuts"] == 0, "Unreviewed full-engine results")
    market = protocol["source_market_commit"]
    require(all(r.get("source_market_commit") == market for r in (preflight, ids, prices)),
            "Frozen market commit differs between reports")
    for key in ("plan", "readiness", "identifiers", "prices"):
        rows = inputs[key]["matrix"]
        require([r["cut"] for r in rows] == cuts, "Missing, duplicated or reordered origin in " + key)
    require(preflight["source_manifest_sha256"] == ready["manifest_sha256"] ==
            ids["provider_manifest_sha256"] == prices["provider_manifest_sha256"], "Source hash disagreement")
    require(preflight["identifier_evidence"]["identifier_audit"]["manifest_sha256"] ==
            ids["identifier_audit"]["manifest_sha256"] ==
            prices["identifier_audit"]["manifest_sha256"], "Identifier hash disagreement")
    require(inventory["candidate_selection"]["retrospective_only"] and
            inventory["candidate_selection"]["does_not_certify_eligibility"] and
            not inventory["eligible_full_engine"] and
            inventory["predictive_validation"] == "not-established", "Inventory falsely claims readiness")

    threshold = inventory["candidate_selection"]["historical_selection_threshold"]
    require(threshold == 0.7, "Candidate selection threshold changed without protocol review")
    candidates = []
    for pre, source, ident, price in zip(preflight["matrix"], ready["matrix"], ids["matrix"], prices["matrix"]):
        spy = source["spy_holdings_source"]
        require(pre["spy_holdings_source"] == spy == ident["spy_source"], "SPY source mismatch")
        require(price["explicit_ticker_weight"] == ident["mapped_positive_weight"],
                "Source ticker weights disagree")
        require(price["spy_source_status"] == spy["status"], "Price source status mismatch")
        if (spy["status"] == "source-available" and
                ident["mapped_positive_weight"] > 0 and
                price["research_history_weight"] >= threshold):
            candidates.append(pre["cut"])
    require(bool(candidates) and candidates[0] == inventory["candidate_cut"],
            "First candidate no longer matches frozen no-outcome selection rule")

    cut = candidates[0]
    by_cut = lambda name: next(row for row in inputs[name]["matrix"] if row["cut"] == cut)
    pre, source, ident, price = (by_cut(name) for name in ("plan", "readiness", "identifiers", "prices"))
    spy = source["spy_holdings_source"]
    require(spy["available_after_day"] < cut and spy["as_of"] <= cut and
            0 <= spy["age_days"] <= 120 and
            (date.fromisoformat(cut) - date.fromisoformat(spy["as_of"])).days == spy["age_days"],
            "SPY source is not publicly available and fresh at the cut")
    require(pre["macro_verified"] == pre["macro_expected"] == source["macro_verified"] ==
            source["macro_expected"] == 16, "Historical macro source incomplete")
    require(not ident["price_binding_verified"] and not price["price_identity_certified"] and
            not prices["continuous_price_identity_verified"] and
            not prices["original_price_vintages_verified"] and
            not prices["execution_cashflows_verified"], "Historical instrument certification changed")
    require(not pre["full_engine_replay_eligible"] and pre["forecast"] is None and
            pre["orders"] is None and not source["full_replay_ready"], "Uncertified engine decision present")
    expected = {
        "macro_vintages": {"verified": 16, "expected": 16, "information_cutoff": "strict-prior-day-vintage"},
        "spy_holdings_source": {"accession": spy["accession"], "as_of": spy["as_of"],
                               "available_after_day": spy["available_after_day"], "age_days": spy["age_days"]},
        "historical_identifiers": {"exact_cusip_ticker_mapped_spy_weight": ident["mapped_positive_weight"],
                                   "verified_continuous_price_binding": False},
        "tradable_prices_and_distributions": {
            "research_history_spy_weight": price["research_history_weight"],
            "point_compatible_spy_weight": price["point_compatible_weight"],
            "execution_cashflows_verified": False,
            "original_price_vintages_verified": False},
    }
    require(inventory["input_audit"]["components_expected"] == len(pre["components"]),
            "First-cut component inventory incomplete")
    require(inventory["input_audit"]["source_spy_cut"] == spy["as_of"] and
            inventory["input_audit"]["original_spy_public_after_day"] == spy["available_after_day"],
            "First-cut SPY metadata differs")
    rows = []
    require(len(inventory["components"]) == len(pre["components"]), "Missing inventory component")
    require([r["component"] for r in inventory["components"]] ==
            sorted(pre["components"]), "Inventory component order/identity differs")
    for item in inventory["components"]:
        name = item["component"]
        stage = pre["components"][name]
        require((item["status"], item["dependencies"], item["blockers"]) ==
                (stage["status"], stage["dependencies"], stage["blockers"]), name + " evidence changed")
        require(item["source_at_cut"] == expected.get(name), name + " source data mismatch")
        require(item["evidence"] and item["recovery_owner_role"] and
                item["access_license_review"] == "required-before-reuse-or-distribution" and
                not item["named_owner_assigned"], name + " unverified recovery/rights assertion")
        require(stage["status"] in ("verified-source", "blocked") and
                bool(stage["blockers"]) == (stage["status"] == "blocked"),
                name + " inconsistent component status")
        upstream = [dep for dep in item["dependencies"] if
                    pre["components"][dep]["status"] != "verified-source"]
        direct = [blocker for blocker in item["blockers"] if not blocker.startswith("dependency:")]
        require(sorted("dependency:" + dep for dep in upstream) ==
                sorted(blocker for blocker in item["blockers"] if blocker.startswith("dependency:")),
                name + " dependency blocker inconsistency")
        rows.append({
            "component": name, "status": item["status"],
            "upstream_blockers": upstream, "direct_blockers": direct,
            "evidence": item["evidence"],
            "recovery_owner_role": item["recovery_owner_role"],
            "license_review": item["access_license_review"],
            "historical_input_certified": False,
        })
    counts = {"verified_sources": sum(r["status"] == "verified-source" for r in rows),
              "blocked": sum(r["status"] == "blocked" for r in rows),
              "certified_components": 0}
    require((counts["verified_sources"], counts["blocked"]) ==
            (inventory["input_audit"]["components_verified_source"],
             inventory["input_audit"]["components_blocked"]), "First-cut readiness counts changed")
    return {
        "schema": "first-cut-source-triage-v1",
        "candidate_cut": cut,
        "selection_basis": "earliest-date-with-70pct-reconstructed-history-weight-public-SPY-source-and-explicit-CUSIP-observations-not-ex-post-performance",
        "causal_cut_certified": False,
        "sample_role": "previously-inspected-retrospective-development",
        "source_chain": {
            "market_commit": market,
            "provider_manifest_sha256": ready["manifest_sha256"],
            "identifier_manifest_sha256": ids["identifier_audit"]["manifest_sha256"],
            "statistical_protocol_sha256": preflight["statistical_protocol_sha256"],
        },
        "evidence_at_cut": {
            "macro_verified": pre["macro_verified"], "macro_expected": pre["macro_expected"],
            "spy_accession": spy["accession"], "spy_as_of": spy["as_of"],
            "spy_available_after_day": spy["available_after_day"], "spy_age_days": spy["age_days"],
            "original_explicit_ticker_weight": ident["mapped_positive_weight"],
            "research_history_weight": price["research_history_weight"],
            "point_compatible_weight": price["point_compatible_weight"],
            "price_identity_certified": False,
            "original_price_vintages_verified": False,
            "cashflow_execution_certified": False,
        },
        "counts": counts,
        "independent_blockers": [r["component"] for r in rows if
                                 r["status"] == "blocked" and not r["upstream_blockers"]],
        "stages": rows,
        "next_action": "Obtain dated vendor instrument identity and as-of risk-parameter provenance before enabling historical forecasts or account replay.",
        "source_paths": list(INPUTS.values()) + [PROVIDER_MANIFEST, IDENTIFIER_MANIFEST],
        "full_engine_replay_ready": False, "production_eligible": False,
        "predictive_validation": "not-established",
    }


def audit(root=ROOT):
    root = Path(root)
    inputs = load_inputs(root)
    report = build_triage(inputs)
    for item in report["stages"]:
        for source in item["evidence"]:
            target = (root / source).resolve()
            require(target.is_relative_to(root.resolve()) and target.is_file(),
                    "Missing or invalid component evidence: " + source)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Fail if the published triage differs")
    parser.add_argument("--write", action="store_true", help="Regenerate triage after source review")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.verify and args.write:
        parser.error("--write and --verify are mutually exclusive")
    result = audit(args.root)
    target = args.root / OUTPUT
    if args.verify:
        require(target.exists() and json.loads(target.read_bytes()) == result,
                "Published first-cut triage does not match frozen evidence")
    elif args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"cut": result["candidate_cut"], **result["counts"],
                      "independent_blockers": result["independent_blockers"],
                      "full_engine_replay_ready": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
