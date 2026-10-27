"""Varianza a horizonte: EWMA plana frente a reversión a la varianza de largo plazo.

Para cada instrumento y origen sin solape, pronostica la varianza realizada de
las siguientes H sesiones con información hasta el origen: (a) EWMA(0,94)
proyectada plana, como martingala; (b) la misma EWMA revirtiendo hacia la
varianza de las 500 sesiones previas con persistencia diaria φ. Puntúa con
QLIKE sobre la suma de residuos cuadrados realizada. Diagnóstico; no promueve
parámetros por sí solo.
"""
import argparse
import collections
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def horizon_forecasts(train, horizon, decay=0.94, persistence=0.99):
    """Flat EWMA and mean-reverting forecasts of summed variance (log-return units)."""
    errors = np.asarray(train, float) - float(np.mean(train))
    long_run = float(errors.var())
    h = long_run
    for e in errors:
        h = decay * h + (1 - decay) * e * e
    flat = horizon * h
    reverting = long_run * horizon + (h - long_run) * float((persistence ** np.arange(horizon)).sum())
    return flat, reverting, float(np.mean(train))


def qlike(forecast, realized):
    return math.log(forecast) + realized / forecast


def evaluate(assets, horizons=(21, 63, 252), persistences=(0.97, 0.99, 0.995),
             train_window=500, decay=0.94):
    rows = collections.defaultdict(list)
    for asset in assets:
        history = asset.get("history") or []
        prices = np.array([row.get("adj_close") or 0 for row in history], float)
        if len(prices) < train_window + 2 or (prices <= 0).any():
            continue
        returns = np.diff(np.log(prices))
        dates = [row["date"] for row in history][1:]
        for horizon in horizons:
            for t in range(train_window, len(returns) - horizon + 1, horizon):
                train = returns[t - train_window:t]
                for phi in persistences:
                    flat, reverting, centre = horizon_forecasts(train, horizon, decay, phi)
                    realized = float(((returns[t:t + horizon] - centre) ** 2).sum())
                    if realized <= 0 or flat <= 0 or reverting <= 0:
                        continue
                    rows[(horizon, phi)].append(
                        (dates[t - 1][:7], qlike(flat, realized) - qlike(reverting, realized)))
    report = []
    for (horizon, phi), values in sorted(rows.items()):
        gains = np.array([v for _, v in values])
        monthly = collections.defaultdict(list)
        for month, gain in values:
            monthly[month].append(gain)
        by_month = np.array([np.mean(v) for v in monthly.values()])
        report.append({
            "horizon": horizon, "persistence": phi, "observations": len(gains),
            "mean_gain_flat_minus_reverting": float(gains.mean()),
            "share_reverting_better": float((gains > 0).mean()),
            "origin_months": len(by_month),
            "month_mean_gain": float(by_month.mean()),
            "month_standard_error": (float(by_month.std(ddof=1) / math.sqrt(len(by_month)))
                                     if len(by_month) > 1 else None),
            "months_reverting_better": float((by_month > 0).mean()),
        })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default=str(ROOT / "dist/data/market.json"))
    parser.add_argument("--output", default=str(ROOT / "out/horizon-variance.json"))
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    report = {"as_of": snapshot["price_as_of"], "method": __doc__.strip().splitlines()[0],
              "positive_gain_means": "mean reversion has lower QLIKE",
              "warning": "Instruments share calendar shocks; use the by-month standard error, not the pooled one.",
              "results": evaluate(snapshot.get("assets", []))}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for row in report["results"]:
        print(row)


if __name__ == "__main__":
    main()
