"""Inspect bounded original SEC XML prologs without modifying filing bytes.

This diagnostic only explains a parser failure. It is not an alternative data
source, XML normalizer, source-vintage certificate or numeric reconciliation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

try:
    from scripts.historical_sec_numeric_concordance import primary_inline_document
    from scripts.historical_sec_embedded_instance import embedded_instance
    from scripts.historical_sec_fsd_intake import require
except ModuleNotFoundError:
    from historical_sec_numeric_concordance import primary_inline_document
    from historical_sec_embedded_instance import embedded_instance
    from historical_sec_fsd_intake import require

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = ROOT / "data/historical/sec-first-cut-original-source-observation-v1.json"
FSD_REPORT = ROOT / "data/historical/sec-first-cut-fsd-extract-v1.json"
ORIGINAL = ROOT / "out/sec-originals/0000950170-24-118967.txt"
SCHEMA = "sec-first-cut-source-xml-prolog-inspection-v1"


def inspect_document(data):
    """Return only initial byte positions and limited, reversible hex."""
    require(type(data) is bytes and 40 <= len(data) <= 64*1024*1024,
            "Original document payload absent or outside size bounds")
    declared = [m.start() for m in re.finditer(rb"<\?xml(?:[ \t\r\n]|>)", data[:1024])]
    offset = len(data) - len(data.lstrip(b" \t\r\n"))
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "first_160_bytes_hex": data[:160].hex(),
        "xml_declarations_in_first_1024_bytes": declared[:8],
        "first_non_ascii_whitespace_offset": offset,
        "begins_with_xml_declaration_after_ascii_whitespace":
            data[offset:offset+5] == b"<?xml",
        "contains_utf8_bom_in_first_8_bytes": b"\xef\xbb\xbf" in data[:8],
        "first_two_lines_hex": [
            line[:160].hex() for line in data.splitlines()[:2]
        ],
    }


def inspect(original=ORIGINAL, observation=OBSERVATION, fsd_report=FSD_REPORT):
    raw = Path(original).read_bytes()
    observed = json.loads(Path(observation).read_bytes())
    report = json.loads(Path(fsd_report).read_bytes())
    original_info = observed["source_provenance"]["original_edgar_filing"]
    require(hashlib.sha256(raw).hexdigest() == original_info["sha256"]
            and report["submissions"][0]["adsh"] == original_info["accession"]
            and report["submissions"][0]["instance"] ==
                "msft-20240930_htm.xml"
            and observed["eligible_full_engine_cuts_added"] == 0,
            "XML probe requires exact previously reviewed original EDGAR bytes")
    filename, primary = primary_inline_document(raw, "10-Q")
    instance = embedded_instance(raw, report["submissions"][0]["instance"])
    return {
        "schema": SCHEMA,
        "original_edgar_sha256": original_info["sha256"],
        "original_bytes_reverified": True,
        "primary_filename": filename,
        "primary": inspect_document(primary),
        "extracted_instance_filename": report["submissions"][0]["instance"],
        "extracted_instance": inspect_document(instance),
        "parser_or_numeric_reconciliation_performed": False,
        "original_first_publication_independently_verified": False,
        "eligible_full_engine_cuts_added": 0,
        "confirmatory_origins_added": 0,
        "predictive_validation": "not-established",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = inspect(args.original)
    if args.output:
        require(args.output.resolve().is_relative_to((ROOT/"out").resolve()),
                "Original XML probe output must remain under ignored out/")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
