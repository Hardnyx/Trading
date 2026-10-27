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
    from .data_providers import FRED_SERIES, ProviderError, analyst_estimates, fred_series, fred_csv_series, fred_observation, retained_estimates
    from .universe import AUTO_CIK, expanded_universe
    from .filing_facts import extract_filing_facts
    from .etf_holdings import enrich_holdings
    from .distributions import price_distribution_index, enrich_distributions
    from .earnings_history import annual_eps_history, growth_replay, replay_metrics
else:
    from data_providers import FRED_SERIES, ProviderError, analyst_estimates, fred_series, fred_csv_series, fred_observation, retained_estimates
    from universe import AUTO_CIK, expanded_universe
    from filing_facts import extract_filing_facts
    from etf_holdings import enrich_holdings
    from distributions import price_distribution_index, enrich_distributions
    from earnings_history import annual_eps_history, growth_replay, replay_metrics

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
    ("AMD", "Advanced Micro Devices", "Tecnología", 2488, 0.11, 28),
    ("ADBE", "Adobe", "Tecnología", 796343, 0.08, 24),
    ("CSCO", "Cisco Systems", "Tecnología", 858877, 0.04, 17),
    ("ORCL", "Oracle", "Tecnología", 1341439, 0.08, 25),
    ("CRM", "Salesforce", "Tecnología", 1108524, 0.08, 26),
    ("NFLX", "Netflix", "Comunicación", 1065280, 0.10, 28),
    ("DIS", "Walt Disney", "Comunicación", 1744489, 0.06, 22),
    ("WMT", "Walmart", "Consumo básico", 104169, 0.05, 26),
    ("KO", "Coca-Cola", "Consumo básico", 21344, 0.04, 22),
    ("PEP", "PepsiCo", "Consumo básico", 77476, 0.04, 21),
    ("HD", "Home Depot", "Consumo discrecional", 354950, 0.06, 23),
    ("MA", "Mastercard", "Financiero", 1141391, 0.09, 29),
    ("BAC", "Bank of America", "Financiero", 70858, 0.04, 13),
    ("LLY", "Eli Lilly", "Salud", 59478, 0.10, 30),
    ("MRK", "Merck", "Salud", 310158, 0.05, 17),
    ("ABBV", "AbbVie", "Salud", 1551152, 0.05, 17),
    ("CAT", "Caterpillar", "Industrial", 18230, 0.06, 20),
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
        ("VTI", "Vanguard Total Stock Market", "Índice amplio"),
        ("VXUS", "Vanguard Total International Stock", "Acciones internacionales"),
        ("VEA", "Vanguard FTSE Developed Markets", "Mercados desarrollados"),
        ("VWO", "Vanguard FTSE Emerging Markets", "Mercados emergentes"),
        ("EEM", "iShares MSCI Emerging Markets", "Mercados emergentes"),
        ("EFA", "iShares MSCI EAFE", "Mercados desarrollados"),
        ("EWJ", "iShares MSCI Japan", "Japón"),
        ("EWZ", "iShares MSCI Brazil", "Brasil"),
        ("EWW", "iShares MSCI Mexico", "México"),
        ("ECH", "iShares MSCI Chile", "Chile"),
        ("EPU", "iShares MSCI All Peru and Global Exposure", "Perú"),
        ("BND", "Vanguard Total Bond Market", "Bonos agregados"),
        ("AGG", "iShares Core U.S. Aggregate Bond", "Bonos agregados"),
        ("IEF", "iShares 7-10 Year Treasury", "Treasuries intermedios"),
        ("IEI", "iShares 3-7 Year Treasury", "Treasuries intermedios"),
        ("SGOV", "iShares 0-3 Month Treasury", "Treasuries ultracortos"),
        ("BIL", "SPDR Bloomberg 1-3 Month T-Bill", "Treasuries ultracortos"),
        ("TIP", "iShares TIPS Bond", "Bonos indexados a inflación"),
        ("LQD", "iShares iBoxx Investment Grade Corporate Bond", "Crédito grado de inversión"),
        ("HYG", "iShares iBoxx High Yield Corporate Bond", "Crédito high yield"),
        ("EMB", "iShares J.P. Morgan USD Emerging Markets Bond", "Deuda emergente USD"),
        ("IAU", "iShares Gold Trust", "Oro"),
        ("SLV", "iShares Silver Trust", "Plata"),
        ("VNQ", "Vanguard Real Estate", "Inmobiliario"),
        ("SMH", "VanEck Semiconductor", "Semiconductores"),
        ("SOXX", "iShares Semiconductor", "Semiconductores"),
        ("KRE", "SPDR S&P Regional Banking", "Bancos regionales"),
    ]],
]



def resolved_universe(previous):
    """Resolve extra stock CIKs from the SEC, retaining verified prior CIKs on failure."""
    requested = ASSETS + expanded_universe()
    if len({row[0] for row in requested}) != len(requested):
        raise ValueError("Símbolos repetidos en el universo")
    pending = [row for row in requested if row[3] == AUTO_CIK]
    mapping = {}
    if pending:
        try:
            raw = download("https://www.sec.gov/files/company_tickers.json",
                           f"sec-company-tickers-{dt.date.today():%Y-%m}.json",
                           max_age=24 * 3600, sec=True)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Catálogo CIK inválido")
            for entry in data.values():
                if not isinstance(entry, dict):
                    continue
                symbol = entry.get("ticker")
                cik = entry.get("cik_str")
                if isinstance(symbol, str) and isinstance(cik, int) and cik > 0:
                    mapping[symbol.upper()] = cik
        except (ValueError, urllib.error.URLError, TimeoutError, UnicodeError):
            # Missing identification is explicit, never reclassified as an ETF.
            pass
    output, warnings = [], []
    for symbol, name, sector, cik, growth, multiple in requested:
        if cik == AUTO_CIK:
            cik = mapping.get(symbol) or previous.get(symbol, {}).get("cik")
            if not isinstance(cik, int) or cik <= 0:
                warnings.append(f"{symbol}: CIK oficial no disponible; activo omitido")
                continue
        output.append((symbol, name, sector, cik, growth, multiple))
    return output, warnings


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


# Financial statements live in periodic reports. Proxy statements (DEF 14A
# pay-versus-performance tables) and other forms restate figures with their
# own scale tagging and, being filed later, would otherwise supersede them.
PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "40-F", "10-KT", "10-QT"}


def periodic_form(form):
    return form is None or form.removesuffix("/A") in PERIODIC_FORMS


def facts_for(facts, tags, unit, cutoff):
    """Keep latest periodic-report filing for each exact accounting period."""
    records = {}
    for priority, tag in enumerate(tags):
        units = facts.get(tag, {}).get("units", {})
        for row in units.get(unit, []):
            if not row.get("end") or row["end"] > cutoff or row.get("filed", "9999") > cutoff:
                continue
            if not periodic_form(row.get("form")):
                continue
            if number(row.get("val")) is None:
                continue
            key = (row.get("start"), row["end"])
            score = (row.get("filed", ""), -priority)
            if key not in records or score > records[key][0]:
                records[key] = (score, dict(row, tag=tag))
    return [r[1] for r in records.values()]


def accounting_components(rows):
    return [{key: row[key] for key in ("start", "end", "filed", "val", "tag", "accn", "source_url", "source_kind") if key in row} for row in rows]


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
        return {"value": chosen["val"], "period_end": chosen["end"], "filed": chosen["filed"], "method": "TTM", "tag": chosen["tag"], "components": accounting_components([chosen])}
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
                    "filed": max(ann["filed"], cur["filed"], prev["filed"]), "method": "TTM", "tag": cur["tag"], "components": accounting_components([ann, cur, prev])}
    if annuals:
        chosen = max(annuals, key=lambda r: r["end"])
        return {"value": chosen["val"], "period_end": chosen["end"], "filed": chosen["filed"], "method": "FY", "tag": chosen["tag"], "components": accounting_components([chosen])}
    return None


def instant(facts, tags, cutoff, unit="USD"):
    rows = facts_for(facts, tags, unit, cutoff)
    rows = [r for r in rows if not r.get("start")]
    if not rows:
        return None
    r = max(rows, key=lambda r: (r["end"], r.get("filed", "")))
    return {"value": r["val"], "period_end": r["end"], "filed": r["filed"], "tag": r["tag"]}


def financials(cik, cutoff, original_filing=None):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    body = json.loads(download(url, f"sec-{cik}.json", max_age=6 * 3600, sec=True))
    facts = body.get("facts", {}).get("us-gaap", {})
    recovery = None
    if original_filing:
        key = f"filing-{cik}-{original_filing['accession']}.html"
        raw = download(original_filing["url"], key, max_age=24 * 3600, sec=True)
        supplement = extract_filing_facts(raw, original_filing, cik, cutoff)
        # Do not mutate the cached companyfacts response. Same-period facts in
        # this original filing take precedence only at its publication date.
        for tag, content in supplement.items():
            target = facts.setdefault(tag, {"units": {}})["units"]
            for unit, rows in content["units"].items():
                identities = {(r["start"], r["end"], r["filed"]) for r in rows}
                target[unit] = [r for r in target.get(unit, []) if (r.get("start"), r.get("end"), r.get("filed")) not in identities] + rows
        cache_path = CACHE / key
        recovery = {"source_url": original_filing["url"], "accession": original_filing["accession"],
                    "report_date": original_filing["report_date"], "filed": original_filing["filing_date"],
                    "standard_fact_count": sum(len(rows) for item in supplement.values() for rows in item["units"].values()),
                    "observed_at": dt.datetime.fromtimestamp(cache_path.stat().st_mtime, UTC).isoformat() if cache_path.exists() else None}
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
    result["continuing_eps"] = ttm(facts, ["IncomeLossFromContinuingOperationsPerDilutedShare"], cutoff, "USD/shares")
    result["discontinued_eps"] = ttm(facts, ["IncomeLossFromDiscontinuedOperationsNetOfTaxPerDilutedShare",
        "DiscontinuedOperationIncomeLossFromDiscontinuedOperationNetOfTaxPerDilutedShare"], cutoff, "USD/shares")
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
    result["observed_at"] = dt.datetime.fromtimestamp((CACHE / f"sec-{cik}.json").stat().st_mtime, UTC).isoformat() if (CACHE / f"sec-{cik}.json").exists() else None
    history_observed = max((value for value in [result["observed_at"], (recovery or {}).get("observed_at")] if value), default=None)
    result["earnings_history"] = annual_eps_history(facts, cik, cutoff, history_observed)
    result["refresh_status"] = "available"
    if recovery:
        result["original_filing_recovery"] = recovery
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
                       "report_date": (recent.get("reportDate") or [""] * len(recent["form"]))[i],
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
    index = price_distribution_index(response, rows, symbol, dt.datetime.now(UTC).isoformat())
    return {"splits": splits, "history": rows, "price": rows[-1]["close"], "price_date": rows[-1]["date"],
            "price_observed_at": index["observed_at"],
            "distribution_index": index,
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

def simple_ratio(ratio, max_denominator=10, tolerance=0.002):
    """Share splits are small integer ratios (2:1, 3:2, 5:4, 1:10)."""
    return any(round(ratio * q) >= 1 and abs(ratio * q - round(ratio * q)) <= tolerance * q
               for q in range(1, max_denominator + 1))


def classify_corporate_actions(asset, window_days=200):
    """Keep share splits; move provider 'splits' that are spin-off price
    adjustments (FedEx Freight, GE Vernova...) out of the per-share basis.

    A split must change the reported shares outstanding by its ratio. Without
    cover-page observations on both sides, only a simple ratio is accepted.
    """
    splits = asset.get("splits")
    if not isinstance(splits, list):
        return
    history = sorted((row for row in ((asset.get("financials") or {}).get("history") or [])
                      if number(row.get("shares_unadjusted")) and row.get("period_end")),
                     key=lambda row: row["period_end"])
    kept, adjustments = [], []
    for split in splits:
        ratio = number(split.get("ratio"))
        if ratio is None or ratio <= 0 or not split.get("date"):
            continue
        before = [row for row in history if row["period_end"] < split["date"]
                  and (date(split["date"]) - date(row["period_end"])).days <= window_days]
        after = [row for row in history if row["period_end"] >= split["date"]
                 and (date(row["period_end"]) - date(split["date"])).days <= window_days]
        observed = (after[0]["shares_unadjusted"] / before[-1]["shares_unadjusted"]
                    if before and after else None)
        # The observed change must match the declared ratio AND be closer to it
        # than to "no change": a 1.061 adjustment is within 10% of 1.001 too.
        is_split = (abs(observed / ratio - 1) <= 0.10 and
                    abs(math.log(observed / ratio)) < abs(math.log(observed))
                    if observed is not None and observed > 0 else simple_ratio(ratio))
        if is_split:
            kept.append(split)
        else:
            adjustments.append(dict(split, classification="price_adjustment_not_share_split",
                                    observed_share_ratio=observed))
    asset["splits"] = kept
    if adjustments:
        asset["price_adjustments"] = adjustments
    else:
        asset.pop("price_adjustments", None)


def eps_split_basis_problem(asset, cutoff):
    """Require a common post-split publication basis independently of NI."""
    eps = (asset.get("financials") or {}).get("eps")
    splits = [s for s in (asset.get("splits") or []) if s.get("date") and
              s["date"] <= cutoff and number(s.get("ratio")) not in (None, 0, 1)]
    if not eps or not splits:
        return None
    latest = max(s["date"] for s in splits)
    components = eps.get("components")
    if (not isinstance(components, list) or not components or
            any(not c.get("filed") or c["filed"] < latest for c in components)):
        return f"{asset['symbol']}: BPA sin base por acción conciliada tras el split {latest}"
    return None


def flag_inconsistent_eps(asset, cutoff):
    """Do not value an apparent pre-split or mismatched EPS as a current share."""
    facts = asset.get("financials")
    if not isinstance(facts, dict):
        return None
    eps, income, shares = (facts.get(key) for key in ("eps", "net_income", "shares"))
    if not all(isinstance(row, dict) for row in (eps, income, shares)):
        return None
    values = [number(row.get("value")) for row in (eps, income, shares)]
    if any(value is None or value <= 0 for value in values):
        return None
    eps_value, net_income, share_count = values
    ratio = eps_value * share_count / net_income
    comparable_period = (eps.get("period_end") == income.get("period_end")
                         and eps.get("method") == income.get("method"))
    recent_split = any(
        split.get("date") and
        0 <= (date(cutoff) - date(split["date"])).days <= 550 and
        number(split.get("ratio")) not in (None, 1)
        for split in asset.get("splits", [])
    )
    if not comparable_period and not recent_split:
        return None
    # Wide bounds account for dilution, buybacks and one-off income items.
    # Crossing them means raw EPS is not trustworthy enough for automation.
    if ratio < 1 / 3 or ratio > 3:
        facts["eps_unverified"] = dict(eps)
        facts["eps"] = None
        asset.setdefault("quality_flags", []).append("eps_share_income_scale_mismatch")
        return (f"{asset['symbol']}: BPA no comparable con beneficio/acciones "
                f"(ratio de conciliación {ratio:.2f}); valoración BPA bloqueada")
    return None


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
        asset.update({k: old.get(k) for k in ["history", "price", "price_date", "price_observed_at", "change", "dividend_per_share", "currency", "source_url", "distribution_index", "splits", "price_adjustments"]})
        if old.get("price_adjustments"):
            # A retained snapshot was already classified; restore the full
            # provider event list so the classification is recomputed.
            asset["splits"] = sorted((asset.get("splits") or []) + [
                {k: v for k, v in row.items() if k in ("date", "ratio")} for row in old["price_adjustments"]],
                key=lambda row: row["date"])
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
            if isinstance(old.get("earnings_history"), dict):
                asset["financials"]["earnings_history"] = dict(old["earnings_history"], through_filing_date=cutoff,
                    records=[r for r in old["earnings_history"].get("records", [])
                             if r.get("filed", "9999") <= cutoff and r.get("period_end", "9999") <= cutoff])
            asset["financials"]["observed_at"] = old.get("observed_at")
            asset["financials"]["refresh_status"] = "retained_after_failure"
            errors.append(f"{symbol}: SEC no actualizada ({error_label(exc)})")
        classify_corporate_actions(asset)
        try:
            asset["filings"] = filings(cik, cutoff)
        except Exception as exc:
            asset["filings"] = [row for row in previous.get(symbol, {}).get("filings", [])
                                if row.get("filing_date", "9999") <= cutoff]
            errors.append(f"{symbol}: presentaciones no actualizadas ({error_label(exc)})")
        reports = [r for r in asset.get("filings", []) if r.get("form") in {"10-K", "10-Q", "20-F"} and r.get("report_date")]
        latest = max(reports, key=lambda r: (r["report_date"], r["filing_date"]), default=None)
        eps = asset["financials"].get("eps") or {}
        probe = dict(asset, financials=dict(asset["financials"]), quality_flags=[])
        inconsistent = eps_split_basis_problem(asset, cutoff) or flag_inconsistent_eps(probe, cutoff)
        if latest and (not eps or inconsistent or latest["report_date"] > eps.get("period_end", "")) and asset["financials"].get("refresh_status") == "available":
            try:
                asset["financials"] = financials(cik, cutoff, original_filing=latest)
            except Exception as exc:
                asset["financials"]["original_filing_recovery"] = {"status": "failed", "source_url": latest["url"], "reason": error_label(exc)}
                errors.append(f"{symbol}: informe original sin reconciliar ({error_label(exc)})")
    else:
        asset["financials"] = None
    if cik and isinstance(asset.get("splits"),list):
        for row in (asset.get("financials") or {}).get("history",[]):
            if row["period_end"] >= asset["history"][0]["date"]:
                factor = math.prod(split["ratio"] for split in asset["splits"] if row["period_end"] < split["date"] <= cutoff)
                row["shares"] = row["shares_unadjusted"] * factor
                row["shares_split_adjusted"] = True
                row["split_source"] = asset["source_url"]
    basis_problem = eps_split_basis_problem(asset, cutoff)
    if basis_problem:
        asset["financials"]["eps_unverified"] = asset["financials"]["eps"]
        asset["financials"]["eps"] = None
        asset.setdefault("quality_flags", []).append("original_eps_split_vintage_unverified")
        errors.append(basis_problem)
    inconsistent_eps = flag_inconsistent_eps(asset, cutoff)
    if inconsistent_eps:
        errors.append(inconsistent_eps)
    if cik and isinstance(asset.get("financials", {}).get("earnings_history"), dict):
        replay = growth_replay(asset["financials"]["earnings_history"], growth)
        asset["financials"]["growth_research"] = {
            key: value for key, value in replay.items() if key != "outcomes"}
        asset["financials"]["growth_research"]["metrics"] = replay_metrics(replay["outcomes"])
        asset["financials"]["growth_research"]["outcomes"] = len(replay["outcomes"])
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


def common_price_cutoff(assets):
    """Use the modal available closing date; a single stale ETF cannot backdate everyone."""
    counts = {}
    for asset in assets:
        day = asset.get("price_date")
        if day:
            counts[day] = counts.get(day, 0) + 1
    if not counts:
        raise ValueError("No hay precios para determinar el corte")
    # A tie favors the newer common date, not a lagging benchmark or stale ETF.
    return max(counts, key=lambda day: (counts[day], day))


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
    # A transport-ready copy. The ordinary JSON remains the source of truth
    # for local tooling and the historical fallback in the browser.
    compressed = public_path.with_suffix(public_path.suffix + ".gz")
    encoded = public_path.read_bytes()
    zipped = gzip.compress(encoded, compresslevel=6, mtime=0)
    temp_gzip = compressed.with_suffix(".gz.tmp")
    temp_gzip.write_bytes(zipped)
    temp_gzip.replace(compressed)
    print(f"Mercado: {len(encoded):,} bytes JSON · {len(zipped):,} bytes gzip", flush=True)


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
    universe, warnings = resolved_universe(old_assets)
    assets, errors = [], list(warnings)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(build_asset, spec, args.as_of, old_assets): spec[0] for spec in universe}
        for future in concurrent.futures.as_completed(futures):
            asset, failed = future.result()
            errors.extend(failed)
            if asset:
                assets.append(asset)
                print(f"OK {asset['symbol']}: {asset['price_date']} · {len(asset['history'])} cierres", flush=True)
            else:
                print(f"ERROR {futures[future]}", flush=True)
    order = {spec[0]: i for i, spec in enumerate(universe)}
    assets.sort(key=lambda a: order[a["symbol"]])
    providers = []
    sec_failures = sum('SEC no actualizada' in warning or 'presentaciones no actualizadas' in warning for warning in errors)
    sec_total = sum(bool(spec[3]) for spec in universe) * 2
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
    fred_csv_count = 0
    fred_fallbacks = 0
    fred_enabled = bool(fred_key) or current_request
    if fred_enabled:
        for definition in FRED_SERIES:
            try:
                fresh = fred_observation(download, definition, args.as_of, fred_key, collected_at)
                fred_csv_count += int(fresh["vintage_mode"] == "observed_current")
                fred_fallbacks += int(fresh.get("api_fallback", False))
                current = next((row for row in macro if row["id"] == fresh["id"]), None)
                if not current or fresh["date"] >= current["date"]:
                    macro = [row for row in macro if row["id"] != fresh["id"]] + [fresh]
                fred_success += 1
            except Exception as exc:
                errors.append(f"FRED {definition[0]}: actualización fallida ({error_label(exc)})")
                if not fred_key:
                    break
    providers.append({"id": "fred", "name": "FRED", "status": "not_configured" if not fred_enabled else "ok" if fred_success == len(FRED_SERIES) and not fred_fallbacks else "partial" if fred_success else "error",
                      "detail": f"{fred_success}/{len(FRED_SERIES)} series; " + (f"{fred_success-fred_csv_count} API con versión identificada · {fred_csv_count} CSV observados hoy · {fred_fallbacks} respaldos por fallo API") if fred_enabled else "FRED_API_KEY necesaria para cortes históricos", "checked_at": collected_at})
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
                "price_as_of": common_price_cutoff(assets), "assets": assets, "macro": macro, "errors": errors, "providers": providers,
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
    # Holdings from today's *current* issuer/SEC-derived snapshots, not
    # retrospective file-date reconstruction. Failures preserve previously
    # observed constituents and never invent missing holdings.
    if current_request:
        holdings = enrich_holdings(
            assets, old_assets, snapshot["price_as_of"], collected_at,
            lambda url, cache_key: download(url, cache_key, max_age=1800),
            archive_dir=ROOT / "data" / "holdings",
        )
        providers.append({
            "id":"etf-holdings", "name":"TickerInside ETF constituents",
            "status":"ok" if holdings["downloaded"]==holdings["checked"] else
                "partial" if holdings["downloaded"] or holdings["retained"] else "error",
            "detail":f'{holdings["downloaded"]}/{holdings["checked"]} fuentes actuales; '
                     f'{holdings["retained"]} capturas originales conservadas',
            "checked_at":collected_at,
        })
        if holdings["errors"]:
            errors.append("ETF holdings: "+str(len(holdings["errors"]))+
                          " fondos sin actualización: "+
                          "; ".join(holdings["errors"][:6]))
    else:
        providers.append({"id":"etf-holdings","name":"TickerInside ETF constituents",
                          "status":"historical_request",
                          "detail":"Sin reconstrucción retrospectiva del contenido observado",
                          "checked_at":collected_at})
    snapshot["sources"].append({
        "name":"TickerInside", "kind":"Copia pública actual, CC BY 4.0",
        "url":"https://tickerinside.com/api/",
        "data":"Holdings de ETF de renta variable transcritas de emisores o SEC N-PORT, fecha original y primer acceso; atribución requerida",
    })
    snapshot["methodology"]["etf_holdings"] = (
        "Solo datos descargados en la captura original. Portafolios ETF históricos "
        "no reproducidos con datos actuales. Fuente secundaria, cobertura parcial."
    )
    if current_request:
        distributions = enrich_distributions(assets, old_assets, args.as_of, dt.datetime.now(UTC).isoformat(),
            lambda url, key: download(url, key, max_age=3600),
            archive_dir=ROOT / "data" / "distributions" / "calendars",
            clock=lambda:dt.datetime.now(UTC).isoformat())
        providers.append({"id":"distributions", "name":"iShares · distribuciones",
            "status":"ok" if not distributions["errors"] else "partial" if distributions["calendar_funds"] or distributions["histories"] else "error",
            "detail":f'{distributions["calendar_funds"]} calendarios mensuales; {distributions["histories"]}/{distributions["requested_histories"]} historiales con importes y pagos; {distributions["profiles"]} perfiles Treasury',
            "checked_at":dt.datetime.now(UTC).isoformat()})
        errors.extend("Distribuciones: "+message for message in distributions["errors"])
    snapshot["methodology"]["distributions"] = "Fechas previstas y cantidades declaradas separadas. El importe futuro no declarado es una hipótesis. El índice de ex-dates de Yahoo no confirma una fecha de pago."
    snapshot["sources"].append({"name":"iShares · calendario de distribuciones",
        "kind":"Documento del emisor", "url":"https://www.ishares.com/us/literature/shareholder-letters/isharesandblackrocketfsdistributionschedule.pdf",
        "data":"Calendario mensual publicado; importes y fechas de pago oficiales para ETF iShares con ticker y moneda comprobados"})
    snapshot["generated_at"] = dt.datetime.now(UTC).isoformat()
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
