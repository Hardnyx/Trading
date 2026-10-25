"""Walk-forward GJR on point-in-time SPY residuals. Research only.

Beta/intercept are fitted with information available before each forecast.
This DOES NOT replace the deployed total-return GJR or claim news causality.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np
if __package__:
    from .volatility_research import (fit_gjr_t, ewma_next,
                                      updated_variance, qlike)
else:
    from volatility_research import (fit_gjr_t, ewma_next,
                                     updated_variance, qlike)

ROOT=Path(__file__).resolve().parents[1]


def aligned_logs(asset, spy, as_of):
    def series(a):
        rows=[r for r in a.get("history",[]) if r.get("date","")<=as_of]
        rows.sort(key=lambda r:r["date"])
        if len({r["date"] for r in rows})!=len(rows):
            raise ValueError("Fechas repetidas")
        logs={}
        previous=None
        for row in rows:
            value=float(row.get("adj_close") or 0)
            if value<=0 or not math.isfinite(value):
                raise ValueError("Precio ajustado inválido")
            if previous is not None:
                logs[row["date"]]=math.log(value/previous)
            previous=value
        return logs
    y,m=series(asset),series(spy)
    dates=sorted(set(y)&set(m))
    return dates,np.array([y[d] for d in dates]),np.array([m[d] for d in dates])


def fit_market_projection(asset_returns,market_returns):
    a=np.asarray(asset_returns,dtype=float)
    m=np.asarray(market_returns,dtype=float)
    if len(a)<252 or len(a)!=len(m):
        raise ValueError("Historia insuficiente para OLS")
    market_mean=float(np.mean(m)); asset_mean=float(np.mean(a))
    centered=m-market_mean
    variance=float(np.dot(centered,centered))
    if variance<1e-12:raise ValueError("Factor de mercado degenerado")
    beta=float(np.dot(centered,a-asset_mean)/variance)
    beta=float(np.clip(beta,-5,5))
    intercept=asset_mean-beta*market_mean
    return intercept,beta


def residual_walk_forward(asset,spy,as_of,*,train_window=500,
                          test_days=126,refit_every=42,decay=.94):
    dates,y,m=aligned_logs(asset,spy,as_of)
    if len(dates)<train_window+test_days or train_window<252 or test_days<20:
        raise ValueError("Historia común insuficiente")
    start=len(dates)-test_days
    fit=None; h=None; ewma=None; alpha=None; beta=None; error=None
    results=[]
    for k in range(start,len(dates)):
        if k==start or (k-start)%refit_every==0:
            past_y=y[k-train_window:k]
            past_m=m[k-train_window:k]
            alpha,beta=fit_market_projection(past_y,past_m)
            residuals=past_y-alpha-beta*past_m
            try:
                fit=fit_gjr_t(residuals,dates[k-1])
                h=float(fit.next_variance_pct2)
            except (ValueError,RuntimeError) as exc:
                fit=None; h=None; error=str(exc)
            common_mu=float(fit.mean_pct) if fit else float(np.mean(residuals)*100)
            ewma=ewma_next(residuals,common_mu,decay)
        innovation=float((y[k]-alpha-beta*m[k])*100)
        row={"for_date":dates[k],"issued_after_close":dates[k-1],
             "beta_known_before":beta,
             "residual_observed_pct":innovation,
             "ewma_variance_pct2":float(ewma),
             "ewma_qlike":qlike(ewma,innovation,common_mu),
             "gjr_variance_pct2":h,
             "gjr_qlike":qlike(h,innovation,float(fit.mean_pct)) if fit else None,
             "training_through":fit.training_end if fit else None,
             "error_retained":True}
        results.append(row)
        if fit:
            h=updated_variance(fit,h,innovation/100)
        ewma=decay*ewma+(1-decay)*(innovation-common_mu)**2
    comparable=[r for r in results if r["gjr_qlike"] is not None]
    improvement=float(np.mean([r["ewma_qlike"]-r["gjr_qlike"]
        for r in comparable])) if comparable else None
    return {"symbol":asset["symbol"],"factor":"SPY",
            "as_of":as_of,"model":"market-residual-GJR-shadow",
            "last_projection_beta":beta,
            "observations":len(results),"valid_gjr":len(comparable),
            "qlike_improvement":improvement,
            "not_promoted":True,
            "error":error,
            "forecast_records":results,
            "warning":"El mercado futuro sólo interviene en evaluar el residual realizado. No se usa en el pronóstico. El GJR de la web sigue sobre retornos totales; no hay atribución causal."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",default=str(ROOT/"dist/data/market.json"))
    p.add_argument("--symbols",default="NVDA,AMZN,SHY,TLT,GLD")
    p.add_argument("--output",default=str(ROOT/"out/residual-garch-shadow.json"))
    p.add_argument("--test-days",type=int,default=126)
    args=p.parse_args()
    data=json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    assets={a["symbol"]:a for a in data["assets"]}
    spy=assets["SPY"]; results={}; errors={}
    for name in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        if name=="SPY":continue
        try:results[name]=residual_walk_forward(assets[name],spy,data["price_as_of"],
                                                test_days=args.test_days)
        except (KeyError,ValueError,RuntimeError) as exc:errors[name]=str(exc)
    report={"method":"shadow-only-SPY-OLS-GJR","price_as_of":data["price_as_of"],
            "source_market_generated_at":data["generated_at"],
            "results":results,"errors":errors,"not_promoted":True}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),
                      encoding="utf-8")
    for sym,r in results.items():
        print(sym,"observaciones",r["observations"],"QLIKE mejora",r["qlike_improvement"])
    for sym,error in errors.items():print(sym,"sin calibración",error)
    if not results:raise SystemExit("No hay residuales evaluables")


if __name__=="__main__":
    main()
