"""Multivariate Student-t vs Gaussian joint-density challenger (research only).

Uses the SAME training covariance and rolling chronology for both candidates.
It does not silently activate fat tails in Monte Carlo without OOS evidence.
An unconditional constant-covariance density is a baseline, not a joint
factor/GJR model. Prices are not the historical fundamentals vintage.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import numpy as np
from scipy.stats import multivariate_normal, multivariate_t
try:
    from .factor_volatility_research import aligned_logs
except ImportError:
    from factor_volatility_research import aligned_logs


NU_GRID=(4,6,8,12,20,40)


def make_covariance(y, ridge=.08):
    if y.ndim!=2 or len(y)<100:
        raise ValueError("Insufficient training observations for joint tails")
    base=np.cov(y,rowvar=False,ddof=1)
    cov=(1-ridge)*base+ridge*np.diag(np.diag(base))
    eigen=np.linalg.eigvalsh(cov)
    if not np.all(np.isfinite(cov)) or eigen.min()<1e-12:
        raise ValueError("Noninvertible joint covariance")
    return cov


def joint_score(sample, mean, cov, nu=None):
    if nu is None:
        return float(np.mean(multivariate_normal.logpdf(
            sample,mean=mean,cov=cov,allow_singular=False)))
    shape=cov*(nu-2)/nu
    return float(np.mean(multivariate_t.logpdf(
        sample,loc=mean,shape=shape,df=nu)))


def rolling_joint_tail_challenger(y, market, *,
                                  train_window=500,test_days=126,refit_every=42):
    a=np.asarray(y,dtype=float)
    b=np.asarray(market,dtype=float)
    if len(a)!=len(b) or len(a)<train_window+test_days or
        not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("Not enough finite joint return observations")
    values=np.column_stack((a,b))
    start=len(values)-test_days
    score_gauss,score_t=[],[]
    fits=[]
    i=start
    while i<len(values):
        past=values[i-train_window:i]
        mu=past.mean(axis=0)
        cov=make_covariance(past)
        grid={nu:joint_score(past,mu,cov,nu) for nu in NU_GRID}
        # Training selection and evaluation are strictly disjoint.
        winner=max(grid,key=grid.get)
        end=min(i+refit_every,len(values))
        holdout=values[i:end]
        g=joint_score(holdout,mu,cov)
        t=joint_score(holdout,mu,cov,winner)
        score_gauss.extend([g]*(end-i))
        score_t.extend([t]*(end-i))
        fits.append({"training_end_index":i-1,
                     "test_start_index":i,
                     "test_end_index":end-1,
                     "train_chosen_nu":winner,
                     "holdout_logscore_gaussian":g,
                     "holdout_logscore_t":t,
                     "holdout_gain_t":t-g})
        i=end
    # Weighted by the number of test observations per block.
    total=sum(x["test_end_index"]-x["test_start_index"]+1 for x in fits)
    gain=sum((x["test_end_index"]-x["test_start_index"]+1)*
             x["holdout_gain_t"] for x in fits)/total
    return {
        "method":"rolling-studentt-vs-gaussian-joint-log-density-v1",
        "factors":["target","market"],"test_days":test_days,
        "oos_logscore_gain_student_t":float(gain),
        "folds":fits,
        "eligible_for_promotion":False,
        "warning":"This unconditional bivariate density is NOT multivariate conditional GJR, does not model news causality, and cannot validate portfolio CVaR by itself.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--market",default="dist/data/market.json")
    p.add_argument("--symbols",default="AMZN,NVDA,SHY,TLT")
    p.add_argument("--benchmark",default="SPY")
    p.add_argument("--output",default="out/joint-tail-challenger.json")
    args=p.parse_args()
    market=json.loads(Path(args.market).read_text(encoding="utf-8"))
    assets={a["symbol"]:a for a in market["assets"]}
    report={"as_of":market["price_as_of"],
            "not_promoted":True,"results":{},"errors":{}}
    for symbol in args.symbols.split(","):
        try:
            _,y,m=aligned_logs(assets[symbol],assets[args.benchmark],
                               market["price_as_of"])
            report["results"][symbol]=rolling_joint_tail_challenger(y,m)
        except (KeyError,ValueError,np.linalg.LinAlgError) as error:
            report["errors"][symbol]=str(error)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),
                    encoding="utf-8")
    for symbol,row in report["results"].items():
        print(symbol,"Student-t holdout gain",
              row["oos_logscore_gain_student_t"])


if __name__=="__main__":
    main()
