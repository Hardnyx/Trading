"""Risk-tail challenger: conditional VaR, ES diagnostics, co-exceedance and blocks.

Research only. Does NOT justify the published 12-month CVaR. True ES coverage
needs more data and a proper backtest; historical prices alone are not
historical ex-ante financial-vintage information.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import math
import numpy as np
from scipy.stats import chi2, norm

try:
    from .factor_volatility_research import aligned_logs
except ImportError:
    from factor_volatility_research import aligned_logs


def ewma_var_oos(returns, window=252, test_days=126, decay=.94, alpha=.05):
    values=np.asarray(returns,dtype=float)
    if (not np.all(np.isfinite(values)) or
        len(values)<window+test_days or test_days<20 or window<60):
        raise ValueError("Not enough valid observations for chronological VaR")
    forecasts=[]
    z=norm.ppf(alpha)
    for t in range(len(values)-test_days,len(values)):
        past=values[t-window:t]
        mu=float(np.mean(past))
        centered=past-mu
        h=max(float(np.var(centered)),1e-12)
        for residual in centered:
            h=decay*h+(1-decay)*float(residual)**2
        sigma=math.sqrt(h)
        var=mu+z*sigma
        expected_tail=mu-sigma*norm.pdf(z)/alpha
        realized=float(values[t])
        forecasts.append({
            "index":t, "mean":mu, "sigma":sigma, "var5":var,
            "normal_es5":expected_tail,
            "realized":realized, "exception":bool(realized<var),
            "standardized_error":(realized-mu)/sigma,
        })
    return forecasts


def _chi_stat(table):
    # LR for a 2-by-2 first-order transition matrix.
    a,b,c,d=table
    p=(b+d)/max(1,a+b+c+d)
    p01=b/max(1,a+b)
    p11=d/max(1,c+d)
    def contribution(k,prob):
        if k<=0:
            return 0.
        return k*math.log(max(prob,1e-12))
    base=contribution(b+d,p)+contribution(a+c,1-p)
    alternate=(contribution(b,p01)+contribution(a,1-p01)+
               contribution(d,p11)+contribution(c,1-p11))
    return max(0.,2*(alternate-base))


def var_backtest(forecasts, alpha=.05):
    errors=[int(row["exception"]) for row in forecasts]
    n=len(errors)
    k=sum(errors)
    if n<20 or not 0<alpha<1:
        raise ValueError("Insufficient VaR evaluation")
    p=k/n
    def ll(k,n,p):
        if p<=0:return 0. if k==0 else -1e30
        if p>=1:return 0. if k==n else -1e30
        return k*math.log(p)+(n-k)*math.log1p(-p)
    lr_uc=max(0.,2*(ll(k,n,p)-ll(k,n,alpha)))
    pairs=[(errors[i-1],errors[i]) for i in range(1,n)]
    transitions=[
        sum(x==0 and y==0 for x,y in pairs),
        sum(x==0 and y==1 for x,y in pairs),
        sum(x==1 and y==0 for x,y in pairs),
        sum(x==1 and y==1 for x,y in pairs),
    ]
    lr_ind=_chi_stat(transitions)
    tails=[row for row in forecasts if row["exception"]]
    return {
        "days":n, "exceptions":k, "exception_rate":p,
        "nominal_alpha":alpha,
        "kupiec_unconditional_p":float(chi2.sf(lr_uc,1)),
        "christoffersen_independence_p":float(chi2.sf(lr_ind,1)),
        "conditional_coverage_p":float(chi2.sf(lr_uc+lr_ind,2)),
        "mean_tail_return":float(np.mean([r["realized"] for r in tails]))
                           if tails else None,
        "mean_predicted_normal_es":float(np.mean([r["normal_es5"] for r in tails]))
                           if tails else None,
        "tail_count_sufficient_for_es":len(tails)>=20,
        "warning":"ES mean is descriptive, not a valid ES statistical backtest when tail exceptions are few.",
    }


def coexceedance(asset_returns, market_returns, alpha=.05):
    y=np.asarray(asset_returns,dtype=float)
    m=np.asarray(market_returns,dtype=float)
    if len(y)!=len(m) or len(y)<126 or not np.all(np.isfinite(y+m)):
        raise ValueError("Need >=126 jointly valid observations")
    a=y<=np.quantile(y,alpha)
    b=m<=np.quantile(m,alpha)
    joint=int(np.sum(a&b))
    return {
        "joint_days":len(y), "joint_left_tail_days":joint,
        "asset_tail_days":int(np.sum(a)), "market_tail_days":int(np.sum(b)),
        "p_asset_tail_given_market_tail":float(np.mean(a[b])) if b.any() else None,
        "independent_expected_joint_days":float(np.sum(a)*np.sum(b)/len(y)),
        "unconditional_correlation":float(np.corrcoef(y,m)[0,1]),
        "warning":"Historical same-day left-tail dependence is a diagnostic; not proof of causal news or future multivariate tail calibration.",
    }


def moving_block_cvar(asset_returns, market_returns, *, weight=.5,
                      block=5, paths=1500, horizon=21, seed=2026):
    """Bootstrap paired observations, preserving contemporaneous dependence."""
    y=np.asarray(asset_returns,dtype=float)
    m=np.asarray(market_returns,dtype=float)
    if len(y)!=len(m) or len(y)<126 or block<2 or horizon<1 or paths<100:
        raise ValueError("Invalid block-bootstrap sample")
    rng=np.random.default_rng(seed)
    weights=np.array([weight,1-weight])
    observations=np.column_stack((y,m))
    returns=np.zeros(paths)
    for p in range(paths):
        days=[]
        while len(days)<horizon:
            start=int(rng.integers(0,len(observations)-block+1))
            days.extend(range(start,start+block))
        # Constant weight rebalancing daily: useful stress, not transaction simulation.
        daily=np.exp(observations[days[:horizon]])-1
        returns[p]=float(np.prod(1+daily@weights)-1)
    sorted_returns=np.sort(returns)
    end=max(1,math.ceil(.05*paths))
    return {
        "method":"paired-moving-block-bootstrap",
        "days":horizon,"block_size":block,"scenarios":paths,
        "expected_return":float(np.mean(returns)),
        "cvar95_loss":max(0.,-float(np.mean(sorted_returns[:end]))),
        "loss_probability":float(np.mean(returns<0)),
        "not_promoted":True,
        "warning":"Historical block bootstrap is an alternative stress estimator, not the same horizon, cost model or information vintage as the web proposal.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",default="dist/data/market.json")
    p.add_argument("--assets",default="AMZN,NVDA,SHY,TLT,GLD")
    p.add_argument("--market",default="SPY")
    p.add_argument("--output",default="out/tail-research.json")
    args=p.parse_args()
    data=json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    assets={a["symbol"]:a for a in data["assets"]}
    report={"method":"shadow-volatility-tail-diagnostics-v1",
            "cut":data["price_as_of"],"not_promoted":True,
            "results":{},"errors":{}}
    for sym in args.assets.split(","):
        try:
            dates,y,m=aligned_logs(assets[sym],assets[args.market],
                                  data["price_as_of"])
            tail=coexceedance(y,m)
            risk=var_backtest(ewma_var_oos(y))
            stress=moving_block_cvar(y,m)
            report["results"][sym]={"coexceedance":tail,
                                     "var_es":risk,"block_stress":stress}
        except (KeyError,ValueError) as error:
            report["errors"][sym]=str(error)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),
                   encoding="utf-8")
    for sym,row in report["results"].items():
        print(sym,"VaR exceptions",row["var_es"]["exceptions"],
              "joint tail days",row["coexceedance"]["joint_left_tail_days"])
    for sym,msg in report["errors"].items():print(sym,"not evaluated:",msg)


if __name__=="__main__":
    main()
