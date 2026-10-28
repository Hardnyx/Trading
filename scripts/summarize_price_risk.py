"""Summarize reconstructed risk without treating correlated rows as evidence.

Primary contrasts are current_exposure at 21 sessions, targeted variance
against the two predeclared EWMA baselines. No result promotes a model.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from scipy.stats import binomtest
try:
    from .risk_ledger import kupiec, christoffersen
except ImportError:
    from risk_ledger import kupiec, christoffersen


def nonoverlapping(rows):
    selected, end = [], ""
    for r in sorted(rows, key=lambda r: (r["origin_date"], r["maturity_date"])):
        if r["origin_date"] >= end:
            selected.append(r)
            end = r["maturity_date"]
    return selected


def block_interval(values, alpha=.05, block=3, draws=2000):
    a = np.asarray(values, float)
    if len(a) < max(20, 4*block) or not np.isfinite(a).all():
        return None
    rng = np.random.default_rng(20261028)
    starts = rng.integers(0, len(a)-block+1, (draws, int(np.ceil(len(a)/block))))
    indices = (starts[:, :, None]+np.arange(block)).reshape(draws, -1)[:, :len(a)]
    means = a[indices].mean(axis=1)
    return [float(v) for v in np.quantile(means, [alpha/2, 1-alpha/2])]


def holm_adjust(pvalues):
    order = sorted(range(len(pvalues)), key=pvalues.__getitem__)
    adjusted = [0.] * len(pvalues)
    previous = 0.
    for rank, index in enumerate(order):
        previous = max(previous, min(1., (len(order)-rank)*pvalues[index]))
        adjusted[index] = previous
    return adjusted


def summarize(report):
    groups = defaultdict(list)
    for r in report["records"]:
        groups[(r["target"], r["horizon"], r["model"])].append(r)
    cells = []
    for (target, horizon, model), all_rows in sorted(groups.items()):
        rows = nonoverlapping(all_rows)
        n, hits = len(rows), sum(r["var95_exception"] for r in rows)
        test = binomtest(hits, n, .05)
        ci = test.proportion_ci(.95, method="exact")
        avg = lambda key: float(np.mean([r[key] for r in rows if r.get(key) is not None])) if any(r.get(key) is not None for r in rows) else None
        by_year = defaultdict(list)
        for row in rows:
            by_year[row["origin_date"][:4]].append(row)
        cells.append({"target": target, "horizon": horizon, "model": model,
                      "origins": len(all_rows), "nonoverlapping_origins": n,
                      "exceptions": hits, "var95_exception_rate": hits/n,
                      "binomial_iid95_interval": [ci.low, ci.high],
                      "binomial_iid_p": test.pvalue, "kupiec": kupiec(hits, n),
                      "christoffersen": christoffersen([[r["var95_exception"] for r in rows]]),
                      "mean_crps": avg("crps"), "mean_qlike": avg("qlike"),
                      "mean_es_excess_residual": avg("es_residual"),
                      "es_origin_block95_interval": block_interval([r["es_residual"] for r in rows]),
                      "tail_count_sufficient_for_review": hits >= 20,
                      "years": {year: {"origins": len(part),
                                  "exception_rate": sum(r["var95_exception"] for r in part)/len(part),
                                  "mean_crps": float(np.mean([r["crps"] for r in part]))}
                                for year, part in by_year.items()}})
    adjusted = holm_adjust([r["binomial_iid_p"] for r in cells])
    for row, p in zip(cells, adjusted):
        row["holm_binomial_iid_p"] = p
        row["coverage_rejection_iid_holm"] = p < .05
    comparisons = []
    for target, horizon, _ in sorted({(r["target"], r["horizon"], None) for r in report["records"]}):
        selected = nonoverlapping(groups[(target, horizon, "targeted_ewma")])
        for baseline in ("flat_ewma", "dynamic_ewma"):
            other = {(r["origin_date"], r["maturity_date"]): r for r in groups[(target, horizon, baseline)]}
            if any((a["origin_date"], a["maturity_date"]) not in other for a in selected):
                raise ValueError("Unpaired original model outcomes: "+target+" "+baseline)
            paired = [(a, other[(a["origin_date"], a["maturity_date"])]) for a in selected
                      if (a["origin_date"], a["maturity_date"]) in other]
            if not paired:
                raise ValueError("Missing targeted model outcomes: "+target)
            primary = target == "PORTFOLIO:current_exposure" and horizon == 21
            gains = [b["crps"]-a["crps"] for a, b in paired]
            interval = block_interval(gains, alpha=.025 if primary else .05)
            comparisons.append({"target": target, "horizon": horizon, "baseline": baseline,
                                "primary": primary, "paired_nonoverlapping_origins": len(paired),
                                "mean_crps_gain_targeted": float(np.mean(gains)),
                                "origin_block_interval": interval,
                                "interval_alpha": .025 if primary else .05,
                                "evidence": "targeted-worse-in-reconstruction" if interval and interval[1] < 0
                                else "targeted-better-in-reconstruction" if interval and interval[0] > 0
                                else "unresolved"})
    return {"method": report["method"], "market_sha256": report.get("market_sha256"),
            "source_sha256": report.get("source_sha256"), "data_price_cut": report.get("data_price_cut"),
            "protocol": report["protocol"], "cells": cells, "comparisons": comparisons,
            "primary_comparisons": [r for r in comparisons if r["primary"]],
            "prospective": False, "production_eligible": False, "automatic_promotion": False,
            "limitations": "Current adjusted prices, current fixed instrument list, no original vintages. Today's basket was selected ex post. Only fallback variance is replayed; no historical GJR selection, economic anchors, macro scenarios, cash-distribution policy or net trading utility. Exact binomial/Kupiec tests assume independent exceptions; no rejection is no certificate. Overlapping origins are excluded, assets are not pooled as independent rows. Coverage p-values use Holm across all reported cells. CRPS block intervals use three origins; only two primary intervals are multiplicity-adjusted. Few tail hits make ES weakly identified; its residual also depends on VaR calibration. No result changes production."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("out/price-risk-replay.json"))
    parser.add_argument("--output", type=Path, default=Path("out/price-risk-summary.json"))
    args = parser.parse_args()
    summary = summarize(json.loads(args.input.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=1)+"\n")
    print(json.dumps({"primary": summary["primary_comparisons"], "production_eligible": False}))


if __name__ == "__main__":
    main()
