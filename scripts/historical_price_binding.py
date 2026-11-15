"""Bind first-cut SPY positions to free price series by matching filed prices.

Positions are paired with the original filing in document order (names
must agree). The original SEC N-PORT reports, for each position, the shares held and their
USD value at the report date; their ratio is the price the fund used. A
ticker observed in other original filings, or else one OpenFIGI maps to the
CUSIP or ISIN, is accepted as the price series of
that CUSIP only when the public close on the report date, undone for later
splits, matches that filed price. No price after the report date enters the
comparison except split factors, and no outcome is read.
"""
import argparse
import base64
import gzip
import html
import json
import urllib.error
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUT = "2024-12-31"
OBSERVATIONS = ROOT / "data/historical/identifier-observations-v1/observations.json.gz"
SEC_DIR = ROOT / "data/historical/provider-inputs-v1/sec"
BINDINGS = ROOT / "data/historical/price-binding-v1"
TOLERANCE = 0.005


def binding_path(cut, root=ROOT):
    """The first cut keeps its original file name; later cuts are named by date."""
    base = root / "data/historical/price-binding-v1"
    return base / ("first-cut.json" if cut == CUT else f"{cut}.json")


def cut_row(cut=CUT, path=OBSERVATIONS):
    archive = json.loads(gzip.decompress(path.read_bytes()))
    row = next(r for r in archive["matrix"] if r["cut"] == cut)
    if row["spy_source"]["status"] != "source-available" or not row["positions"]:
        raise ValueError(f"{cut}: no fresh SPY holdings source ({row['spy_source']['status']})")
    return row


def first_cut_row(path=OBSERVATIONS):
    return cut_row(CUT, path)


def filed_positions(accession, folder=SEC_DIR):
    """Filing positions in document order: name, CUSIP, ISIN, shares, USD value."""
    path = next(folder.glob(f"{accession}-*.json.gz"))
    document = json.loads(gzip.decompress(path.read_bytes()))
    xml = base64.b64decode(document["raw_base64"]).decode("utf-8")
    out = []
    for block in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", xml, re.S):
        get = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S) or [None, None])[1]
        isin = re.search(r'<isin value="([A-Z0-9]{12})"', block)
        out.append({"name": html.unescape(get("name") or ""), "cusip": get("cusip"), "isin": isin[1] if isin else None,
                    "units": get("units"), "shares": float(get("balance") or 0), "value_usd": float(get("valUSD") or 0)})
    return out, document["filing"]["reportDate"]


def openfigi_tickers(id_type, value, opener=urllib.request.urlopen):
    """US composite common-stock tickers that OpenFIGI maps to an identifier today."""
    body = json.dumps([{"idType": id_type, "idValue": value, "exchCode": "US"}]).encode()
    request = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body,
                                     headers={"Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with opener(request, timeout=30) as response:
                data = json.load(response)[0].get("data", [])
            return sorted({d["ticker"] for d in data if d.get("ticker")})
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(15 * (attempt + 1))
    return []


def yahoo_symbol(ticker):
    return ticker.replace("/", "-").replace(".", "-")


def yahoo_close(symbol, day, opener=urllib.request.urlopen):
    """Split-adjusted close on `day` and the product of later split ratios."""
    start = int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) - 5 * 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}"
           f"&period2={int(time.time())}&interval=1d&events=split")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener(request, timeout=30) as response:
        result = json.load(response)["chart"]["result"][0]
    days = [datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t in result.get("timestamp", [])]
    closes = result["indicators"]["quote"][0]["close"]
    close = next((c for d, c in zip(days, closes) if d == day and c), None)
    later = 1.0
    for split in (result.get("events", {}).get("splits") or {}).values():
        if datetime.fromtimestamp(split["date"], timezone.utc).strftime("%Y-%m-%d") > day:
            later *= split["numerator"] / split["denominator"]
    return close, later


def with_retry(fetch, symbol, day, attempts=4):
    for attempt in range(attempts):
        try:
            return fetch(symbol, day)
        except urllib.error.HTTPError as error:
            if error.code == 404 or attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
        except (KeyError, TypeError, IndexError):
            return None, None
    return None, None


def check_symbol(symbol, report_date, filed_price, fetch):
    try:
        close, later = with_retry(fetch, symbol, report_date)
    except Exception as error:
        return {"symbol": symbol, "status": "no-public-series", "error": type(error).__name__}
    if close is None:
        return {"symbol": symbol, "status": "no-public-series"}
    raw = close * later
    return {"symbol": symbol, "public_close_unsplit": round(raw, 6), "later_split_factor": later,
            "relative_difference": round(raw / filed_price - 1, 6),
            "status": "verified" if abs(raw / filed_price - 1) <= TOLERANCE else "price-mismatch"}


def bind(row, filings, report_date, fetch=yahoo_close, figi=openfigi_tickers, pause=0.2):
    """Try the ticker observed in original filings, then OpenFIGI tickers for the CUSIP or ISIN."""
    rows = []
    for position, filing in zip(row["positions"], filings):
        if position["name"] != filing["name"]:
            raise ValueError("Archived positions are not in filing order")
        if position["weight"] <= 0:
            continue
        observed = (position.get("ticker_observation") or {}).get("source_ticker")
        record = {"cusip": position["cusip"], "isin": filing["isin"], "name": filing["name"],
                  "weight": position["weight"], "ticker_observation": observed}
        if filing["units"] != "NS" or not filing["shares"]:
            record["status"] = "no-filed-share-price"
            rows.append(record)
            continue
        filed_price = filing["value_usd"] / filing["shares"]
        record["filed_price"] = round(filed_price, 6)
        attempts = []
        if observed:
            attempts.append(("original-filing-ticker", yahoo_symbol(observed)))
        result = None
        for source, symbol in attempts:
            result = check_symbol(symbol, report_date, filed_price, fetch)
            result["ticker_source"] = source
            time.sleep(pause)
            if result["status"] == "verified":
                break
        if not result or result["status"] != "verified":
            id_type, value = (("ID_CUSIP", position["cusip"]) if position["cusip"] and position["cusip"] != "000000000"
                              else ("ID_ISIN", filing["isin"]))
            try:
                candidates = figi(id_type, value) if value else []
            except Exception:
                candidates = []
            time.sleep(2.5 if pause else 0)  # OpenFIGI without a key: 25 requests per minute
            for ticker in candidates:
                if any(yahoo_symbol(ticker) == s for _, s in attempts):
                    continue
                trial = check_symbol(yahoo_symbol(ticker), report_date, filed_price, fetch)
                trial["ticker_source"] = "openfigi-" + id_type.lower()
                time.sleep(pause)
                if result is None or trial["status"] == "verified":
                    result = trial
                if trial["status"] == "verified":
                    break
        if result is None:
            result = {"status": "no-ticker-candidate"}
        record.update(result)
        rows.append(record)
    return rows


def summarize(rows):
    statuses = {}
    for r in rows:
        s = statuses.setdefault(r["status"], {"positions": 0, "weight": 0.0})
        s["positions"] += 1
        s["weight"] = round(s["weight"] + r["weight"], 6)
    return statuses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default=CUT)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    options.output = options.output or binding_path(options.cut)
    row = cut_row(options.cut)
    accession = row["spy_source"]["accession"]
    filings, report_date = filed_positions(accession)
    rows = bind(row, filings, report_date)
    result = {"schema": "first-cut-price-binding-v1", "cut": options.cut, "spy_accession": accession,
              "report_date": report_date, "tolerance": TOLERANCE, "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "method": "filed USD value / shares versus the public close on the report date, undone for later splits",
              "public_source": "Yahoo chart endpoint (unofficial; personal research)", "summary": summarize(rows),
              "positions": rows, "outcomes_read": False, "vendor_identity_certified": False}
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["summary"], indent=1))


if __name__ == "__main__":
    main()
