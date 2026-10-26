"""News-aware GARCH-X candidate using verified time-stamped release surprises.

This prototype tests whether an additional news multiplier beats a FROZEN
baseline GJR forecast on a strictly later holdout. Events must be independently
verified, with consensus captured BEFORE the announcement. News never removes
the realized error or changes the previous forecast. No auto-promotion.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import timedelta
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar

try:
    from .research_gate import instant, validate_event
    from .volatility_research import walk_forward
except ImportError:
    from research_gate import instant, validate_event
    from volatility_research import walk_forward


def dated_news_signal(events, issued_at, symbol, days=5):
    issued=instant(issued_at)
    weighted=0.
    for event in events:
        checked=validate_event(event, issued_at)
        if not checked["event_known_before_forecast"]:
            continue
        affected=set(event.get("asset_ids") or [])
        if affected and symbol not in affected and event.get("scope")!="macro":
            continue
        age=(issued-instant(event["known_at_utc"])).total_seconds()/86400
        if age<0 or age>days:
            continue
        surprise=checked["surprise"]
        if surprise is None:
            continue # no expert guess about sentiment
        sigma=event.get("consensus_scale")
        if not isinstance(sigma,(int,float)) or not math.isfinite(sigma) or sigma<=0:
            continue # unit-consistent surprise normalization required
        weighted+=abs(surprise/sigma)*math.exp(-age/2)
    return min(5.,weighted)


def compare_news_garchx(forecast_rows, events, symbol, *,
                        training_ratio=.65, min_event_days=12):
    observations=[]
    for row in forecast_rows:
        var=row.get("gjr_variance_pct2")
        if not isinstance(var,(int,float)) or not math.isfinite(var) or var<=0:
            continue
        issued=row["issued_after_close"]+"T23:59:59Z"
        x=dated_news_signal(events,issued,symbol)
        mu=row.get("observation_pct",0) # observation is NOT mean
        surprise=row.get("standardized_surprise")
        if not isinstance(surprise,(int,float)) or not math.isfinite(surprise):
            continue
        # Standardized innovation observed ex post; baseline variance was frozen.
        squared=var*surprise*surprise
        observations.append((x,var,squared,row["for_date"]))
    n=len(observations)
    split=int(n*training_ratio)
    if n<70 or split<40 or n-split<20:
        return {"status":"insufficient_history","n":n,"not_promoted":True}
    training=observations[:split]
    holdout=observations[split:]
    event_days=sum(x>0 for x,_,_,_ in training)
    holdout_events=sum(x>0 for x,_,_,_ in holdout)
    if event_days<min_event_days or holdout_events<3:
        return {"status":"insufficient_verified_surprises",
                "train_events":event_days,"holdout_events":holdout_events,
                "n":n,"not_promoted":True}
    def loss(delta, sample):
        return float(sum(math.log(h)+delta*x+q/(h*math.exp(delta*x))
                         for x,h,q,_ in sample)/len(sample))
    # Shrink effects towards zero to avoid overfitting limited event histories.
    model=minimize_scalar(lambda a:loss(a,training)+.05*a*a,
                          bounds=(-.8,.8),method="bounded")
    delta=float(model.x)
    baseline=loss(0.,holdout)
    alternative=loss(delta,holdout)
    return {
        "status":"evaluated_not_promoted",
        "train_days":len(training), "test_days":len(holdout),
        "train_event_days":event_days,"test_event_days":holdout_events,
        "delta":delta,
        "holdout_qlike_baseline":baseline,
        "holdout_qlike_garchx":alternative,
        "holdout_gain":baseline-alternative,
        "incremental_improvement":alternative<baseline,
        "frozen_forecasts_unmodified":True,
        "not_promoted":True,
        "warning":"News are verified releases, not causal price attributions. Improvement requires additional independent validation windows and multiple-testing controls.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--market",default="dist/data/market.json")
    p.add_argument("--events",default="data/events/verified.json")
    p.add_argument("--symbols",default="SPY,AMZN,NVDA")
    p.add_argument("--output",default="out/news-garchx-shadow.json")
    p.add_argument("--window",type=int,default=500)
    p.add_argument("--test-days",type=int,default=126)
    args=p.parse_args()
    events=json.loads(Path(args.events).read_text(encoding="utf-8"))
    if not isinstance(events,list):
        raise ValueError("News registry must be a list")
    if len({e.get("event_id") for e in events})!=len(events):
        raise ValueError("Repeated event ID")
    for e in events:validate_event(e)
    market=json.loads(Path(args.market).read_text(encoding="utf-8"))
    assets={a["symbol"]:a for a in market["assets"]}
    result={"method":"news-garch-x-shadow-v1",
            "verified_events":len(events),"not_promoted":True,
            "results":{},"errors":{}}
    for sym in args.symbols.split(","):
        try:
            shadow=walk_forward(assets[sym]["history"],market["price_as_of"],
                                train_window=args.window,test_days=args.test_days)
            result["results"][sym]=compare_news_garchx(
                shadow["forecasts"],events,sym)
        except (ValueError,RuntimeError,KeyError) as error:
            result["errors"][sym]=str(error)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),
                   encoding="utf-8")
    print("GARCH-X research status",{
        sym:row.get("status") for sym,row in result["results"].items()})


if __name__=="__main__":
    main()
