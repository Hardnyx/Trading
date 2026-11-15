"""Corporate actions of the first-cut members over the outcome window.

For every price-verified member, collect cash dividends and splits from the
public series and the last traded day inside the window. Members whose series
stops early, or never had a public series, are listed as corporate events that
need their terms from SEC 8-K filings. This data serves outcome accounting of a
development-period reconstruction; it is never an input of the decision.
"""
import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "data/historical/price-binding-v1/first-cut.json"
OUT = ROOT / "data/historical/first-cut-corporate-actions-v1"


def epoch(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d")


def yahoo_events(symbol, start, end, opener=urllib.request.urlopen, attempts=4):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={epoch(start)}"
           f"&period2={epoch(end)}&interval=1d&events=div%2Csplits")
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with opener(request, timeout=30) as response:
                result = json.load(response)["chart"]["result"][0]
            break
        except urllib.error.HTTPError as error:
            if error.code == 404 or attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    days = [iso(t) for t in result.get("timestamp", [])]
    events = result.get("events", {})
    dividends = sorted(({"ex_date": iso(d["date"]), "amount": d["amount"]} for d in (events.get("dividends") or {}).values()),
                       key=lambda r: r["ex_date"])
    splits = sorted(({"date": iso(s["date"]), "ratio": s["numerator"] / s["denominator"],
                      # Yahoo encodes spin-offs as fractional "splits" near 1; whole ratios are share splits.
                      "kind": "share-split" if abs(s["numerator"] / s["denominator"] - round(s["numerator"] / s["denominator"])) < 1e-9
                              or abs(s["denominator"] / s["numerator"] - round(s["denominator"] / s["numerator"])) < 1e-9
                              else "spin-off-price-adjustment"}
                     for s in (events.get("splits") or {}).values()), key=lambda r: r["date"])
    return {"first_day": days[0] if days else None, "last_day": days[-1] if days else None,
            "dividends": [d for d in dividends if start <= d["ex_date"] <= end],
            "splits": [s for s in splits if start <= s["date"] <= end]}


def collect(binding, cut, window_end, fetch=yahoo_events, pause=0.2):
    members, events = [], []
    for row in binding["positions"]:
        base = {"cusip": row["cusip"], "name": row.get("name"), "weight": row["weight"]}
        if row["status"] != "verified":
            events.append({**base, "type": "no-public-series-at-binding", "binding_status": row["status"],
                           "terms_source_needed": "SEC 8-K or proxy for the transaction"})
            continue
        try:
            data = fetch(row["symbol"], cut, window_end)
            time.sleep(pause)
        except Exception as error:
            events.append({**base, "symbol": row["symbol"], "type": "series-unavailable", "error": type(error).__name__})
            continue
        members.append({**base, "symbol": row["symbol"], **data})
        # The window ends on a weekday close; a series ending more than 10 days earlier stopped trading.
        if data["last_day"] and (dt.date.fromisoformat(window_end) - dt.date.fromisoformat(data["last_day"])).days > 10:
            events.append({**base, "symbol": row["symbol"], "type": "series-ends-in-window", "last_day": data["last_day"],
                           "terms_source_needed": "SEC 8-K or proxy for the transaction"})
    return members, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default="2024-12-31")
    parser.add_argument("--window-end", default="2025-12-31")
    options = parser.parse_args()
    members, events = collect(json.loads(BINDING.read_text()), options.cut, options.window_end)
    report = {"schema": "first-cut-corporate-actions-v1", "cut": options.cut, "window_end": options.window_end,
              "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source": "Yahoo chart events (unofficial; personal research); transaction terms pending from SEC filings",
              "members": len(members), "members_with_dividends": sum(bool(m["dividends"]) for m in members),
              "members_with_share_splits": [m["symbol"] for m in members if any(x["kind"] == "share-split" for x in m["splits"])],
              "members_with_spin_off_adjustments": [m["symbol"] for m in members if any(x["kind"] != "share-split" for x in m["splits"])],
              "corporate_events": events, "member_events": members, "decision_input": False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{options.cut}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("members", "members_with_dividends", "members_with_share_splits",
                                             "members_with_spin_off_adjustments")}, indent=1))
    print(len(events), "corporate events:", sorted({e["type"] for e in events}))


if __name__ == "__main__":
    main()
