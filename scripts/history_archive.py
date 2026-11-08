"""Long free histories for research, in their current revision.

Collects the longest public history each free source publishes: daily
prices, dividends and splits of the published universe (Yahoo), US rates,
credit, inflation, labour, recession and financial-conditions series (FRED),
Fama-French daily factors, Shiller's monthly market valuation, the New York
Fed yield-curve recession model and the Philadelphia Fed survey of
professional forecasters, plus the current S&P 500 constituents with their
date added.

These are current revisions downloaded now, NOT original vintages: prices
are restated by the provider after splits, macro series after revisions.
They are research inputs and never replace the point-in-time snapshot that
the engine uses. Each dataset records its source, terms, observation time,
coverage and the SHA-256 of the original bytes.

Files are yearly gzip CSV partitions written with a fixed gzip header, so an
unchanged closed year produces identical bytes and no repository change.
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import time
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "history"
UTC = dt.timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
UA = "Mozilla/5.0 (compatible; trading-research-archive)"
REVISION = "current revision downloaded at observed_at; not an original vintage"

# FRED series: id, frequency, description. Moody's spreads stand in for ICE
# BofA option-adjusted spreads, which FRED limits to three years by licence.
FRED = [
    ("DGS3MO", "daily", "Treasury 3-month constant maturity"),
    ("DGS1", "daily", "Treasury 1-year constant maturity"),
    ("DGS2", "daily", "Treasury 2-year constant maturity"),
    ("DGS5", "daily", "Treasury 5-year constant maturity"),
    ("DGS10", "daily", "Treasury 10-year constant maturity"),
    ("DGS30", "daily", "Treasury 30-year constant maturity"),
    ("T10Y3M", "daily", "10-year minus 3-month Treasury spread"),
    ("DFF", "daily", "Effective federal funds rate"),
    ("TB3MS", "monthly", "3-month Treasury bill, secondary market"),
    ("DFII10", "daily", "10-year TIPS real yield"),
    ("T10YIE", "daily", "10-year breakeven inflation"),
    ("T5YIE", "daily", "5-year breakeven inflation"),
    ("DTWEXBGS", "daily", "Nominal broad US dollar index"),
    ("DAAA", "daily", "Moody's Aaa corporate bond yield"),
    ("DBAA", "daily", "Moody's Baa corporate bond yield"),
    ("AAA10Y", "daily", "Moody's Aaa minus 10-year Treasury"),
    ("BAA10Y", "daily", "Moody's Baa minus 10-year Treasury"),
    ("VIXCLS", "daily", "CBOE volatility index"),
    ("NFCI", "weekly", "Chicago Fed national financial conditions index"),
    ("ICSA", "weekly", "Initial unemployment claims"),
    ("USREC", "monthly", "NBER recession indicator"),
    ("CPIAUCSL", "monthly", "CPI all items, seasonally adjusted"),
    ("CPILFESL", "monthly", "Core CPI, seasonally adjusted"),
    ("UNRATE", "monthly", "Unemployment rate"),
    ("PAYEMS", "monthly", "Nonfarm payrolls"),
    ("CIVPART", "monthly", "Labour force participation rate"),
    ("AHETPI", "monthly", "Average hourly earnings, production workers"),
    ("INDPRO", "monthly", "Industrial production index"),
    ("UMCSENT", "monthly", "University of Michigan consumer sentiment"),
]
FRENCH = {
    "ff5-daily": ("F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "Mkt-RF SMB HML RMW CMA RF daily, percent"),
    "momentum-daily": ("F-F_Momentum_Factor_daily_CSV.zip", "Momentum factor daily, percent"),
}
FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
SHILLER = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
NYFED = "https://www.newyorkfed.org/medialibrary/media/research/capital_markets/allmonth.xls"
SPF = ("https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/"
       "survey-of-professional-forecasters/historical-data/medianLevel.xlsx")
SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def now():
    return dt.datetime.now(UTC)


def fetch(url, attempts=3, timeout=90):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 404):
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def gzip_csv(header, rows):
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    # Fixed mtime and no filename: identical content gives identical bytes.
    return gzip.compress(text.getvalue().encode("utf-8"), compresslevel=9, mtime=0)


def write_if_changed(path, data):
    """Compare content, not bytes: zlib versions compress identical text differently."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_bytes()
        if current == data:
            return False
        if path.suffix == ".gz":
            try:
                if gzip.decompress(current) == gzip.decompress(data):
                    return False
            except (OSError, EOFError):
                pass  # an unreadable file is replaced
    path.write_bytes(data)
    return True


def write_yearly(directory, header, rows):
    """rows sorted by ISO date in column 0; one gzip CSV per calendar year."""
    years = {}
    for row in rows:
        years.setdefault(row[0][:4], []).append(row)
    changed = 0
    for year, part in years.items():
        changed += write_if_changed(directory / f"{year}.csv.gz", gzip_csv(header, part))
    stale = {p.name for p in directory.glob("*.csv.gz")} - {f"{y}.csv.gz" for y in years}
    for name in stale:  # a year the source no longer publishes
        (directory / name).unlink()
        changed += 1
    return {"files": len(years), "changed_files": changed}


def coverage(rows, dated=True):
    if not dated:
        return {"rows": len(rows)}
    return {"rows": len(rows), "first": rows[0][0] if rows else None, "last": rows[-1][0] if rows else None}


def number(value, digits=6):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return round(result, digits) if math.isfinite(result) else None


# Prices -------------------------------------------------------------------

def parse_yahoo(raw, symbol, moment):
    body = json.loads(raw)
    result = (body.get("chart") or {}).get("result")
    if not result:
        raise ValueError("no chart result")
    r = result[0]
    if (r.get("meta") or {}).get("symbol", symbol).upper() != symbol.upper():
        raise ValueError("symbol mismatch")
    if (r.get("meta") or {}).get("dataGranularity") not in (None, "1d"):
        raise ValueError("not daily data")
    quote = r["indicators"]["quote"][0]
    regular_end = (r.get("meta") or {}).get("currentTradingPeriod", {}).get("regular", {}).get("end", 0)
    today = moment.astimezone(NEW_YORK).date().isoformat()
    rows, seen = [], set()
    for i, stamp in enumerate(r.get("timestamp") or []):
        day = dt.datetime.fromtimestamp(stamp, NEW_YORK).date().isoformat()
        # A session still trading has no final close yet.
        if day > today or (day == today and moment.timestamp() < regular_end) or day in seen:
            continue
        close = number(quote["close"][i])
        if close is None or close <= 0:
            continue
        seen.add(day)
        rows.append([day, number(quote["open"][i]), number(quote["high"][i]), number(quote["low"][i]),
                     close, int(quote["volume"][i]) if quote["volume"][i] is not None else None])
    rows.sort(key=lambda row: row[0])
    events = []
    for item in ((r.get("events") or {}).get("dividends") or {}).values():
        amount = number(item.get("amount"))
        if amount is not None and amount > 0:
            events.append([dt.datetime.fromtimestamp(item["date"], NEW_YORK).date().isoformat(), "dividend", amount])
    for item in ((r.get("events") or {}).get("splits") or {}).values():
        if item.get("denominator"):
            events.append([dt.datetime.fromtimestamp(item["date"], NEW_YORK).date().isoformat(), "split",
                           number(item["numerator"] / item["denominator"], 8)])
    events.sort()
    return rows, events, (r.get("meta") or {}).get("currency")


def collect_prices(symbols, moment, pause=0.35):
    entries, errors = {}, []
    for symbol in symbols:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{symbol}?period1=0&period2=9999999999&interval=1d&events=div%2Csplits")
        try:
            raw = fetch(url)
            rows, events, currency = parse_yahoo(raw, symbol, moment)
            if len(rows) < 20:
                raise ValueError("fewer than 20 sessions")
            folder = OUT / "prices" / symbol
            written = write_yearly(folder, ["date", "open", "high", "low", "close", "volume"], rows)
            write_if_changed(folder / "events.csv.gz", gzip_csv(["date", "type", "value"], events))
            entries[symbol] = {**coverage(rows), **written, "currency": currency,
                               "dividends": sum(e[1] == "dividend" for e in events),
                               "splits": sum(e[1] == "split" for e in events), "raw_sha256": sha256(raw)}
        except Exception as error:  # one instrument never stops the archive
            errors.append(f"{symbol}: {type(error).__name__}: {str(error)[:120]}")
        time.sleep(pause)
    return entries, errors


# FRED ---------------------------------------------------------------------

def parse_fred(raw, series):
    rows = []
    reader = csv.reader(io.StringIO(raw.decode("utf-8")))
    header = next(reader)
    if len(header) != 2 or header[1] != series:
        raise ValueError("unexpected FRED header")
    for date, value in reader:
        value = number(value)
        if value is not None:
            rows.append([date[:10], value])
    rows.sort()
    return rows


def collect_fred():
    entries, errors = {}, []
    for series, frequency, description in FRED:
        try:
            raw = fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}")
            rows = parse_fred(raw, series)
            written = write_yearly(OUT / "macro" / series, ["date", "value"], rows)
            entries[series] = {**coverage(rows), **written, "frequency": frequency,
                               "description": description, "raw_sha256": sha256(raw)}
        except Exception as error:
            errors.append(f"{series}: {type(error).__name__}: {str(error)[:120]}")
    return entries, errors


# Fama-French --------------------------------------------------------------

def parse_french(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    lines = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    header, rows = None, []
    for line in lines:
        cells = [c.strip() for c in line.split(",")]
        if header is None:
            if len(cells) > 1 and cells[0] == "" and cells[1]:
                header = ["date"] + cells[1:]
            continue
        if not cells[0].isdigit() or len(cells[0]) != 8:
            if rows:
                break  # the daily block ends; later blocks are other tables
            continue
        rows.append([f"{cells[0][:4]}-{cells[0][4:6]}-{cells[0][6:]}"] + [number(c) for c in cells[1:]])
    if header is None or not rows:
        raise ValueError("no daily table")
    return header, rows


def collect_french():
    entries, errors = {}, []
    for name, (file, description) in FRENCH.items():
        try:
            raw = fetch(FRENCH_BASE + file)
            header, rows = parse_french(raw)
            written = write_yearly(OUT / "factors" / name, header, rows)
            entries[name] = {**coverage(rows), **written, "columns": header[1:],
                             "description": description, "raw_sha256": sha256(raw)}
        except Exception as error:
            errors.append(f"{name}: {type(error).__name__}: {str(error)[:120]}")
    return entries, errors


# Shiller, New York Fed and Philadelphia Fed --------------------------------

def parse_shiller(raw):
    import xlrd
    sheet = xlrd.open_workbook(file_contents=raw).sheet_by_name("Data")
    labels = [str(sheet.cell_value(7, c)).strip() for c in range(sheet.ncols)]
    want = {"P": "price", "D": "dividend", "E": "earnings", "CPI": "cpi", "Rate GS10": "gs10", "CAPE": "cape"}
    columns = {}
    for c, label in enumerate(labels):
        if label in want and want[label] not in columns.values():
            columns[c] = want[label]
    if set(columns.values()) != set(want.values()):
        raise ValueError("Shiller columns changed")
    rows = []
    for r in range(8, sheet.nrows):
        stamp = sheet.cell_value(r, 0)
        if not isinstance(stamp, float):
            continue
        year, month = int(stamp), int(round((stamp - int(stamp)) * 100))
        if not 1 <= month <= 12:
            continue
        rows.append([f"{year:04d}-{month:02d}-01"] + [number(sheet.cell_value(r, c)) for c in columns])
    return ["date"] + list(columns.values()), rows


def parse_nyfed(raw):
    import xlrd
    book = xlrd.open_workbook(file_contents=raw)
    sheet = book.sheet_by_index(0)
    labels = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    index = {name: labels.index(name) for name in ("Date", "Spread", "Rec_prob", "NBER_Rec")}
    rows = []
    for r in range(1, sheet.nrows):
        serial = sheet.cell_value(r, index["Date"])
        if not isinstance(serial, float):
            continue
        day = xlrd.xldate_as_datetime(serial, book.datemode).date().isoformat()
        rows.append([day, number(sheet.cell_value(r, index["Spread"])),
                     number(sheet.cell_value(r, index["Rec_prob"])), number(sheet.cell_value(r, index["NBER_Rec"]))])
    return ["date", "spread_10y_3m", "recession_probability_12m", "nber_recession"], rows


def parse_spf(raw):
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    sheets = {}
    for name in book.sheetnames:
        values = list(book[name].iter_rows(values_only=True))
        header = [str(v) for v in values[0]]
        if header[:2] != ["YEAR", "QUARTER"]:
            raise ValueError(f"SPF sheet {name} changed")
        rows = []
        for row in values[1:]:
            if row[0] is None or row[1] is None:
                continue
            rows.append([f"{int(row[0])}Q{int(row[1])}"] + [number(v, 6) if v != "#N/A" else None for v in row[2:]])
        sheets[name] = (["survey"] + header[2:], rows)
    return sheets


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.depth, self.row, self.cell = {}, 0, None, None
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.current = self.tables.setdefault(attrs.get("id") or f"table{len(self.tables)}", [])
        elif tag == "tr" and self.depth == 1:
            self.row = []
        elif tag in ("td", "th") and self.row is not None and self.depth == 1:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.current.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_sp500(raw):
    parser = _Tables()
    parser.feed(raw.decode("utf-8"))
    table = parser.tables.get("constituents")
    if not table or table[0][:2] != ["Symbol", "Security"]:
        raise ValueError("constituents table changed")
    header = table[0]
    at = {name: header.index(name) for name in ("Symbol", "Security", "GICS Sector", "Date added", "CIK")}
    rows = [[r[at["Symbol"]], r[at["Security"]], r[at["GICS Sector"]], r[at["Date added"]], r[at["CIK"]]]
            for r in table[1:] if len(r) >= len(header)]
    if len(rows) < 450:
        raise ValueError("too few constituents")
    return ["symbol", "security", "gics_sector", "date_added", "cik"], sorted(rows)


def collect_single(name, url, parser, folder, yearly):
    raw = fetch(url)
    header, rows = parser(raw)
    target = OUT / folder
    if yearly:
        written = write_yearly(target, header, rows)
    else:
        written = {"files": 1, "changed_files": int(write_if_changed(target.with_suffix(".csv.gz"), gzip_csv(header, rows)))}
    return {name: {**coverage(rows, dated=header[0] == "date"), **written, "columns": header[1:], "raw_sha256": sha256(raw)}}


def collect_spf():
    raw = fetch(SPF)
    entries = {}
    for name, (header, rows) in parse_spf(raw).items():
        changed = write_if_changed(OUT / "consensus" / "spf-median-level" / f"{name}.csv.gz", gzip_csv(header, rows))
        entries[name] = {"rows": len(rows), "first": rows[0][0] if rows else None,
                         "last": rows[-1][0] if rows else None, "changed_files": int(changed)}
    return entries, sha256(raw)


SOURCES = {
    "prices": {"source": "Yahoo Finance chart API (unofficial)", "terms": "Unofficial endpoint; personal research use; restated after splits",
               "layout": "prices/<SYMBOL>/<YEAR>.csv.gz (split-adjusted OHLC, volume) and events.csv.gz (dividends, splits)"},
    "macro": {"source": "FRED, Federal Reserve Bank of St. Louis", "terms": "Public series; cite FRED and the original source",
              "layout": "macro/<SERIES>/<YEAR>.csv.gz"},
    "factors": {"source": "Kenneth R. French Data Library (CRSP-based)", "terms": "Free for research; cite Fama and French",
                "layout": "factors/<NAME>/<YEAR>.csv.gz, percent"},
    "valuation": {"source": "Robert J. Shiller, ie_data.xls", "terms": "Public academic dataset; cite Shiller",
                  "layout": "valuation/shiller-monthly.csv.gz; recent months contain Shiller's own estimates",
                  "note": "The public file ends where Shiller last updated it; it is not extended here."},
    "recession_model": {"source": "Federal Reserve Bank of New York, yield-curve recession model", "terms": "Public; model probabilities, not observations",
                        "layout": "recession/nyfed-yield-curve.csv.gz",
                        "note": "Rows dated up to 12 months after the last spread hold the model's forecast for that month."},
    "consensus": {"source": "Federal Reserve Bank of Philadelphia, Survey of Professional Forecasters, median of levels",
                  "terms": "Public; quarterly survey medians as published, by survey quarter",
                  "layout": "consensus/spf-median-level/<VARIABLE>.csv.gz"},
    "universe": {"source": "Wikipedia, List of S&P 500 companies (secondary)", "terms": "CC BY-SA; secondary source, current members only",
                 "layout": "universe/sp500-constituents.csv.gz; survivors only, no removed companies"},
}


LABELS = {
    "prices": "Precios diarios, dividendos y splits",
    "macro": "Tasas, crédito, inflación, empleo y condiciones financieras",
    "factors": "Factores Fama-French diarios",
    "valuation": "Valuación de largo plazo del S&P (Shiller)",
    "recession_model": "Modelo de recesión por curva (Fed de Nueva York)",
    "consensus": "Consenso de pronosticadores (Fed de Filadelfia)",
    "universe": "Constituyentes actuales del S&P 500",
}


def inventory(manifest):
    """Compact public summary for the page; the archive itself stays in data/history."""
    rows = []
    order = list(LABELS) + sorted(set(manifest["datasets"]) - set(LABELS))
    for name in [n for n in order if n in manifest["datasets"]]:
        data = manifest["datasets"][name]
        entries = data.get("entries", {})
        firsts = [e["first"] for e in entries.values() if e.get("first")]
        lasts = [e["last"] for e in entries.values() if e.get("last")]
        row = {"id": name, "label": LABELS.get(name, name), "source": data["source"], "terms": data["terms"],
               "observed_at": data.get("observed_at"), "series": len(entries),
               "observations": sum(e.get("rows", 0) for e in entries.values()),
               "first": min(firsts) if firsts else None, "last": max(lasts) if lasts else None,
               "errors": len(data.get("errors", [])), "note": data.get("note")}
        if name == "prices":
            starts = sorted((e["first"], symbol) for symbol, e in entries.items())
            row.update({"dividends": sum(e.get("dividends", 0) for e in entries.values()),
                        "splits": sum(e.get("splits", 0) for e in entries.values()),
                        "before_1990": sum(first < "1990-01-01" for first, _ in starts),
                        "latest_start": starts[-1][0] if starts else None})
        if name == "macro":
            row["catalog"] = [{"id": k, "description": e.get("description"), "frequency": e.get("frequency"),
                               "first": e.get("first"), "last": e.get("last")} for k, e in entries.items()]
        rows.append(row)
    return {"schema_version": 1, "revision": manifest["revision"], "purpose": manifest["purpose"],
            "location": "data/history in the repository", "datasets": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=sorted(SOURCES), help="Datasets to refresh")
    args = parser.parse_args()
    wanted = set(args.only or SOURCES)
    moment = now()
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"datasets": {}}
    manifest.update({"schema_version": 1, "revision": REVISION,
                     "purpose": "Research history in its current revision; never an input of the point-in-time engine snapshot."})
    errors = []

    def record(name, entries, errs, extra=None):
        if entries or name not in manifest["datasets"]:
            manifest["datasets"][name] = {**SOURCES[name], **(extra or {}), "observed_at": moment.isoformat(),
                                          "entries": entries, "errors": errs}
        else:  # a failed refresh keeps the previous record and says so
            manifest["datasets"][name]["errors"] = errs
            manifest["datasets"][name]["last_failed_at"] = moment.isoformat()
        errors.extend(f"{name}: {e}" for e in errs)

    if "prices" in wanted:
        market = json.loads((ROOT / "dist" / "data" / "market.json").read_text())
        symbols = sorted(a["symbol"] for a in market["assets"] if a.get("type") in ("stock", "etf"))
        record("prices", *collect_prices(symbols, moment))
    if "macro" in wanted:
        record("macro", *collect_fred())
    if "factors" in wanted:
        record("factors", *collect_french())
    for name, url, parse, folder, yearly in [
        ("valuation", SHILLER, parse_shiller, "valuation/shiller-monthly", False),
        ("recession_model", NYFED, parse_nyfed, "recession/nyfed-yield-curve", False),
        ("universe", SP500, parse_sp500, "universe/sp500-constituents", False),
    ]:
        if name in wanted:
            try:
                record(name, collect_single(name, url, parse, folder, yearly), [])
            except Exception as error:
                record(name, {}, [f"{type(error).__name__}: {str(error)[:160]}"])
    if "consensus" in wanted:
        try:
            entries, raw_hash = collect_spf()
            record("consensus", entries, [], {"raw_sha256": raw_hash})
        except Exception as error:
            record("consensus", {}, [f"{type(error).__name__}: {str(error)[:160]}"])
    manifest["datasets"] = dict(sorted(manifest["datasets"].items()))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=False) + "\n")
    (ROOT / "dist" / "data" / "history-inventory.json").write_text(
        json.dumps(inventory(manifest), ensure_ascii=False, separators=(",", ":")) + "\n")
    for name, data in manifest["datasets"].items():
        print(f"{name}: {len(data.get('entries', {}))} series, {len(data.get('errors', []))} errors")
    for error in errors[:30]:
        print("AVISO", error)


if __name__ == "__main__":
    main()
