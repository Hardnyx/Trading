"""Unwrap only the two SEC SGML TEXT container tags observed in original EDGAR.

The markers are filing transport wrappers around a real XML declaration, not
part of the underlying iXBRL/XBRL XML. Original raw bytes and hashes are
retained by the caller; malformed or unknown wrappers remain fatal.
"""


def unwrap_sec_xml_payload(raw, kind):
    """Return XML parser bytes without an exact SEC wrapper, if present."""
    if type(raw) is not bytes or kind not in ("XBRL", "XML"):
        raise ValueError("Expected SEC payload bytes and an explicit wrapper kind")
    tag = kind.encode("ascii")
    prefix, close = b"<" + tag + b">\n", b"\n</" + tag + b">"
    if raw.startswith((b"<XBRL>", b"<XML>")):
        if not raw.startswith(prefix):
            raise ValueError("Unexpected SEC SGML XML wrapper kind or newline")
        # SEC <TEXT> extraction can retain the single line break after the
        # closing marker. Only the exact matching end tag is removable.
        ends = (close, close + b"\n", close + b"\r\n")
        suffix = next((ending for ending in ends
                       if raw.endswith(ending)), None)
        if suffix is None:
            raise ValueError("Unexpected or incomplete SEC SGML XML wrapper")
        inner = raw[len(prefix):-len(suffix)]
        if len(inner) < 40 or inner.startswith((b"<XBRL>", b"<XML>")):
            raise ValueError("Missing or nested SEC XML source after wrapper")
        return inner
    return raw
