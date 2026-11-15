"""Archive issuer bond ETF pages as captured by the Internet Archive before a cut.

For each fund, the last capture on or before the cut (and no older than the
engine's 45-day valuation age) is downloaded in its original form (id_ mode),
compressed and hashed. The capture time is set by the Internet Archive, an
independent third party. Parsing and model use are separate steps.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from .distributions import DISTRIBUTION_URLS
except ImportError:
    from distributions import DISTRIBUTION_URLS

ROOT = Path(__file__).resolve().parents[1]
MAX_AGE_DAYS = 45
HEADERS = {"User-Agent": "research-archive-client"}


def fetch(url, timeout=60, attempts=5):
    """The archive throttles bursts with refusals and 503s: back off and retry."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as response:
                return response.read()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(20 * (attempt + 1))


def product_prefix(url):
    """iShares keeps the product number and changes the trailing slug over time."""
    parts = urllib.parse.urlparse(url)
    segments = parts.path.strip("/").split("/")
    if "products" in segments:
        keep = segments[:segments.index("products") + 2]
        return parts.netloc + "/" + "/".join(keep) + "/"
    return parts.netloc + parts.path


def last_capture(url, cut):
    """Latest HTTP-200 HTML capture of the product page on or before the cut: (timestamp, url)."""
    query = urllib.parse.urlencode({"url": product_prefix(url), "matchType": "prefix",
                                    "to": cut.replace("-", "") + "235959", "output": "json",
                                    "filter": ["statuscode:200", "mimetype:text/html"], "fl": "timestamp,original",
                                    "collapse": "digest", "limit": "-2000"}, doseq=True)
    rows = json.loads(fetch("https://web.archive.org/cdx/search/cdx?" + query) or b"[]")
    pages = [(stamp, original) for stamp, original in rows[1:]
             if "?" not in original and not original.endswith((".ajax", ".csv", ".json", ".pdf"))] if rows else []
    return max(pages) if pages else (None, None)


def capture(symbol, url, cut, out):
    stamp, original = last_capture(url, cut)
    record = {"symbol": symbol, "source_url": url, "cut": cut, "archived_url": original}
    if not stamp:
        return {**record, "status": "no-capture-before-cut"}
    taken = dt.datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    age = (dt.date.fromisoformat(cut) - taken.date()).days
    record.update(archive_timestamp=stamp, captured_at=taken.isoformat(), age_days=age)
    if age > MAX_AGE_DAYS:
        return {**record, "status": "capture-too-old"}
    raw = fetch(f"https://web.archive.org/web/{stamp}id_/{original}", timeout=120)
    # iShares serves a product by number whatever the slug; the page itself must name the fund.
    page = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw  # stored as received, checked decoded
    if not re.search(rb"\b" + symbol.encode() + rb"\b", page):
        return {**record, "status": "page-does-not-name-fund"}
    name = f"{symbol}-{stamp}.html.gz"
    (out / name).write_bytes(gzip.compress(raw, mtime=0))
    return {**record, "status": "archived", "file": name, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "archive_url": f"https://web.archive.org/web/{stamp}/{original}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cut", default="2024-12-31")
    parser.add_argument("--budget-minutes", type=float, default=40,
                        help="stop starting new funds after this; the rest are declared not attempted")
    options = parser.parse_args()
    deadline = time.monotonic() + options.budget_minutes * 60
    out = ROOT / "data/historical/issuer-archive-v1" / options.cut
    out.mkdir(parents=True, exist_ok=True)
    previous = {}
    if (out / "manifest.json").exists():
        previous = {r["symbol"]: r for r in json.loads((out / "manifest.json").read_text())["captures"]
                    if r.get("status") == "archived" and (out / r["file"]).exists()}
    rows = []
    for symbol, url in sorted(DISTRIBUTION_URLS.items()):
        if symbol in previous:  # archived captures are immutable; only missing funds are retried
            rows.append(previous[symbol])
            continue
        if time.monotonic() > deadline:
            rows.append({"symbol": symbol, "source_url": url, "status": "not-attempted-time-budget"})
            continue
        try:
            rows.append(capture(symbol, url, options.cut, out))
        except Exception as error:
            rows.append({"symbol": symbol, "source_url": url, "status": "error", "error": f"{type(error).__name__}: {str(error)[:120]}"})
        time.sleep(8)
    manifest = {"schema": "issuer-archive-capture-v1", "cut": options.cut, "max_age_days": MAX_AGE_DAYS,
                "source": "Internet Archive Wayback Machine, original-content mode", "captures": rows,
                "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({r["symbol"]: r["status"] for r in rows}, indent=1))


if __name__ == "__main__":
    main()
