"""Issuer distribution facts and planned dates; no invented future amounts."""
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import re

if __package__:
    from .bond_profiles import ISSUER_URLS, _Components, parse_profile
else:
    from bond_profiles import ISSUER_URLS, _Components, parse_profile

SCHEDULE_URL = "https://www.ishares.com/us/literature/shareholder-letters/isharesandblackrocketfsdistributionschedule.pdf"
UTC = dt.timezone.utc
# Distribution support is independent of the smaller set of calibrated bond
# profiles. Adding a payment source does not promote duration/yield estimates.
DISTRIBUTION_URLS = {
    **ISSUER_URLS,
    "AGG": "https://www.ishares.com/us/products/239458/ishares-core-us-aggregate-bond-etf",
    "IEF": "https://www.ishares.com/us/products/239456/ishares-7-10-year-treasury-bond-etf",
    "IEI": "https://www.ishares.com/us/products/239455/ishares-3-7-year-treasury-bond-etf",
    "SGOV": "https://www.ishares.com/us/products/314116/ishares-0-3-month-treasury-bond-etf",
    "SHV": "https://www.ishares.com/us/products/239466/ishares-01-year-treasury-bond-etf",
    "TIP": "https://www.ishares.com/us/products/239467/ishares-tips-bond-etf",
    "LQD": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf",
    "HYG": "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf",
    "EMB": "https://www.ishares.com/us/products/239572/ishares-jp-morgan-usd-emerging-markets-bond-etf",
    "IGSB": "https://www.ishares.com/us/products/239451/ishares-1-5-year-investment-grade-corporate-bond-etf",
}


# Funds whose dated yield/duration profile feeds a return model. Credit funds
# use the credit conventions in research-model.mjs on top of the profile.
PROFILE_FUNDS = {"SHY", "TLT", "IEF", "IEI", "SGOV", "SHV", "AGG", "LQD", "IGSB", "HYG", "EMB", "TIP"}


def _date(value):
    return dt.datetime.strptime(str(value), "%Y%m%d").date().isoformat()


def parse_issuer_history(html, symbol, observed_at, previous=None):
    parser = _Components()
    parser.feed(html)
    identities = [c for c in parser.components if "ticker" in c and "currencyCode" in c]
    product_id = DISTRIBUTION_URLS[symbol].split("/products/")[1].split("/")[0]
    if not identities or any(c.get("ticker") != symbol or c.get("currencyCode") != "USD" or
                             str(c.get("productId")) != product_id for c in identities):
        raise ValueError("Issuer fund identity or currency mismatch")
    tables = [c["distributionTableData"] for c in parser.components
              if isinstance(c.get("distributionTableData"), list)]
    if len(tables) != 1:
        raise ValueError("Issuer distribution table missing or ambiguous")
    columns = {c["name"]: c for c in tables[0]}
    labels = {"recordDate": "Record Date", "exDate": "Ex-Date",
              "payableDate": "Payable Date", "totalDistribution": "Total Distribution"}
    for key, label in labels.items():
        if columns.get(key, {}).get("label") != label:
            raise ValueError("Issuer distribution column changed: " + key)
    count = len(columns["exDate"].get("value", []))
    if not count or any(len(columns[k].get("value", [])) != count for k in labels):
        raise ValueError("Incomplete issuer distribution columns")
    old = {r["ex_date"]: r for r in (previous or {}).get("records", [])
           if isinstance(r.get("observed_at"), str) and r["observed_at"] <= observed_at}
    rows = []
    seen = set()
    for i in range(count):
        ex = _date(columns["exDate"]["value"][i])
        record = _date(columns["recordDate"]["value"][i])
        pay = _date(columns["payableDate"]["value"][i])
        amount = float(columns["totalDistribution"]["value"][i])
        if ex in seen or pay < ex or record < ex or not math.isfinite(amount) or amount < 0:
            raise ValueError("Invalid issuer distribution dates or amount")
        seen.add(ex)
        row = {"ex_date": ex, "record_date": record, "pay_date": pay,
               "amount_per_share": amount, "currency": "USD", "observed_at": observed_at}
        prior = old.get(ex)
        if prior and all(prior.get(k) == row[k] for k in row if k != "observed_at"):
            row["observed_at"] = prior["observed_at"]
        rows.append(row)
    rows.sort(key=lambda r: r["ex_date"])
    return {"symbol": symbol, "currency": "USD",
            "source_url": DISTRIBUTION_URLS[symbol], "source_layer": "issuer",
            "observed_at": observed_at, "source_sha256": hashlib.sha256(html.encode()).hexdigest(),
            "records": rows, "basis": "issuer-reported-per-share"}


def parse_monthly_schedule(pdf_bytes, symbols, observed_at):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    candidates = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if "MONTHLY DISTRIBUTION" in text and "AGG iShares Core U.S. Aggregate Bond ETF" in text:
            candidates.append(text)
    if len(candidates) != 1:
        raise ValueError("Monthly issuer calendar layout changed")
    text = candidates[0]
    first_fund = text.index("AGG iShares Core U.S. Aggregate Bond ETF")
    next_table = text.find("DECLARATION DATE:", first_fund)
    fund_text = text[first_fund:next_table if next_table >= 0 else len(text)]
    matched = sorted(s for s in symbols if re.search(r"\b" + re.escape(s) + r"\s+iShares\b", fund_text))
    if not matched:
        raise ValueError("No requested fund verified in monthly calendar")
    published = re.search(r"\b([A-Z][a-z]+ \d{1,2}, 20\d\d)\b", text)
    if not published:
        raise ValueError("Issuer calendar publication date missing")
    published_on = dt.datetime.strptime(published[1], "%B %d, %Y").date().isoformat()
    if published_on > observed_at[:10]:
        raise ValueError("Calendar published after observation")
    triples = []
    pending = {}
    for line in text[:first_fund].splitlines():
        for label, key in [("DECLARATION DATE:", "declaration_date"),
                           ("EX-DATE/RECORD DATE:", "ex_date"), ("PAY DATE:", "pay_date")]:
            if line.strip().startswith(label):
                tokens = re.findall(r"\b\d{1,2}-[A-Za-z]{3}-\d{2}\b", line)
                if not tokens or key in pending:
                    raise ValueError("Issuer calendar row changed")
                pending[key] = [dt.datetime.strptime(t, "%d-%b-%y").date().isoformat() for t in tokens]
                if key == "pay_date":
                    if set(pending) != {"declaration_date", "ex_date", "pay_date"} or len({len(v) for v in pending.values()}) != 1:
                        raise ValueError("Misaligned calendar columns")
                    for j in range(len(pending[key])):
                        row = {k: v[j] for k, v in pending.items()}
                        if not row["declaration_date"] <= row["ex_date"] <= row["pay_date"]:
                            raise ValueError("Calendar chronology changed")
                        # The extra year-end column is explicitly conditional.
                        row["conditional"] = row["ex_date"][5:7] == "12" and int(row["ex_date"][-2:]) >= 29
                        row["amount_per_share"] = None
                        triples.append(row)
                    pending = {}
    if pending or len(triples) < 12 or len({r["ex_date"] for r in triples}) != len(triples):
        raise ValueError("Incomplete or duplicated calendar")
    triples.sort(key=lambda r: r["ex_date"])
    return {"source_url": SCHEDULE_URL, "source_layer": "issuer-planned-calendar",
            "source_sha256": hashlib.sha256(pdf_bytes).hexdigest(), "published_on": published_on,
            "observed_at": observed_at, "symbols": matched, "frequency": 12,
            "coverage_start": triples[0]["ex_date"], "coverage_end": triples[-1]["pay_date"],
            "records": triples}


def price_distribution_index(response, history, symbol, observed_at):
    records = []
    for row in response.get("events", {}).get("dividends", {}).values():
        amount = float(row["amount"])
        day = dt.datetime.fromtimestamp(row["date"], UTC).date().isoformat()
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("Invalid quoted distribution amount")
        if history[0]["date"] <= day <= history[-1]["date"]:
            records.append({"ex_date": day, "amount_per_share": amount})
    records.sort(key=lambda r: r["ex_date"])
    if len({r["ex_date"] for r in records}) != len(records):
        raise ValueError("Duplicate quoted distribution date")
    return {"source_url": f"https://finance.yahoo.com/quote/{symbol}/history/",
            "observed_at": observed_at, "coverage_start": history[0]["date"],
            "coverage_end": history[-1]["date"], "complete_ex_date_index": True,
            "currency": response.get("meta", {}).get("currency"), "records": records}


def enrich_distributions(assets, old_assets, cutoff, observed_at, fetch, archive_dir=None, clock=None):
    received_at = clock or (lambda: observed_at)
    errors = []
    histories = 0
    profiles = 0
    requested = sum(a.get("type") == "etf" and a["symbol"] in DISTRIBUTION_URLS for a in assets)
    calendar = None
    try:
        raw = fetch(SCHEDULE_URL, "ishares-distribution-calendar.pdf")
        if len(raw) > 5_000_000:
            raise ValueError("Issuer calendar exceeds size limit")
        calendar = parse_monthly_schedule(raw, [a["symbol"] for a in assets if a.get("type") == "etf"], received_at())
        previous = next((a.get("distribution_calendar") for a in old_assets.values()
                         if a.get("distribution_calendar", {}).get("source_sha256") == calendar["source_sha256"]), None)
        if previous:
            calendar["observed_at"] = previous["observed_at"]
        if archive_dir:
            dest = Path(archive_dir) / (calendar["source_sha256"] + ".json")
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(calendar, ensure_ascii=False, indent=2) + "\n")
    except Exception as exc:
        errors.append("calendar: " + str(exc)[:160])
    for asset in assets:
        symbol = asset["symbol"]
        old = old_assets.get(symbol, {})
        prior = old.get("distribution_calendar")
        if prior and prior.get("observed_at", "9999") <= observed_at:
            asset["distribution_calendar"] = prior
        if calendar and symbol in calendar["symbols"]:
            asset["distribution_calendar"] = {k: v for k, v in calendar.items() if k != "symbols"}
        if asset.get("type") != "etf" or symbol not in DISTRIBUTION_URLS:
            continue
        previous = old.get("issuer_distributions")
        if previous:
            asset["issuer_distributions"] = previous
        prior_profile = old.get("bond_profile")
        if (symbol in PROFILE_FUNDS and prior_profile
                and prior_profile.get("date", "9999") <= cutoff
                and prior_profile.get("observed_at", "9999") <= observed_at):
            asset["bond_profile"] = prior_profile
        try:
            html = fetch(DISTRIBUTION_URLS[symbol], f"issuer-{symbol}.html").decode("utf-8")
            result = parse_issuer_history(html, symbol, received_at(), previous)
            if archive_dir:
                dest = Path(archive_dir).parent / "histories" / symbol / (result["source_sha256"] + ".json")
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            asset["issuer_distributions"] = result
            histories += 1
            # Treasury, credit (investment grade, high yield, EM sovereign) and
            # inflation-linked profiles; each has its return model in research-model.
            if symbol in PROFILE_FUNDS:
                try:
                    asset["bond_profile"] = parse_profile(html, symbol, cutoff, received_at(),
                        source_url=DISTRIBUTION_URLS[symbol])
                    asset["bond_profile"]["source_sha256"] = result["source_sha256"]
                    profiles += 1
                except Exception as exc:
                    errors.append(symbol + " profile: " + str(exc)[:160])
        except Exception as exc:
            errors.append(symbol + ": " + str(exc)[:160])
    return {"calendar_funds": len(calendar["symbols"]) if calendar else 0,
            "histories": histories, "profiles": profiles, "requested_histories": requested, "errors": errors}
