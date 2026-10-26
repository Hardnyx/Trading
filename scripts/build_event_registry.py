"""Build event ledger from SEC filings already collected in ORIGINAL archives.

Filings have trustworthy SEC acceptance timestamps. To prevent historical
knowledge reconstruction from being mistaken for observation, 'known_at_utc'
is the LATER of SEC acceptance and the first downloaded archived snapshot.
No consensus surprises are manufactured, so these events do not yet drive
GARCH-X regressors. All previously sealed events remain unchanged.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path

try:
    from .research_gate import instant, validate_event
except ImportError:
    from research_gate import instant, validate_event


def extract_filings(archive):
    seen_at=instant(archive["collected_at"])
    if archive.get("collection_mode")!="current":
        return []
    items=[]
    for asset in archive.get("assets",[]):
        for filing in asset.get("filings",[]):
            url=filing.get("url")
            accepted=filing.get("accepted_at")
            accession=filing.get("accession")
            if not all((url,accepted,accession)) or not url.startswith("https://www.sec.gov/"):
                continue
            try:
                first_seen=max(seen_at,instant(accepted))
            except ValueError:
                continue
            items.append({
                "event_id":"SEC:"+asset["symbol"]+":"+str(accession),
                "type":"SEC:"+str(filing.get("form","filing")),
                "asset_ids":[asset["symbol"]],
                "published_at_utc":instant(accepted).isoformat(),
                "known_at_utc":first_seen.isoformat(),
                "source_url":url,
                "scope":"company_filing",
                "attribution_status":"verified_publication_no_surprise",
                "numeric_surprise_available":False,
                "first_archive":archive.get("collected_at"),
            })
    return items


def combine_archives(paths):
    events={}
    for path in sorted(paths):
        archive=json.loads(Path(path).read_text(encoding="utf-8"))
        for row in extract_filings(archive):
            if row["event_id"] not in events:
                validate_event(row)
                events[row["event_id"]]=row
    return sorted(events.values(),key=lambda row:(row["known_at_utc"],
                                                 row["event_id"]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-dir",default="data/snapshots")
    p.add_argument("--output",default="out/sec-filing-events.json")
    p.add_argument("--limit",type=int,default=15)
    args=p.parse_args()
    paths=sorted(Path(args.archive_dir).glob("*/*.json"))[-args.limit:]
    events=combine_archives(paths)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(events,indent=2,ensure_ascii=False,allow_nan=False),
                   encoding="utf-8")
    print("Sealed SEC release events",len(events),
          "numeric surprises",sum(x["numeric_surprise_available"] for x in events))


if __name__=="__main__":
    main()
