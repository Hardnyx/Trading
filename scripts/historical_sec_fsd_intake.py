"""Stream local SEC Financial Statement Data Sets without backdating availability.

The quarterly ZIP is a retrospective research source. Submission acceptance
times are reported metadata, not independent proof that an original filing or
its numeric content was archived before a historical trading decision.
"""
import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "historical-sec-fsd-research-intake-v1"
TEMPLATE_SCHEMA = "historical-sec-fsd-original-source-request-v1"
SOURCE_PAGE = "https://www.sec.gov/dera/data/financial-statement-data-sets.html"
FORMS = frozenset(("10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT",
                  "10-KT/A", "10-QT", "10-QT/A", "20-F", "20-F/A",
                  "40-F", "40-F/A", "6-K", "6-K/A"))
ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")
QUARTER_ZIP = re.compile(r"([0-9]{4}q[1-4])\.zip\Z", re.IGNORECASE)
SEC_EASTERN = ZoneInfo("America/New_York")
REQUIRED_SUB = frozenset(("adsh", "cik", "name", "form", "period",
                         "filed", "accepted", "instance"))
REQUIRED_NUM = frozenset(("adsh", "tag", "version", "coreg", "ddate",
                         "qtrs", "uom", "value", "footnote"))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def cik_number(value):
    require(isinstance(value, str) and
            re.fullmatch(r"[0-9]{1,10}", value) is not None and
            int(value) > 0, "CIK must be a 1-10-digit positive identifier")
    return str(int(value))


def cutoff_timestamp(value):
    require(isinstance(value, str), "Explicit timezone-aware cutoff required")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO cutoff timestamp") from exc
    require(moment.tzinfo is not None and moment.utcoffset() is not None,
            "Historical cutoff must carry an explicit timezone")
    return moment.astimezone(timezone.utc)


def as_filed_acceptance(value):
    """Parse the SEC SUB timestamp without rounding a nonzero subsecond.

    Official quarterly FSD SUB rows can end in .0 (numeric export formatting).
    The original SEC-HEADER carries second precision, so a nonzero fractional
    part cannot be reconciled as an exact documented acceptance time.
    """
    require(isinstance(value, str), "SEC acceptance timestamp missing")
    matched = re.fullmatch(
        r"([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.0{1,6})?",
        value,
    )
    require(matched is not None,
            "SEC accepted timestamp requires exact seconds or zero-only fraction")
    try:
        local = datetime.strptime(matched.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("Invalid SEC accepted calendar timestamp") from exc
    eastern = local.replace(tzinfo=SEC_EASTERN, fold=0)
    require(eastern.utcoffset() ==
            local.replace(tzinfo=SEC_EASTERN, fold=1).utcoffset(),
            "Ambiguous SEC Eastern timestamp requires original filing audit")
    return eastern.astimezone(timezone.utc)


def fsds_day(value, label):
    require(isinstance(value, str) and
            re.fullmatch(r"[0-9]{8}", value) is not None,
            "Noncanonical SEC " + label + " date")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as exc:
        raise ValueError("Invalid SEC " + label + " date") from exc


def decimal_text(raw):
    if raw in ("", None):
        return None
    require(isinstance(raw, str) and raw.strip() == raw,
            "Noncanonical SEC numeric value")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("SEC NUM value not decimal") from exc
    require(value.is_finite(), "SEC NUM value must be finite")
    return raw


def archive_members(zip_file):
    members = {}
    for info in zip_file.infolist():
        name = info.filename.replace("\\", "/")
        parts = name.split("/")
        require(name and not name.startswith("/") and
                all(part not in ("", ".", "..") for part in parts if part) and
                not re.match(r"^[A-Za-z]:", name),
                "Unsafe filename in SEC archive")
        if info.is_dir():
            continue
        stem = parts[-1].lower()
        require(stem not in members, "Duplicate SEC ZIP member name: " + stem)
        members[stem] = info
    require("sub.txt" in members and "num.txt" in members,
            "SEC ZIP must contain SUB and NUM data")
    return members


def table_reader(archive, member, required):
    with archive.open(member) as handle:
        with io.TextIOWrapper(handle, encoding="utf-8-sig",
                              errors="strict", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            require(reader.fieldnames is not None and
                    len(set(reader.fieldnames)) == len(reader.fieldnames)
                    and required.issubset(reader.fieldnames),
                    "SEC tabular header missing required fields")
            has_segments = "segments" in reader.fieldnames
            for line_number, row in enumerate(reader, start=2):
                require(None not in row and
                        all(v is not None for v in row.values()),
                        "Malformed SEC TSV row at line " + str(line_number))
                yield row, has_segments


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as src:
        while True:
            part = src.read(1024*1024)
            if not part:
                break
            h.update(part)
    return h.hexdigest()


def extract(archive_path, cut_asof, ciks, *, tag_filters=(),
            max_facts=50000):
    path = Path(archive_path)
    match = QUARTER_ZIP.fullmatch(path.name)
    require(match is not None and path.is_file(),
            "Expected existing SEC YYYYqN.zip archive")
    cutoff = cutoff_timestamp(cut_asof)
    require(type(max_facts) is int and 0 < max_facts <= 200000,
            "Explicit non-truncating maximum fact count required")
    require(isinstance(ciks, (tuple, list)) and ciks and
            isinstance(tag_filters, (tuple, list)),
            "Explicit CIK selection is required")
    targets = set(map(cik_number, ciks))
    tags = set(tag_filters)
    require(all(isinstance(t, str) and
                re.fullmatch(r"[A-Za-z0-9_]{1,256}", t) is not None
                for t in tags), "Noncanonical SEC XBRL tag filter")
    archive_sha256 = digest_file(path)
    submissions = {}
    excluded_late = 0
    excluded_form = 0
    with ZipFile(path) as z:
        members = archive_members(z)
        for sub, _ in table_reader(z, members["sub.txt"], REQUIRED_SUB):
            if cik_number(sub["cik"]) not in targets:
                continue
            adsh = sub["adsh"]
            require(ACCESSION.fullmatch(adsh) is not None,
                    "Invalid SEC accession number")
            require(adsh not in submissions, "Repeated SEC accession")
            if sub["form"] not in FORMS:
                excluded_form += 1
                continue
            accepted = as_filed_acceptance(sub["accepted"])
            fsds_day(sub["filed"], "filed")
            fsds_day(sub["period"], "period")
            if accepted > cutoff:
                excluded_late += 1
                continue
            require(sub["instance"] and
                    re.fullmatch(r"[^/\\\s]+", sub["instance"]) is not None,
                    "Invalid SEC filing instance path")
            cik = cik_number(sub["cik"])
            submissions[adsh] = {
                "adsh": adsh, "cik": cik, "company_name_as_filed": sub["name"],
                "form": sub["form"], "form_is_amendment": sub["form"].endswith("/A"),
                "filed_day_reported": fsds_day(sub["filed"], "filed").isoformat(),
                "fiscal_period_end_reported":
                    fsds_day(sub["period"], "period").isoformat(),
                "accepted_eastern_as_filed": sub["accepted"],
                "accepted_utc": accepted.isoformat(),
                "instance": sub["instance"],
                "edgar_submission_folder":
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/",
                "original_filing_bytes_verified": False,
                "first_publication_independently_verified": False,
            }
        require(len(submissions) <= 100000, "Too many SEC submissions selected")
        facts = []
        seen_keys = set()
        segments_column_present = None
        for num, has_segments in table_reader(
                z, members["num.txt"], REQUIRED_NUM):
            segments_column_present = has_segments
            filing = submissions.get(num["adsh"])
            if filing is None:
                continue
            tag = num["tag"]
            if tags and tag not in tags:
                continue
            require(isinstance(tag, str) and tag and
                    num["version"] and num["uom"],
                    "Incomplete NUM tag, taxonomy or unit")
            dday = fsds_day(num["ddate"], "ddate")
            accepted_day = date.fromisoformat(filing["accepted_utc"][:10])
            require(dday <= accepted_day,
                    "Numeric period appears after SEC acceptance date")
            try:
                qtrs = int(num["qtrs"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Noninteger SEC qtrs") from exc
            require(str(qtrs) == num["qtrs"] and 0 <= qtrs <= 100,
                    "Invalid NUM duration quarters")
            segments = num.get("segments", "") if has_segments else None
            coreg = num["coreg"]
            key = (num["adsh"], tag, num["version"], coreg,
                   num["ddate"], qtrs, num["uom"], segments)
            require(key not in seen_keys, "Duplicate SEC NUM key")
            seen_keys.add(key)
            facts.append({
                "adsh": num["adsh"], "cik": filing["cik"],
                "accepted_utc": filing["accepted_utc"],
                "form": filing["form"], "amendment": filing["form_is_amendment"],
                "tag": tag, "version": num["version"],
                "ddate": dday.isoformat(), "qtrs": qtrs, "uom": num["uom"],
                "coreg": coreg, "segments": segments,
                "segments_column_present": has_segments,
                "value_decimal_as_filed": decimal_text(num["value"]),
                "footnote_as_filed": num["footnote"],
                "consolidated_unsegmented_candidate":
                    has_segments and coreg == "" and segments == "",
                "ready_for_historical_valuation": False,
            })
            require(len(facts) <= max_facts,
                    "Matching NUM facts exceed limit; abort instead of truncating")
    return {
        "schema": SCHEMA,
        "scope": "retrospective-as-filed-research-only",
        "source_official_page": SOURCE_PAGE,
        "quarter_archive": match.group(1).lower(),
        "archive_file_name": path.name,
        "archive_sha256": archive_sha256,
        "cutoff_utc": cutoff.isoformat(),
        "requested_ciks": sorted(targets),
        "requested_tags": sorted(tags),
        "selected_submission_count": len(submissions),
        "excluded_target_submissions_after_cutoff": excluded_late,
        "excluded_target_nonfinancial_forms": excluded_form,
        "selected_fact_count": len(facts),
        "segments_column_present_in_num": segments_column_present,
        "submissions": sorted(submissions.values(), key=lambda row: (
            row["accepted_utc"], row["adsh"])),
        "facts": sorted(facts, key=lambda row: (
            row["adsh"], row["tag"], row["ddate"], row["qtrs"],
            row["uom"], row["coreg"], str(row["segments"]))),
        "duplicate_periods_from_multiple_submissions_not_auto_resolved": True,
        "ticker_identity_or_security_master_certified": False,
        "original_filing_publication_independently_verified": False,
        "quarterly_extract_available_at_historical_cutoff_proven": False,
        "filer_accounting_tag_semantics_reconciled": False,
        "fundamentals_and_quality_component_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def template():
    return {
        "schema": TEMPLATE_SCHEMA,
        "source_page": SOURCE_PAGE,
        "source_zip_example":
            "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip",
        "archive_original_expected": "2024q4.zip",
        "local_zip_required": True,
        "requires_sub_txt_and_num_txt": True,
        "fields_kept": ["adsh", "cik", "form", "filed", "accepted",
                        "instance", "tag", "version", "ddate", "qtrs",
                        "uom", "coreg", "segments", "value", "footnote"],
        "required_user_inputs": ["archive ZIP", "historical decision time with timezone",
                                  "historically verified CIK identifiers"],
        "research_only": True,
        "source_website_access_not_attempted": True,
        "original_filing_archive_and_publication_audit_needed": True,
        "eligible_full_engine_cuts": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template", type=Path)
    mode.add_argument("--archive", type=Path)
    parser.add_argument("--cutoff")
    parser.add_argument("--cik", action="append")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--max-facts", type=int, default=50000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.template is not None:
        require(args.cutoff is None and args.cik is None and
                not args.tag and args.output is None,
                "Template generation cannot take market or issuer inputs")
        output = args.template
        result = template()
    else:
        require(args.cutoff is not None and bool(args.cik),
                "Original ZIP, explicit decision cutoff and CIK required")
        result = extract(args.archive, args.cutoff, args.cik,
                         tag_filters=args.tag, max_facts=args.max_facts)
        output = args.output
    if args.verify:
        require(result["predictive_validation"] == "not-established"
                and (result.get("eligible_full_engine_cuts_added",
                                result.get("eligible_full_engine_cuts")) == 0)
                and not result.get("fundamentals_and_quality_component_certified",
                                   False),
                "SEC extract may never activate a causal market replay")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n",
                          encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("submissions", "facts")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
