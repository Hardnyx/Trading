"""Reconcile archived SEC 13F security-class statements against original SPY CUSIPs.

A 13F is a dated manager disclosure, not a security master or a price vintage.
Independent manager holdings corroborate CUSIP/class strings, not issuer CIK,
LEI, permanent FIGI, execution or predictive skill. No outcome labels are used.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from scripts.historical_spy_issuer_lei import review as spy_review
    from scripts.historical_vendor_identity import valid_cusip
    from scripts.historical_sources import local_tag
    from scripts.historical_sec_original_filing import parse_original
    from scripts.sec_original_acquisition import get_original, validate_agent
    from scripts.sec_sgml_text_wrapper import unwrap_sec_xml_payload
except ModuleNotFoundError:
    from historical_spy_issuer_lei import review as spy_review
    from historical_vendor_identity import valid_cusip
    from historical_sources import local_tag
    from historical_sec_original_filing import parse_original
    from sec_original_acquisition import get_original, validate_agent
    from sec_sgml_text_wrapper import unwrap_sec_xml_payload

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "historical-independent-manager-13f-class-review-v1"
ACCESSION = "0001752724-24-248565"
CIK = "102909"
FILENAME = "13F_0000102909_20240930.xml"
URL = ("https://www.sec.gov/Archives/edgar/data/102909/"
       "000175272424248565/0001752724-24-248565.txt")
INDEX = "https://www.sec.gov/Archives/edgar/data/102909/0001752724-24-248565-index.htm"
CUT = "2024-12-31T21:00:00+00:00"
FIRST_PUBLISHED = "2024-11-13T16:58:36+00:00"
PERIOD = "2024-09-30"
ARCHIVE = ROOT / "data/historical/independent-13f-v1"
ORIGINAL = ARCHIVE / (ACCESSION + ".txt.gz")
RECEIPT = ARCHIVE / "receipt.json"
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
FIELDS = ("source_position", "cusip", "spy_original_name", "weight", "cut",
          "review_status", "other_manager_name_as_filed", "other_manager_class_as_filed",
          "other_manager_reported_shares", "original_13f_accession",
          "original_13f_sha256", "original_13f_accepted_utc",
          "security_master_certified", "historical_price_verified")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def child_text(element, key):
    matches = [p for p in element if local_tag(p) == key]
    require(len(matches) == 1, f"Missing or duplicate 13F field {key}")
    return (matches[0].text or "").strip()


def source_payload(raw):
    require(type(raw) is bytes and 50 <= len(raw) <= MAX_DOCUMENT_BYTES and
            b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "Unsafe or oversized complete SEC 13F")
    blocks = re.findall(rb"(?ms)^<DOCUMENT>\s*\r?\n(.*?)^</DOCUMENT>\s*\r?$", raw)
    require(1 <= len(blocks) <= 10, "Missing or unexpected complete SEC documents")
    found = []
    for block in blocks:
        kind = re.findall(rb"(?m)^<TYPE>([^\r\n]+)", block)
        fn = re.findall(rb"(?m)^<FILENAME>([^\r\n]+)", block)
        require(len(kind) == 1 and len(fn) == 1, "Ambiguous SEC 13F document envelope")
        if fn[0] != FILENAME.encode():
            continue
        require(kind[0].strip().upper() == b"INFORMATION TABLE",
                "13F XML was not an original information table")
        pieces = re.findall(rb"(?ms)^<TEXT>\s*\r?\n(.*?)^</TEXT>\s*\r?$", block)
        require(len(pieces) == 1, "Original 13F information table missing")
        found.append(unwrap_sec_xml_payload(pieces[0].rstrip(b"\r\n"), "XML"))
    require(len(found) == 1, "Original 13F information table missing or duplicated")
    return found[0]


def parse_table(raw):
    require(type(raw) is bytes and len(raw) <= MAX_DOCUMENT_BYTES and
            b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "Unsafe 13F information table XML")
    xml = ET.fromstring(raw)
    require(local_tag(xml) == "informationTable", "Unexpected 13F XML root")
    rows = []
    for item in xml:
        require(local_tag(item) == "infoTable", "Unexpected 13F information-table element")
        cusip = child_text(item, "cusip").upper()
        issuer = child_text(item, "nameOfIssuer")
        title = child_text(item, "titleOfClass")
        require(issuer and title and 1 <= len(issuer) <= 250 and 1 <= len(title) <= 120,
                "Missing original 13F issuer/class")
        amounts = [p for p in item if local_tag(p) == "shrsOrPrnAmt"]
        require(len(amounts) == 1, "Missing 13F share/principal denomination")
        unit = child_text(amounts[0], "sshPrnamtType").upper()
        number = child_text(amounts[0], "sshPrnamt")
        require(re.fullmatch(r"[0-9]{1,20}(?:\.[0-9]{1,8})?", number) is not None,
                "Invalid 13F as-filed amount")
        option = [p for p in item if local_tag(p) == "putCall"]
        require(len(option) <= 1, "Ambiguous 13F option field")
        option_value = (option[0].text or "").strip().upper() if option else ""
        require(option_value in ("", "PUT", "CALL"), "Unexpected original 13F option")
        rows.append({"cusip": cusip, "issuer": issuer, "title": title,
                     "unit": unit, "shares_as_filed": number, "option": option_value})
    require(1 <= len(rows) <= 25000, "Unexpected 13F information table size")
    return rows


def validate_complete_original(raw):
    h = parse_original(raw, ACCESSION)
    require(h["cik"] == CIK and h["form"] == "13F-HR" and
            h["filed"] == "20241113" and
            h["accepted_utc"] == FIRST_PUBLISHED and
            h["accepted_utc"] < CUT and len(raw) <= MAX_DOCUMENT_BYTES,
            "Original SEC Vanguard 13F header or timestamp mismatch")
    header = raw.split(b"<SEC-HEADER>", 1)[1].split(b"</SEC-HEADER>", 1)[0]
    declared_periods = re.findall(
        rb"(?m)^[ \\t]*CONFORMED PERIOD OF REPORT:[ \\t]*([0-9]{8})[ \\t]*\\r?$",
        header)
    require(declared_periods == [PERIOD.replace("-", "").encode("ascii")],
            "Original SEC 13F holdings period differs from the frozen quarter")
    rows = parse_table(source_payload(raw))
    return h, rows


def compare(rows, spy, original):
    require(spy.get("cut") == "2024-12-31" and
            spy.get("total_positive_sec_positions") == 504 and
            spy.get("valid_original_cusip_positions") == 478 and
            spy.get("permanent_security_identity_certified") is False and
            spy.get("full_engine_eligible_cuts_added") == 0,
            "Original first-cut SPY denominator/eligibility changed")
    require(original["accession"] == ACCESSION and original["accepted_utc"] == FIRST_PUBLISHED,
            "Original 13F identity changed")
    by_cusip = defaultdict(list)
    reportable = 0
    for item in rows:
        if not valid_cusip(item["cusip"]):
            continue
        if item["unit"] == "SH" and not item["option"]:
            reportable += 1
            by_cusip[item["cusip"]].append(item)
    result = []
    counts = Counter()
    for position in spy["position_rows"]:
        if not valid_cusip(position["cusip"]):
            continue
        original_rows = by_cusip.get(position["cusip"], [])
        distinct = {(x["issuer"], x["title"]) for x in original_rows}
        if not original_rows:
            status = "no-independent-original-13f-shares"
        elif len(distinct) > 1:
            status = "ambiguous-independent-13f-issuer-or-class"
        else:
            status = "independent-13f-cusip-and-class-observed"
        counts[status] += 1
        result.append({
            "source_position": position["source_position"],
            "cusip": position["cusip"],
            "spy_original_name": position["original_spy_name"],
            "weight": position["weight"], "cut": spy["cut"],
            "review_status": status,
            "other_manager_name_as_filed": ";".join(sorted({v[0] for v in distinct})),
            "other_manager_class_as_filed": ";".join(sorted({v[1] for v in distinct})),
            "other_manager_reported_shares": ";".join(sorted({x["shares_as_filed"] for x in original_rows})),
            "original_13f_accession": ACCESSION,
            "original_13f_sha256": original["raw_sha256"],
            "original_13f_accepted_utc": original["accepted_utc"],
            "security_master_certified": False,
            "historical_price_verified": False,
        })
    require(len(result) == 478 and len({r["source_position"] for r in result}) == 478,
            "SEC 13F reconciliation dropped original SPY positions")
    return {"schema": SCHEMA, "cut": spy["cut"], "original_13f_accession": ACCESSION,
            "original_13f_cik": CIK, "original_13f_index": INDEX,
            "original_13f_accepted_utc": original["accepted_utc"],
            "original_13f_sha256": original["raw_sha256"],
            "original_13f_byte_count": original["raw_byte_count"],
            "original_manager": "VANGUARD GROUP INC",
            "original_information_table_rows": len(rows),
            "original_nonoption_share_rows": reportable,
            "spy_positive_positions": 504, "spy_valid_cusip_positions": len(result),
            "status_counts": dict(sorted(counts.items())),
            "positions": result,
            "original_available_before_cut_by_sec_header": True,
            "original_first_publication_independently_authenticated": False,
            "issuer_cik_security_binding_certified": False,
            "vendor_historical_security_master_certified": False,
            "historical_prices_or_actions_certified": False,
            "full_engine_eligible_cuts_added": 0,
            "predictive_validation": "not-established"}


def validate_archive(raw, receipt):
    require(receipt.get("schema") == SCHEMA and
            receipt.get("source_url") == URL and
            receipt.get("original_13f_accession") == ACCESSION and
            receipt.get("original_sha256") == hashlib.sha256(raw).hexdigest() and
            receipt.get("original_byte_count") == len(raw) and
            receipt.get("original_13f_accepted_utc") == FIRST_PUBLISHED and
            receipt.get("first_publication_independently_authenticated") is False and
            receipt.get("predictive_validation") == "not-established" and
            receipt.get("full_engine_eligible_cuts_added") == 0,
            "Archived original 13F receipt differs from original bytes")
    return validate_complete_original(raw)


def archived(root=ROOT):
    root = Path(root)
    base = root / "data/historical/independent-13f-v1"
    compressed = base / (ACCESSION + ".txt.gz")
    receipt_file = base / "receipt.json"
    require(compressed.is_file() and receipt_file.is_file(), "Original independent SEC 13F not archived")
    compressed_bytes = compressed.read_bytes()
    require(len(compressed_bytes) <= 10 * 1024 * 1024, "Oversized archived 13F")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed_bytes)) as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    require(len(raw) <= MAX_DOCUMENT_BYTES, "Oversized decompressed SEC 13F")
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    require(hashlib.sha256(compressed_bytes).hexdigest() == receipt.get("archive_sha256"),
            "Independent SEC original compressed archive changed")
    original, rows = validate_archive(raw, receipt)
    return original, rows


def write_report(report, path, csv_path=None):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({k: v for k, v in report.items() if k != "positions"},
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if csv_path is not None:
        csv_dest = Path(csv_path)
        csv_dest.parent.mkdir(parents=True, exist_ok=True)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(report["positions"], key=lambda r: (-r["weight"], r["source_position"])))
        csv_dest.write_text(stream.getvalue(), encoding="utf-8")


def acquire(*, user_agent):
    # The pinned filing is immutable; re-running collection must not fetch
    # or redate the same historical source after it has been archived.
    if ORIGINAL.is_file() and RECEIPT.is_file():
        original, rows = archived()
        return compare(rows, spy_review(), original)
    require(not ORIGINAL.exists() and not RECEIPT.exists(),
            "Incomplete original 13F archive cannot be refreshed")
    validate_agent(user_agent)
    raw, http = get_original(URL, user_agent=user_agent, maximum=MAX_DOCUMENT_BYTES)
    original, rows = validate_complete_original(raw)
    archive_dir = ARCHIVE
    archive_dir.mkdir(parents=True, exist_ok=True)
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    receipt = {"schema": SCHEMA, "source_url": URL, "index_url": INDEX,
               "original_13f_accession": ACCESSION, "original_sha256": original["raw_sha256"],
               "original_byte_count": len(raw),
               "archive_sha256": hashlib.sha256(compressed).hexdigest(),
               "original_13f_accepted_utc": original["accepted_utc"],
               "retrieved_utc": datetime.now(timezone.utc).isoformat(),
               "http_last_modified_as_reported": http.get("http_last_modified"),
               "first_publication_independently_authenticated": False,
               "full_engine_eligible_cuts_added": 0,
               "predictive_validation": "not-established"}
    original_out = archive_dir / (ACCESSION + ".txt.gz")
    receipt_out = archive_dir / "receipt.json"
    if original_out.exists() or receipt_out.exists():
        # A re-run cannot replace or redate existing source bytes.
        require(original_out.is_file() and receipt_out.is_file() and
                original_out.read_bytes() == compressed,
                "Existing independent SEC 13F original must not be overwritten")
        previous = json.loads(receipt_out.read_text(encoding="utf-8"))
        require(previous["original_sha256"] == receipt["original_sha256"] and
                previous["archive_sha256"] == receipt["archive_sha256"],
                "Previously recorded independent SEC original differs")
    else:
        original_out.write_bytes(compressed)
        receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return compare(rows, spy_review(), original)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collect", action="store_true", help="Acquire exact original SEC 13F with SEC_USER_AGENT")
    p.add_argument("--verify", action="store_true", help="Verify stored original and generate source-only counts")
    p.add_argument("--report", type=Path, default=ROOT / "out/independent-13f-report.json")
    p.add_argument("--csv", type=Path, default=ROOT / "out/independent-13f-requests.csv")
    args = p.parse_args(argv)
    if args.collect:
        report = acquire(user_agent=os.environ.get("SEC_USER_AGENT"))
    else:
        original, rows = archived()
        report = compare(rows, spy_review(), original)
    if not args.verify:
        write_report(report, args.report, args.csv)
    print(json.dumps({k: v for k, v in report.items() if k != "positions"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
