"""Produce a factual readiness report; never label retrospective replay as backtest."""
from __future__ import annotations
import argparse
from datetime import timedelta
import json
from pathlib import Path

if __package__:
    from .research_gate import audit_archives, instant, maturation_status
else:
    from research_gate import audit_archives, instant, maturation_status


def readiness(archive_files, journal=None):
    result={"model":"research-evidence-gates-v1","not_promoted":True,
            "requirements":{
                "source_original_vintage":"must exist before forecast issue",
                "financials":"SEC filed timestamp and original collection",
                "consensus":"original pre-release observation required",
                "macro":"no later/revised series in historical forecasts",
                "universe":"survivorship-free membership still unavailable",
                "returns":"prospective mature and point-in-time 12-month forecasts",
                "risk":"independent tail coverage and decision utility tests",
                "news":"verified publication, ex-ante surprise and OOS GARCH-X uplift",
            }}
    records=audit_archives(archive_files)
    result["archives"]=records
    result["forecast_journal"]={"provided":bool(journal),
                                "mature":0,"immature":0,
                                "invalid":0}
    if journal:
        last=records["results"][-1]["collected_at"][:10] if records["results"] else None
        for row in journal:
            issued=row.get("origin",{}).get("created_at")
            target=row.get("target_date")
            if not issued or not target or not last:
                status="unverified_origin"
            else:
                status=maturation_status(issued,target,last,
                        original_archive=bool(row.get("origin",{}).get("prospective")))
            if status=="eligible_for_outcome_matching":
                result["forecast_journal"]["mature"]+=1
            elif status=="immature":
                result["forecast_journal"]["immature"]+=1
            else:result["forecast_journal"]["invalid"]+=1
    result["decision"]="NOT_PROMOTED"
    result["reason"]=[
        "No independent point-in-time forward return and portfolio utility record is certified",
        "Historical archives are only valid after original collection, not retroactive to price date",
        "No multiple-testing-corrected GARCH-X or joint-tail calibration is deployed",
    ]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-dir",default="data/snapshots")
    p.add_argument("--journal",default="")
    p.add_argument("--output",default="out/research-readiness.json")
    p.add_argument("--limit",type=int,default=15)
    args=p.parse_args()
    paths=sorted(Path(args.archive_dir).glob("*/*.json"))[-args.limit:]
    records=json.loads(Path(args.journal).read_text(encoding="utf-8")) if args.journal else None
    if records is not None and not isinstance(records,list):
        raise ValueError("Journal must be an array")
    result=readiness(paths,records)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),
                      encoding="utf-8")
    print("Evidence gates:",result["decision"],"archives",len(paths),
          "mature 12-month forecasts",result["forecast_journal"]["mature"])


if __name__=="__main__":
    main()
