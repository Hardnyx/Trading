"""H2 calendar inventory: every registered cut has an audited snapshot or an explicit exclusion.

For each of the protocol's cuts it reports the SPY holdings source status,
whether a reconstructed snapshot and its input audit exist and pass, and the
reason for any gap. A cut excluded for a stale SPY source keeps that reason;
no rule is relaxed to fill the calendar. Reads no outcome after any cut.
"""
import argparse
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = "data/historical/identifier-observations-v1/observations.json.gz"
MANIFEST = "data/historical/provider-inputs-v1/manifest.json"
OUT = "data/historical/full-engine-input-audit-v1/calendar.json"


def report_path(root, cut):
    base = root / "data/historical/full-engine-input-audit-v1"
    return base / ("report.json" if cut == "2024-12-31" else f"report-{cut}.json")


def inventory(root=ROOT):
    cuts = json.loads((root / MANIFEST).read_text())["cuts"]
    matrix = {r["cut"]: r for r in json.loads(gzip.decompress((root / OBSERVATIONS).read_bytes()))["matrix"]}
    rows = []
    for cut in cuts:
        source = matrix[cut]["spy_source"]
        row = {"cut": cut, "spy_accession": source.get("accession"), "spy_as_of": source.get("as_of"),
               "spy_age_days": source.get("age_days"), "spy_source_status": source.get("status")}
        report = report_path(root, cut)
        if source.get("status") != "source-available" or not matrix[cut]["positions"]:
            row.update(status="excluded", reason="stale or invalid SPY holdings source under the registered rule")
        elif not report.exists():
            row.update(status="pending", reason="fresh source; reconstruction not yet run")
        else:
            audit = json.loads(report.read_text())
            failed = sorted(k for k, v in audit["checks"].items() if not v["passed"])
            universe = audit["checks"]["universe"]
            row.update(status="audited-pass" if audit["input_checks_passed"] else "audited-blocked",
                       failed_checks=failed, members=universe["members"],
                       spy_weight_covered=universe["spy_weight_covered"],
                       spy_weight_with_ttm_eps=universe["spy_weight_with_ttm_eps"],
                       snapshot_sha256=audit["snapshot_sha256"])
        rows.append(row)
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"schema": "historical-cut-calendar-v1", "cuts": len(rows), "counts": counts,
            "every_cut_accounted": all(r["status"] != "pending" for r in rows), "rows": rows,
            "development_period_only": True, "outcomes_read": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    result = inventory()
    path = ROOT / OUT
    if options.verify:
        if json.loads(path.read_text()) != result:
            raise SystemExit("Calendar inventory is out of date; rerun scripts/historical_cut_inventory.py")
        print("calendar inventory reproduced:", result["counts"])
        return
    path.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
