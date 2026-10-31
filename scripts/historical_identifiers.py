"""Recover dated, explicit CUSIP/ticker observations from original SEC N-PORT.

Raw filing symbols are not vendor price identifiers. No name matching, current
symbol lookup, ticker punctuation conversion or whole-universe certification.
"""
import argparse
import base64
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

if __package__:
    from .audit_historical_inputs import read_record
    from .historical_sources import (Downloader, MARKET_COMMIT, PROTOCOL as PROVIDER_PROTOCOL, archive, canonical,
        iso, local_tag, parse_nport, select_holdings, sha)
else:
    from audit_historical_inputs import read_record
    from historical_sources import (Downloader, MARKET_COMMIT, PROTOCOL as PROVIDER_PROTOCOL, archive, canonical,
        iso, local_tag, parse_nport, select_holdings, sha)

PROTOCOL = "historical-identifier-sources-v1"
CIK = 1100663
# Current fund identifiers are discovery hints only. Every original must
# independently contain the expected registrant and series identity.
FUNDS = {"IVV": "S000004310", "ITOT": "S000004317", "IYY": "S000004330",
         "ISCB": "S000004433", "ILCB": "S000004367"}
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-/]{0,19}")


def xml_root(raw):
    if len(raw) > 8_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsafe or oversized source XML")
    return ET.fromstring(raw)


def value(node, tag):
    found = next((n for n in node.iter() if local_tag(n) == tag), None)
    return (found.text or "").strip() if found is not None else ""


def cusip_valid(cusip):
    if not re.fullmatch(r"[A-Z0-9*@#]{8}[0-9]", cusip or "") or cusip == "000000000":
        return False
    values = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#"
    total = 0
    for i, char in enumerate(cusip[:8]):
        n = values.index(char) * (1 + i % 2)
        total += n // 10 + n % 10
    return (10 - total % 10) % 10 == int(cusip[-1])


def discovery_url(fund, last_cut):
    return ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + FUNDS[fund]
            + "&type=NPORT-P&dateb=" + iso(last_cut).replace("-", "")
            + "&owner=exclude&count=100&output=atom")


def original_url(accession):
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise ValueError("Invalid source accession")
    return f"https://www.sec.gov/Archives/edgar/data/{CIK}/{accession.replace('-', '')}/primary_doc.xml"


def parse_discovery(raw, first_day, last_day):
    root = xml_root(raw)
    info = next((n for n in root if local_tag(n) == "company-info"), None)
    if info is None or value(info, "cik").lstrip("0") != str(CIK):
        raise ValueError("Unexpected discovery registrant")
    rows = []
    days = []
    for entry in root:
        if local_tag(entry) != "entry":
            continue
        accession, day, form = (value(entry, k) for k in ("accession-number", "filing-date", "filing-type"))
        iso(day)
        days.append(day)
        original_url(accession)
        expected = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{accession.replace('-', '')}/{accession}-index.htm"
        if value(entry, "filing-href") != expected or form not in ("NPORT-P", "NPORT-P/A"):
            raise ValueError("Invalid discovery entry identity")
        if first_day <= day <= last_day:
            rows.append({"accession": accession, "filing_date": day, "form": form})
    if len({r["accession"] for r in rows}) != len(rows):
        raise ValueError("Duplicate discovery accession")
    # Never silently interpret a truncated 100-entry page as complete.
    if len(days) >= 100 and min(days) >= first_day:
        raise ValueError("Discovery requires pagination")
    return sorted(rows, key=lambda r: (r["filing_date"], r["accession"]))


def parse_observations(raw, fund, filing):
    root = xml_root(raw)
    info = next((n for n in root.iter() if local_tag(n) == "genInfo"), None)
    if info is None or value(info, "regCik").lstrip("0") != str(CIK) or value(info, "seriesId") != FUNDS[fund]:
        raise ValueError("Original registrant or fund series mismatch")
    period = iso(value(info, "repPdDate"))
    filed = iso(filing["filing_date"])
    if period > filed:
        raise ValueError("Holdings period is later than filing")
    public = max(filed, (date.fromisoformat(period) + timedelta(days=60)).isoformat())
    positions = []
    rejected = Counter()
    for item in root.iter():
        if local_tag(item) != "invstOrSec":
            continue
        if value(item, "assetCat") != "EC" or value(item, "curCd") != "USD" or value(item, "payoffProfile") != "Long":
            rejected["not-long-usd-equity"] += 1
            continue
        cusip = value(item, "cusip")
        if not cusip_valid(cusip):
            rejected["invalid-cusip"] += 1
            continue
        identifiers = next((n for n in item if local_tag(n) == "identifiers"), None)
        symbols = set()
        if identifiers is not None:
            for n in identifiers:
                if local_tag(n) == "ticker" or (local_tag(n) == "other" and n.get("otherDesc", "").lower() in ("ticker", "ticker symbol")):
                    symbol = n.get("value", (n.text or "").strip())
                    if SYMBOL.fullmatch(symbol):
                        symbols.add(symbol)
        if len(symbols) != 1:
            rejected["missing-or-ambiguous-explicit-ticker"] += 1
            continue
        positions.append({"cusip": cusip, "source_ticker": next(iter(symbols)),
                          "lei": value(item, "lei"), "name": value(item, "name"),
                          "title": value(item, "title")})
    return {"fund": fund, "series_id": FUNDS[fund], "as_of": period,
            "available_after_day": public, "observations": positions,
            "rejected": dict(sorted(rejected.items())),
            "symbol_namespace": "explicit-original-filing-not-price-provider"}


def record(raw, kind, url, **extra):
    return {"protocol": PROTOCOL, "kind": kind, "source_url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_sha256": sha(raw), "raw_base64": base64.b64encode(raw).decode(), **extra}


def observation_pointer(normalized):
    """Bind the complete derivation without duplicating every row in a manifest."""
    return {"normalized_sha256": sha(canonical(normalized)), "as_of": normalized["as_of"],
            "available_after_day": normalized["available_after_day"],
            "explicit_observations": len(normalized["observations"]), "rejected": normalized["rejected"]}


def collect(root, cuts, fetch=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    start = (date.fromisoformat(cuts[0]) - timedelta(days=180)).isoformat()
    manifest_path = root / "manifest.json"
    prior = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {}
    if prior and (prior.get("protocol") != PROTOCOL or prior.get("cuts") != cuts or
                  not prior.get("funds") or any(FUNDS.get(k) != v for k, v in prior["funds"].items())):
        raise ValueError("Identifier collection identity mismatch")
    fetch = fetch or Downloader()
    manifest = {"protocol": PROTOCOL, "source_market_commit": MARKET_COMMIT, "cuts": cuts,
                "funds": FUNDS, "discovery": {}, "documents": [], "errors": [], "production_eligible": False}
    def save():
        temporary = root / "manifest.pending"
        temporary.write_bytes(canonical(manifest) + b"\n")
        temporary.replace(manifest_path)
    previous = {(p["fund"], p["accession"]): p for p in prior.get("documents", [])}
    for fund in FUNDS:
        try:
            url = discovery_url(fund, cuts[-1])
            prior_discovery = prior.get("discovery", {}).get(fund)
            if prior_discovery:
                old_discovery, raw = read_record(root, prior_discovery)
                if old_discovery.get("source_url") != url or old_discovery.get("protocol") != PROTOCOL:
                    raise ValueError("Archived discovery identity mismatch")
            else:
                raw = fetch(url, sec=True)
            rows = parse_discovery(raw, start, cuts[-1])
            ptr, _ = archive(root, f"discovery/{fund}-{sha(raw)[:16]}.json.gz", record(raw, "sec-series-atom", url))
            manifest["discovery"][fund] = {**ptr, "source_url": url}
            save()
            for filing in rows:
                key = fund, filing["accession"]
                old = previous.get(key)
                local = root / f"nport/{fund}/{filing['accession']}.json.gz"
                if not old and local.exists():
                    # A source beyond the last checkpoint remains recoverable
                    # without a new network response or a new first-retrieval date.
                    stored = json.loads(gzip.decompress(local.read_bytes()))
                    old = {"path": str(local.relative_to(root)), "sha256": sha(local.read_bytes()),
                           "raw_sha256": stored["raw_sha256"], "fund": fund,
                           "accession": filing["accession"], "filing": filing,
                           **observation_pointer(parse_observations(base64.b64decode(stored["raw_base64"], validate=True), fund, filing))}
                if old:
                    original, body = read_record(root, old)
                    if original.get("filing") != filing or original.get("source_url") != original_url(filing["accession"]):
                        raise ValueError("Archived filing identity mismatch")
                    normalized = parse_observations(body, fund, filing)
                    if any(old.get(k) != v for k, v in observation_pointer(normalized).items()):
                        raise ValueError("Archived observation mismatch")
                    pointer = old
                else:
                    url = original_url(filing["accession"])
                    body = fetch(url, sec=True)
                    normalized = parse_observations(body, fund, filing)
                    source = record(body, "sec-nport-identifiers", url, filing=filing, fund=fund)
                    ptr, _ = archive(root, f"nport/{fund}/{filing['accession']}.json.gz", source)
                    pointer = {**ptr, "fund": fund, "accession": filing["accession"], "filing": filing,
                               **observation_pointer(normalized)}
                manifest["documents"].append(pointer)
                save()
                print(json.dumps({"fund": fund, "accession": filing["accession"], "explicit_identifiers": len(normalized["observations"])}), flush=True)
        except Exception as error:
            # Provider errors can include request details; preserve only safe type.
            safe = {"fund": fund, "kind": type(error).__name__}
            if type(getattr(error, "status", None)) is int:
                safe["http_status"] = error.status
            if isinstance(getattr(error, "kind", None), str):
                safe["provider_error"] = error.kind
            manifest["errors"].append(safe)
            save()
    manifest["collection_complete"] = not manifest["errors"] and len(manifest["discovery"]) == len(FUNDS)
    save()
    return manifest


def verified_observations(root, cuts):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_bytes())
    if (manifest.get("protocol") != PROTOCOL or manifest.get("cuts") != cuts or
            manifest.get("funds") != FUNDS or manifest.get("source_market_commit") != MARKET_COMMIT):
        raise ValueError("Identifier manifest identity mismatch")
    first = (date.fromisoformat(cuts[0]) - timedelta(days=180)).isoformat()
    expected = {}
    for fund, ptr in manifest["discovery"].items():
        source, raw = read_record(root, ptr)
        if source.get("protocol") != PROTOCOL or source.get("kind") != "sec-series-atom" or source.get("source_url") != discovery_url(fund, cuts[-1]):
            raise ValueError("Discovery source contract mismatch")
        expected[fund] = {row["accession"]: row for row in parse_discovery(raw, first, cuts[-1])}
    result = []
    seen = set()
    for ptr in manifest["documents"]:
        fund, accession = ptr["fund"], ptr["accession"]
        if (fund, accession) in seen:
            raise ValueError("Duplicate archived identifier filing")
        seen.add((fund, accession))
        filing = expected[fund][accession]
        source, raw = read_record(root, ptr)
        if (source.get("protocol") != PROTOCOL or source.get("kind") != "sec-nport-identifiers" or
                source.get("source_url") != original_url(accession) or source.get("filing") != filing or
                source.get("fund") != fund or ptr.get("filing") != filing):
            raise ValueError("Original identifier source contract mismatch")
        normalized = parse_observations(raw, fund, filing)
        if any(ptr.get(k) != v for k, v in observation_pointer(normalized).items()):
            raise ValueError("Identifier observations do not match original XML")
        result.append({**normalized, "accession": accession, "source_url": source["source_url"],
                       "raw_sha256": source["raw_sha256"], "archive_sha256": ptr["sha256"]})
    missing = sorted(f"{fund}/{accession}" for fund, rows in expected.items() for accession in rows if (fund, accession) not in seen)
    missing_discoveries = sorted(set(FUNDS) - set(manifest["discovery"]))
    return result, {"manifest_sha256": sha((root / "manifest.json").read_bytes()),
                    "verified_documents": len(result), "missing_documents": missing,
                    "missing_discoveries": missing_discoveries,
                    "collection_errors": manifest.get("errors", [])}


def match_positions(positions, sources, cut, maximum_age=120):
    """A symbol observed before cut is not a certified vendor-price binding."""
    eligible = [s for s in sources if s["available_after_day"] < cut and
                0 <= (date.fromisoformat(cut) - date.fromisoformat(s["as_of"])).days <= maximum_age]
    by_cusip = {}
    for source in eligible:
        for row in source["observations"]:
            by_cusip.setdefault(row["cusip"], []).append((source, row))
    matches = []
    for position in positions:
        candidates = by_cusip.get(position["cusip"], [])
        status, chosen = "no-prior-explicit-ticker", None
        if candidates:
            latest = max(s["as_of"] for s, _ in candidates)
            current = [(s, row) for s, row in candidates if s["as_of"] == latest]
            symbols = {row["source_ticker"] for _, row in current}
            leis = {row["lei"] for _, row in current if row["lei"] and row["lei"] != "N/A"}
            if len(symbols) != 1 or len(leis) > 1:
                status = "conflicting-explicit-identifiers"
            else:
                status = "explicit-ticker-observed"
                chosen = {"source_ticker": next(iter(symbols)), "as_of": latest,
                          "evidence": [{k: s[k] for k in ("fund", "accession", "source_url", "raw_sha256", "available_after_day")} for s, _ in current]}
        matches.append({**position, "identifier_status": status, "ticker_observation": chosen,
                        "price_instrument_binding": None})
    return matches


def build_report(provider_root, identifier_root):
    provider_root = Path(provider_root)
    original_manifest = (provider_root / "manifest.json").read_bytes()
    provider = json.loads(original_manifest)
    cuts = provider["cuts"]
    if (provider.get("source_market_commit") != MARKET_COMMIT or provider.get("protocol") != PROVIDER_PROTOCOL or
            not cuts or cuts != sorted(set(cuts))):
        raise ValueError("SPY source market identity mismatch")
    sources, audit = verified_observations(identifier_root, cuts)
    spy = []
    for ptr in provider["sec"]["documents"]:
        if not ptr["form"].startswith("NPORT"):
            continue
        record_, raw = read_record(provider_root, ptr)
        if record_["filing"]["accessionNumber"] != ptr["accession"]:
            raise ValueError("SPY source accession mismatch")
        n = parse_nport(raw, record_["filing"])
        if n != ptr["normalized"]:
            raise ValueError("SPY source derivation mismatch")
        spy.append({"accession": ptr["accession"], "normalized": n})
    matrix = []
    for cut in cuts:
        selected = select_holdings(spy, cut)
        if selected["status"] != "source-available":
            matrix.append({"cut": cut, "status": "blocked-spy-source", "spy_source": selected,
                           "positions": [], "mapped_positive_weight": 0, "price_binding_verified": False})
            continue
        positions = next(s["normalized"]["positions"] for s in spy if s["accession"] == selected["accession"])
        rows = match_positions(positions, sources, cut)
        matrix.append({"cut": cut, "status": "partial-identifier-observations", "spy_source": selected,
                       "positions": rows, "mapped_positive_weight": sum(r["weight"] for r in rows if r["weight"] > 0 and r["ticker_observation"]),
                       "unresolved_positive_weight": sum(r["weight"] for r in rows if r["weight"] > 0 and not r["ticker_observation"]),
                       "price_binding_verified": False})
    positive_weights = [r["mapped_positive_weight"] for r in matrix if r["mapped_positive_weight"] > 0]
    matched_ids = {p["cusip"] for row in matrix for p in row["positions"] if p["weight"] > 0 and p["ticker_observation"]}
    return {"protocol": "historical-cusip-ticker-observations-v1", "source_market_commit": MARKET_COMMIT,
            "provider_manifest_sha256": sha(original_manifest), "identifier_audit": audit,
            "resolver_sha256": sha(Path(__file__).read_bytes()), "matrix": matrix,
            "summary": {"cuts": len(cuts), "spy_fresh_cuts": sum(r["status"] != "blocked-spy-source" for r in matrix),
                        "cuts_with_explicit_tickers": sum(r["mapped_positive_weight"] > 0 for r in matrix),
                        "verified_identifier_documents": len(sources),
                        "explicit_observations": sum(len(s["observations"]) for s in sources),
                        "distinct_explicit_cusips": len({r["cusip"] for s in sources for r in s["observations"]}),
                        "distinct_matched_spy_cusips": len(matched_ids),
                        "positive_cut_mapped_weight_range": [min(positive_weights), max(positive_weights)] if positive_weights else None,
                        "cuts_blocked_by_spy_source": sum(r["status"] == "blocked-spy-source" for r in matrix),
                        "fresh_spy_cuts_without_ticker_match": sum(r["status"] != "blocked-spy-source" and r["mapped_positive_weight"] == 0 for r in matrix),
                        "full_engine_eligible_cuts": 0},
            "full_replay_ready": False, "production_eligible": False, "predictive_validation": "not-established",
            "scope": "Exact CUSIP to explicit original filing ticker observations available before each cut. No current-ticker inference, vendor price binding, continuous ticker validity, historical index universe or return validation."}


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "observations.json.gz").write_bytes(gzip.compress(canonical(report) + b"\n", mtime=0))
    lines = ["# Identificadores históricos: evidencia original", "",
             "Cruce exacto de CUSIP con tickers explícitos en N-PORT originales de iShares.",
             "Los símbolos del documento todavía no están vinculados a instrumentos de precios históricos.", "",
             "| Cierre | Fuente SPY | Peso con ticker explícito | Peso positivo pendiente |", "|---|---|---:|---:|"]
    for row in report["matrix"]:
        pending = row.get("unresolved_positive_weight")
        pending = "sin fuente admisible" if pending is None else f"{100*pending:.2f}%"
        lines.append(f'| {row["cut"]} | {row["spy_source"]["status"]} | {100*row["mapped_positive_weight"]:.2f}% | {pending} |')
    lines += ["", "No se normalizan los pesos desconocidos. No se amplía la edad máxima de 120 días.",
              "Un 0% con SPY admisible significa que no hay una observación explícita admisible; no significa que el ETF no tuviera esos instrumentos.",
              "Los tickers se conservan tal como aparecen, sin convertir puntos, barras o clases de acciones.",
              "La cobertura de símbolos no certifica anclas fundamentales, precios operables ni universo completo.", ""]
    (output / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "matrix"}
    summary["matrix"] = [{k: v for k, v in row.items() if k != "positions"} for row in report["matrix"]]
    (output / "coverage.json").write_bytes(canonical(summary) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-input", default="data/historical/provider-inputs-v1")
    parser.add_argument("--input", default="data/historical/identifier-sources-v1")
    parser.add_argument("--output", default="data/historical/identifier-observations-v1")
    parser.add_argument("--collect", action="store_true")
    args = parser.parse_args()
    if args.collect:
        cuts = json.loads((Path(args.provider_input) / "manifest.json").read_bytes())["cuts"]
        collect(args.input, cuts)
    report = build_report(args.provider_input, args.input)
    write_report(report, args.output)
    print(json.dumps(report["summary"], sort_keys=True))
    audit = report["identifier_audit"]
    return 2 if audit["missing_documents"] or audit["missing_discoveries"] or audit["collection_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
