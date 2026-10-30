"""Source-backed component matrix and fail-closed full-engine replay preflight.

This runs source verification only. It cannot certify a model snapshot, execute
the portfolio engine, or turn a missing adapter into an eligible historical cut.
"""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import subprocess

if __package__:
    from .audit_historical_inputs import audit_sources
    from .historical_sources import ROOT, MARKET_COMMIT, SERIES, account_origins, canonical, sha
else:
    from audit_historical_inputs import audit_sources
    from historical_sources import ROOT, MARKET_COMMIT, SERIES, account_origins, canonical, sha


PROTOCOL_PATH = "docs/protocolo-replay-integral-v1.json"
# Direct prerequisites, not a claim that an available source is model-ready.
DEPENDENCIES = {
    "macro_vintages": (),
    "spy_holdings_source": (),
    "historical_identifiers": ("spy_holdings_source",),
    "historical_universe": ("historical_identifiers",),
    "fundamentals_and_quality": ("historical_universe",),
    "bond_etf_profiles": ("historical_identifiers",),
    "corporate_actions": ("historical_universe",),
    "tradable_prices_and_distributions": ("corporate_actions",),
    "historical_model_parameters": (),
    "return_forecasts": ("macro_vintages", "historical_universe", "fundamentals_and_quality",
                         "bond_etf_profiles", "tradable_prices_and_distributions", "historical_model_parameters"),
    "volatility_and_dependence": ("macro_vintages", "tradable_prices_and_distributions", "historical_model_parameters"),
    "monte_carlo": ("return_forecasts", "volatility_and_dependence"),
    "portfolio_optimization": ("monte_carlo", "historical_universe"),
    "orders_and_account": ("portfolio_optimization", "tradable_prices_and_distributions"),
}
MISSING = {
    "historical_identifiers": "missing-verified-historical-cusip-instrument-price-links",
    "historical_universe": "missing-historical-membership-including-delisted-instruments",
    "fundamentals_and_quality": "missing-full-point-in-time-financials-quality-and-confidence-adapter",
    "bond_etf_profiles": "missing-original-historical-bond-and-etf-profiles",
    "corporate_actions": "missing-causal-split-spinoff-merger-and-delisting-reconciliation",
    "tradable_prices_and_distributions": "current-adjusted-history-is-not-certified-historical-execution-and-cashflows",
    "historical_model_parameters": "current-kernel-and-catalogue-have-no-per-cut-training-or-ex-ante-provenance",
    "return_forecasts": "full-as-of-snapshot-and-production-valuation-adapter-not-implemented",
    "volatility_and_dependence": "per-cut-refit-and-production-risk-adapter-not-implemented",
    "monte_carlo": "historical-production-simulation-adapter-not-implemented",
    "portfolio_optimization": "historical-production-composer-adapter-not-implemented",
    "orders_and_account": "historical-orders-and-corporate-action-account-adapter-not-implemented",
}


def build_plan(root, cuts, definitions=SERIES):
    """Recheck originals on every invocation; never trust readiness booleans."""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest.get("source_market_commit") != MARKET_COMMIT:
        raise ValueError("Frozen market identity mismatch")
    names = [row[0] for row in definitions]
    if manifest.get("series_ids") != names:
        raise ValueError("Historical macro series identity mismatch")
    if not cuts or cuts != sorted(set(cuts)):
        raise ValueError("Cuts must be nonempty, ordered and unique")
    audit = audit_sources(root, cuts, definitions)
    matrix = []
    for row in audit["matrix"]:
        stages = {}
        for name, dependencies in DEPENDENCIES.items():
            blockers = ["dependency:" + dep for dep in dependencies if stages[dep]["status"] != "verified-source"]
            if name == "macro_vintages":
                if row["macro_missing"]:
                    blockers.append("unverified-macro-series:" + ",".join(row["macro_missing"]))
            elif name == "spy_holdings_source":
                state = row["spy_holdings_source"]["status"]
                if state != "source-available":
                    blockers.append(state)
            else:
                blockers.append(MISSING[name])
            stages[name] = {"status": "blocked" if blockers else "verified-source",
                            "dependencies": list(dependencies), "blockers": blockers}
        matrix.append({"cut": row["cut"], "macro_verified": row["macro_verified"],
                       "macro_expected": row["macro_expected"],
                       "spy_holdings_source": row["spy_holdings_source"],
                       "components": stages, "full_engine_replay_eligible": False,
                       "forecast": None, "orders": None})
    return {
        "protocol": "historical-full-engine-preflight-v1",
        "execution_mode": "source-verification-only",
        "source_market_commit": MARKET_COMMIT,
        "source_manifest_sha256": audit["manifest_sha256"],
        "source_auditor_sha256": audit["auditor_sha256"],
        "planner_sha256": sha(Path(__file__).read_bytes()),
        "cuts": cuts, "matrix": matrix, "errors": audit["errors"],
        "summary": {
            "cuts": len(cuts), "macro_records_verified": audit["macro_records_verified"],
            "macro_records_expected": audit["macro_records_expected"],
            "sec_holdings_documents_verified": audit["sec_holdings_documents_verified"],
            "fresh_public_spy_holdings_cuts": audit["cuts_with_fresh_public_holdings"],
            "component_status_counts": {name: dict(Counter(row["components"][name]["status"] for row in matrix))
                                        for name in DEPENDENCIES},
            "full_engine_eligible_cuts": 0, "full_engine_executed_cuts": 0,
        },
        "engine_dispatch_enabled": False, "production_eligible": False,
        "predictive_validation": "not-established",
        "sample_role": "previously-inspected-development-history",
        "independent_holdout_claimed": False,
        "selection_policy": "retain every scheduled cut and its blockers; no eligible-only performance claim",
        "scope": "Source verification and dependency plan, not forecasts, Monte Carlo, optimization or a full-engine backtest. Model stages remain blocked until their causal adapters are implemented and verified.",
    }


def render_markdown(plan):
    lines = ["# Matriz causal del replay integral", "",
             "Verificación de fuentes y dependencias. No se ejecutó el motor ni se generaron predicciones.", "",
             "Los 48 cierres ya inspeccionados son desarrollo retrospectivo; no constituyen un holdout independiente.", "",
             "| Cierre | Macro verificada | SPY público | Fecha cartera SPY | Edad (días) | Peso sin ticker | Motor |",
             "|---|---:|---|---|---:|---:|---|"]
    for row in plan["matrix"]:
        h = row["spy_holdings_source"]
        weight = h.get("unmatched_weight")
        weight = "sin fuente" if weight is None else f"{100*weight:.2f}%"
        lines.append(f'| {row["cut"]} | {row["macro_verified"]}/{row["macro_expected"]} | '
                     f'{h["status"]} | {h.get("as_of", "sin fuente")} | {h.get("age_days", "")} | {weight} | bloqueado |')
    lines += ["", "## Componentes y bloqueo directo", "",
              "El JSON y el CSV incluyen también las dependencias bloqueadas en cada fecha.", "",
              "| Componente | Fuente verificada | Bloqueado | Motivo directo pendiente |", "|---|---:|---:|---|"]
    for name in DEPENDENCIES:
        counts = plan["summary"]["component_status_counts"][name]
        lines.append(f'| {name} | {counts.get("verified-source", 0)} | {counts.get("blocked", 0)} | {MISSING.get(name, "según archivo y fecha")} |')
    lines += ["", "Una fuente verificada no acredita identificadores, anclas o parámetros causales del motor.",
              "El perfil actual, los precios ajustados actuales y el kernel congelado hoy no sustituyen evidencia histórica.",
              "Los bloques de ejecución conservan pronósticos y órdenes nulos. No se saltan cortes fallidos.", ""]
    return "\n".join(lines)


def write_plan(plan, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "coverage.json").write_bytes(canonical(plan) + b"\n")
    (output / "coverage.md").write_text(render_markdown(plan), encoding="utf-8")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["cut", "component", "status", "dependencies", "blockers"])
    for row in plan["matrix"]:
        for name, stage in row["components"].items():
            writer.writerow([row["cut"], name, stage["status"], ";".join(stage["dependencies"]), ";".join(stage["blockers"])])
    (output / "coverage.csv").write_text(buffer.getvalue(), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/historical/provider-inputs-v1")
    parser.add_argument("--output", default="data/historical/replay-plan-v1")
    parser.add_argument("--require-full-engine", action="store_true",
                        help="Write the evidence, then fail if any scheduled cut cannot run the full engine")
    args = parser.parse_args()
    market = json.loads(subprocess.check_output(["git", "show", MARKET_COMMIT + ":dist/data/market.json"], cwd=ROOT))
    plan = build_plan(args.input, account_origins(market), SERIES)
    protocol_bytes = (ROOT / PROTOCOL_PATH).read_bytes()
    protocol = json.loads(protocol_bytes)
    if protocol["source_market_commit"] != MARKET_COMMIT or protocol["expected_cuts"] != plan["cuts"]:
        raise ValueError("Registered protocol calendar or market identity mismatch")
    plan["statistical_protocol_sha256"] = sha(protocol_bytes)
    plan["engine_source_sha256"] = {str(p.relative_to(ROOT)): sha(p.read_bytes())
                                     for p in sorted((ROOT / "dist/assets/js").rglob("*.mjs"))}
    write_plan(plan, args.output)
    print(json.dumps({**plan["summary"], "engine_dispatch_enabled": False}, sort_keys=True))
    return 2 if plan["errors"] or args.require_full_engine else 0


if __name__ == "__main__":
    raise SystemExit(main())
