#!/usr/bin/env python3
"""Actualiza un corte reproducible sin claves ni dependencias de terceros.

SEC: datos XBRL oficiales. Yahoo: endpoint público no oficial; puede cambiar.
U.S. Treasury: curva XML oficial. BLS: inflación y empleo oficiales. Nunca se sustituyen fallos por datos inventados.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import json
import math
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
OUTPUT = ROOT / "dist/data/market.json"
UTC = dt.timezone.utc
UA = "TradingResearch/0.1 (https://github.com/Hardnyx/Trading)"
SEC_UA = os.environ.get("SEC_USER_AGENT", UA)
LOCK = threading.Lock()
LAST_SEC = 0.0
ASSETS = [
    ("AAPL", "Apple", "Tecnología", 320193, 0.06, 25),
    ("MSFT", "Microsoft", "Tecnología", 789019, 0.10, 29),
    ("NVDA", "NVIDIA", "Tecnología", 1045810, 0.15, 30),
    ("AMZN", "Amazon", "Consumo discrecional", 1018724, 0.12, 30),
    ("GOOGL", "Alphabet", "Comunicación", 1652044, 0.09, 23),
    ("META", "Meta Platforms", "Comunicación", 1326801, 0.09, 23),
    ("JPM", "JPMorgan Chase", "Financiero", 19617, 0.05, 14),
    ("V", "Visa", "Financiero", 1403161, 0.09, 26),
    ("XOM", "Exxon Mobil", "Energía", 34088, 0.03, 13),
    ("JNJ", "Johnson & Johnson", "Salud", 200406, 0.04, 17),
    ("PG", "Procter & Gamble", "Consumo básico", 80424, 0.04, 22),
    ("COST", "Costco", "Consumo básico", 909832, 0.09, 34),
    ("SPY", "SPDR S&P 500", "Índice amplio", None, None, None),
    ("QQQ", "Invesco Nasdaq 100", "Índice tecnológico", None, None, None),
    ("IWM", "iShares Russell 2000", "Small caps", None, None, None),
    ("TLT", "iShares 20+ Year Treasury", "Treasuries largos", None, None, None),
    ("GLD", "SPDR Gold Shares", "Oro", None, None, None),
    ("SHY", "iShares 1–3 Year Treasury", "Treasuries cortos", None, None, None),
]



def download(url, cache_key, max_age=0, sec=False):
    global LAST_SEC
    CACHE.mkdir(exist_ok=True)
    path = CACHE / cache_key
    if path.exists() and max_age and time.time() - path.stat().st_mtime < max_age:
        return path.read_bytes()
    for attempt in range(3):
        if sec:
            with LOCK:
                pause = max(0, 0.6 - (time.monotonic() - LAST_SEC))
                if pause:
                    time.sleep(pause)
                LAST_SEC = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": SEC_UA if sec else UA,
                "Accept": "application/json,text/csv,*/*",
            })
            with urllib.request.urlopen(req, timeout=40) as response:
                result = response.read()
            path.write_bytes(result)
            return result
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def date(value):
    return dt.date.fromisoformat(value[:10])


def number(value):
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def facts_for(facts, tags, unit, cutoff):
    """Keep latest available filing for each exact accounting period."""
    records = {}
    for priority, tag in enumerate(tags):
        units = facts.get(tag, {}).get("units", {})
        for row in units.get(unit, []):
            if not row.get("end") or row["end"] > cutoff or row.get("filed", "9999") > cutoff:
                continue
            if number(row.get("val")) is None:
                continue
            key = (row.get("start"), row["end"])
            score = (row.get("filed", ""), -priority)
            if key not in records or score > records[key][0]:
                records[key] = (score, dict(row, tag=tag))
    return [r[1] for r in records.values()]


def ttm(facts, tags, cutoff, unit="USD"):
    rows = facts_for(facts, tags, unit, cutoff)
    rows = [r for r in rows if r.get("start") and 60 <= (date(r["end"]) - date(r["start"])).days <= 390]
    if not rows:
        return None
    latest_end = max(r["end"] for r in rows)
    annuals = [r for r in rows if 330 <= (date(r["end"]) - date(r["start"])).days <= 390]
    direct = [r for r in annuals if r["end"] == latest_end]
    if direct:
        chosen = max(direct, key=lambda r: r.get("filed", ""))
        return {"value": chosen["val"], "period_end": chosen["end"], "filed": chosen["filed"], "method": "TTM", "tag": chosen["tag"]}
    current = sorted([r for r in rows if r["end"] == latest_end], key=lambda r: r["start"])
    for cur in current:
        bases = [a for a in annuals if abs((date(cur["start"]) - date(a["end"])).days - 1) <= 10]
        if not bases:
            continue
        ann = max(bases, key=lambda r: r["end"])
        prior = [r for r in rows if 350 <= (date(cur["end"]) - date(r["end"])).days <= 380
                 and abs((date(cur["end"]) - date(cur["start"])).days - (date(r["end"]) - date(r["start"])).days) <= 12]
        if prior:
            prev = min(prior, key=lambda r: abs((date(cur["end"]) - date(r["end"])).days - 365))
            return {"value": ann["val"] + cur["val"] - prev["val"], "period_end": cur["end"],
                    "filed": max(ann["filed"], cur["filed"], prev["filed"]), "method": "TTM", "tag": cur["tag"]}
    if annuals:
        chosen = max(annuals, key=lambda r: r["end"])
        return {"value": chosen["val"], "period_end": chosen["end"], "filed": chosen["filed"], "method": "FY", "tag": chosen["tag"]}
    return None


def instant(facts, tags, cutoff, unit="USD"):
    rows = facts_for(facts, tags, unit, cutoff)
    rows = [r for r in rows if not r.get("start")]
    if not rows:
        return None
    r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
    return {"value": r["val"], "period_end": r["end"], "filed": r["filed"], "tag": r["tag"]}


def financials(cik, cutoff):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    body = json.loads(download(url, f"sec-{cik}.json", max_age=6 * 3600, sec=True))
    facts = body.get("facts", {}).get("us-gaap", {})
    mapping = {
        "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenuesNetOfInterestExpense"],
        "operating_income": ["OperatingIncomeLoss"],
        "net_income": ["NetIncomeLoss", "ProfitLoss"],
        "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
        "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
        "sbc": ["ShareBasedCompensation"],
        "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    }
    result = {name: ttm(facts, tags, cutoff) for name, tags in mapping.items()}
    result["eps"] = ttm(facts, ["EarningsPerShareDiluted"], cutoff, "USD/shares")
    result["cash"] = instant(facts, ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], cutoff)
    result["equity"] = instant(facts, ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], cutoff)
    result["assets"] = instant(facts, ["Assets"], cutoff)
    result["long_debt"] = instant(facts, ["LongTermDebtNoncurrent", "LongTermDebt"], cutoff)
    result["current_debt"] = instant(facts, ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"], cutoff)
    result["shares"] = instant(body.get("facts", {}).get("dei", {}), ["EntityCommonStockSharesOutstanding"], cutoff, "shares")
    if not result["shares"]:
        result["shares"] = instant(facts, ["CommonStockSharesOutstanding"], cutoff, "shares")
    # A share count from an old taxonomy/class is unsafe for current market cap.
    if result["shares"] and (date(cutoff) - date(result["shares"]["period_end"])).days > 400:
        result["shares"] = None
    for key, record in result.items():
        if isinstance(record, dict) and record.get("period_end") and (date(cutoff) - date(record["period_end"])).days > 550:
            result[key] = None
    result["source_url"] = f"https://www.sec.gov/edgar/browse/?CIK={cik}&owner=exclude"
    result["entity"] = body.get("entityName")
    return result


def filings(cik, cutoff):
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    body = json.loads(download(url, f"submissions-{cik}.json", max_age=3600, sec=True))
    recent = body.get("filings", {}).get("recent", {})
    output = []
    for i, form in enumerate(recent.get("form", [])):
        day = recent.get("filingDate", [])[i]
        if form not in {"10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "20-F", "6-K"} or day > cutoff:
            continue
        accession = recent["accessionNumber"][i]
        primary = recent["primaryDocument"][i]
        accepted = (recent.get("acceptanceDateTime") or [""] * len(recent["form"]))[i]
        output.append({"form": form, "filing_date": day, "accepted_at": accepted,
                       "accession": accession, "description": (recent.get("primaryDocDescription") or recent["form"])[i],
                       "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{primary}"})
        if len(output) == 10:
            break
    return output


def prices(symbol, cutoff):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d&events=div%2Csplits"
    body = json.loads(download(url, f"prices-{symbol}.json", max_age=3600))
    response = body.get("chart", {}).get("result")
    if not response:
        raise ValueError("Sin serie de precios")
    response = response[0]
    quote = response["indicators"]["quote"][0]
    adjusted = response["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    if len(adjusted) != len(response["timestamp"]):
        raise ValueError("Falta la serie ajustada; no se sustituye por cierre simple")
    regular_end = response.get("meta", {}).get("currentTradingPeriod", {}).get("regular", {}).get("end", 0)
    now = dt.datetime.now(UTC).timestamp()
    rows = []
    for i, timestamp in enumerate(response["timestamp"]):
        day = dt.datetime.fromtimestamp(timestamp, UTC).date().isoformat()
        if day > cutoff or (day == dt.datetime.now(UTC).date().isoformat() and now < regular_end):
            continue
        close = number(quote["close"][i])
        adj = number(adjusted[i])
        if close and adj and close > 0 and adj > 0:
            rows.append({"date": day, "close": round(close, 6), "adj_close": round(adj, 6), "volume": quote["volume"][i]})
    if len(rows) < 63:
        raise ValueError("Historia insuficiente")
    dividend_sum = sum(x["amount"] for x in response.get("events", {}).get("dividends", {}).values()
                       if 0 <= (date(rows[-1]["date"]) - dt.datetime.fromtimestamp(x["date"], UTC).date()).days < 365)
    return {"history": rows, "price": rows[-1]["close"], "price_date": rows[-1]["date"],
            "change": rows[-1]["close"] / rows[-2]["close"] - 1,
            "dividend_per_share": round(dividend_sum, 6), "currency": response["meta"].get("currency", "USD"),
            "source_url": f"https://finance.yahoo.com/quote/{symbol}/history/"}


def treasury_curves(cutoff):
    definitions = [("DGS3MO", "Treasury 3M", "BC_3MONTH"), ("DGS2", "Treasury 2Y", "BC_2YEAR"),
                   ("DGS5", "Treasury 5Y", "BC_5YEAR"), ("DGS10", "Treasury 10Y", "BC_10YEAR"),
                   ("DGS30", "Treasury 30Y", "BC_30YEAR")]
    histories = {key: [] for key, _, _ in definitions}
    for year in range(date(cutoff).year - 1, date(cutoff).year + 1):
        url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
        body = download(url, f"treasury-nominal-{year}.xml", max_age=6 * 3600)
        for entry in ET.fromstring(body).iter():
            if entry.tag.split("}")[-1] != "properties":
                continue
            values = {child.tag.split("}")[-1]: child.text for child in entry}
            day = (values.get("NEW_DATE") or "")[:10]
            if not day or day > cutoff:
                continue
            for key, _, column in definitions:
                if values.get(column):
                    histories[key].append({"date": day, "value": float(values[column])})
    output = []
    for key, label, _ in definitions:
        rows = sorted(histories[key], key=lambda r: r["date"])
        if rows:
            output.append({"id": key, "label": label, "unit": "%", "description": "Curva par nominal oficial",
                           "value": rows[-1]["value"], "date": rows[-1]["date"], "previous": rows[-2]["value"],
                           "history": rows, "source_url": "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed"})
    return output


def bls_series(series_id, label, cutoff, cpi=False):
    year = date(cutoff).year
    url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}?startyear={year-2}&endyear={year}"
    body = json.loads(download(url, f"bls-{series_id}.json", max_age=6 * 3600))
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError("BLS no devolvió observaciones")
    rows = []
    for record in body["Results"]["series"][0]["data"]:
        period = record.get("period", "")
        if not period.startswith("M") or not 1 <= int(period[1:]) <= 12:
            continue
        day = f"{record['year']}-{int(period[1:]):02d}-01"
        if day <= cutoff:
            try:
                value = float(record["value"])
            except (ValueError, TypeError):
                continue
            if math.isfinite(value):
                rows.append({"date": day, "value": value})
    rows.sort(key=lambda r: r["date"])
    if not rows:
        raise ValueError("Sin observaciones BLS")
    yoy = None
    if cpi:
        previous_year = f"{int(rows[-1]['date'][:4])-1}{rows[-1]['date'][4:]}"
        prior = next((r for r in rows if r["date"] == previous_year), None)
        if prior:
            yoy = rows[-1]["value"] / prior["value"] - 1
    return {"id": "CPI" if cpi else "UNRATE", "label": label, "unit": "índice" if cpi else "%",
            "description": "IPC desestacionalizado" if cpi else "Tasa de desempleo desestacionalizada",
            "value": rows[-1]["value"], "date": rows[-1]["date"], "previous": rows[-2]["value"], "yoy": yoy,
            "history": rows, "source_url": f"https://data.bls.gov/timeseries/{series_id}"}


def build_asset(spec, cutoff, previous):
    symbol, name, sector, cik, growth, multiple = spec
    errors = []
    asset = {"symbol": symbol, "name": name, "sector": sector, "type": "stock" if cik else "etf", "cik": cik,
             "assumptions": {"growth": growth, "multiple": multiple, "discount": 0.10, "horizon": 3}}
    try:
        asset.update(prices(symbol, cutoff))
    except Exception as exc:
        old = previous.get(symbol)
        if not old or not old.get("history"):
            return None, [f"{symbol}: precios no disponibles ({type(exc).__name__})"]
        asset.update({k: old.get(k) for k in ["history", "price", "price_date", "change", "dividend_per_share", "currency", "source_url"]})
        errors.append(f"{symbol}: se conserva el precio del {asset['price_date']}; actualización fallida")
    if cik:
        try:
            asset["financials"] = financials(cik, cutoff)
        except Exception as exc:
            asset["financials"] = previous.get(symbol, {}).get("financials")
            errors.append(f"{symbol}: SEC no actualizada ({type(exc).__name__})")
        try:
            asset["filings"] = filings(cik, cutoff)
        except Exception as exc:
            asset["filings"] = previous.get(symbol, {}).get("filings", [])
            errors.append(f"{symbol}: presentaciones no actualizadas ({type(exc).__name__})")
    else:
        asset["financials"] = None
    return asset, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=dt.datetime.now(UTC).date().isoformat(), help="Corte máximo YYYY-MM-DD")
    args = parser.parse_args()
    date(args.as_of)
    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    old_assets = {a["symbol"]: a for a in previous.get("assets", [])}
    assets, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(build_asset, spec, args.as_of, old_assets): spec[0] for spec in ASSETS}
        for future in concurrent.futures.as_completed(futures):
            asset, failed = future.result()
            errors.extend(failed)
            if asset:
                assets.append(asset)
                print(f"OK {asset['symbol']}: {asset['price_date']} · {len(asset['history'])} cierres", flush=True)
            else:
                print(f"ERROR {futures[future]}", flush=True)
    assets.sort(key=lambda a: next(i for i, s in enumerate(ASSETS) if s[0] == a["symbol"]))
    macro = []
    old_macro = {s["id"]: s for s in previous.get("macro", [])}
    macro_tasks = [("Treasury", lambda: treasury_curves(args.as_of)),
                   ("BLS IPC", lambda: [bls_series("CUSR0000SA0", "IPC EE.UU.", args.as_of, cpi=True)]),
                   ("BLS Empleo", lambda: [bls_series("LNS14000000", "Desempleo", args.as_of)])]
    for name, task in macro_tasks:
        try:
            macro.extend(task())
            print(f"OK {name}", flush=True)
        except Exception as exc:
            errors.append(f"{name}: actualización fallida ({type(exc).__name__})")
    for key, record in old_macro.items():
        if not any(row['id'] == key for row in macro):
            macro.append(record)
    if not assets:
        raise SystemExit("No hay datos válidos; el archivo anterior no se modifica")
    snapshot = {"schema_version": 1, "generated_at": dt.datetime.now(UTC).isoformat(), "requested_as_of": args.as_of,
                "price_as_of": min(a["price_date"] for a in assets), "assets": assets, "macro": macro, "errors": errors,
                "sources": [
                    {"name": "Yahoo Finance", "kind": "Endpoint público no oficial", "url": "https://finance.yahoo.com/", "data": "Cierres, Adj Close, dividendos y volumen"},
                    {"name": "SEC EDGAR", "kind": "API oficial", "url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces", "data": "Hechos financieros XBRL"},
                    {"name": "U.S. Treasury", "kind": "Feed XML oficial", "url": "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed", "data": "Curva par nominal"},
                    {"name": "BLS", "kind": "API oficial", "url": "https://www.bls.gov/developers/", "data": "IPC y desempleo"},
                ],
                "methodology": {"universe_point_in_time": False, "financials_point_in_time": False,
                                "returns": "Adj Close de Yahoo; precios ajustados por el proveedor por splits y distribuciones",
                                "portfolio": "Pesos constantes: rebalanceo diario teórico, sin costos ni impuestos",
                                "valuation": "Supuestos editables propios; no son consenso ni precios objetivo de analistas",
                                "limitations": "Universo actual seleccionado. Histórico financiero con últimas rectificaciones disponibles. No constituye un backtest point-in-time."}}
    temporary = OUTPUT.with_suffix(".tmp")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temporary.replace(OUTPUT)
    print(f"Guardado {OUTPUT.name}: {len(assets)} activos, {len(macro)} series, {len(errors)} avisos", flush=True)


if __name__ == "__main__":
    main()
