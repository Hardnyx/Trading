"""Fundamentals of the first-cut members as known on the cut, from SEC companyfacts.

Uses the engine's own `financials(cik, cutoff)`, which keeps only facts whose
filing date is on or before the cut, so later restatements and filings never
enter. Members are the SPY positions whose price series was verified against
the original N-PORT. Run in CI with SEC_USER_AGENT. Not a certification of the
original filing publication or of tag semantics.
"""
import argparse
import datetime as dt
import gzip
import json
import time
from pathlib import Path

try:
    from . import refresh_data as rd
except ImportError:
    import refresh_data as rd

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "data/historical/price-binding-v1/first-cut.json"
OUT = ROOT / "data/historical/first-cut-fundamentals-v1"
KEEP = ("eps", "continuing_eps", "revenue", "operating_income", "net_income", "cfo", "capex", "sbc", "buybacks",
        "cash", "equity", "assets", "long_debt", "current_debt", "shares")


def ticker_ciks():
    raw = rd.download("https://www.sec.gov/files/company_tickers.json", "company_tickers.json", max_age=24 * 3600, sec=True)
    rows = json.loads(raw).values()
    return {r["ticker"].upper().replace(".", "-"): int(r["cik_str"]) for r in rows}


def compact(record):
    if not isinstance(record, dict):
        return None
    return {k: record.get(k) for k in ("value", "period_end", "filed", "tag", "method") if k in record}


def collect(cut, binding, ciks, financials=rd.financials, pause=0.15):
    members = []
    for row in binding["positions"]:
        if row["status"] != "verified":
            continue
        symbol = row["symbol"].upper()
        entry = {"cusip": row["cusip"], "symbol": symbol, "name": row["name"], "weight": row["weight"]}
        cik = ciks.get(symbol)
        if cik is None:
            entry["status"] = "no-sec-cik-for-ticker"
        else:
            try:
                data = financials(cik, cut)
                entry.update(cik=cik, entity=data.get("entity"), status="available",
                             facts={k: compact(data.get(k)) for k in KEEP})
                latest = max((f["filed"] for f in entry["facts"].values() if f and f.get("filed")), default=None)
                if latest and latest > cut:
                    raise ValueError("A fact filed after the cut leaked")
                entry["latest_filed"] = latest
            except Exception as error:
                entry.update(cik=cik, status="error", error=f"{type(error).__name__}: {str(error)[:120]}")
            time.sleep(pause)
        members.append(entry)
    return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default="2024-12-31")
    options = parser.parse_args()
    binding = json.loads(BINDING.read_text())
    members = collect(options.cut, binding, ticker_ciks())
    summary = {}
    for m in members:
        summary[m["status"]] = summary.get(m["status"], 0) + 1
    eps = sum(1 for m in members if m.get("facts", {}).get("eps"))
    report = {"schema": "first-cut-fundamentals-v1", "cut": options.cut, "source": "SEC companyfacts, facts filed on or before the cut",
              "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "summary": summary, "members_with_ttm_eps": eps,
              "members": members, "original_publication_certified": False, "outcomes_read": False}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{options.cut}.json.gz").write_bytes(gzip.compress(json.dumps(report, indent=1).encode(), mtime=0))
    print(json.dumps({"summary": summary, "members_with_ttm_eps": eps}, indent=1))


if __name__ == "__main__":
    main()
