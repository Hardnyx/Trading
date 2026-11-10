"""Research-only numerical crosscheck against an embedded SEC XBRL instance.

The selected XML must occur inside the SAME complete accession .txt whose
SEC-HEADER is reconciled against the quarterly FSD extract. This is separate
from the primary iXBRL comparison: an extracted instance, even when matching,
never proves the primary inline document, historical availability or skill.
"""
import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from scripts.filing_facts import TAGS
    from scripts.historical_sec_fsd_intake import extract, require
    from scripts.historical_sec_original_filing import reconcile, MAX_BYTES
    from scripts.historical_sec_numeric_concordance import (
        XBRLI, ISO, XSI_NIL, xml_contexts_and_units,
    )
except ModuleNotFoundError:
    from filing_facts import TAGS
    from historical_sec_fsd_intake import extract, require
    from historical_sec_original_filing import reconcile, MAX_BYTES
    from historical_sec_numeric_concordance import (
        XBRLI, ISO, XSI_NIL, xml_contexts_and_units,
    )

SCHEMA = "historical-sec-embedded-extracted-instance-crosscheck-v1"
MAX_INSTANCE_BYTES = 64 * 1024 * 1024
MAX_ROWS = 50000
US_GAAP_NS = re.compile(r"https?://fasb\.org/us-gaap/([0-9]{4})\Z")
DECIMAL = re.compile(r"-?[0-9]{1,30}(?:\.[0-9]{1,30})?(?:[Ee][+-]?[0-9]{1,2})?\Z")


def embedded_instance(complete, filename):
    """Select one specifically named XML instance from the original SGML."""
    require(type(complete) is bytes and complete.startswith(b"<SEC-DOCUMENT>")
            and 40 <= len(complete) <= MAX_BYTES,
            "Complete EDGAR accession bytes are required")
    require(isinstance(filename, str) and re.fullmatch(
        r"[A-Za-z0-9_.-]{1,256}\.xml", filename, flags=re.IGNORECASE),
        "Expected a safe original XML instance filename")
    blocks = re.findall(
        rb"(?ms)^<DOCUMENT>[ \t]*\r?\n(.*?)^</DOCUMENT>[ \t]*\r?$",
        complete,
    )
    require(bool(blocks), "No original SEC-DOCUMENT attachments found")
    found = []
    for block in blocks:
        names = re.findall(rb"(?m)^<FILENAME>([^\r\n]+)", block)
        if len(names) != 1 or names[0].decode("ascii", errors="replace") != filename:
            continue
        kinds = re.findall(rb"(?m)^<TYPE>([^\r\n]+)", block)
        require(len(kinds) == 1 and kinds[0].strip() in
                (b"XML", b"EX-101.INS", b"EX-101.INS/A"),
                "Matching XML filename is not an identified instance document")
        sections = re.findall(
            rb"(?ms)^<TEXT>[ \t]*\r?\n(.*?)^</TEXT>[ \t]*\r?$",
            block,
        )
        require(len(sections) == 1 and
                40 <= len(sections[0]) <= MAX_INSTANCE_BYTES,
                "Original extracted instance payload absent or oversized")
        found.append(sections[0])
    require(len(found) == 1,
            "Named extracted instance missing or duplicated in complete filing")
    return found[0]


def instance_facts(raw, cik):
    """Parse exact numeric XML literals, excluding dimensions and extensions."""
    require(type(raw) is bytes and 40 <= len(raw) <= MAX_INSTANCE_BYTES,
            "Missing or oversized SEC XML instance")
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "External entities and DTD are forbidden in SEC instance")
    doc = raw.lstrip(b" \t\r\n")
    require(doc.startswith(b"<"), "Unrecognized XML preamble")
    namespaces = {}
    try:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(doc), events=("start-ns",)):
            require(prefix not in namespaces or namespaces[prefix] == uri,
                    "Ambiguous rebound instance namespace")
            namespaces[prefix] = uri
        root = ET.fromstring(doc)
    except ET.ParseError as exc:
        raise ValueError("Embedded XBRL instance is not well-formed XML") from exc
    require(root.tag == f"{{{XBRLI}}}xbrl",
            "Selected source is not an XBRL instance root")
    contexts, units = xml_contexts_and_units(root, namespaces, cik)
    facts = defaultdict(set)
    scanned = 0
    excluded = 0
    for element in root:
        if not element.tag.startswith("{") or "}" not in element.tag:
            continue
        uri, local = element.tag[1:].split("}", 1)
        version = US_GAAP_NS.fullmatch(uri)
        if version is None or local not in TAGS:
            continue
        scanned += 1
        context = contexts.get(element.get("contextRef"))
        unit = units.get(element.get("unitRef"))
        literal = (element.text or "").strip()
        if context is None or unit is None or (
                element.get(XSI_NIL) in ("1", "true")) or (
                DECIMAL.fullmatch(literal) is None):
            excluded += 1
            continue
        try:
            amount = Decimal(literal)
        except InvalidOperation:
            excluded += 1
            continue
        if not amount.is_finite():
            excluded += 1
            continue
        key = (local, "us-gaap/" + version.group(1),
               context[0], context[1], unit)
        facts[key].add(amount)
    return facts, {
        "unsegmented_supported_literals_examined": scanned,
        "excluded_unsupported_context_or_literal": excluded,
        "unique_context_keys": len(facts),
    }


def compare(report, original_path, accession, *, archive_path=None,
            max_rows=MAX_ROWS):
    """Crosscheck a *secondary* original attachment without promoting a cut."""
    require(type(max_rows) is int and 1 <= max_rows <= MAX_ROWS,
            "Explicit finite comparison limit required")
    header = reconcile(report, original_path, accession,
                       archive_path=archive_path)
    require(isinstance(report.get("facts"), list) and
            isinstance(report.get("requested_ciks"), list) and
            isinstance(report.get("requested_tags"), list),
            "Original SEC FSD report and source selection are required")
    reconstructed = False
    if archive_path is not None:
        source = extract(
            archive_path, report["cutoff_utc"],
            report["requested_ciks"],
            tag_filters=report["requested_tags"], max_facts=200000,
        )
        require(source["archive_sha256"] == report["archive_sha256"]
                and source["submissions"] == report["submissions"]
                and source["facts"] == report["facts"]
                and source["selected_submission_count"] ==
                    report["selected_submission_count"]
                and source["selected_fact_count"] ==
                    report["selected_fact_count"]
                and source["excluded_target_submissions_after_cutoff"] ==
                    report["excluded_target_submissions_after_cutoff"]
                and source["excluded_target_nonfinancial_forms"] ==
                    report["excluded_target_nonfinancial_forms"],
                "Derived FSD rows differ from original quarterly ZIP")
        reconstructed = True
    selected = [v for v in report["submissions"] if v.get("adsh") == accession]
    require(len(selected) == 1 and
            isinstance(selected[0].get("instance"), str),
            "Exactly one FSD accession and instance name required")
    raw = Path(original_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() ==
            header["original_filing_sha256"],
            "SEC complete submission changed after header reconciliation")
    instance = embedded_instance(raw, selected[0]["instance"])
    exact, stats = instance_facts(instance, header["cik"])
    rows = [x for x in report["facts"] if x.get("adsh") == accession]
    require(len(rows) <= max_rows, "Derived rows exceed safety limit")
    counts = dict.fromkeys((
        "exact_literal_match", "decimal_mismatch",
        "missing_in_embedded_instance", "ambiguous_instance",
        "ineligible_derived_dimension", "unsupported_derived_tag_or_unit",
        "missing_derived_numeric_value",
    ), 0)
    compared = []
    for row in rows:
        candidates = set()
        tag, version, uom = row["tag"], row["version"], row["uom"]
        if not row.get("segments_column_present") or row.get("segments") != "" or (
                row.get("coreg") != "" or
                row.get("consolidated_unsegmented_candidate") is not True):
            status = "ineligible_derived_dimension"
        elif tag not in TAGS or not re.fullmatch(
                r"us-gaap/[0-9]{4}", version) or uom not in ("USD", "USD/shares"):
            status = "unsupported_derived_tag_or_unit"
        elif row.get("value_decimal_as_filed") is None:
            status = "missing_derived_numeric_value"
        else:
            literal = row["value_decimal_as_filed"]
            require(isinstance(literal, str) and
                    DECIMAL.fullmatch(literal) is not None,
                    "Noncanonical SEC FSD numeric literal")
            key = (tag, version, row["ddate"], row["qtrs"], uom)
            candidates = exact.get(key, set())
            if not candidates:
                status = "missing_in_embedded_instance"
            elif len(candidates) != 1:
                status = "ambiguous_instance"
            else:
                status = ("exact_literal_match"
                          if next(iter(candidates)) == Decimal(literal)
                          else "decimal_mismatch")
        counts[status] += 1
        compared.append({
            "tag": tag, "version": version, "ddate": row["ddate"],
            "qtrs": row["qtrs"], "uom": uom,
            "segments": row.get("segments"), "coreg": row.get("coreg"),
            "comparison_status": status,
            "derived_value_as_reported": row["value_decimal_as_filed"],
            "embedded_value_if_unique":
                str(next(iter(candidates))) if len(candidates) == 1 else None,
        })
    require(sum(counts.values()) == len(rows),
            "Derived rows were not fully accounted for")
    return {
        "schema": SCHEMA,
        "scope": "limited-secondary-embedded-instance-research-only",
        "accession": accession,
        "original_complete_submission_sha256": header["original_filing_sha256"],
        "embedded_instance_filename": selected[0]["instance"],
        "embedded_instance_sha256": hashlib.sha256(instance).hexdigest(),
        "embedded_instance_found_in_same_original_submission": True,
        "source_fsd_archive_bytes_reverified": reconstructed,
        "header_acceptance_exact_match":
            header["header_form_filed_accepted_cik_accession_match"],
        "header_acceptance_minute_only_consistent":
            header["fsd_acceptance_minute_bucket_consistent_not_exact"],
        "original_acceptance_utc": header["original_accepted_utc_from_sec_header"],
        "source_instance_is_extracted_not_primary_inline": True,
        "original_primary_inline_document_numeric_facts_reconciled": False,
        "original_first_publication_independently_verified": False,
        "complete_original_numeric_fact_set_reconciled": False,
        "historical_security_identity_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
        "selected_rows": len(rows), "comparison_counts": counts,
        "instance_scan": stats, "rows": compared,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fsd-report", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--accession", required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    report = json.loads(args.fsd_report.read_text(encoding="utf-8"))
    result = compare(report, args.original, args.accession,
                     archive_path=args.archive)
    if args.verify:
        require(result["original_primary_inline_document_numeric_facts_reconciled"]
                is False and
                result["original_first_publication_independently_verified"]
                is False and result["eligible_full_engine_cuts_added"] == 0
                and result["predictive_validation"] == "not-established",
                "Extracted instance cannot certify the primary iXBRL or PIT")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
