"""Guard mandatory checks and explicit manual research workflows using stdlib."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / ".github/workflows/check.yml"
FULL = ROOT / ".github/workflows/research-full.yml"
PAGES = ROOT / ".github/workflows/pages.yml"
REQUIRED_FAST = (
    "npm run check", "npm test",
    "python -m unittest discover -s tests -p 'test_*.py'",
    "scripts/first_cut_source_audit.py --verify",
    "scripts/prospective_study_registry.py --verify",
    "scripts/overfit_policy_guard.py --verify",
    "scripts/ci_workflow_policy.py --verify",
)
REQUIRED_FULL = (
    "scripts/confirmatory_bootstrap_diagnostic.py --verify",
    "scripts/confirmatory_familywise_bootstrap.py --verify",
    "scripts/confirmatory_partial_null_bootstrap.py --verify",
    "scripts/confirmatory_calibration_gate.py --verify",
    "scripts/confirmatory_power_feasibility.py --verify",
    "scripts/confirmatory_economic_materiality.py --verify",
    "scripts/confirmatory_hac_stress.py --verify",
    "scripts/confirmatory_calendar_floor.py --verify",
    "scripts/historical_spy_membership_audit.py",
    "scripts/historical_sec_numeric_concordance.py --help",
    "scripts/archived_ewma_independent_replay.py",
    "scripts/benchmark_expanding_mean.mjs",
    "name: confirmatory-calibration-gate",
    "name: historical-sec-fsd-source-request",
    "name: historical-sec-original-source-request",
)
HEAVY_FORBIDDEN_FAST = (
    "confirmatory_bootstrap_diagnostic.py",
    "confirmatory_familywise_bootstrap.py",
    "confirmatory_partial_null_bootstrap.py",
    "confirmatory_hac_stress.py",
    "historical_spy_membership_audit.py",
    "actions/upload-artifact@",
)
SOURCE_PATH_FILTERS = (
    "'dist/**'", "'scripts/**'", "'tests/**'", "'data/**'",
    "'docs/*.json'", "'docs/**/*.json'",
    "'.github/workflows/**'", "'requirements-research.txt'",
    "'package.json'", "'AGENTS.md'",
)
DEPLOY_PATH_FILTERS = (
    "'dist/**'", "'package.json'", "'scripts/stamp-release.mjs'",
    "'.github/workflows/pages.yml'",
)


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def events(workflow):
    require(workflow.startswith("name: ") and "\non:\n" in workflow,
            "Missing workflow name or triggers")
    suffix = workflow.split("\non:\n", 1)[1]
    require("\npermissions:\n" in suffix, "Missing permissions stanza")
    return suffix.split("\npermissions:\n", 1)[0]


def validate(fast, full, pages):
    f, r, p = (events(workflow) for workflow in (fast, full, pages))
    require("  push:\n    branches: [main]\n    paths:\n" in f and
            "  workflow_dispatch:" in f and
            all(name in f for name in SOURCE_PATH_FILTERS) and
            "  pull_request:" not in f and "  schedule:" not in f,
            "Fast CI source triggers were weakened")
    require("  workflow_dispatch:" in r and
            all("  " + event + ":" not in r for event in
                ("push", "pull_request", "schedule", "workflow_call")),
            "Full statistical audit must be manual")
    require("  push:\n    branches: [main]\n    paths:\n" in p and
            "  workflow_dispatch:" in p and "  workflow_call:" in p and
            all(name in p for name in DEPLOY_PATH_FILTERS),
            "Pages trigger must be limited to app/release changes")
    require(all(command in fast for command in REQUIRED_FAST),
            "Fast CI lost mandatory unit tests or causal guards")
    require(not any(command in fast for command in HEAVY_FORBIDDEN_FAST),
            "Fast CI contains an expensive full-research diagnostic")
    require(all(command in full for command in REQUIRED_FULL) and
            "fetch-depth: 0" in full and
            "git fetch --no-tags --depth=1 origin" in full,
            "Manual full audit lost evidence generation or source lineage")
    require("actions/deploy-pages@v4" in pages and
            "Verify public site serves this exact build" in pages,
            "Pages build attestation was removed")
    return {
        "fast_ci_scoped": True, "full_audit_manual_only": True,
        "full_evidence_preserved": True, "pages_scoped": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    result = validate(FAST.read_text(encoding="utf-8"),
                      FULL.read_text(encoding="utf-8"),
                      PAGES.read_text(encoding="utf-8"))
    if options.verify:
        require(all(result.values()), "Selective Actions policy failed")
    print(result)


if __name__ == "__main__":
    main()
