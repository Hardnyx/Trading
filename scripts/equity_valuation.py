"""Dated index valuation of international equity funds from their issuer page.

The issuer's trailing P/E feeds an earnings-yield building block in the return
model; nothing here is an expected return. A fund keeps its previous dated
record when the page is unavailable, and never takes a record dated after the
cut or first observed after it.
"""
import hashlib
import math

try:
    from .bond_profiles import _Components
except ImportError:
    from bond_profiles import _Components

# URLs from the issuer's product catalog; each page is checked for ticker,
# currency and product id. Broad funds only: single-country funds would take
# high anchors from cheap markets whose discount reflects political,
# governance or currency risk, and there is no country cap yet. IWM is left
# out because the issuer's P/E excludes loss-making companies, about 40% of
# the Russell 2000; S&P 400 and 600 require profitability for inclusion.
VALUATION_URLS = {
    "EFA": "https://www.ishares.com/us/products/239623/ishares-msci-eafe-etf",
    "EEM": "https://www.ishares.com/us/products/239637/ishares-msci-emerging-markets-etf",
    "ACWX": "https://www.ishares.com/us/products/239594/ishares-msci-acwi-ex-u-s-etf",
    "IJH": "https://www.ishares.com/us/products/239763/ishares-core-s-p-mid-cap-etf",
    "IJR": "https://www.ishares.com/us/products/239774/ishares-core-s-p-small-cap-etf",
}


def _date(value):
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise ValueError("Invalid issuer date")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def parse_valuation(html, symbol, cutoff, observed_at, source_url):
    parser = _Components()
    parser.feed(html)
    product = source_url.split("/products/")[1].split("/")[0]
    identities = [c for c in parser.components if "ticker" in c and "currencyCode" in c]
    if not identities or any(c.get("ticker") != symbol or c.get("currencyCode") != "USD" or
                             str(c.get("productId")) != product for c in identities):
        raise ValueError("Issuer page identity does not match the fund")
    row, expense = None, None
    for component in parser.components:
        points = component.get("containersByNameMap", {}).get("default", {}).get("dataPointsByNameMap", {})
        if isinstance(points.get("priceEarnings"), dict):
            row = points["priceEarnings"]
        fee = component.get("feeDataPoints", {}).get("expr", {})
        if isinstance(fee, dict) and str(fee.get("formattedValue", "")).endswith("%"):
            expense = float(fee["formattedValue"].replace("%", "")) / 100
    if not row or row.get("label") != "P/E Ratio":
        raise ValueError("Issuer P/E missing or relabelled")
    pe, day = row.get("value"), _date(row.get("asOfDate"))
    if not isinstance(pe, (int, float)) or not math.isfinite(pe) or not 3 <= pe <= 80:
        raise ValueError("Invalid issuer P/E")
    if day > cutoff:
        raise ValueError("Issuer valuation is after the requested cutoff")
    if expense is None or not 0 <= expense <= .03:
        raise ValueError("Invalid issuer expense ratio")
    return {"priceEarnings": pe, "date": day, "expenseRatio": expense,
            "source_url": source_url, "observed_at": observed_at,
            "source_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest()}


def enrich_equity_valuations(assets, old_assets, cutoff, observed_at, fetch):
    found, errors = 0, []
    for asset in assets:
        symbol = asset["symbol"]
        if asset.get("type") != "etf" or symbol not in VALUATION_URLS:
            continue
        prior = old_assets.get(symbol, {}).get("equity_valuation")
        if prior and prior.get("date", "9999") <= cutoff and prior.get("observed_at", "9999") <= observed_at:
            asset["equity_valuation"] = prior
        try:
            html = fetch(VALUATION_URLS[symbol], f"valuation-{symbol}.html").decode("utf-8")
            result = parse_valuation(html, symbol, cutoff, observed_at, VALUATION_URLS[symbol])
            # Same figures and date as before: keep the first observation.
            if prior and all(prior.get(k) == result[k] for k in ("priceEarnings", "date", "expenseRatio")):
                result["observed_at"] = prior["observed_at"]
            asset["equity_valuation"] = result
            found += 1
        except Exception as exc:
            errors.append(f"{symbol}: {str(exc)[:160]}")
    return {"requested": sum(a.get("type") == "etf" and a["symbol"] in VALUATION_URLS for a in assets),
            "found": found, "errors": errors}
