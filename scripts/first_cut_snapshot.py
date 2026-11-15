"""Engine market snapshot reconstructed as it could be known on the first cut.

Members are the SPY positions whose free price series was bound to the filed
N-PORT price; sectors come from the S&P 500 list revision in force at the cut,
fundamentals and filings from SEC records filed on or before it, macro series
from provider vintages known by it, and bond fund profiles from issuer pages
archived before it. Prices are restated in the share basis of the cut: later
splits are undone and nothing after the cut enters the history. The same
asset builder as the daily refresh is used, so the engine reads the usual
format. This is a development-period reconstruction, never a prospective
record, and no outcome after the cut is read.
"""
import argparse
import concurrent.futures
import datetime as dt
import gzip
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path

if __package__:
    from . import refresh_data
    from .history_archive import parse_sp500
    from .universe import SECTOR_PRIORS, expanded_universe
else:
    import refresh_data
    from history_archive import parse_sp500
    from universe import SECTOR_PRIORS, expanded_universe

ROOT = Path(__file__).resolve().parents[1]
CUT = "2024-12-31"
BINDING = ROOT / "data/historical/price-binding-v1/first-cut.json"
FUNDAMENTALS = ROOT / "data/historical/first-cut-fundamentals-v1/2024-12-31.json.gz"
PROVIDERS = ROOT / "data/historical/provider-inputs-v1"
PROFILES = ROOT / "data/historical/issuer-archive-v1/2024-12-31/profiles.json"
CURRENT = ROOT / "dist/data/market.json"
OUT = ROOT / "data/historical/first-cut-snapshot-v1"
WIKI = "https://en.wikipedia.org/w/api.php"
WIKI_PAGE = "List of S&P 500 companies"
MAX_SEC_FAILURE = 0.02
HISTORY_DAYS = 5 * 365 + 1  # the daily refresh asks for five years of daily prices
GICS_ES = {
    "Information Technology": "Tecnología", "Financials": "Financiero", "Health Care": "Salud",
    "Consumer Discretionary": "Consumo discrecional", "Industrials": "Industrial", "Energy": "Energía",
    "Utilities": "Servicios públicos", "Communication Services": "Comunicación", "Real Estate": "Inmobiliario",
    "Materials": "Materiales", "Consumer Staples": "Consumo básico",
}
UA = "TradingResearch/0.3 (https://github.com/Hardnyx/Trading)"


def epoch(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()


def wiki_revision(cut, opener=urllib.request.urlopen):
    """Last revision of the constituents list saved on or before the cut, and its rendered HTML."""
    query = urllib.parse.urlencode({"action": "query", "prop": "revisions", "titles": WIKI_PAGE, "rvlimit": 1,
                                    "rvstart": f"{cut}T23:59:59Z", "rvdir": "older",
                                    "rvprop": "ids|timestamp", "format": "json"})
    with opener(urllib.request.Request(f"{WIKI}?{query}", headers={"User-Agent": UA}), timeout=30) as response:
        page = next(iter(json.load(response)["query"]["pages"].values()))
    revision = page["revisions"][0]
    if revision["timestamp"][:10] > cut:
        raise ValueError("Revision after the cut")
    url = "https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"title": WIKI_PAGE, "oldid": revision["revid"]})
    with opener(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as response:
        raw = response.read()
    return {"revid": revision["revid"], "timestamp": revision["timestamp"], "url": url}, raw


def sector_index(raw):
    header, rows = parse_sp500(raw)
    at = {name: header.index(name) for name in ("symbol", "gics_sector", "cik")}
    by_cik, by_symbol = {}, {}
    for row in rows:
        sector = row[at["gics_sector"]].strip()
        cik = re.sub(r"\D", "", row[at["cik"]])
        if cik:
            by_cik[int(cik)] = sector
        by_symbol[row[at["symbol"]].strip().replace(".", "-")] = sector
    return by_cik, by_symbol


def member_specs(binding, fundamentals, by_cik, by_symbol):
    """Engine specs for price-verified members; members without a list sector stay out, reported."""
    facts = {m["cusip"]: m for m in fundamentals["members"]}
    specs, excluded = [], []
    for row in binding["positions"]:
        if row["status"] != "verified":
            continue
        member = facts.get(row["cusip"]) or {}
        cik = member.get("cik")
        gics = by_cik.get(cik) or by_symbol.get(row["symbol"])
        if not cik or gics not in GICS_ES:
            excluded.append({"symbol": row["symbol"], "cusip": row["cusip"], "weight": row["weight"],
                             "reason": "no CIK" if not cik else "no sector in the list revision"})
            continue
        sector = GICS_ES[gics]
        growth, multiple = SECTOR_PRIORS[sector]
        specs.append((row["symbol"], member.get("entity") or row.get("name"), sector, int(cik), growth, multiple))
    return specs, excluded


def fund_specs():
    return [row for row in refresh_data.ASSETS + expanded_universe() if row[3] is None]


def restate_chart(body, cut):
    """A Yahoo chart response as of `cut`, in the cut's share basis.

    Yahoo restates every close and distribution for splits after it; undo
    those, drop every row and event after the cut, and keep the provider's
    dividend adjustment ratio (a constant factor on pre-cut rows) unchanged.
    """
    result = body["chart"]["result"][0]
    events = result.get("events") or {}
    splits = events.get("splits") or {}
    later = math.prod(s["numerator"] / s["denominator"] for s in splits.values()
                      if s.get("denominator") and iso(s["date"]) > cut)
    keep = [i for i, t in enumerate(result.get("timestamp") or []) if iso(t) <= cut]
    quote = result["indicators"]["quote"][0]
    scaled = lambda values, factor: [None if values[i] is None else values[i] * factor for i in keep]
    restated = dict(result, timestamp=[result["timestamp"][i] for i in keep])
    restated["indicators"] = {
        "quote": [{key: (scaled(values, later) if key in ("open", "high", "low", "close") else
                         scaled(values, 1 / later) if key == "volume" else [values[i] for i in keep])
                   for key, values in quote.items()}],
        "adjclose": [{"adjclose": scaled(result["indicators"].get("adjclose", [{}])[0].get("adjclose", []), later)}]
        if result["indicators"].get("adjclose") else [],
    }
    restated["events"] = {
        "dividends": {k: dict(v, amount=v["amount"] * later) for k, v in (events.get("dividends") or {}).items()
                      if iso(v["date"]) <= cut},
        "splits": {k: v for k, v in splits.items() if iso(v["date"]) <= cut},
    }
    restated["meta"] = {key: value for key, value in (result.get("meta") or {}).items()
                        if key in ("currency", "symbol", "exchangeName", "instrumentType", "timezone")}
    return {"chart": {"result": [restated], "error": None}}, later


def asof_download(original, cut, factors):
    """Replace the daily refresh's five-year chart request with one ending at the cut."""
    start = (dt.date.fromisoformat(cut) - dt.timedelta(days=HISTORY_DAYS)).isoformat()

    def download(url, cache_key, max_age=0, sec=False, payload=None):
        match = re.match(r"https://query1\.finance\.yahoo\.com/v8/finance/chart/([^?]+)\?range=5y", url)
        if not match:
            return original(url, cache_key, max_age, sec, payload)
        symbol = match[1]
        # period2 runs to today only so that splits after the cut are seen and undone.
        period = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={epoch(start)}"
                  f"&period2={int(dt.datetime.now(dt.timezone.utc).timestamp())}&interval=1d&events=div%2Csplits")
        body, later = restate_chart(json.loads(original(period, f"asof-{cut}-{symbol}.json", 12 * 3600)), cut)
        factors[symbol] = later
        return json.dumps(body).encode()
    return download


def macro_vintages(cut, current):
    """Engine macro entries from provider vintages known by the cut; labels from the current entries."""
    manifest = json.loads((PROVIDERS / "manifest.json").read_text())
    templates = {m["id"]: m for m in current.get("macro", [])}
    out = []
    for series, row in sorted(manifest["macro"][cut].items()):
        if row.get("status") != "available":
            continue
        normalized = json.loads(gzip.decompress((PROVIDERS / row["path"]).read_bytes()))["normalized"]
        if normalized["known_by_day"] > cut or normalized["date"] > cut or \
                any(h["date"] > cut for h in normalized.get("history") or []):
            raise ValueError(f"{series}: vintage not known by the cut")
        template = templates.get(series, {})
        out.append({**normalized, "label": template.get("label", series), "description": template.get("description", ""),
                    "observed_at": None, "vintage_sha256": row["sha256"]})
    return out


def bond_profiles(path=PROFILES):
    """Issuer profiles archived before the cut, in the engine's bond_profile schema."""
    funds = json.loads(path.read_text())["funds"]
    out = {}
    for symbol, fund in funds.items():
        p = fund.get("profile") or {}
        duration, ytm = p.get("effective_duration_years"), p.get("yield_to_maturity")
        if fund.get("status") != "parsed" or not duration or not (ytm or p.get("real_yield")):
            continue
        dated = [x["as_of"] for x in (duration, ytm, p.get("real_yield"), p.get("sec_yield_30d")) if x and x.get("as_of")]
        profile = {"source_url": fund["archive_url"], "observed_at": None, "archived_at": fund["captured_at"],
                   "expenseRatio": (p.get("expense_ratio") or {}).get("value"),
                   "duration": duration["value"], "duration_date": duration["as_of"],
                   "date": max(dated), "source_sha256": fund["raw_sha256"]}
        if ytm:
            profile.update(yieldToMaturity=ytm["value"], yieldToMaturity_date=ytm["as_of"])
        if p.get("sec_yield_30d"):
            profile.update(secYield=p["sec_yield_30d"]["value"], secYield_date=p["sec_yield_30d"]["as_of"])
        if p.get("real_yield"):
            profile.update(inflationLinked=True, realYield=p["real_yield"]["value"], realYield_date=p["real_yield"]["as_of"])
        out[symbol] = profile
    return out


def future_leaks(asset, cut):
    """Fields of a built asset dated after the cut."""
    leaks = []
    if any(r["date"] > cut for r in asset.get("history") or []):
        leaks.append("price history")
    for row in (asset.get("financials") or {}).get("history") or []:
        if row.get("filed", "") > cut or row.get("period_end", "") > cut:
            leaks.append("financial history")
            break
    for key, value in (asset.get("financials") or {}).items():
        if isinstance(value, dict) and (value.get("filed", "") > cut or value.get("period_end", "") > cut):
            leaks.append(f"financials.{key}")
    if any(r.get("filing_date", "") > cut for r in asset.get("filings") or []):
        leaks.append("filings")
    if any(r["ex_date"] > cut for r in (asset.get("distribution_index") or {}).get("records", [])):
        leaks.append("distributions")
    return leaks


def build(specs, cut, workers=6):
    factors, errors, assets, failed = {}, [], [], []
    refresh_data.download = asof_download(refresh_data.download, cut, factors)
    refresh_data.ISSUER_URLS = {}  # today's issuer pages are not known by the cut; archived profiles go in below
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for spec, (asset, messages) in zip(specs, pool.map(lambda s: refresh_data.build_asset(s, cut, {}), specs)):
            errors += messages
            if asset is None:
                failed.append(spec[0])
                continue
            leaks = future_leaks(asset, cut)
            if leaks:
                raise ValueError(f"{spec[0]}: data after the cut in {leaks}")
            asset["later_split_factor_undone"] = factors.get(spec[0], 1.0)
            assets.append(asset)
    sec_failed = sum(a["type"] == "stock" and (a.get("financials") or {}).get("refresh_status") != "available" for a in assets)
    if sec_failed > MAX_SEC_FAILURE * max(1, sum(a["type"] == "stock" for a in assets)):
        # No earlier snapshot backs a reconstruction: missing SEC records would silently drop fundamentals.
        raise RuntimeError(f"{sec_failed} members without SEC records filed by the cut")
    return assets, errors, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default=CUT)
    parser.add_argument("--limit", type=int, default=0, help="first N members only, for a smoke run")
    parser.add_argument("--output", type=Path, default=OUT)
    options = parser.parse_args()
    revision, raw = wiki_revision(options.cut)
    by_cik, by_symbol = sector_index(raw)
    binding = json.loads(BINDING.read_text())
    fundamentals = json.loads(gzip.decompress(FUNDAMENTALS.read_bytes()))
    stocks, excluded = member_specs(binding, fundamentals, by_cik, by_symbol)
    specs = (stocks[:options.limit] if options.limit else stocks) + fund_specs()
    assets, errors, failed = build(specs, options.cut)
    current = json.loads(CURRENT.read_text())
    profiles = bond_profiles()
    for asset in assets:
        if asset["symbol"] in profiles:
            asset["bond_profile"] = profiles[asset["symbol"]]
    retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
    price_as_of = refresh_data.common_price_cutoff(assets)
    snapshot = {
        "schema_version": current["schema_version"], "generated_at": retrieved, "requested_as_of": options.cut,
        "price_as_of": price_as_of, "macro": macro_vintages(options.cut, current), "errors": errors,
        "providers": [], "sources": current.get("sources", []),
        "methodology": {**current.get("methodology", {}),
                        "universe_point_in_time": "True: SPY N-PORT positions at the cut, price-verified",
                        "financials_point_in_time": "Filed on or before the cut (current SEC records filtered by filing date)",
                        "reconstruction": "Development-period reconstruction retrieved after the cut; not a prospective record"},
        "reconstruction": {
            "schema": "first-cut-asof-snapshot-v1", "cut": options.cut, "retrieved_at": retrieved,
            "sector_source": revision, "members_requested": len(stocks), "members_excluded": excluded,
            "funds_requested": len(fund_specs()), "failed": failed,
            "bond_profiles": sorted(profiles), "price_basis": "share basis of the cut; later splits undone",
            "etf_universe": "current fund list; funds without a five-year-window series at the cut drop out",
            "outcomes_read": False, "decision_record": False,
        },
        "assets": sorted(assets, key=lambda a: (a["type"], a["symbol"])),
    }
    options.output.mkdir(parents=True, exist_ok=True)
    name = f"{options.cut}{'-smoke' if options.limit else ''}"
    (options.output / f"{name}.json.gz").write_bytes(
        gzip.compress(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(), mtime=0))
    summary = {k: snapshot["reconstruction"][k] for k in ("members_requested", "funds_requested", "failed")}
    summary.update(assets=len(assets), stocks=sum(a["type"] == "stock" for a in assets), price_as_of=price_as_of,
                   with_eps=sum(bool((a.get("financials") or {}).get("eps")) for a in assets),
                   macro=len(snapshot["macro"]), errors=len(errors), excluded=len(excluded))
    (options.output / f"{name}.summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
