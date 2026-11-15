"""Parse bond ETF characteristics from issuer pages archived before a cut.

Reads the pages stored by issuer_archive_capture.py (possibly still gzip
encoded as received) and extracts each dated characteristic block. Values
dated after the cut are rejected. Output feeds the bond_etf_profiles
component of the first-cut reconstruction; nothing is estimated.
"""
import argparse
import datetime as dt
import gzip
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEM = re.compile(r'<div class="product-data-item col-([\w]+)\s*">(.*?)<div class="data">\s*([^<]+?)\s*</div>', re.S)
CAPTION = re.compile(r'<div class="caption">\s*([^<]+?)\s*<', re.S)
AS_OF = re.compile(r'<div class="as-of-date">\s*as of\s*([^<]+?)\s*</div>', re.S)
EXPENSE = re.compile(r'Expense Ratio:\s*([0-9.]+)%')
WANTED = {"Effective Duration": "effective_duration_years", "Yield to Maturity": "yield_to_maturity",
          "Average Yield to Maturity": "yield_to_maturity", "12m Trailing Yield": "trailing_yield_12m",
          "30 Day SEC Yield": "sec_yield_30d", "Weighted Avg Maturity": "weighted_avg_maturity_years",
          "Convexity": "convexity", "Weighted Avg Coupon": "weighted_avg_coupon", "Option Adjusted Spread": "option_adjusted_spread"}


def page_text(path):
    raw = gzip.decompress(path.read_bytes())
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def number(text):
    match = re.search(r"-?[0-9]+(?:\.[0-9]+)?", text.replace(",", ""))
    if not match:
        return None
    value = float(match.group())
    return value / 100 if "%" in text else value


def parse(text, cut):
    profile, rejected = {}, []
    for key, body, value in ITEM.findall(text):
        caption = CAPTION.search(body)
        label = html.unescape(caption.group(1)).strip() if caption else None
        if label not in WANTED:
            continue
        stamp = AS_OF.search(body)
        as_of = dt.datetime.strptime(stamp.group(1).strip(), "%b %d, %Y").date().isoformat() if stamp else None
        if as_of and as_of > cut:
            rejected.append(label)
            continue
        profile.setdefault(WANTED[label], {"value": number(html.unescape(value)), "as_of": as_of, "raw": value.strip()})
    expense = EXPENSE.search(text)
    if expense:
        profile["expense_ratio"] = {"value": float(expense.group(1)) / 100, "as_of": None, "raw": expense.group(0)}
    return profile, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default="2024-12-31")
    options = parser.parse_args()
    base = ROOT / "data/historical/issuer-archive-v1" / options.cut
    manifest = json.loads((base / "manifest.json").read_text())
    funds = {}
    for capture in manifest["captures"]:
        if capture.get("status") != "archived":
            funds[capture["symbol"]] = {"status": capture.get("status")}
            continue
        profile, rejected = parse(page_text(base / capture["file"]), options.cut)
        funds[capture["symbol"]] = {"status": "parsed" if "effective_duration_years" in profile else "missing-duration",
                                    "captured_at": capture["captured_at"], "archive_url": capture["archive_url"],
                                    "raw_sha256": capture["raw_sha256"], "profile": profile, "rejected_after_cut": rejected}
    out = {"schema": "issuer-archive-bond-profiles-v1", "cut": options.cut, "funds": funds,
           "source": "issuer pages captured by the Internet Archive before the cut", "estimated_values": False}
    (base / "profiles.json").write_text(json.dumps(out, indent=1) + "\n")
    for symbol, fund in sorted(funds.items()):
        p = fund.get("profile", {})
        print(symbol, fund["status"], {k: (v["value"], v["as_of"]) for k, v in p.items() if k in ("effective_duration_years", "yield_to_maturity", "expense_ratio")})


if __name__ == "__main__":
    main()
