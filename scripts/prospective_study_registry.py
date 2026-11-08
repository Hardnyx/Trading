"""Register H0.3 future full-engine cohort without promoting past or signal-only data."""
import argparse
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "docs/protocolo-confirmacion-integral-v2.json"
ORIGINS = "data/confirmatory/full-engine-v2/origins"
SIGNALS = "dist/data/signal-validation.json"
HEX = re.compile(r"^[a-f0-9]{64}$")


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def utc(value, label):
    require(isinstance(value, str), "Missing " + label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid timestamp for " + label) from error
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "Timezone required for " + label)
    return result.astimezone(timezone.utc)


def iso_day(value, label):
    require(isinstance(value, str), "Missing date for " + label)
    try:
        d = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Invalid date for " + label) from error
    require(d.isoformat() == value, "Noncanonical date for " + label)
    return d


def read_contract(root=ROOT):
    root = Path(root)
    reg = json.loads((root / CONTRACT).read_bytes())
    parent = reg["predecessor"]
    require(parent["path"] == "docs/protocolo-replay-integral-v1.json" and
            HEX.fullmatch(parent["sha256"]) and
            sha((root / parent["path"]).read_bytes()) == parent["sha256"],
            "Original v1 protocol SHA256 differs from preregistered evidence")
    return reg, json.loads((root / parent["path"]).read_bytes())


def check_contract(reg, v1):
    require(reg.get("schema") == "full-engine-prospective-registration-v2" and
            reg.get("status") == "registered-methodology-inactive-confirmatory-inference" and
            reg.get("baseline_engine_commit") ==
            "0cbf5cefa7c17700a17b75568c6a80e83e56123f",
            "Registration scope or source freeze changed")
    require(v1["protocol"] == "full-engine-evaluation-v1" and
            v1["sample_role"] == "previously-inspected-development-history" and
            v1["independent_holdout"]["registered"] is False and
            len(v1["expected_cuts"]) == 48,
            "Inspected history was reclassified as independent")
    s = reg["sampling"]
    require(reg["registration_day_utc"] == "2026-11-08" and
            iso_day(s["first_possible_cut"], "earliest cut") >
            iso_day(reg["registration_day_utc"], "registration") and
            s["first_month"] == s["first_possible_cut"][:7] == "2026-11" and
            s["origin_frequency"] == "monthly" and
            s["minimum_mature_eligible_months"] >= 96 and
            s["minimum_contiguous_months_for_largest_block"] >= 96 and
            s["horizons_sessions"] == v1["horizons_sessions"] and
            s["exclude_previously_examined"] is True and
            s["no_outcome_driven_selection"] is True and
            s["retain_absent_months"] is True and
            s["exclude_missing_from_numerator_without_replacing_with_cash"] is True,
            "Prospective origin cutoff or 96-month sampling minimum was reduced")
    family = [{"id": f"{p}:{h}", "parent": p, "horizon_sessions": h}
              for p in ("return_mse", "ranking_ic") for h in (21, 63, 252)]
    family.append({"id": "net_economic_value:21", "parent": "net_economic_value",
                   "horizon_sessions": 21})
    require(reg["primary_tests"] == family and
            [r["id"] for r in v1["primary_tests"]] ==
            ["return_mse", "ranking_ic", "net_economic_value"],
            "The seven registered primary tests changed")
    m = reg["multiplicity"]
    require(m["method"] == v1["multiple_testing"]["method"] == "Holm step-down" and
            m["alpha"] == v1["multiple_testing"]["familywise_alpha"] == 0.05 and
            m["direction"] == v1["multiple_testing"]["direction"] and
            m["missing_primary_p_value"] == 1,
            "Registered multiplicity was relaxed")
    b = reg["bootstrap"]
    old = v1["uncertainty"]
    require(b["method"] == old["method"] and
            b["block_lengths_months"] == old["block_lengths_months"] == [12, 24] and
            b["draws"] == old["draws"] and
            b["seed"] == old["seed"] and
            b["interval"] == old["interval"] and
            b["minimum_complete_blocks"] == 4,
            "Registered block inference rule changed")
    fixed = reg["fixed_cohort"]
    require(reg["forecast_target"] == v1["forecast_target"] and
            fixed["engine_version"] == "0.35.0" and
            fixed["price_kernel_version"] == "1.0.0" and
            fixed["restart_incompatible_changes"] is True and
            fixed["never_pool_code_or_source_cohorts"] is True and
            reg["admission"]["no_pre_registration_forecasts"] is True and
            reg["admission"]["first_git_publication_verified"] is True and
            reg["admission"]["full_engine_decision_and_order_required"] is True,
            "Model/publishing eligibility requirements were weakened")
    effects = reg["economic_effect_thresholds"]
    require(effects["status"] == "unjustified-power-not-established" and
            all(effects[k] is None for k in ("return_mse", "ranking_ic",
                                            "net_economic_value")),
            "Unjustified minimum economic effect was presented as registered")
    active = reg["activation"]
    require(active["registration_recorded"] is True and
            active["confirmatory_collection_open"] is False and
            active["formal_inference_enabled"] is False and
            len(active["blockers"]) == 4 and
            reg["other_evidence"]["historical_development_origins"] == 48 and
            reg["other_evidence"]["existing_signal_protocol"] ==
            "monthly-complete-stock-signal-v1",
            "Confirmatory cohort was silently activated")
    return True


def candidate_preflight(origin, reg):
    """Validate recorded metadata only. Never certify original vendor captures."""
    require(origin.get("schema") == "full-engine-first-capture-v2" and
            origin.get("study") == reg["schema"] and
            origin.get("role") == "new-full-engine-only",
            "Signal-only or retrospective origin submitted as full-engine")
    cut = iso_day(origin.get("cut"), "decision")
    require(cut >= iso_day(reg["sampling"]["first_possible_cut"], "study boundary") and
            origin.get("month") == cut.isoformat()[:7],
            "Origin precedes registration or month differs")
    issued = utc(origin.get("issued_at"), "issuance")
    retrieved = utc(origin.get("market_collected_at"), "source capture")
    require(issued >= retrieved and issued.date() >= cut,
            "Source/issuance clock is inconsistent")
    require(origin.get("engine_version") == reg["fixed_cohort"]["engine_version"] and
            origin.get("price_kernel_version") ==
            reg["fixed_cohort"]["price_kernel_version"],
            "Unregistered model/kernel cohort")
    hashes = origin.get("evidence", {})
    require(isinstance(hashes, dict) and all(HEX.fullmatch(hashes.get(k, ""))
            for k in ("market_sha256", "inputs_sha256", "model_sha256",
                      "policy_sha256", "risk_calibration_sha256", "forecast_sha256")),
            "Incomplete frozen input or model hashes")
    require(iso_day(origin.get("calibration_end"), "calibration end") <= cut,
            "Future risk calibration in historical forecast")
    require(origin.get("horizons_sessions") == reg["sampling"]["horizons_sessions"] and
            origin.get("optimizer_executed") is True and
            origin.get("orders_recorded") is True,
            "Full-engine forecast or orders not captured")
    require(all(origin.get(k) is None for k in
                ("realized_returns", "scoring", "future_outcomes")),
            "Realized outcomes were inserted into the original forecast")
    return {"cut": str(cut), "month": origin["month"],
            "metadata_verified": True,
            "causal_source_certification": False,
            "confirmatory_eligible": False}


def first_publication(root, path, raw):
    """Use the actual first Git add and original bytes, not a claimed commit time."""
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root,
                                       stderr=subprocess.DEVNULL).decode().strip()
    try:
        require(git("rev-parse", "--is-shallow-repository") == "false",
                "Unshallow Git history required to audit first publication")
        rel = path.relative_to(root).as_posix()
        commits = git("log", "--reverse", "--diff-filter=A", "--format=%H", "--", rel)
        require(bool(commits), "First-add commit is unavailable")
        commit = commits.splitlines()[0]
        first = subprocess.check_output(["git", "show", commit + ":" + rel],
                                        cwd=root, stderr=subprocess.DEVNULL)
        require(sha(first) == sha(raw), "Published forecast was replaced")
        return {"verified": True, "commit": commit, "at": git("show", "-s",
                "--format=%cI", commit), "original_sha256": sha(raw)}
    except subprocess.CalledProcessError as error:
        raise ValueError("Missing verifiable forecast publication") from error


def inspect(root=ROOT):
    root = Path(root)
    reg, old = read_contract(root)
    check_contract(reg, old)
    folder = root / ORIGINS
    rows = []
    months = set()
    for path in sorted(folder.glob("*.json.gz")):
        raw = path.read_bytes()
        require(len(raw) < 100_000_000, "Archived original exceeds size limit")
        record = json.loads(gzip.decompress(raw))
        require(path.name == record.get("cut", "") + ".json.gz",
                "First-capture file name differs from its date")
        current = candidate_preflight(record, reg)
        require(current["month"] not in months,
                "Duplicate full-engine first capture in monthly cohort")
        months.add(current["month"])
        published = first_publication(root, path, raw)
        require(utc(published["at"], "publication") >=
                utc(record["issued_at"], "issuance") and
                utc(published["at"], "publication").date() >=
                iso_day(reg["sampling"]["first_possible_cut"], "first possible cut"),
                "Original forecast was not first published within study")
        rows.append({**current, "first_publication": published})
    signals = json.loads((root / SIGNALS).read_bytes())
    require(signals["protocol"] == reg["other_evidence"]["existing_signal_protocol"] and
            signals["predictive_validation"] == "not-established" and
            signals["sealed"] == sum(c["sealed"] for c in signals["cohorts"].values()),
            "Previously sealed stock signals were changed or promoted")
    return {
        "study": reg["schema"], "state": reg["status"],
        "first_possible_cut": reg["sampling"]["first_possible_cut"],
        "prior_development_cuts_excluded": len(old["expected_cuts"]),
        "prior_signal_seals_excluded": signals["sealed"],
        "separate_signal_cohorts": len(signals["cohorts"]),
        "new_full_engine_files_inspected": len(rows),
        "new_file_evidence": rows,
        "causally_certified_full_engine_origins": 0,
        "eligible_mature_months": 0,
        "minimum_eligible_mature_months": reg["sampling"]["minimum_mature_eligible_months"],
        "minimum_economic_effects_registered": False,
        "formal_inference_allowed": False,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).add_argument(
        "--verify", action="store_true").parse_args(argv)
    result = inspect()
    print(json.dumps({k:v for k,v in result.items() if k != "new_file_evidence"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
