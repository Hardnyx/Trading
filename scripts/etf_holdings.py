"""Dated, attributed, current ETF constituents. Historical archive endpoints unused.

The provider transcribes issuer files or SEC N-PORT. Preserve the first date
Trading saw each record: an old holdings date is not proof of prior knowledge.
"""
import datetime as dt
import gzip
import json
from pathlib import Path
import re

API="https://tickerinside.com/api/v1/fund/{symbol}.json"
ATTRIBUTION="TickerInside (https://tickerinside.com/), CC BY 4.0; filings or issuer holdings"
EQUITY_ETFS=frozenset("""SPY QQQ IWM VTI VXUS VEA VWO EEM EFA EWJ EWZ EWW ECH EPU
 XLK XLC XLY XLP XLF XLE XLV XLI XLU XLRE XLB SMH SOXX VNQ KRE""".split())
VALID_TICKER=re.compile(r"^[A-Z][A-Z0-9.\-]{0,13}$")
DATE=re.compile(r"^\d{4}-\d\d-\d\d$")

def parse_fund(raw, ticker, price_cut, observed_at, depth=300):
    if not isinstance(raw,dict) or raw.get("ticker")!=ticker:
        raise ValueError("ETF identifier mismatch")
    date=raw.get("holdings_as_of")
    if not isinstance(date,str) or not DATE.fullmatch(date) or date>price_cut:
        raise ValueError("Missing holdings date or holdings date after price cut")
    if raw.get("source_layer") not in ("issuer","sec_nport"):
        raise ValueError("Unverifiable issuer / SEC source")
    holdings=raw.get("holdings")
    if not isinstance(holdings,dict) or not holdings:
        raise ValueError("Missing constituents")
    weights=[]
    for symbol,pct in holdings.items():
        if not isinstance(symbol,str) or not VALID_TICKER.fullmatch(symbol):
            continue  # unrecognized instrument stays unknown, not fabricated
        if type(pct) not in (float,int) or not 0<=pct<=100:
            raise ValueError("Invalid holding weight")
        if pct>0: weights.append((symbol,pct/100))
    total=sum(weight for _,weight in weights)
    if total<.65 or total>1.02:
        raise ValueError("Insufficient or leveraged equity coverage")
    weights.sort(key=lambda row:(-row[1],row[0]))
    positions=[{"symbol":s,"weight":round(w,9)} for s,w in weights[:depth]]
    return {"as_of":date,"observed_at":observed_at,
            "positions":positions,"positions_reported":len(weights),
            "covered_weight":round(sum(p["weight"] for p in positions),9),
            "all_equity_weight":round(total,9),
            "source_layer":raw["source_layer"],
            "source_url":API.format(symbol=ticker.lower()),
            "attribution":ATTRIBUTION,
            "provenance":"third-party-current-snapshot"}

def previous_eligible(previous, price_cut, observation):
    return (isinstance(previous,dict) and
      isinstance(previous.get("as_of"),str) and
      isinstance(previous.get("observed_at"),str) and
      previous["as_of"]<=price_cut and previous["observed_at"]<=observation and
      isinstance(previous.get("positions"),list))

def enrich_holdings(assets, old_assets, price_cut, observed_at, fetch,
                    *, archive_dir=None):
    checked=0; downloaded=0; retained=0; errors=[]
    for asset in assets:
        symbol=asset["symbol"]
        if asset.get("type")!="etf" or symbol not in EQUITY_ETFS:continue
        checked+=1
        previous=old_assets.get(symbol,{}).get("holdings")
        old=previous if previous_eligible(previous,price_cut,observed_at) else None
        if old:asset["holdings"]=old
        try:
            url=API.format(symbol=symbol.lower())
            original=fetch(url,f"etf-current-{symbol.lower()}.json")
            if len(original)>3_000_000:raise ValueError("Response exceeds ETF size limit")
            result=parse_fund(json.loads(original),symbol,price_cut,observed_at)
            if old and old.get("as_of")==result["as_of"] and old.get("positions")==result["positions"]:
                result["observed_at"]=old["observed_at"]
            elif archive_dir is not None:
                dest=Path(archive_dir)/result["as_of"]/(symbol+".json.gz")
                if not dest.exists():
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with dest.open("xb") as f:f.write(gzip.compress(original,mtime=0))
            asset["holdings"]=result
            downloaded+=1
        except Exception as exc:
            retained+=int(old is not None)
            errors.append(f"{symbol}: {type(exc).__name__}: {str(exc)[:110]}")
    return {"checked":checked,"downloaded":downloaded,"retained":retained,
            "errors":errors}
