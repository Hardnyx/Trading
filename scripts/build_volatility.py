"""Publica parámetros de volatilidad por activo con evaluación walk-forward.

No infiere causas de noticias. Cada pronóstico usa únicamente datos anteriores
al resultado. No se publican pronósticos históricos como si fueran actuales.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from volatility_research import (
    fit_gjr_t, prices_to_returns, walk_forward, MIN_FIT,
)

ROOT = Path(__file__).resolve().parents[1]


def compact_volatility(snapshot, *, limit=None, test_days=126,
                       train_window=500, refit_every=42):
    cut = snapshot["price_as_of"]
    result = {
        "schema_version": 1,
        "as_of": cut,
        "source_market_generated_at": snapshot["generated_at"],
        "method": "GJR-GARCH(1,1)-Student-t / EWMA(0.94)",
        "forecast_unit": "variance in percentage-points squared per trading day",
        "use": "conditional_risk_only_not_expected_return",
        "training_window": train_window,
        "walkforward_days": test_days,
        "promotion_rule": "126 OOS days; GJR QLIKE lower than EWMA, >=2 of 3 blocks improve, VaR95 exceptions <=10%, valid variance/nu and parameters",
        "no_news_attribution": True,
        "instruments": {},
    }
    assets = snapshot.get("assets", [])
    if limit is not None:
        wanted = set(limit)
        assets = [a for a in assets if a["symbol"] in wanted]
    for asset in assets:
        symbol = asset["symbol"]
        if asset.get("type") == "cash":
            continue
        try:
            dates, returns = prices_to_returns(asset.get("history", []), cut)
            if dates[-1] != cut or len(returns) < train_window + test_days:
                raise ValueError("Fecha sin actualizar o menos historia que la ventana walk-forward")
            check = walk_forward(
                asset["history"], cut, train_window=train_window,
                test_days=test_days, refit_every=refit_every,
            )
            fit = fit_gjr_t(returns[-train_window:], cut)
            sample = [r for r in check["forecasts"] if r["gjr_qlike"] is not None]
            # The partition and thresholds are fixed before fitting.
            blocks = [
                sample[k:k+42] for k in range(0, len(sample), 42)
            ]
            wins = sum(
                sum(row["gjr_qlike"]-row["ewma_qlike"] for row in block) < 0
                for block in blocks if len(block) >= 30
            )
            improvement = check["qlike_improvement"]
            rate = check["gjr_var95_exception_rate"]
            approved = (
                len(sample) >= test_days and improvement is not None
                and improvement > 0 and wins >= 2 and
                rate is not None and rate <= 0.10 and
                2 < fit.nu <= 62 and fit.persistence < 0.995 and
                fit.next_variance_pct2 > 0
            )
            result["instruments"][symbol] = {
                "status": "accepted" if approved else "research_only",
                "last_price_date": dates[-1],
                "fitted_through": fit.training_end,
                "omega": fit.omega,
                "alpha": fit.alpha,
                "gamma": fit.gamma,
                "beta": fit.beta,
                "nu": fit.nu,
                "mean_pct": fit.mean_pct,
                "variance_next_pct2": fit.next_variance_pct2,
                "annualized_volatility_next": math.sqrt(
                    fit.next_variance_pct2 * 252) / 100,
                "persistence": fit.persistence,
                "verification": {
                    "observations": len(sample),
                    "ewma_qlike": check["ewma_qlike"],
                    "gjr_qlike": check["gjr_qlike"],
                    "qlike_improvement": improvement,
                    "blocks_better": wins,
                    "blocks_checked": len(blocks),
                    "var95_exception_rate": rate,
                    "var95_exceptions": check["gjr_var95_exceptions"],
                },
            }
        except (ValueError, IndexError, RuntimeError, OverflowError) as exc:
            result["instruments"][symbol] = {
                "status": "unavailable", "reason": str(exc)[:180],
            }
    stats = [x["status"] for x in result["instruments"].values()]
    result["summary"] = {
        "eligible": stats.count("accepted"),
        "research_only": stats.count("research_only"),
        "unavailable": stats.count("unavailable"),
        "evaluated": len(stats),
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", default=str(ROOT / "dist/data/market.json"))
    p.add_argument("--output", default=str(ROOT / "dist/data/volatility.json"))
    p.add_argument("--symbols", default="")
    p.add_argument("--train-window", type=int, default=500)
    p.add_argument("--test-days", type=int, default=126)
    args = p.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    result = compact_volatility(
        snapshot, limit=[s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None,
        train_window=args.train_window, test_days=args.test_days,
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    temp = path.with_suffix(".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(path)
    print(f"Volatilidad {result['as_of']}: {result['summary']}", flush=True)


if __name__ == "__main__":
    main()
