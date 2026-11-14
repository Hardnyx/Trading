"""Guard mandatory checks and explicit manual research workflows using stdlib."""
import argparse
import re
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
    "scripts/confirmatory_fixed_b_stress.py --verify",
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
    "confirmatory_fixed_b_stress.py",
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


POOL = ROOT / ".github/workflows/pool-opportunity.yml"
SIGNAL = ROOT / ".github/workflows/signal-validation.yml"


def validate_refresh_dependents(pool, signal):
    """Check daily evidence capture and weekly exploratory research scheduling."""
    pool_on, signal_on = events(pool), events(signal)
    require(
        "  workflow_dispatch:" in pool_on
        and "  schedule:" in pool_on
        and "- cron: '37 2 * * 0'" in pool_on
        and "  push:\n    branches: [main]\n    paths:\n" in pool_on
        and "  workflow_run:" not in pool_on,
        "Exploratory pool audit must be weekly rather than after each refresh",
    )
    require(
        all(command in pool for command in (
            "node scripts/pool_opportunity_audit.mjs",
            "node scripts/antithetic_selection_research.mjs",
            "node scripts/antithetic_matrix_research.mjs --quick",
            "node scripts/economic_sensitivity_research.mjs --quick",
            "name: finite-pool-opportunity",
        )),
        "Exploratory pool workflow lost preserved research and artifacts",
    )
    require(
        "  workflow_run:\n    workflows: [Refresh market data]\n    types: [completed]\n"
        in signal_on
        and "  workflow_dispatch:" in signal_on
        and "  push:\n    branches: [main]\n    paths:\n" in signal_on,
        "Prospective evidence must follow each completed refresh",
    )
    require(
        ("DATA_REFRESH_RESULT: " + "$" +
         "{{ github.event_name == 'workflow_run' &&"
         " github.event.workflow_run.conclusion || 'not-requested' }}") in signal
        and 'python scripts/validation_watch.py --upstream-status "$DATA_REFRESH_RESULT"'
        in signal
        and "node scripts/signal_ledger.mjs" in signal,
        "Prospective ledger lost failed refresh recording",
    )
    require(
        all(value in signal for value in (
            "published_changes:",
            "steps.published.outputs.changed",
            "id: persist",
            "id: verify",
            "steps.persist.outputs.changed",
            "steps.verify.outputs.changed",
            "if: needs.ledger.outputs.published_changes == 'true'",
            "needs.ledger.outputs.published_ref",
        ))
        and signal.count('echo \'changed=true\' >> "$GITHUB_OUTPUT"') >= 2,
        "Signal Pages deployment must require newly committed evidence",
    )
    return {
        "weekly_exploratory_audit": True,
        "daily_prospective_ledger": True,
        "failed_refresh_evidence": True,
        "conditional_signal_pages": True,
    }



def validate_page_reuse(pages, signal):
    """Only verified successful refresh events may skip duplicate Python suite."""
    require(
        "skip_python_revalidation:" in pages
        and "type: boolean" in pages
        and "default: false" in pages
        and pages.count("if: " + "$" + "{{ !inputs.skip_python_revalidation }}") == 3
        and "npm run check" in pages
        and "npm test" in pages
        and "python -m unittest discover -s tests -p 'test_*.py'" in pages,
        "Pages must run full Python except on explicitly verified upstream reuse",
    )
    require(
        "skip_python_revalidation:" in signal
        and "github.event_name == 'workflow_run'" in signal
        and "github.event.workflow_run.conclusion == 'success'" in signal,
        "Signal may only reuse Python checks after a successful market refresh",
    )
    return {"safe_pages_test_reuse": True}



# Guard repository-wide runner costs and expected automatic scheduling. This
# is a static policy; GitHub billing and completed-run costs are not inferred.
WORKFLOW_DIR = ROOT / ".github/workflows"
STANDARD_RUNNERS = frozenset(("ubuntu-latest", "ubuntu-24.04"))
EXPECTED_SCHEDULES = {
    "refresh-data.yml": ("30 23 * * *",),
    "history-archive.yml": ("17 13 * * 6",),
    "pool-opportunity.yml": ("37 2 * * 0",),
}


def validate_actions_budget(workflows):
    """Reject nonstandard runners, excessive timeouts and new automatic cron."""
    require(bool(workflows), "No workflows supplied for the budget audit")
    scheduled = {}
    for filename, source in sorted(workflows.items()):
        triggers = events(source)
        runners = re.findall(r"(?m)^[ \t]+runs-on:[ \t]*([^\r\n]*)$", source)
        require(
            runners and all(value.strip() in STANDARD_RUNNERS for value in runners),
            f"Nonstandard or unreviewed runner in {filename}",
        )
        timeouts = re.findall(r"(?m)^[ \t]+timeout-minutes:[ \t]*([^\r\n]*)$", source)
        require(
            timeouts and all(value.strip().isdigit() and 0 < int(value.strip()) <= 60
                             for value in timeouts),
            f"Missing or excessive timeout in {filename}",
        )
        crons = tuple(re.findall(r"(?m)^    - cron: '([^']+)'$", triggers))
        if "  schedule:\n" in triggers or crons:
            scheduled[filename] = crons
    require(
        scheduled == EXPECTED_SCHEDULES,
        "Scheduled workflow inventory or cadence changed without review",
    )
    return {
        "standard_runners_only": True,
        "bounded_workflow_timeouts": True,
        "scheduled_cadence_reviewed": True,
    }



REFRESH = ROOT / ".github/workflows/refresh-data.yml"


def validate_prospective_refresh_persistence(refresh):
    """A failed first capture must be committed before the refresh fails."""
    steps = (
        "      - name: Seal one prospective proposal per original market close\n"
        "        id: prospective_seal\n"
        "        continue-on-error: true\n",
        "      - name: Commit the updated snapshot\n",
        "      - name: Fail refresh after preserving an unsuccessful prospective seal\n"
        "        if: steps.prospective_seal.outcome == 'failure'\n",
    )
    require(all(step in refresh for step in steps) and
            refresh.index(steps[0]) < refresh.index(steps[1]) < refresh.index(steps[2])
            and "git add data/confirmatory/full-engine-v2" in refresh
            and 'exit 1' in refresh.split(steps[2], 1)[1].split("\n  deploy:", 1)[0],
            "Prospective seal failures must persist before the refresh reports failure")
    return {"failed_prospective_capture_preserved": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    result = validate(FAST.read_text(encoding="utf-8"),
                      FULL.read_text(encoding="utf-8"),
                      PAGES.read_text(encoding="utf-8"))
    result.update(validate_refresh_dependents(
        POOL.read_text(encoding="utf-8"),
        SIGNAL.read_text(encoding="utf-8")))
    result.update(validate_page_reuse(
        PAGES.read_text(encoding="utf-8"),
        SIGNAL.read_text(encoding="utf-8")))
    result.update(validate_prospective_refresh_persistence(
        REFRESH.read_text(encoding="utf-8")))
    result.update(validate_actions_budget({
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOW_DIR.glob("*.yml"))
    }))
    if options.verify:
        require(all(result.values()), "Selective Actions policy failed")
    print(result)


if __name__ == "__main__":
    main()
