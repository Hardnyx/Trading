"""Recover attributed historical provider vintages; never modify live inputs.

ALFRED snapshots are provider-certified historical periods downloaded today,
not forecasts collected in the past. SEC holdings retain both period and
conservative availability dates. Unknown identifiers remain unmatched.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from threading import Lock
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

if __package__:
    from .account_inputs import account_origins
else:
    from account_inputs import account_origins

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "historical-provider-inputs-v1"
MARKET_COMMIT = "8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5"
SPY_CIK = 884394
SERIES = [
    ("DGS3MO", "DGS3MO", "%"), ("DGS2", "DGS2", "%"),
    ("DGS5", "DGS5", "%"), ("DGS10", "DGS10", "%"), ("DGS30", "DGS30", "%"),
    ("CPI_CORE", "CPILFESL", "index"), ("AHE", "CES0500000003", "USD/hour"),
    ("LFPR", "CIVPART", "%"), ("CPI", "CPIAUCSL", "index"),
    ("UNRATE", "UNRATE", "%"), ("DFF", "DFF", "%"), ("T10YIE", "T10YIE", "%"),
    ("DFII10", "DFII10", "%"), ("DTWEXBGS", "DTWEXBGS", "index"),
    ("PAYEMS", "PAYEMS", "thousands"), ("INDPRO", "INDPRO", "index"),
]
sha = lambda value: hashlib.sha256(value).hexdigest()


def iso(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Missing exact ISO date")
    return date.fromisoformat(value).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fred_parameters(source_id, cut):
    cut = iso(cut)
    vintage = (date.fromisoformat(cut) - timedelta(days=1)).isoformat()
    return {"series_id": source_id, "file_type": "json", "realtime_start": vintage,
            "realtime_end": vintage, "observation_start": f"{int(cut[:4])-5}-01-01",
            "observation_end": vintage, "sort_order": "asc", "output_type": 1,
            "limit": 100000, "offset": 0}


def normalize_fred(body, definition, cut):
    target, source, unit = definition
    params = fred_parameters(source, cut)
    vintage = params["realtime_start"]
    if not isinstance(body, dict) or body.get("realtime_start") != vintage or body.get("realtime_end") != vintage:
        raise ValueError("Provider did not confirm the requested historical vintage")
    raw = body.get("observations")
    if not isinstance(raw, list) or type(body.get("count")) is not int or body["count"] != len(raw) or body.get("offset") != 0:
        raise ValueError("Incomplete or paginated historical response")
    if body.get("units") != "lin" or body.get("output_type") != 1:
        raise ValueError("Unexpected transformation or output mode")
    history, seen = [], set()
    for row in raw:
        day = iso(row.get("date"))
        if day in seen or not params["observation_start"] <= day <= vintage:
            raise ValueError("Duplicate or out-of-window historical observation")
        seen.add(day)
        start, end = iso(row.get("realtime_start")), iso(row.get("realtime_end"))
        if not start <= vintage <= end:
            raise ValueError("Observation belongs to a different vintage")
        value = row.get("value")
        if value == ".":
            continue
        if isinstance(value, bool):
            raise ValueError("Invalid observation")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Invalid observation")
        history.append({"date": day, "value": number})
    history.sort(key=lambda row: row["date"])
    if not history:
        raise ValueError("No available observations in historical vintage")
    latest = history[-1]
    old = next((r for r in history if r["date"] == str(int(latest["date"][:4])-1)+latest["date"][4:]), None)
    return {"id": target, "source_id": source, "unit": unit,
            "date": latest["date"], "value": latest["value"],
            "previous": history[-2]["value"] if len(history)>1 else None,
            "yoy": latest["value"]/old["value"]-1 if target in ("CPI", "CPI_CORE") and old and old["value"] else None,
            "history": history, "provider": "FRED/ALFRED", "vintage_date": vintage,
            "known_by_day": vintage, "vintage_mode": "provider_historical_asof",
            "source_url": "https://fred.stlouisfed.org/series/"+source,
            "knowledge_basis": "Official API real-time period, day precision; strict prior-day cutoff"}


def validate_macro_record(record, definition, cut):
    """Historical replay accepts only the explicit provider-vintage contract."""
    if record.get("protocol") != PROTOCOL or record.get("kind") != "alfred-vintage":
        raise ValueError("Not an archived provider vintage")
    raw = base64.b64decode(record["raw_base64"], validate=True)
    if sha(raw) != record.get("raw_sha256"):
        raise ValueError("Archived source hash mismatch")
    expected = fred_parameters(definition[1], cut)
    if record.get("request") != expected:
        raise ValueError("Source identity, vintage or request mismatch")
    normalized = normalize_fred(json.loads(raw), definition, cut)
    if normalized != record.get("normalized"):
        raise ValueError("Normalized data do not match the archived source")
    retrieved = datetime.fromisoformat(record["retrieved_at"].replace("Z","+00:00"))
    if retrieved.tzinfo is None or retrieved.date().isoformat()<normalized["vintage_date"]:
        raise ValueError("Invalid actual retrieval timestamp")
    return {**normalized, "observed_at": record["retrieved_at"],
            "retrieved_at": record["retrieved_at"], "source_sha256": sha(raw)}


def submission_rows(body):
    columns = body.get("filings", {}).get("recent") if isinstance(body.get("filings"), dict) else body
    if not isinstance(columns, dict) or not isinstance(columns.get("accessionNumber"), list):
        raise ValueError("Invalid SEC submissions table")
    names = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument", "acceptanceDateTime"]
    n = len(columns["accessionNumber"])
    if any(not isinstance(columns.get(key), list) or len(columns[key]) != n for key in names):
        raise ValueError("Inconsistent SEC submissions columns")
    rows = []
    for i in range(n):
        row = {key: columns[key][i] for key in names}
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row["accessionNumber"]):
            raise ValueError("Invalid SEC accession")
        iso(row["filingDate"])
        rows.append(row)
    return rows


def local_tag(node):
    return node.tag.rsplit("}", 1)[-1]


def parse_nport(raw, filing):
    if len(raw)>4_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsafe or oversized N-PORT document")
    root = ET.fromstring(raw)
    find = lambda parent, tag: next((n for n in parent.iter() if local_tag(n)==tag), None)
    text = lambda parent, tag: (find(parent, tag).text or "").strip() if find(parent, tag) is not None else ""
    info = find(root, "genInfo")
    if info is None or text(info,"regCik").lstrip("0") != str(SPY_CIK):
        raise ValueError("N-PORT registrant does not match SPY")
    period = iso(text(info,"repPdDate"))
    filed = iso(filing["filingDate"])
    if period > filed or (filing.get("reportDate") and filing["reportDate"] != period):
        raise ValueError("Inconsistent report and filing dates")
    # Conservative historical public-data policy. Never equate portfolio date
    # or early filing acceptance with public availability of confidential data.
    available = max(filed, (date.fromisoformat(period)+timedelta(days=60)).isoformat())
    rows = []
    for item in root.iter():
        if local_tag(item) != "invstOrSec":
            continue
        weight = float(text(item,"pctVal"))/100
        if not math.isfinite(weight) or not -1 <= weight <= 1:
            raise ValueError("Invalid original holding weight")
        tickers = set()
        identifiers = find(item,"identifiers")
        if identifiers is not None:
            for node in identifiers.iter():
                if local_tag(node)=="ticker" or (local_tag(node)=="other" and node.get("otherDesc","").lower() in ("ticker","ticker symbol")):
                    candidate = node.get("value",(node.text or "").strip())
                    if re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}",candidate):
                        tickers.add(candidate)
        symbol = next(iter(tickers)) if len(tickers)==1 else None
        rows.append({"symbol": symbol, "name": text(item,"name"), "title": text(item,"title"),
                     "cusip": text(item,"cusip"), "weight": weight})
    if not rows:
        raise ValueError("No original N-PORT holdings")
    positive = sum(r["weight"] for r in rows if r["weight"]>0)
    negative = sum(-r["weight"] for r in rows if r["weight"]<0)
    mapped = sum(r["weight"] for r in rows if r["weight"]>0 and r["symbol"])
    return {"symbol":"SPY", "as_of":period, "available_after_day":available,
            "availability_basis":"SEC public accession plus minimum 60 calendar days from holdings date; next day eligibility, not intraday certification",
            "positions":rows, "reported_positive_weight":positive, "negative_weight":negative,
            "explicit_ticker_weight":mapped, "unmatched_weight":positive-mapped,
            "structurally_valid":.65<=positive<=1.05 and negative<=.05,
            "original_identifiers_only":True, "live_anchor_coverage_verified":False}


def select_holdings(records, cut, maximum_age=120):
    iso(cut)
    eligible = [r for r in records if r.get("normalized") and
                r["normalized"]["available_after_day"] < cut and r["normalized"]["as_of"]<=cut]
    eligible.sort(key=lambda r:(r["normalized"]["as_of"], r["normalized"]["available_after_day"], r["accession"]), reverse=True)
    if not eligible:
        return {"status":"no-prior-public-record"}
    row = eligible[0]; n = row["normalized"]
    age = (date.fromisoformat(cut)-date.fromisoformat(n["as_of"])).days
    status = "source-available" if age<=maximum_age and n["structurally_valid"] else "stale-or-invalid-source"
    return {"status":status, "accession":row["accession"], "as_of":n["as_of"],
            "available_after_day":n["available_after_day"], "age_days":age,
            "explicit_ticker_weight":n["explicit_ticker_weight"],
            "unmatched_weight":n["unmatched_weight"], "anchor_ready":False,
            "note":"Source availability is not valid-constituent anchor coverage or a complete historical universe"}


class FetchError(Exception):
    def __init__(self, kind, status=None):
        super().__init__(kind)
        self.kind, self.status = kind, status


class Downloader:
    def __init__(self, delay=.65):
        self.delay = delay
        self.lock = Lock()
        self.last_request = 0

    def pace(self):
        with self.lock:
            time.sleep(max(0,self.delay-(time.monotonic()-self.last_request)))
            self.last_request=time.monotonic()

    def __call__(self, url, *, sec=False, max_bytes=8_000_000):
        agent = os.environ.get("SEC_USER_AGENT", "") if sec else "TradingHistoricalResearch/1.0"
        if sec and not agent:
            raise FetchError("missing-sec-user-agent")
        for attempt in range(3):
            self.pace()
            try:
                request = urllib.request.Request(url,headers={"User-Agent":agent,"Accept":"application/json, application/xml, text/html"})
                with urllib.request.urlopen(request,timeout=30) as response:
                    raw = response.read(max_bytes+1)
                if len(raw)>max_bytes:
                    raise FetchError("oversized-response")
                return raw
            except urllib.error.HTTPError as error:
                if error.code in (429,500,502,503,504) and attempt<2:
                    time.sleep(2*(attempt+1));continue
                raise FetchError("http-error",error.code) from None
            except (urllib.error.URLError,TimeoutError):
                if attempt<2:continue
                raise FetchError("network-error") from None


def source_path(root, relative):
    path=(root/relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Source archive path escapes its root")
    return path


def archive(root, relative, record):
    path = source_path(root,relative)
    data = canonical(record)
    if path.exists():
        prior = gzip.decompress(path.read_bytes())
        old = json.loads(prior)
        if old.get("raw_sha256") != record.get("raw_sha256"):
            raise ValueError("Immutable historical archive conflict")
        record = old
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("xb") as output:
            output.write(gzip.compress(data,mtime=0))
    return {"path":relative, "sha256":sha(path.read_bytes()), "raw_sha256":record["raw_sha256"]},record


def safe_error(error):
    # URLs and arbitrary exception messages can contain the API credential.
    return {"kind":error.kind,"http_status":error.status} if isinstance(error,FetchError) else {"kind":type(error).__name__}


def recover_macro(root, old, cut, definition, fetch, key, code_hash):
    target, source, _ = definition
    prior = old.get("macro",{}).get(cut,{}).get(target,{})
    try:
        raw=None;retrieved=None;basis="download-completed"
        if prior.get("path"):
            path=source_path(root,prior["path"])
            if sha(path.read_bytes())!=prior["sha256"]:raise ValueError("Archived blob mismatch")
            previous=json.loads(gzip.decompress(path.read_bytes()))
            validate_macro_record(previous,definition,cut)
            raw=base64.b64decode(previous["raw_base64"],validate=True)
            retrieved=previous["retrieved_at"]
            basis=previous.get("retrieval_timestamp_basis","initial-collection-clock")
        params=fred_parameters(source,cut)
        if raw is None:
            if not key:raise FetchError("missing-fred-api-key")
            url="https://api.stlouisfed.org/fred/series/observations?"+urllib.parse.urlencode({**params,"api_key":key})
            raw=fetch(url);retrieved=datetime.now(timezone.utc).isoformat()
            if key.encode() in raw:raise FetchError("credential-in-response")
        normalized=normalize_fred(json.loads(raw),definition,cut)
        record={"protocol":PROTOCOL,"kind":"alfred-vintage","request":params,
                "retrieved_at":retrieved,"retrieval_timestamp_basis":basis,
                "raw_sha256":sha(raw),"raw_base64":base64.b64encode(raw).decode(),
                "normalized":normalized,"collector_sha256":code_hash}
        relative=f"macro/{cut}/{target}-{sha(raw)[:20]}-{code_hash[:12]}.json.gz"
        pointer,record=archive(root,relative,record)
        validate_macro_record(record,definition,cut)
        return target,{**pointer,"status":"available","vintage_day":normalized["vintage_date"],
                       "last_observation":normalized["date"],"observations":len(normalized["history"])},None
    except Exception as error:
        detail={"source":"ALFRED","cut":cut,"series":target,**safe_error(error)}
        return target,{"status":"unavailable",**safe_error(error)},detail


def collect(root, market, *, fetch=None, limit=None):
    fetch = fetch or Downloader()
    root = Path(root);root.mkdir(parents=True,exist_ok=True)
    manifest_path = root/"manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    cuts = account_origins(market)
    if limit is not None:
        if limit<1:raise ValueError("A positive cut limit is required")
        cuts=cuts[:limit]
    if not cuts:raise ValueError("No historical cuts")
    code_hash = sha(Path(__file__).read_bytes())
    result = {"protocol":PROTOCOL,"source_market_commit":MARKET_COMMIT,"price_cut":market["price_as_of"],
              "retrieved_at":datetime.now(timezone.utc).isoformat(),"collector_sha256":code_hash,
              "cuts":cuts,"series_ids":[r[0] for r in SERIES],"macro":{},"sec":{},"errors":[],
              "production_eligible":False,"automatic_promotion":False,"full_model_backtest":"blocked"}
    result["source_hashes"]={}
    for module in list(sys.modules.values()):
        path=getattr(module,"__file__",None)
        if path and Path(path).suffix==".py" and Path(path).resolve().is_relative_to(ROOT/"scripts"):
            path=Path(path).resolve();result["source_hashes"][str(path.relative_to(ROOT))]=sha(path.read_bytes())
    result["source_hashes"]["requirements-research.txt"]=sha((ROOT/"requirements-research.txt").read_bytes())
    key = os.environ.get("FRED_API_KEY", "")
    result["health"]="in-progress";result["macro_health"]="incomplete"
    result["expected_macro_records"]=len(cuts)*len(SERIES)
    ignore=root/".gitignore"
    if not ignore.exists():ignore.write_text(".manifest.tmp\n")
    def checkpoint():
        result["available_macro_records"]=sum(r["status"]=="available" for rows in result["macro"].values() for r in rows.values())
        temporary=root/".manifest.tmp"
        temporary.write_bytes(canonical(result)+b"\n")
        os.replace(temporary,manifest_path)
    checkpoint()
    for cut in cuts:
        result["macro"][cut] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(recover_macro,root,old,cut,definition,fetch,key,code_hash) for definition in SERIES]
            for future in as_completed(futures):
                target,pointer,error=future.result()
                result["macro"][cut][target]=pointer
                if error:result["errors"].append(error)
                checkpoint()
        print(json.dumps({"cut":cut,"macro_available":sum(r["status"]=="available" for r in result["macro"][cut].values()),"expected":len(SERIES)}),flush=True)
    try:
        result["sec"]=collect_spy(root,cuts,market["price_as_of"],fetch,result["retrieved_at"],code_hash)
    except Exception as error:
        result["sec"]={"status":"unavailable",**safe_error(error)}
        result["errors"].append({"source":"SEC-SPY",**safe_error(error)})
    result["expected_macro_records"]=len(cuts)*len(SERIES)
    result["available_macro_records"]=sum(r["status"]=="available" for rows in result["macro"].values() for r in rows.values())
    result["macro_health"]="complete" if result["available_macro_records"]==result["expected_macro_records"] else "incomplete"
    result["health"]="complete-collection" if not result["errors"] and not result["sec"].get("errors") else "partial-collection"
    result["remaining_blockers"]=["Original dated bond and ETF valuation profiles","Complete historical financial quality/confidence",
                                  "Historical universe, identifiers and corporate actions","Holdings-to-valid-anchor coverage and full decision replay"]
    result["collection_finished_at"]=datetime.now(timezone.utc).isoformat()
    checkpoint()
    return result


def collect_spy(root,cuts,last_cut,fetch,retrieved,code_hash):
    url=f"https://data.sec.gov/submissions/CIK{SPY_CIK:010d}.json"
    raw=fetch(url,sec=True);body=json.loads(raw)
    if int(body.get("cik",0))!=SPY_CIK or (body.get("tickers") and "SPY" not in body["tickers"]):
        raise ValueError("SEC registrant identity mismatch")
    pointer,_=archive(root,f"sec/submissions-{sha(raw)[:20]}.json.gz",{"raw_sha256":sha(raw),"raw_base64":base64.b64encode(raw).decode(),"source_url":url,"retrieved_at":retrieved})
    rows=submission_rows(body);metadata_archives=[pointer]
    start=(date.fromisoformat(cuts[0])-timedelta(days=400)).isoformat()
    for part in body.get("filings",{}).get("files",[]):
        if part.get("filingFrom","")>last_cut or part.get("filingTo","")<start:continue
        name=part.get("name","")
        if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json",name):raise ValueError("Unsafe submissions archive name")
        extra=fetch("https://data.sec.gov/submissions/"+name,sec=True)
        ref,_=archive(root,f"sec/submissions-{sha(extra)[:20]}.json.gz",{"raw_sha256":sha(extra),"raw_base64":base64.b64encode(extra).decode(),"retrieved_at":retrieved,"source_url":"https://data.sec.gov/submissions/"+name})
        metadata_archives.append(ref)
        rows.extend(submission_rows(json.loads(extra)))
    selected={}
    for row in rows:
        if not start<=row["filingDate"]<=last_cut or row["form"] not in ("NPORT-P","NPORT-P/A","N-30D","N-CSR","N-Q"):continue
        acc=row["accessionNumber"]
        if acc in selected and selected[acc]!=row:raise ValueError("Conflicting SEC accession metadata")
        selected[acc]=row
    records=[];errors=[]
    for accession,filing in sorted(selected.items(),key=lambda item:(item[1]["filingDate"],item[0])):
        row={"accession":accession,"filing_date":filing["filingDate"],"form":filing["form"],"report_date":filing["reportDate"],"normalized":None}
        try:
            primary=filing["primaryDocument"]
            # XML primary documents preserve identifiers and weights. If SEC
            # names a rendered N-PORT primary, the standard raw XML is retained.
            if filing["form"].startswith("NPORT"):
                filename="primary_doc.xml"
            else:
                if not re.fullmatch(r"[A-Za-z0-9_.-]+",primary):raise ValueError("Unsafe primary document")
                filename=primary
            source=f"https://www.sec.gov/Archives/edgar/data/{SPY_CIK}/{accession.replace('-','')}/{filename}"
            cached=[]
            for path in (root/"sec").glob(accession+"-*.json.gz"):
                prior=json.loads(gzip.decompress(path.read_bytes()))
                original=base64.b64decode(prior["raw_base64"],validate=True)
                if (sha(original)!=prior["raw_sha256"] or prior.get("source_url")!=source or
                    prior.get("filing")!=filing or path.name!=f"{accession}-{sha(original)[:20]}.json.gz"):
                    raise ValueError("SEC cached source identity mismatch")
                instant=datetime.fromisoformat(prior["retrieved_at"].replace("Z","+00:00"))
                if instant.tzinfo is None:raise ValueError("Undated cached source")
                cached.append((instant,original,prior))
            if cached:
                _,original,record=min(cached,key=lambda r:r[0])
            else:
                original=fetch(source,sec=True,max_bytes=4_000_000)
                record={"raw_sha256":sha(original),"raw_base64":base64.b64encode(original).decode(),"source_url":source,
                        "filing":filing,"retrieved_at":datetime.now(timezone.utc).isoformat(),"retrieval_timestamp_basis":"download-completed"}
            ref,record=archive(root,f"sec/{accession}-{sha(original)[:20]}.json.gz",record)
            row.update(ref);row["source_url"]=source
            if filing["form"].startswith("NPORT"):
                row["normalized"]=parse_nport(original,filing)
            else:row["note"]="Original report retained; no holdings inferred from an unparsed HTML statement"
        except Exception as error:
            row["error"]=safe_error(error);errors.append({"accession":accession,**safe_error(error)})
        records.append(row)
    return {"status":"collected" if not errors else "partial","registrant_cik":SPY_CIK,"submissions":pointer,"metadata_archives":metadata_archives,
            "documents":records,"errors":errors,"by_cut":{cut:select_holdings(records,cut) for cut in cuts},
            "holdings_age_limit_days":120,"anchor_ready":False,"collector_sha256":code_hash}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="data/historical/provider-inputs-v1")
    parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    market=json.loads(subprocess.check_output(["git","show",MARKET_COMMIT+":dist/data/market.json"],cwd=ROOT))
    result=collect(args.output,market,limit=args.limit)
    print(json.dumps({k:result[k] for k in ("health","macro_health","expected_macro_records","available_macro_records","full_model_backtest")}))
    raise SystemExit(0 if result["health"]=="complete-collection" else 2)
