import base64
import copy
from datetime import date, timedelta
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from scripts.historical_sources import (PROTOCOL, SERIES, FetchError, archive,
    collect, fred_parameters, normalize_fred, parse_nport, select_holdings,
    sha, submission_rows, validate_macro_record)
from scripts.audit_historical_inputs import audit_sources


def response(cut, source="DGS3MO", value="2.5"):
    p=fred_parameters(source,cut);v=p["realtime_start"]
    return {"realtime_start":v,"realtime_end":v,"units":"lin","output_type":1,
            "count":2,"offset":0,"observations":[
                {"date":v,"realtime_start":v,"realtime_end":v,"value":value},
                {"date":p["observation_start"],"realtime_start":v,"realtime_end":v,"value":"."}]}


def record(cut="2022-10-31"):
    raw=json.dumps(response(cut)).encode()
    return {"protocol":PROTOCOL,"kind":"alfred-vintage","request":fred_parameters("DGS3MO",cut),
            "retrieved_at":"2026-10-30T05:00:00+00:00","raw_sha256":sha(raw),
            "raw_base64":base64.b64encode(raw).decode(),
            "normalized":normalize_fred(json.loads(raw),SERIES[0],cut)}


def nport(period="2022-09-30", ticker=True):
    identity='<identifiers><ticker value="AAA"/></identifiers>' if ticker else '<identifiers><isin value="US0000000001"/></identifiers>'
    return f'''<edgarSubmission xmlns="urn:sec"><genInfo><regCik>0000884394</regCik><repPdDate>{period}</repPdDate></genInfo>
      <invstOrSecs><invstOrSec><name>A</name><title>Common</title><cusip>000000001</cusip><pctVal>40</pctVal>{identity}</invstOrSec>
      <invstOrSec><name>B</name><title>Common</title><cusip>000000002</cusip><pctVal>60</pctVal><identifiers><ticker value="BBB"/></identifiers></invstOrSec></invstOrSecs></edgarSubmission>'''.encode()


class HistoricalSources(unittest.TestCase):
    def test_prior_day_vintage_is_fixed_independently_of_download_day(self):
        p=fred_parameters("DGS3MO","2022-10-31")
        self.assertEqual(p["realtime_start"],"2022-10-30")
        self.assertEqual(p["realtime_end"],p["realtime_start"])
        self.assertNotIn("api_key",p)
        result=validate_macro_record(record(),SERIES[0],"2022-10-31")
        self.assertEqual(result["known_by_day"],"2022-10-30")
        self.assertEqual(result["observed_at"],"2026-10-30T05:00:00+00:00")
        self.assertEqual(result["value"],2.5)

    def test_current_or_wrong_vintage_cannot_be_used_as_original_data(self):
        r=record();r["kind"]="observed-current"
        with self.assertRaisesRegex(ValueError,"provider vintage"):
            validate_macro_record(r,SERIES[0],"2022-10-31")
        body=response("2022-10-31");body["realtime_start"]="2026-10-29"
        with self.assertRaisesRegex(ValueError,"historical vintage"):
            normalize_fred(body,SERIES[0],"2022-10-31")
        body=response("2022-10-31");body["observations"][0]["realtime_start"]="2022-10-31"
        with self.assertRaisesRegex(ValueError,"different vintage"):
            normalize_fred(body,SERIES[0],"2022-10-31")

    def test_missing_pagination_duplicates_and_future_observations_fail_closed(self):
        base=response("2022-10-31")
        variants=[]
        b=copy.deepcopy(base);b["count"]=3;variants.append(b)
        b=copy.deepcopy(base);b["offset"]=1;variants.append(b)
        b=copy.deepcopy(base);b["observations"][1]=b["observations"][0];variants.append(b)
        b=copy.deepcopy(base);b["observations"][0]["date"]="2022-10-31";variants.append(b)
        b=copy.deepcopy(base);b["units"]="pc1";variants.append(b)
        for b in variants:
            with self.assertRaises(ValueError):normalize_fred(b,SERIES[0],"2022-10-31")

    def test_source_hash_identity_and_derivation_are_checked(self):
        for mutate in [lambda r:r.update(raw_sha256="0"*64),
                       lambda r:r["request"].update(series_id="DGS10"),
                       lambda r:r["normalized"].update(value=999)]:
            r=record();mutate(r)
            with self.assertRaises(ValueError):validate_macro_record(r,SERIES[0],"2022-10-31")
        r=record();r["retrieved_at"]="2022-10-29T00:00:00"
        with self.assertRaisesRegex(ValueError,"retrieval"):
            validate_macro_record(r,SERIES[0],"2022-10-31")

    def test_nport_preserves_unmapped_identifiers_instead_of_guessing_tickers(self):
        f={"filingDate":"2022-11-29","reportDate":"2022-09-30"}
        r=parse_nport(nport(ticker=False),f)
        self.assertEqual(r["positions"][0]["symbol"],None)
        self.assertAlmostEqual(r["unmatched_weight"],.4)
        self.assertAlmostEqual(r["explicit_ticker_weight"],.6)
        self.assertFalse(r["live_anchor_coverage_verified"])
        self.assertEqual(r["available_after_day"],"2022-11-29")

    def test_filing_date_does_not_make_undisclosed_nport_known_at_report_date(self):
        f={"filingDate":"2022-10-28","reportDate":"2022-09-30"}
        n=parse_nport(nport(),f)
        self.assertEqual(n["available_after_day"],"2022-11-29")
        rows=[{"accession":"one","normalized":n}]
        self.assertEqual(select_holdings(rows,"2022-10-31")["status"],"no-prior-public-record")
        self.assertEqual(select_holdings(rows,"2022-11-29")["status"],"no-prior-public-record")
        self.assertEqual(select_holdings(rows,"2022-11-30")["status"],"source-available")
        self.assertEqual(select_holdings(rows,"2023-01-31")["status"],"stale-or-invalid-source")

    def test_future_amendments_cannot_replace_the_record_available_at_the_cut(self):
        a={"accession":"original","normalized":parse_nport(nport(),{"filingDate":"2022-11-29","reportDate":"2022-09-30"})}
        b=copy.deepcopy(a);b["accession"]="amendment";b["normalized"]["available_after_day"]="2023-01-01"
        self.assertEqual(select_holdings([b,a],"2022-12-30")["accession"],"original")

    def test_wrong_registrant_inconsistent_periods_and_entities_are_rejected(self):
        filing={"filingDate":"2022-11-29","reportDate":"2022-09-30"}
        for raw in [nport().replace(b"0000884394",b"0000000001"),nport("2022-06-30"),b'<!DOCTYPE test>'+nport()]:
            with self.assertRaises(ValueError):parse_nport(raw,filing)

    def test_immutable_raw_archive_preserves_first_retrieval(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=record();ptr,_=archive(root,"one.json.gz",a)
            later={**a,"retrieved_at":"2026-11-30T01:00:00Z"}
            again,kept=archive(root,"one.json.gz",later)
            self.assertEqual(ptr,again);self.assertEqual(kept["retrieved_at"],a["retrieved_at"])
            with self.assertRaisesRegex(ValueError,"conflict"):
                archive(root,"one.json.gz",{**a,"raw_sha256":"different"})
            with self.assertRaisesRegex(ValueError,"escapes"):
                archive(root,"../outside.json.gz",a)

    def test_collector_resumes_first_vintage_without_redownloading_or_exposing_credentials(self):
        cuts=["2022-10-31","2022-11-30"];calls=[]
        columns={"accessionNumber":[],"filingDate":[],"reportDate":[],"form":[],"primaryDocument":[],"acceptanceDateTime":[]}
        def fetch(url,**kwargs):
            calls.append(url)
            if "stlouisfed" in url:
                q=parse_qs(urlparse(url).query);cut=str(date.fromisoformat(q['realtime_start'][0])+timedelta(days=1))
                return json.dumps(response(cut,q["series_id"][0])).encode()
            return json.dumps({"cik":884394,"tickers":["SPY"],"filings":{"recent":columns,"files":[]}}).encode()
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"FRED_API_KEY":"sentinel-private-key"}),patch('scripts.historical_sources.account_origins',return_value=cuts),patch('scripts.historical_sources.SERIES',SERIES[:2]):
            a=collect(folder,{"price_as_of":"2026-10-28"},fetch=fetch)
            self.assertEqual(a["available_macro_records"],4)
            self.assertEqual(a["macro_health"],"complete")
            self.assertEqual(a["full_model_backtest"],"blocked")
            self.assertFalse(a["production_eligible"])
            first=sum("stlouisfed" in u for u in calls)
            b=collect(folder,{"price_as_of":"2026-10-28"},fetch=fetch)
            self.assertEqual(sum("stlouisfed" in u for u in calls),first)
            self.assertEqual(a["macro"],b["macro"])
            audit=audit_sources(folder,cuts,SERIES[:2])
            self.assertEqual(audit["macro_records_verified"],4)
            self.assertFalse(audit["full_replay_ready"])
            self.assertEqual(audit["errors"],[])
            with self.assertRaisesRegex(ValueError,"calendar"):
                audit_sources(folder,cuts[:1],SERIES[:2])
            pointer=a["macro"][cuts[0]]["DGS3MO"]
            path=Path(folder)/pointer["path"];saved=path.read_bytes();path.write_bytes(b"corrupt")
            invalid=audit_sources(folder,cuts,SERIES[:2]);self.assertEqual(invalid["macro_records_verified"],3)
            self.assertFalse(invalid["all_macro_verified"]);self.assertEqual(len(invalid["errors"]),1)
            path.write_bytes(saved)
            for path in Path(folder).rglob('*'):
                if path.is_file():
                    raw=gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes()
                    self.assertNotIn(b"sentinel-private-key",raw)

    def test_incomplete_collection_is_explicit_and_never_fills_with_current_csv(self):
        def fetch(url,**kwargs):raise FetchError("http-error",403)
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"FRED_API_KEY":"key"}),patch('scripts.historical_sources.account_origins',return_value=["2022-10-31"]),patch('scripts.historical_sources.SERIES',SERIES[:1]):
            r=collect(folder,{"price_as_of":"2026-10-28"},fetch=fetch)
            self.assertEqual(r["macro_health"],"incomplete")
            self.assertEqual(r["health"],"partial-collection")
            self.assertEqual(r["available_macro_records"],0)
            self.assertEqual(r["macro"]["2022-10-31"]["DGS3MO"]["http_status"],403)

    def test_submissions_columns_must_reconcile(self):
        with self.assertRaisesRegex(ValueError,"Inconsistent"):
            submission_rows({"accessionNumber":["0000000001-22-000001"]})
