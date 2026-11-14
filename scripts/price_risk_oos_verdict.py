"""Apply the registered verdict rules to the 2008-2019 price risk replay."""
import argparse
import json
from pathlib import Path

import numpy as np

try:
    from .summarize_price_risk import block_interval, holm_adjust, nonoverlapping, summarize
except ImportError:
    from summarize_price_risk import block_interval, holm_adjust, nonoverlapping, summarize

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-riesgo-precios-2008-2019-v1.json"


def verdict(report, design):
    summary = summarize(report)
    cells = {(c["target"], c["horizon"], c["model"]): c for c in summary["cells"]}
    a = design["primary_claims"]["A_calibration"]
    rows = [cells[(t, a["horizon"], a["model"])] for t in a["targets"]]
    holm = holm_adjust([r["kupiec"]["p_value"] for r in rows])
    calibration = [{"target": r["target"], "origins": r["nonoverlapping_origins"], "exceptions": r["exceptions"],
                    "rate": r["var95_exception_rate"], "exact95": r["binomial_iid95_interval"],
                    "kupiec_p": r["kupiec"]["p_value"], "holm_p": p,
                    "christoffersen_p": r["christoffersen"]["p_value"]} for r, p in zip(rows, holm)]
    if any(c["holm_p"] < .05 for c in calibration):
        a_verdict = "not-supported"
    elif all(c["exact95"][1] <= .12 for c in calibration):
        a_verdict = "supported"
    else:
        a_verdict = "inconclusive"
    b = design["primary_claims"]["B_improvement"]
    by = {}
    for r in report["records"]:
        if r["horizon"] == b["horizon"]:
            by.setdefault((r["target"], r["model"]), []).append(r)
    improvement = []
    for target in b["targets"]:
        selected = nonoverlapping(by[(target, "targeted_ewma")])
        flat = {(r["origin_date"], r["maturity_date"]): r for r in by[(target, "flat_ewma")]}
        gains = [flat[(r["origin_date"], r["maturity_date"])]["crps"] - r["crps"] for r in selected]
        interval = block_interval(gains, alpha=.05 / len(b["targets"]))
        improvement.append({"target": target, "origins": len(gains), "mean_gain": float(np.mean(gains)),
                            "relative_gain": float(np.mean(gains) / np.mean([r["crps"] for r in selected])),
                            "interval": interval})
    if any(i["interval"][1] < 0 for i in improvement):
        b_verdict = "not-supported"
    elif any(i["interval"][0] > 0 for i in improvement):
        b_verdict = "supported"
    else:
        b_verdict = "inconclusive"
    return {"schema": "price-risk-out-of-sample-verdict-v1", "design_sha256": report.get("design_sha256"),
            "market_sha256": report.get("market_sha256"),
            "A_calibration": {"verdict": a_verdict, "cells": calibration},
            "B_improvement": {"verdict": b_verdict, "cells": improvement},
            "descriptive_cells": summary["cells"], "descriptive_comparisons": summary["comparisons"],
            "production_eligible": False, "limits": design["limits"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "out/price-risk-oos-replay.json")
    parser.add_argument("--output", type=Path, default=ROOT / "out/price-risk-oos-verdict.json")
    options = parser.parse_args()
    result = verdict(json.loads(options.input.read_text()), json.loads(DESIGN.read_text(encoding="utf-8")))
    options.output.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=lambda o: o.item()) + "\n")
    print(json.dumps({k: result[k] for k in ("A_calibration", "B_improvement")}, indent=1, default=lambda o: o.item()))


if __name__ == "__main__":
    main()
