"""Multifactor residual/GJR experimental challenger, never production weights.

Only factor exposures estimated on returns known before the forecast are used.
The CURRENT public snapshot is suitable for statistical price experimentation,
not for historical point-in-time valuation or a survivorship-free backtest.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np

if __package__:
    from .factor_volatility_research import aligned_logs
    from .volatility_research import fit_gjr_t, ewma_next, updated_variance, qlike
else:
    from factor_volatility_research import aligned_logs
    from volatility_research import fit_gjr_t, ewma_next, updated_variance, qlike


FACTOR_CANDIDATES = ("SPY", "TLT", "HYG", "GLD")
MIN_TRAIN = 252


def aligned_multifactor(asset, factor_assets, as_of):
    """Strict dated intersection, no forward fill between nontrading days."""
    if not factor_assets:
        raise ValueError("Factor assets required")
    data = [aligned_logs(asset, f, as_of) for f in factor_assets]
    common = sorted(set.intersection(*(set(dates) for dates, _, _ in data)))
    if len(common) < MIN_TRAIN:
        raise ValueError("Insufficient common original price observations")
    targets = {d: float(v) for d, v in zip(data[0][0], data[0][1])}
    lookup = [{d: float(v) for d, v in zip(dates, market)}
              for dates, _, market in data]
    y = np.array([targets[d] for d in common], dtype=float)
    X = np.array([[f[d] for f in lookup] for d in common], dtype=float)
    return common, y, X


def ridge_projection(y, factors, prior_strength=0.05):
    """Intercept unpenalized; ridge stabilizes collinear market/rates factors."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(factors, dtype=float)
    if X.ndim != 2 or len(y) != len(X) or len(y) < MIN_TRAIN:
        raise ValueError("Bad factor training design")
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(X)):
        raise ValueError("Nonfinite factor input")
    means = np.mean(X, axis=0)
    average = np.mean(y)
    centered = X - means
    scales = np.std(centered, axis=0)
    if np.any(scales < 1e-10):
        raise ValueError("Degenerate factor history")
    Z = centered / scales
    # Regularize all loadings with comparable predictor scales.
    lam = prior_strength * len(y)
    beta_std = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]),
                               Z.T @ (y-average))
    beta = beta_std / scales
    intercept = float(average - means @ beta)
    residual = y - intercept - X @ beta
    return intercept, beta, residual


def multifactor_walk_forward(asset, factors, as_of, *,
                             window=500, test_days=126, refit_every=42):
    names = tuple(f["symbol"] for f in factors)
    dates, y, X = aligned_multifactor(asset, factors, as_of)
    if window < MIN_TRAIN or test_days < 20 or len(dates) < window+test_days:
        raise ValueError("Insufficient independent out-of-sample observations")
    start = len(dates)-test_days
    beta = None
    fit = None
    gjr = None
    ewma = None
    rows = []
    for i in range(start, len(dates)):
        if i == start or (i-start) % refit_every == 0:
            alpha, beta, innovations = ridge_projection(
                y[i-window:i], X[i-window:i])
            centered = float(np.mean(innovations)*100)
            ewma = ewma_next(innovations, centered)
            try:
                fit = fit_gjr_t(innovations, dates[i-1])
                gjr = float(fit.next_variance_pct2)
            except (ValueError, RuntimeError):
                fit = None
                gjr = None
        realized = float((y[i]-alpha-X[i] @ beta)*100)
        observation = {
            "date": dates[i],
            "issued_after_close": dates[i-1],
            "factor_betas_from_past": dict(zip(names, map(float,beta))),
            "innovation_pct": realized,
            "ewma_forecast_pct2": float(ewma),
            "ewma_qlike": qlike(ewma, realized, centered),
            "gjr_forecast_pct2": gjr,
            "gjr_qlike": qlike(gjr, realized, fit.mean_pct) if fit else None,
            "error_retained": True,
            "no_instant_news_attribution": True,
        }
        rows.append(observation)
        ewma = 0.94*ewma+0.06*(realized-centered)**2
        if fit:
            gjr = updated_variance(fit, gjr, realized/100)
    comparable = [x for x in rows if x["gjr_qlike"] is not None]
    gain = float(np.mean([x["ewma_qlike"]-x["gjr_qlike"]
                          for x in comparable])) if comparable else None
    return {
        "asset": asset["symbol"], "factors": names,
        "as_of": as_of, "test_days": len(rows),
        "paired_days": len(comparable),
        "qlike_gain_over_residual_ewma": gain,
        "current_factor_betas": dict(zip(names, map(float, beta))),
        "not_promoted": True,
        "forecast_records": rows,
        "limitation": "Factor GJR is not proof of out-of-sample portfolio utility. Factors are realized after the forecast and used only to score the ex-post residual.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", default="dist/data/market.json")
    p.add_argument("--symbols", default="AMZN,NVDA,SHY,TLT")
    p.add_argument("--factors", default="SPY,TLT,HYG,GLD")
    p.add_argument("--test-days", type=int, default=63)
    p.add_argument("--window", type=int, default=500)
    p.add_argument("--output", default="out/multifactor-gjr.json")
    args = p.parse_args()
    market = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    lookup = {a["symbol"]:a for a in market["assets"]}
    factors = [lookup[s] for s in args.factors.split(",") if s in lookup]
    result = {"method": "shadow-multifactor-ridge-gjr-v1",
              "market_cut": market["price_as_of"], "not_promoted": True,
              "results": {}, "errors": {}}
    for sym in args.symbols.split(","):
        if sym not in lookup or sym in {a["symbol"] for a in factors}:
            result["errors"][sym] = "Missing asset or simultaneously chosen factor"
            continue
        try:
            result["results"][sym] = multifactor_walk_forward(
                lookup[sym], factors, market["price_as_of"],
                window=args.window, test_days=args.test_days)
        except (ValueError, RuntimeError, IndexError, np.linalg.LinAlgError) as error:
            result["errors"][sym] = str(error)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False),
                   encoding="utf-8")
    for sym, row in result["results"].items():
        print(sym, "factor GJR gain QLIKE",
              row["qlike_gain_over_residual_ewma"],
              "paired days",row["paired_days"])
    for sym, message in result["errors"].items():
        print(sym, "no comparable multifactor test:",message)


if __name__=="__main__":
    main()
