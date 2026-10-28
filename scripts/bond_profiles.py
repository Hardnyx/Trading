"""Dated issuer bond characteristics. No convexity inference from unknown units."""
import datetime as dt
import json
import math
from html.parser import HTMLParser

ISSUER_URLS = {
    "SHY": "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf",
    "TLT": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
}

class _Components(HTMLParser):
    def __init__(self):
        super().__init__()
        self.components = []

    def handle_starttag(self, tag, attrs):
        if tag == "walrus-render-on-client":
            raw = dict(attrs).get("componentprops")
            if raw:
                try:
                    self.components.append(json.loads(raw))
                except (ValueError, TypeError):
                    pass

# Inflation-linked funds publish a real yield; their nominal return adds the
# inflation expected at the cut (breakeven), applied in the return model.
INFLATION_LINKED = {"TIP"}


def parse_profile(html, symbol, cutoff, observed_at, *, source_url=None):
    parser = _Components()
    parser.feed(html)
    points, expense = {}, None
    inflation = symbol in INFLATION_LINKED
    for component in parser.components:
        container = component.get("containersByNameMap", {}).get("default", {})
        for key, row in container.get("dataPointsByNameMap", {}).items():
            if key in {"modelOad", "fxHedgedYield", "realYield", "thirtyDaySecYield"} and isinstance(row, dict):
                points[key] = row
        fee = component.get("feeDataPoints", {}).get("expr", {})
        if isinstance(fee, dict) and fee.get("formattedValue", "").endswith("%"):
            expense = float(fee["formattedValue"].replace("%", "")) / 100
    result = {"source_url": source_url or ISSUER_URLS[symbol], "observed_at": observed_at, "expenseRatio": expense}
    if inflation:
        result["inflationLinked"] = True
    dates = []
    for source, target, scale, label in [
        ("modelOad", "duration", 1, "Effective Duration"),
        ("realYield", "realYield", .01, "Real Yield") if inflation else
        ("fxHedgedYield", "yieldToMaturity", .01, "Average Yield to Maturity"),
        ("thirtyDaySecYield", "secYield", .01, "30 Day SEC Yield"),
    ]:
        row = points.get(source, {})
        if row and row.get("label") != label:
            raise ValueError(f"Issuer label changed for {source}")
        value = row.get("value")
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            if target == "secYield":
                continue
            raise ValueError(f"Missing issuer characteristic: {target}")
        # Field identifiers and visible labels are both preserved for review.
        day = dt.datetime.strptime(str(row.get("asOfDate")), "%Y%m%d").date().isoformat()
        if day > cutoff:
            raise ValueError("Issuer observation is after the requested cutoff")
        result[target] = value * scale
        result[target + "_date"] = day
        dates.append(day)
    rate = result["realYield"] if inflation else result["yieldToMaturity"]
    if expense is None or not 0 <= expense <= .1 or not 0 <= result["duration"] <= 40 or not -.05 <= rate <= 1:
        raise ValueError("Invalid issuer bond profile")
    result["date"] = min(dates)
    return result
