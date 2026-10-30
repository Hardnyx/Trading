"""Verify archived source bytes and expose the remaining full-replay blockers."""
from datetime import datetime, timezone
import argparse
import base64
import gzip
import json
from pathlib import Path
import subprocess

if __package__:
    from .historical_sources import (ROOT, MARKET_COMMIT, PROTOCOL, SERIES, account_origins,
        canonical, parse_nport, select_holdings, sha, source_path, validate_macro_record)
else:
    from historical_sources import (ROOT, MARKET_COMMIT, PROTOCOL, SERIES, account_origins,
        canonical, parse_nport, select_holdings, sha, source_path, validate_macro_record)


def read_record(root, pointer):
    raw=source_path(root,pointer["path"]).read_bytes()
    if sha(raw)!=pointer["sha256"]:
        raise ValueError("Compressed source hash mismatch")
    record=json.loads(gzip.decompress(raw))
    body=base64.b64decode(record["raw_base64"],validate=True)
    if sha(body)!=record["raw_sha256"] or record["raw_sha256"]!=pointer["raw_sha256"]:
        raise ValueError("Original source hash mismatch")
    return record,body


def audit_sources(root, cuts, definitions=SERIES):
    root=Path(root);manifest=json.loads((root/"manifest.json").read_text())
    if manifest.get("protocol")!=PROTOCOL or manifest.get("cuts")!=cuts:
        raise ValueError("Historical review calendar or source protocol mismatch")
    errors=[];matrix=[];verified=0;sec_records=[]
    for pointer in manifest.get("sec",{}).get("documents",[]):
        if not pointer.get("form","").startswith("NPORT") or not pointer.get("path"):continue
        try:
            record,body=read_record(root,pointer)
            filing=record["filing"]
            if filing["accessionNumber"]!=pointer["accession"]:
                raise ValueError("SEC accession mismatch")
            normalized=parse_nport(body,filing)
            if normalized!=pointer["normalized"]:
                raise ValueError("Holdings do not match the original source")
            sec_records.append({"accession":pointer["accession"],"normalized":normalized})
        except Exception as error:
            errors.append({"source":"SEC","accession":pointer.get("accession"),"kind":type(error).__name__})
    for cut in cuts:
        available=[];missing=[]
        for definition in definitions:
            target=definition[0]
            pointer=manifest.get("macro",{}).get(cut,{}).get(target,{})
            try:
                record,_=read_record(root,pointer)
                validate_macro_record(record,definition,cut)
                available.append(target);verified+=1
            except Exception as error:
                missing.append(target)
                errors.append({"source":"ALFRED","cut":cut,"series":target,"kind":type(error).__name__})
        holdings=select_holdings(sec_records,cut)
        matrix.append({"cut":cut,"macro_verified":len(available),"macro_expected":len(definitions),
                       "macro_missing":missing,"spy_holdings_source":holdings,
                       "bond_profiles":"missing-original-history","financial_quality":"incomplete-history",
                       "historical_universe":"unverified","full_replay_ready":False})
    return {"protocol":"historical-source-readiness-v1","audited_at":datetime.now(timezone.utc).isoformat(),
            "auditor_sha256":sha(Path(__file__).read_bytes()),
            "manifest_sha256":sha((root/"manifest.json").read_bytes()),
            "macro_records_verified":verified,"macro_records_expected":len(cuts)*len(definitions),
            "all_macro_verified":verified==len(cuts)*len(definitions),
            "sec_holdings_documents_verified":len(sec_records),
            "cuts_with_fresh_public_holdings":sum(r["spy_holdings_source"]["status"]=="source-available" for r in matrix),
            "errors":errors,"matrix":matrix,"full_replay_ready":False,"production_eligible":False,
            "predictive_validation":"not-established",
            "scope":"Verified component sources with provider historical-vintage and conservative public-filing contracts; not a certified original whole-market archive, mapped constituent anchors or an economic backtest"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",default="data/historical/provider-inputs-v1")
    args=parser.parse_args()
    market=json.loads(subprocess.check_output(["git","show",MARKET_COMMIT+":dist/data/market.json"],cwd=ROOT))
    result=audit_sources(args.input,account_origins(market))
    (Path(args.input)/"readiness.json").write_bytes(canonical(result)+b"\n")
    print(json.dumps({k:result[k] for k in ("macro_records_verified","macro_records_expected","sec_holdings_documents_verified","cuts_with_fresh_public_holdings","full_replay_ready")}))
    raise SystemExit(0 if not result["errors"] else 2)
