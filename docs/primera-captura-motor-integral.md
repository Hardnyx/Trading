# First monthly full-engine capture

**Milestone:** H3.1, integration of original forward-captured production decisions; confirmatory collection is not activated.

The existing daily `scripts/seal_forecast.mjs` invokes `referenceRequest` and `composeMultiStart`. When its first prospective post-close decision is made on the **last calendar weekday** of a New York month, the same computed proposal is passed to `scripts/capture_full_engine_origin.mjs`. This does not run a second optimizer or tune a parameter after observing outcomes.

The receipt saves the original market and volatility byte streams to immutable gzip archives, plus the unchanged JSON of the canonical reference request and full proposal. SHA256 hashes bind those inputs to the original code-file manifest, decision cut and calibration cutoff. The first `*.json.gz` receipt is never replaced; an already-sealed month is not silently overwritten. The nightly data workflow adds these files directly to `main` alongside the source snapshot. No brokerage API or trading action is called.

**Exchange-calendar limitation:** A last weekday is a conservative candidate, not an independently certified last NYSE trading session. A month whose last weekday is an exchange holiday may be missed; missing months are not filled after the fact. The original market must contain SPY's exact cut, data collected after 16:00 New York time, and reference and calibration dates no later than the cut. Future-observed source metadata causes a refusal.

An infeasible optimizer or a rejected candidate now creates an immutable research attempt under `data/confirmatory/full-engine-v2/attempts/` with its reason and input hashes. Genuine candidate receipts live under `data/confirmatory/full-engine-v2/origins/` and inputs under `data/confirmatory/full-engine-v2/inputs/`. The audit checks the true first Git commit, original bytes, policy, proposal and source graph rather than trusting a claimed timestamp. Any code/source changes that prevent a compatible cohort from being formed remain visible.

**No forecast skill is certified by capturing a proposal.** The snapshot is a hypothetical account without a live broker ledger. The full-instrument forecasts, PIT vendor chain, cash-flow reconciliation, and independent materiality/power preregistration remain blockers. Recording a `hold` or CASH decision cannot be counted as an independently demonstrated economic advantage.

Reproduce the unit tests with `node --test tests/full-engine-first-capture.test.mjs` and run the read-only gate using `python scripts/prospective_study_registry.py --verify`.

The registry now also decompresses and verifies both original archives, rehashes the exact serialized request/proposal/source manifest, compares policy and proposal cut clocks, and checks every module against the first-publication Git commit. Source metadata and hashes still cannot establish vendor timestamp authenticity or economic eligibility.

If the original daily seal or month-end full-engine capture fails, the refresh
workflow preserves its first blocked-attempt receipt and original input hashes in
the data commit **before** reporting a failed refresh. The dependent signal
ledger therefore receives a failed upstream status rather than a false successful
capture. A blocked attempt has no forecast or account outcome and never becomes
an admissible confirmation origin. Later retries cannot overwrite the first
failure receipt, even if a real future seal for the same cut is subsequently
archived; no retrospective issuance is permitted. Non-month-end failures do
not fabricate a monthly attempt.
