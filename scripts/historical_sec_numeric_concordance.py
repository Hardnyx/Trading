"""Conservative numerical crosscheck: SEC FSD vs complete EDGAR iXBRL filing.

Only an XHTML/XML parseable inline primary filing and an exact subset of
unsegmented US-GAAP facts are supported. SEC FSD duration buckets and dates
may be rounded; this tool never treats unmatched data as evidence of error
in the filer or silently chooses among conflicting contextual observations.
No original byte, public availability, or historical instrument eligibility
is inferred from a numerical match.
"""
import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from scripts.filing_facts import TAGS
    from scripts.historical_sec_fsd_intake import SCHEMA as FSD_SCHEMA, require, extract
    from scripts.historical_sec_original_filing import reconcile
except ModuleNotFoundError:
    from filing_facts import TAGS
    from historical_sec_fsd_intake import SCHEMA as FSD_SCHEMA, require, extract
    from historical_sec_original_filing import reconcile

SCHEMA = "historical-sec-primary-inline-numeric-crosscheck-v1"
XBRLI = "http://www.xbrl.org/2003/instance"
IX = ("http://www.xbrl.org/2013/inlineXBRL",
      "http://www.xbrl.org/2008/inlineXBRL")
ISO = "http://www.xbrl.org/2003/iso4217"
IHTM_TRANSFORMS = {
    "http://www.xbrl.org/inlineXBRL/transformation/2015-02-26",
    "http://www.xbrl.org/inlineXBRL/transformation/2020-02-12",
    "http://www.xbrl.org/inlineXBRL/transformation/2022-02-16",
}
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
MAX_PRIMARY_BYTES = 48 * 1024 * 1024
MAX_REVIEW_ROWS = 50000


def primary_inline_document(raw, form):
    """Find exactly one named main filing in a complete SGML SEC submission.

    Never select supporting exhibits or derived EX-101 XML as a substitute
    for the original primary inline document.
    """
    require(isinstance(raw, bytes) and raw.startswith(b"<SEC-DOCUMENT>")
            and form in ("10-K", "10-Q", "10-K/A", "10-Q/A"),
            "Expected original complete submission and supported main form")
    blocks = re.findall(rb"(?ms)^<DOCUMENT>[ \t]*\r?\n(.*?)^</DOCUMENT>[ \t]*\r?$", raw)
    require(bool(blocks), "Complete submission has no well-delimited documents")
    primary = []
    for block in blocks:
        forms = re.findall(rb"(?m)^<TYPE>([^\r\n]+)", block)
        if len(forms) != 1 or forms[0].decode("ascii", errors="replace").strip() != form:
            continue
        filenames = re.findall(rb"(?m)^<FILENAME>([^\r\n]+)", block)
        require(len(filenames) == 1 and
                re.fullmatch(rb"[A-Za-z0-9_.-]{1,256}", filenames[0]),
                "Primary inline filing filename is missing or unsafe")
        sections = re.findall(rb"(?ms)^<TEXT>[ \t]*\r?\n(.*?)^</TEXT>[ \t]*\r?$", block)
        require(len(sections) == 1 and 40 <= len(sections[0]) <= MAX_PRIMARY_BYTES,
                "Primary filing has no unique supported text section")
        primary.append((filenames[0].decode("ascii"), sections[0]))
    require(len(primary) == 1, "Primary inline filing is absent or ambiguous")
    filename, document = primary[0]
    require(filename.lower().endswith((".htm", ".html", ".xhtml"))
            and b"<" in document,
            "Primary filing is not an inline HTML document")
    return filename, document


def xml_contexts_and_units(root, namespaces, cik):
    contexts, units = {}, {}
    expected_cik = str(int(cik))
    for node in root.iter():
        if node.tag == f"{{{XBRLI}}}context":
            identifier = node.find(f".//{{{XBRLI}}}identifier")
            if identifier is None or not (identifier.text or "").isdigit() or \
                    str(int(identifier.text)) != expected_cik:
                continue
            if any(e.tag.rsplit("}", 1)[-1] in (
                    "segment", "scenario", "explicitMember", "typedMember")
                   for e in node.iter()):
                continue
            period = node.find(f"{{{XBRLI}}}period")
            if period is None:
                continue
            instant = period.findtext(f"{{{XBRLI}}}instant")
            start = period.findtext(f"{{{XBRLI}}}startDate")
            end = period.findtext(f"{{{XBRLI}}}endDate")
            if instant and (start or end):
                continue
            try:
                if instant:
                    date.fromisoformat(instant)
                    contexts[node.get("id")] = (instant, 0)
                elif start and end:
                    first, last = date.fromisoformat(start), date.fromisoformat(end)
                    days = (last-first).days + 1
                    if not 45 <= days <= 390:
                        continue
                    quarters = int(days / (365.2425/4) + 0.5)
                    if 1 <= quarters <= 4:
                        contexts[node.get("id")] = (end, quarters)
            except ValueError:
                continue
        elif node.tag == f"{{{XBRLI}}}unit":
            unit_id = node.get("id")
            def measures(element):
                values = []
                for measure in element.iter(f"{{{XBRLI}}}measure"):
                    prefix, sep, local = (measure.text or "").strip().partition(":")
                    if not sep:
                        return []
                    values.append((namespaces.get(prefix), local))
                return values
            divisor = node.find(f"{{{XBRLI}}}divide")
            if divisor is None and measures(node) == [(ISO, "USD")]:
                units[unit_id] = "USD"
            elif divisor is not None:
                top = divisor.find(f"{{{XBRLI}}}unitNumerator")
                bottom = divisor.find(f"{{{XBRLI}}}unitDenominator")
                if top is not None and bottom is not None and \
                        measures(top) == [(ISO, "USD")] and \
                        measures(bottom) == [(XBRLI, "shares")]:
                    units[unit_id] = "USD/shares"
    return contexts, units


def exact_primary_facts(raw, cik):
    """Normalize supported iXBRL fractions into exact Decimal fact sets."""
    require(type(raw) is bytes and 40 <= len(raw) <= MAX_PRIMARY_BYTES,
            "Missing or oversized primary iXBRL bytes")
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "DTD or entities are prohibited in primary filing")
    # SEC-DOCUMENT SGML envelopes can insert ASCII whitespace before a
    # primary XHTML XML declaration. Normalize only parser input, never the
    # original byte hash or historical evidence used for publication.
    parse_bytes = raw.lstrip(b" \t\r\n")
    require(parse_bytes.startswith(b"<"),
            "Unsupported leading primary document content")
    namespaces = {}
    try:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(parse_bytes), events=("start-ns",)):
            require(prefix not in namespaces or namespaces[prefix] == uri,
                    "Ambiguous rebound XML namespace")
            namespaces[prefix] = uri
        root = ET.fromstring(parse_bytes)
    except ET.ParseError as exc:
        raise ValueError(
            "Primary inline document is not well-formed XHTML; no numeric certification"
        ) from exc
    contexts, units = xml_contexts_and_units(root, namespaces, cik)
    facts = defaultdict(set)
    examined = 0
    unsupported = 0
    for node in root.iter():
        if node.tag not in {f"{{{uri}}}nonFraction" for uri in IX}:
            continue
        prefix, sep, local = node.get("name", "").partition(":")
        taxonomy = namespaces.get(prefix, "") if sep else ""
        if local not in TAGS or \
                not re.fullmatch(r"https?://fasb\.org/us-gaap/[0-9]{4}", taxonomy):
            continue
        examined += 1
        version = "us-gaap/" + taxonomy.rsplit("/", 1)[-1]
        ctx = contexts.get(node.get("contextRef"))
        uom = units.get(node.get("unitRef"))
        if ctx is None or uom is None or node.get(XSI_NIL) in ("1", "true") \
                or node.get("sign", "") not in ("", "-"):
            unsupported += 1
            continue
        transform = node.get("format")
        if transform:
            tprefix, tsep, tname = transform.partition(":")
            if not tsep or tname != "num-dot-decimal" or \
                    namespaces.get(tprefix) not in IHTM_TRANSFORMS:
                unsupported += 1
                continue
        value_text = "".join(node.itertext()).strip().replace(",", "")
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value_text) is None:
            unsupported += 1
            continue
        try:
            scale = int(node.get("scale", "0"))
            if not -12 <= scale <= 12:
                unsupported += 1
                continue
            amount = Decimal(value_text) * (Decimal(10) ** scale)
            if node.get("sign") == "-":
                amount = -amount
        except (InvalidOperation, ValueError):
            unsupported += 1
            continue
        if not amount.is_finite():
            unsupported += 1
            continue
        key = (local, version, ctx[0], ctx[1], uom)
        facts[key].add(amount)
    return facts, {"supported_us_gaap_inline_facts_seen": examined,
                   "unsupported_or_nonconsolidated_inline_facts": unsupported,
                   "unique_supported_context_keys": len(facts)}


def compare(report, original_path, accession, *, archive_path=None,
            max_review_rows=MAX_REVIEW_ROWS):
    require(type(max_review_rows) is int and 1 <= max_review_rows <= MAX_REVIEW_ROWS,
            "Review row limit must be explicit and positive")
    verified_header = reconcile(report, original_path, accession,
                                archive_path=archive_path)
    require(report.get("schema") == FSD_SCHEMA and
            isinstance(report.get("facts"), list),
            "Expected complete uncertified FSD NUM report")
    source_rows_reconstructed = False
    if archive_path is not None:
        # Rehashing the ZIP alone would not detect edited extracted report
        # rows. Recreate the exact requested selection from the source bytes.
        require(isinstance(report.get("requested_ciks"), list)
                and bool(report["requested_ciks"])
                and isinstance(report.get("requested_tags"), list),
                "FSD request selection provenance is incomplete")
        regenerated = extract(
            archive_path, report["cutoff_utc"], report["requested_ciks"],
            tag_filters=report["requested_tags"], max_facts=200000)
        require(regenerated["archive_sha256"] == report["archive_sha256"]
                and regenerated["submissions"] == report["submissions"]
                and regenerated["facts"] == report["facts"]
                and regenerated["selected_submission_count"] ==
                    report["selected_submission_count"]
                and regenerated["selected_fact_count"] ==
                    report["selected_fact_count"]
                and regenerated["excluded_target_submissions_after_cutoff"] ==
                    report["excluded_target_submissions_after_cutoff"]
                and regenerated["excluded_target_nonfinancial_forms"] ==
                    report["excluded_target_nonfinancial_forms"],
                "FSD report data differ from original SEC ZIP re-extraction")
        source_rows_reconstructed = True
    raw = Path(original_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() ==
            verified_header["original_filing_sha256"],
            "Original bytes changed during numerical reconciliation")
    form = next(s["form"] for s in report["submissions"]
                if s["adsh"] == accession)
    filename, primary = primary_inline_document(raw, form)
    original_facts, stats = exact_primary_facts(primary,
                                               verified_header["cik"])
    selected = [v for v in report["facts"] if v.get("adsh") == accession]
    require(len(selected) <= max_review_rows,
            "FSD selected rows exceed review ceiling; no silent truncation")
    output, counts = [], {
        "exact_match": 0, "decimal_mismatch": 0,
        "missing_in_original_subset": 0, "ambiguous_original": 0,
        "ineligible_derived_dimension": 0, "unsupported_derived_tag_or_unit": 0,
        "missing_derived_numeric_value": 0,
    }
    for fact in selected:
        raw_value = fact.get("value_decimal_as_filed")
        tag, version, uom = fact["tag"], fact["version"], fact["uom"]
        if not fact.get("segments_column_present") or \
                fact.get("segments") != "" or fact.get("coreg") != "" or \
                fact.get("consolidated_unsegmented_candidate") is not True:
            status = "ineligible_derived_dimension"
        elif tag not in TAGS or \
                not re.fullmatch(r"us-gaap/[0-9]{4}", version) or \
                uom not in ("USD", "USD/shares"):
            status = "unsupported_derived_tag_or_unit"
        elif raw_value is None:
            status = "missing_derived_numeric_value"
        else:
            try:
                desired = Decimal(raw_value)
                require(desired.is_finite(), "Nonfinite derived numeric value")
                qtrs = fact["qtrs"]
                require(type(qtrs) is int and 0 <= qtrs <= 4,
                        "Invalid derived quarter bucket")
                key = (tag, version, fact["ddate"], qtrs, uom)
                candidates = original_facts.get(key, set())
                if not candidates:
                    status = "missing_in_original_subset"
                elif len(candidates) > 1:
                    status = "ambiguous_original"
                else:
                    status = ("exact_match" if next(iter(candidates)) == desired
                              else "decimal_mismatch")
            except (InvalidOperation, TypeError) as exc:
                raise ValueError("Invalid derived numeric report") from exc
        counts[status] += 1
        output.append({
            "accession": accession, "tag": tag, "version": version,
            "ddate": fact["ddate"], "qtrs": fact["qtrs"], "uom": uom,
            "coreg": fact["coreg"], "segments": fact["segments"],
            "derived_value_decimal": raw_value,
            "comparison_status": status,
            "matched_original_primary_value_decimal":
                str(next(iter(candidates))) if status == "exact_match" else None,
        })
    require(sum(counts.values()) == len(selected),
            "Numeric crosscheck failed to account for selected FSD rows")
    return {
        "schema": SCHEMA,
        "scope": "limited-exact-primary-inline-subset-research-only",
        "accession": accession,
        "original_complete_filing_sha256":
            verified_header["original_filing_sha256"],
        "original_primary_filename": filename,
        "original_primary_sha256": hashlib.sha256(primary).hexdigest(),
        "source_fsd_zip_hash_reverified":
            verified_header["fsd_original_zip_bytes_reverified"],
        "derived_fsd_rows_reproduced_from_original_zip":
            source_rows_reconstructed,
        "original_header_matches_derived_fsd":
            verified_header["header_form_filed_accepted_cik_accession_match"],
        "original_header_fsd_minute_only_consistent":
            verified_header["fsd_acceptance_minute_bucket_consistent_not_exact"],
        "original_header_accepted_utc":
            verified_header["original_accepted_utc_from_sec_header"],
        "fsd_reported_accepted_utc":
            verified_header["fsd_accepted_utc_as_reported"],
        "source_original_first_dissemination_verified": False,
        "historical_security_identity_certified": False,
        "selected_derived_rows": len(selected),
        "comparison_counts": counts,
        "original_inline_coverage": stats,
        "rounding_or_month_end_normalization_not_assumed": True,
        "full_xbrl_document_numeric_fact_set_reconciled": False,
        "original_filing_publication_independently_verified": False,
        "fundamentals_and_quality_component_certified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
        "rows": output,
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
        require(result["full_xbrl_document_numeric_fact_set_reconciled"] is False
                and result["fundamentals_and_quality_component_certified"] is False
                and result["eligible_full_engine_cuts_added"] == 0
                and result["original_filing_publication_independently_verified"] is False,
                "Limited numerical matching cannot promote PIT validation")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+"\n",
                               encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "rows"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
