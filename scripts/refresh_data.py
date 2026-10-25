#!/usr/bin/env python3
"""Actualiza un corte reproducible con la biblioteca estándar de Python.

SEC: datos XBRL oficiales. Yahoo: endpoint público no oficial; puede cambiar.
U.S. Treasury: curva XML oficial. BLS: inflación y empleo oficiales. Nunca se sustituyen fallos por datos inventados.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import hashlib
import gzip
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

if __package__:
    from .data_providers import FRED_SERIES, ProviderError, analyst_estimates, fred_series, fred_csv_series, retained_estimates
else:
    from data_providers import FRED_SERIES, ProviderError, analyst_estimates, fred_series, fred_csv_series, retained_estimates

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
OUTPUT = ROOT / "dist/data/market.json"
RESEARCH_OUTPUT = ROOT / "data/research/latest.json"
ARCHIVE = ROOT / "data/snapshots"
UTC = dt.timezone.utc
UA = "TradingResearch/0.3 (https://github.com/Hardnyx/Trading)"
SEC_UA = os.environ.get("SEC_USER_AGENT") or UA
LOCK = threading.Lock()
LAST_SEC = 0.0
ACCESS_FAILURES = {}
if __package__:
    from .bond_profiles import ISSUER_URLS, parse_profile
else:
    from bond_profiles import ISSUER_URLS, parse_profile

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
    *[(symbol, name, sector, None, None, None) for symbol, name, sector in [
        ("XLK", "Technology Select Sector SPDR", "Tecnología"),
        ("XLC", "Communication Services Select Sector SPDR", "Comunicación"),
        ("XLY", "Consumer Discretionary Select Sector SPDR", "Consumo discrecional"),
        ("XLP", "Consumer Staples Select Sector SPDR", "Consumo básico"),
        ("XLF", "Financial Select Sector SPDR", "Financiero"),
        ("XLE", "Energy Select Sector SPDR", "Energía"),
        ("XLV", "Health Care Select Sector SPDR", "Salud"),
        ("XLI", "Industrial Select Sector SPDR", "Industrial"),
        ("XLU", "Utilities Select Sector SPDR", "Servicios públicos"),
        ("XLRE", "Real Estate Select Sector SPDR", "Inmobiliario"),
        ("XLB", "Materials Select Sector SPDR", "Materiales"),
    ]],
]


def download(url, cache_key, max_age=0, sec=False, payload=None):
    global LAST_SEC
    CACHE.mkdir(exist_ok=True)
    path = CACHE / cache_key
    if path.exists() and max_age and time.time() - path.stat().st_mtime < max_age:
        return path.read_bytes()
    host = urllib.parse.urlsplit(url).hostname
    if host in ACCESS_FAILURES:
        raise urllib.error.HTTPError(url, ACCESS_FAILURES[host], 'Acceso rechazado previamente en esta ejecución', None, None)
    for attempt in range(3):
        if sec:
            with LOCK:
                pause = max(0, 0.6 - (time.monotonic() - LAST_SEC))
                if pause:
                    time.sleep(pause)
                LAST_SEC = time.monotonic()
        if host in ACCESS_FAILURES:
            raise urllib.error.HTTPError(url, ACCESS_FAILURES[host], 'Acceso rechazado previamente en esta ejecución', None, None)
        try:
            headers = {
                "User-Agent": SEC_UA if sec else UA,
                "Accept": "application/json,text/csv,*/*",
                "Accept-Encoding": "gzip",
            }
            if payload is not None:
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, headers=headers,
                                         data=json.dumps(payload).encode() if payload is not None else None)
            with urllib.request.urlopen(req, timeout=40) as response:
                result = response.read()
                if result.startswith(b'\x1f\x8b'):
                    result = gzip.decompress(result)
            path.write_bytes(result)
            return result
        except (urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError):
                if error.code in (401, 403):
                    ACCESS_FAILURES[host] = error.code
                if error.code in (400, 401, 402, 403, 404, 410):
                    raise
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def date(value):
    return dt.date.fromisoformat(value[:10])


def error_label(error):
    if getattr(error, 'code', None):
        return f'HTTP {error.code}'
    return str(error) if isinstance(error, ProviderError) else type(error).__name__


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
    for year, suffix in [(1,"NextTwelveMonths"),(2,"YearTwo"),(3,"YearThree"),(4,"YearFour"),(5,"YearFive"),(6,"AfterYearFive")]:
        result[f"debt_due_{year}"] = instant(facts,["LongTermDebtMaturitiesRepaymentsOfPrincipalIn" + suffix],cutoff)
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
    share_rows = facts_for(body.get("facts", {}).get("dei", {}),["EntityCommonStockSharesOutstanding"],"shares",cutoff)
    share_rows = sorted([r for r in share_rows if not r.get("start") and r["end"] >= (date(cutoff)-dt.timedelta(days=1100)).isoformat()],key=lambda r:r["end"])[-16:]
    result["history"] = []
    for row in share_rows:
        observed = {"period_end":row["end"],"filed":row["filed"],"shares_unadjusted":row["val"],"shares":row["val"],"shares_split_adjusted":False}
        # Historical accounting observations retain their actual publication date;
        # this is today's available history, not a reconstructed historical vintage.
        op = ttm(facts,mapping["operating_income"],row["filed"])
        rev = ttm(facts,mapping["revenue"],row["filed"])
        if op and rev and op["period_end"] == rev["period_end"] and rev["value"] > 0:
            observed["operating_margin"] = op["value"] / rev["value"]
        result["history"].append(observed)
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
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1d&events=div%2Csplits"
    body = json.loads(download(url, f"prices-5y-{symbol}.json", max_age=3600))
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
    splits = [{"date": dt.datetime.fromtimestamp(x["date"], UTC).date().isoformat(),
               "ratio": x["numerator"] / x["denominator"]}
              for x in response.get("events", {}).get("splits", {}).values()
              if x.get("denominator", 0) > 0 and dt.datetime.fromtimestamp(x["date"], UTC).date().isoformat() <= cutoff]
    return {"splits": splits, "history": rows, "price": rows[-1]["close"], "price_date": rows[-1]["date"],
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


BLS_SERIES = [
    ("CUSR0000SA0", "CPI", "IPC EE.UU.", "índice", "IPC general desestacionalizado"),
    ("CUSR0000SA0L1E", "CPI_CORE", "IPC subyacente", "índice", "IPC sin alimentos ni energía, desestacionalizado"),
    ("LNS14000000", "UNRATE", "Desempleo", "%", "Tasa de desempleo desestacionalizada"),
    ("CES0000000001", "PAYEMS", "Nóminas no agrícolas", "miles de personas", "Empleo total no agrícola desestacionalizado"),
    ("CES0500000003", "AHE", "Salario horario privado", "USD/hora", "Salario horario medio de empleados privados, desestacionalizado"),
    ("LNS11300000", "LFPR", "Participación laboral", "%", "Participación en la fuerza laboral desestacionalizada"),
]


def bls_batch(definitions, cutoff):
    """Fetch all BLS series in one POST; never expose the registration key."""
    year = date(cutoff).year
    api_key = os.environ.get("BLS_API_KEY", "").strip()
    version = "v2" if api_key else "v1"
    endpoint = f"https://api.bls.gov/publicAPI/{version}/timeseries/data/"
    ids = [entry[0] for entry in definitions]
    if len(set(ids)) != len(ids) or not ids or len(ids) > (50 if api_key else 25):
        raise ProviderError("Número de series BLS fuera de límite")
    payload = {"seriesid": ids, "startyear": str(year - 2), "endyear": str(year)}
    if api_key:
        payload["registrationkey"] = api_key
    signature = hashlib.sha256(",".join(ids).encode()).hexdigest()[:12]
    try:
        response = download(endpoint, f"bls-{version}-{year}-{signature}-post.json",
                            max_age=6 * 3600, payload=payload)
        body = json.loads(response)
    except urllib.error.HTTPError as error:
        raise ProviderError("BLS rechazó la petición" if error.code in (400, 401, 403)
                            else "BLS temporalmente no disponible", error.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise ProviderError("BLS temporalmente no disponible") from None
    except (ValueError, UnicodeError, TypeError):
        raise ProviderError("Respuesta BLS no válida") from None
    if not isinstance(body, dict) or body.get("status") != "REQUEST_SUCCEEDED":
        raise ProviderError("BLS no completó la consulta")
    results = body.get("Results")
    series = results.get("series") if isinstance(results, dict) else None
    if not isinstance(series, list):
        raise ProviderError("BLS no devolvió series válidas")
    by_id = {item.get("seriesID"): item for item in series
             if isinstance(item, dict) and isinstance(item.get("seriesID"), str)}
    # Some BLS responses omit seriesID for single-series queries; accept only
    # when there is a single requested and returned series.
    if len(ids) == len(series) == 1 and not by_id:
        by_id[ids[0]] = series[0]
    output = []
    for source_id, target, label, unit, description in definitions:
        item = by_id.get(source_id)
        if not item or not isinstance(item.get("data"), list):
            continue
        records = {}
        for row in item["data"]:
            if not isinstance(row, dict):
                continue
            period = row.get("period")
            if not isinstance(period, str) or len(period) != 3 or not period.startswith("M") or not period[1:].isdigit():
                continue
            month = int(period[1:])
            if not 1 <= month <= 12:  # Ignore M13 annual averages.
                continue
            try:
                day = f"{int(row['year']):04d}-{month:02d}-01"
                value = float(row["value"].replace(",", "") if isinstance(row["value"], str) else row["value"])
            except (ValueError, TypeError, KeyError):
                continue
            if day <= cutoff and math.isfinite(value):
                records[day] = {"date": day, "value": value}
        rows = [records[key] for key in sorted(records)]
        if not rows:
            continue
        previous_year = f"{int(rows[-1]['date'][:4])-1}{rows[-1]['date'][4:]}"
        prior = records.get(previous_year)
        yoy = (rows[-1]["value"] / prior["value"] - 1
               if target.startswith("CPI") and prior and prior["value"] else None)
        output.append({
            "id": target, "label": label, "unit": unit, "description": description,
            "value": rows[-1]["value"], "date": rows[-1]["date"],
            "previous": rows[-2]["value"] if len(rows) > 1 else None, "yoy": yoy,
            "history": rows, "provider": "BLS", "source_id": source_id,
            "vintage_mode": "observed_current", "source_url": f"https://data.bls.gov/timeseries/{source_id}",
        })
    if not output:
        raise ProviderError("BLS no devolvió observaciones válidas")
    return output


def bls_series(series_id, label, cutoff, cpi=False):
    """Backwards-compatible single-series call for collectors and tests."""
    definition = (series_id, "CPI" if cpi else "UNRATE", label,
                  "índice" if cpi else "%", "IPC desestacionalizado" if cpi else "Tasa de desempleo desestacionalizada")
    return bls_batch([definition], cutoff)[0]

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
            return None, [f"{symbol}: precios no disponibles ({error_label(exc)})"]
        rows = [row for row in old["history"] if row["date"] <= cutoff]
        if len(rows) < 2:
            return None, [f"{symbol}: precios anteriores al corte no disponibles ({error_label(exc)})"]
        asset.update({k: old.get(k) for k in ["history", "price", "price_date", "change", "dividend_per_share", "currency", "source_url"]})
        asset.update(history=rows, price=rows[-1]["close"], price_date=rows[-1]["date"], change=rows[-1]["close"] / rows[-2]["close"] - 1)
        if old.get("price_date", "9999") > cutoff:
            asset["dividend_per_share"] = None
        errors.append(f"{symbol}: se conserva el precio del {asset['price_date']}; actualización fallida ({error_label(exc)})")
    if cik:
        try:
            asset["financials"] = financials(cik, cutoff)
        except Exception as exc:
            old = previous.get(symbol, {}).get("financials") or {}
            asset["financials"] = {key: value if not isinstance(value, dict) or
                                   (value.get("filed", "9999") <= cutoff and value.get("period_end", "9999") <= cutoff)
                                   else None for key, value in old.items()}
            if isinstance(asset["financials"].get("history"),list):
                asset["financials"]["history"] = [r for r in asset["financials"]["history"] if r.get("filed","9999") <= cutoff and r.get("period_end","9999") <= cutoff]
            errors.append(f"{symbol}: SEC no actualizada ({error_label(exc)})")
        try:
            asset["filings"] = filings(cik, cutoff)
        except Exception as exc:
            asset["filings"] = [row for row in previous.get(symbol, {}).get("filings", [])
                                if row.get("filing_date", "9999") <= cutoff]
            errors.append(f"{symbol}: presentaciones no actualizadas ({error_label(exc)})")
    else:
        asset["financials"] = None
    if cik and isinstance(asset.get("splits"),list):
        for row in (asset.get("financials") or {}).get("history",[]):
            if row["period_end"] >= asset["history"][0]["date"]:
                factor = math.prod(split["ratio"] for split in asset["splits"] if row["period_end"] < split["date"] <= cutoff)
                row["shares"] = row["shares_unadjusted"] * factor
                row["shares_split_adjusted"] = True
                row["split_source"] = asset["source_url"]
    if symbol in ISSUER_URLS:
        try:
            raw = download(ISSUER_URLS[symbol], f"issuer-{symbol}.html", max_age=6 * 3600)
            asset["bond_profile"] = parse_profile(raw.decode("utf-8") if isinstance(raw, bytes) else raw,
                                                 symbol, cutoff, dt.datetime.now(UTC).isoformat())
        except Exception as exc:
            old_profile = previous.get(symbol, {}).get("bond_profile")
            if old_profile and old_profile.get("date", "9999") <= cutoff:
                asset["bond_profile"] = old_profile
            errors.append(f"{symbol}: perfil de duración/TIR sin actualizar ({error_label(exc)})")
    return asset, errors


def public_snapshot(snapshot):
    return dict(snapshot, assets=[{key: value for key, value in asset.items() if key != "analyst_estimates"}
                                 for asset in snapshot["assets"]])


def fmp_execution_allowed():
    return os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("REPOSITORY_PRIVATE") == "true"


def archive_observation(snapshot, directory=None, include_research=False):
    """Preserve what was observed at collection time without repeating price history."""
    if not include_research:
        snapshot = public_snapshot(snapshot)
    directory = ARCHIVE if directory is None else directory
    collected = dt.datetime.fromisoformat(snapshot['generated_at'].replace('Z', '+00:00'))
    if collected.tzinfo is None:
        raise ValueError('La captura necesita una hora de colección con zona horaria')
    collected = collected.astimezone(UTC)
    source = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    payload = {
        'schema_version': 1,
        'collected_at': snapshot['generated_at'],
        'requested_as_of': snapshot['requested_as_of'],
        'price_as_of': snapshot['price_as_of'],
        'collection_mode': 'current' if snapshot['requested_as_of'] == collected.date().isoformat() else 'historical_request',
        'source_snapshot_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'assets': [dict({k: v for k, v in asset.items() if k != 'history'},
                        quote=asset['history'][-1] if asset.get('history') else None)
                   for asset in snapshot['assets']],
        'macro': [{k: v for k, v in series.items() if k != 'history'} for series in snapshot.get('macro', [])],
        'errors': snapshot.get('errors', []),
        'sources': snapshot.get('sources', []),
        'providers': snapshot.get('providers', []),
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n'
    folder = Path(directory) / collected.strftime('%Y-%m')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (collected.strftime('%Y-%m-%dT%H%M%S%fZ') + '.json')
    try:
        with path.open('x', encoding='utf-8') as handle:
            handle.write(content)
    except FileExistsError:
        if path.read_text(encoding='utf-8') != content:
            raise ValueError('No se puede sobrescribir una captura anterior')
    return path


def write_snapshot(snapshot, public_path=None, private_path=None):
    """Keep personal licensed research outside the publicly deployed directory."""
    public_path = OUTPUT if public_path is None else public_path
    private_path = RESEARCH_OUTPUT if private_path is None else private_path
    has_research = any(asset.get("analyst_estimates") for asset in snapshot["assets"])
    if has_research or private_path.exists():
        private_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = private_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        temporary.replace(private_path)
        archive_observation(snapshot, private_path.parent / "snapshots", include_research=True)
    public = public_snapshot(snapshot)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = public_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(public, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temporary.replace(public_path)


def previous_snapshot():
    research = json.loads(RESEARCH_OUTPUT.read_text()) if RESEARCH_OUTPUT.exists() else {}
    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else research
    estimates = {asset["symbol"]: asset.get("analyst_estimates") for asset in research.get("assets", [])}
    for asset in previous.get("assets", []):
        if estimates.get(asset["symbol"]):
            asset["analyst_estimates"] = estimates[asset["symbol"]]
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=dt.datetime.now(UTC).date().isoformat(), help="Corte máximo YYYY-MM-DD")
    args = parser.parse_args()
    date(args.as_of)
    previous = previous_snapshot()
    collected_at = dt.datetime.now(UTC).isoformat()
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
    providers = []
    sec_failures = sum('SEC no actualizada' in warning or 'presentaciones no actualizadas' in warning for warning in errors)
    sec_total = sum(bool(spec[3]) for spec in ASSETS) * 2
    sec_success = sum(asset["type"] == "stock" for asset in assets) * 2 - sec_failures
    providers.append({"id": "sec", "name": "SEC EDGAR", "status": "error" if not sec_success else "partial" if sec_success < sec_total else "ok",
                      "detail": f"{sec_success}/{sec_total} consultas actualizadas", "checked_at": collected_at})
    macro = []
    old_macro = {s["id"]: s for s in previous.get("macro", [])}
    current_request = args.as_of == collected_at[:10]
    macro_tasks = [("Treasury", lambda: treasury_curves(args.as_of))]
    for name, task in macro_tasks:
        try:
            fresh = task()
            for series in fresh:
                series["observed_at"] = collected_at
                series.setdefault("provider", "Treasury" if name == "Treasury" else "BLS")
            macro.extend(fresh)
            providers.append({"id": name.lower().replace(" ", "-"), "name": name, "status": "ok", "detail": f"{len(fresh)} series", "checked_at": collected_at})
            print(f"OK {name}", flush=True)
        except Exception as exc:
            errors.append(f"{name}: actualización fallida ({error_label(exc)})")
            providers.append({"id": name.lower().replace(" ", "-"), "name": name, "status": "error", "detail": error_label(exc), "checked_at": collected_at})
    if current_request:
        try:
            fresh = bls_batch(BLS_SERIES, args.as_of)
            for series in fresh:
                series["observed_at"] = collected_at
            macro.extend(fresh)
            missing = len(BLS_SERIES) - len(fresh)
            providers.append({"id": "bls", "name": "BLS", "status": "ok" if not missing else "partial",
                              "detail": f"{len(fresh)}/{len(BLS_SERIES)} series · API {'v2 registrada' if os.environ.get('BLS_API_KEY') else 'v1 pública'}",
                              "checked_at": collected_at})
            if missing:
                errors.append(f"BLS: {missing} series no disponibles")
        except Exception as exc:
            errors.append(f"BLS: actualización fallida ({error_label(exc)})")
            providers.append({"id": "bls", "name": "BLS", "status": "error",
                              "detail": error_label(exc), "checked_at": collected_at})
    else:
        providers.append({"id": "bls", "name": "BLS", "status": "historical_request",
                          "detail": "Sin vintage BLS para reconstruir el corte histórico",
                          "checked_at": collected_at})
    fred_key = os.environ.get("FRED_API_KEY", "").strip()
    fred_success = 0
    fred_enabled = bool(fred_key) or current_request
    if fred_enabled:
        for definition in FRED_SERIES:
            try:
                fresh = fred_series(download, definition, args.as_of, fred_key, collected_at) if fred_key else fred_csv_series(download, definition, args.as_of, collected_at)
                current = next((row for row in macro if row["id"] == fresh["id"]), None)
                if not current or fresh["date"] >= current["date"]:
                    macro = [row for row in macro if row["id"] != fresh["id"]] + [fresh]
                fred_success += 1
            except Exception as exc:
                errors.append(f"FRED {definition[0]}: actualización fallida ({error_label(exc)})")
                if not fred_key:
                    break
    providers.append({"id": "fred", "name": "FRED", "status": "not_configured" if not fred_enabled else "ok" if fred_success == len(FRED_SERIES) else "partial" if fred_success else "error",
                      "detail": f"{fred_success}/{len(FRED_SERIES)} series; " + ("API con versión al corte" if fred_key else "CSV público observado hoy") if fred_enabled else "FRED_API_KEY necesaria para cortes históricos", "checked_at": collected_at})
    fmp_key = os.environ.get("FMP_API_KEY", "").strip()
    fmp_success = 0
    fmp_allowed = fmp_execution_allowed()
    stock_count = sum(asset["type"] == "stock" for asset in assets)
    for asset in assets:
        if asset["type"] != "stock":
            continue
        old = retained_estimates(old_assets.get(asset["symbol"], {}).get("analyst_estimates"), args.as_of)
        asset["analyst_estimates"] = old
        if not fmp_key or not current_request or not fmp_allowed:
            continue
        try:
            asset["analyst_estimates"] = analyst_estimates(download, asset["symbol"], args.as_of, fmp_key, collected_at, old)
            fmp_success += 1
        except Exception as exc:
            errors.append(f"FMP {asset['symbol']}: consenso no actualizado ({error_label(exc)})")
    providers.append({"id": "fmp", "name": "FMP · consenso", "status": "not_configured" if not fmp_key else "private_required" if not fmp_allowed else "historical_request" if not current_request else "ok" if fmp_success == stock_count else "partial" if fmp_success else "error",
                      "detail": "FMP_API_KEY pendiente" if not fmp_key else "Usar ejecución local o repositorio privado" if not fmp_allowed else "Consenso actual omitido en corte histórico" if not current_request else f"{fmp_success}/{stock_count} activos consultados; corte privado", "checked_at": collected_at})
    for key, record in old_macro.items():
        if (record.get('date', '9999') <= args.as_of and
                (not record.get('vintage_date') or record['vintage_date'] <= args.as_of) and
                (not record.get('observed_at') or record['observed_at'][:10] <= args.as_of) and
                not any(row['id'] == key for row in macro)):
            macro.append(record)
    if not assets:
        raise SystemExit("No hay datos válidos; el archivo anterior no se modifica")
    snapshot = {"schema_version": 1, "generated_at": dt.datetime.now(UTC).isoformat(), "requested_as_of": args.as_of,
                "price_as_of": min(a["price_date"] for a in assets), "assets": assets, "macro": macro, "errors": errors, "providers": providers,
                "sources": [
                    {"name": "Yahoo Finance", "kind": "Endpoint público no oficial", "url": "https://finance.yahoo.com/", "data": "Cierres, Adj Close, dividendos y volumen"},
                    {"name": "SEC EDGAR", "kind": "API oficial", "url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces", "data": "Hechos financieros XBRL"},
                    {"name": "U.S. Treasury", "kind": "Feed XML oficial", "url": "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed", "data": "Curva par nominal"},
                    {"name": "BLS", "kind": "API oficial", "url": "https://www.bls.gov/developers/", "data": "IPC y desempleo"},
                    {"name": "FRED", "kind": "CSV público / API histórica con clave", "url": "https://fred.stlouisfed.org/docs/api/fred/", "data": "IPC, desempleo, Fed funds, inflación implícita, nóminas y producción industrial"},
                    {"name": "iShares", "kind": "Página del emisor", "url": "https://www.ishares.com/", "data": "Duración, TIR, SEC yield y gastos de SHY/TLT fechados"},
                    {"name": "FMP", "kind": "API opcional con clave · corte privado", "url": "https://site.financialmodelingprep.com/developer/docs/stable/financial-estimates", "data": "Consenso anual de BPA y ventas; revisiones entre capturas. Se carga mediante Importar corte JSON."},
                ],
                "methodology": {"universe_point_in_time": False, "financials_point_in_time": False,
                                "returns": "Adj Close de Yahoo; precios ajustados por el proveedor por splits y distribuciones",
                                "portfolio": "Pesos constantes: rebalanceo diario teórico, sin costos ni impuestos",
                                "valuation": "Previsión propia; consenso opcional comparable; incertidumbre y escenarios editables",
                                "limitations": "Universo actual seleccionado. Histórico financiero con últimas rectificaciones disponibles. No constituye un backtest point-in-time."}}
    archived = archive_observation(snapshot)
    write_snapshot(snapshot)
    print(f"Captura conservada: {archived.relative_to(ROOT)}", flush=True)
    print(f"Guardado {OUTPUT.name}: {len(assets)} activos, {len(macro)} series, {len(errors)} avisos", flush=True)
    for warning in errors:
        print(f'AVISO {warning}', flush=True)
    for provider in providers:
        print(f"FUENTE {provider['name']}: {provider['status']} · {provider['detail']}", flush=True)


if __name__ == "__main__":
    main()
