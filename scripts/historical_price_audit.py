"""Compare original N-PORT per-share marks with frozen provider prices.

Restores declared split units mechanically and prepares research-only trailing
histories. Point compatibility is never a certified vendor identity or a causal
whole-period price, dividend, corporate-action or execution archive.
"""
import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import subprocess

if __package__:
    from .historical_identifiers import build_report as identifier_report, xml_root, value
    from .audit_historical_inputs import read_record
    from .historical_sources import ROOT, MARKET_COMMIT, canonical, iso, sha
else:
    from historical_identifiers import build_report as identifier_report, xml_root, value
    from audit_historical_inputs import read_record
    from historical_sources import ROOT, MARKET_COMMIT, canonical, iso, sha

PROTOCOL_PATH = "docs/protocolo-precios-historicos-v1.json"


def finite_positive(number):
    return type(number) in (int, float) and math.isfinite(number) and number > 0


def nport_marks(raw):
    """Keep ambiguous or ineligible marks as explicit exclusions, not averages."""
    by_cusip = {}
    for item in xml_root(raw).iter():
        if item.tag.rsplit("}", 1)[-1] != "invstOrSec":
            continue
        cusip = value(item, "cusip")
        reason = None
        if (value(item, "assetCat") != "EC" or value(item, "curCd") != "USD" or
                value(item, "units") != "NS" or value(item, "payoffProfile") != "Long" or
                value(item, "fairValLevel") != "1"):
            reason = "not-long-usd-common-shares-level-one"
        try:
            balance, usd = float(value(item, "balance")), float(value(item, "valUSD"))
            price = usd / balance if finite_positive(balance) and finite_positive(usd) else None
        except (ValueError, ZeroDivisionError):
            balance, usd, price = None, None, None
        if not finite_positive(price):
            reason = reason or "invalid-share-quantity-or-fair-value"
        row = {"cusip": cusip, "balance": balance, "value_usd": usd,
               "reported_per_share_mark": price, "reason": reason}
        if cusip in by_cusip:
            by_cusip[cusip] = {"cusip": cusip, "reason": "multiple-original-positions-for-cusip"}
        else:
            by_cusip[cusip] = row
    return by_cusip


def validate_asset(asset, price_cut):
    if asset.get("type") != "stock" or asset.get("currency") != "USD":
        raise ValueError("not-frozen-usd-stock")
    if asset.get("price_date") != price_cut:
        raise ValueError("asset-price-cut-mismatch")
    history = asset.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("missing-price-history")
    days = []
    for row in history:
        day = iso(row.get("date"))
        if day > price_cut or not finite_positive(row.get("close")) or not finite_positive(row.get("adj_close")):
            raise ValueError("invalid-frozen-price-row")
        days.append(day)
    if days != sorted(set(days)):
        raise ValueError("ambiguous-frozen-price-dates")
    if days[-1] != price_cut:
        raise ValueError("missing-frozen-last-price")
    for key in ("splits", "price_adjustments"):
        events = asset.get(key) or []
        if not isinstance(events, list):
            raise ValueError("invalid-corporate-action-list")
        seen = set()
        for event in events:
            day = iso(event.get("date"))
            if day in seen or day > price_cut or not finite_positive(event.get("ratio")):
                raise ValueError("invalid-or-duplicate-corporate-action")
            seen.add(day)
    if {e["date"] for e in (asset.get("splits") or [])} & {e["date"] for e in (asset.get("price_adjustments") or [])}:
        raise ValueError("event-classified-both-split-and-price-adjustment")


def split_factor(asset, origin, price_cut):
    return math.prod(e["ratio"] for e in (asset.get("splits") or []) if origin < e["date"] <= price_cut)


def point_check(asset, mark, reference_day, price_cut, protocol):
    if mark.get("reason"):
        return {"status": mark["reason"]}
    if any(reference_day < e["date"] <= price_cut for e in (asset.get("price_adjustments") or [])):
        return {"status": "unreconciled-future-non-share-adjustment"}
    row = next((r for r in asset["history"] if r["date"] == reference_day), None)
    if row is None:
        return {"status": "missing-exact-reference-date"}
    factor = split_factor(asset, reference_day, price_cut)
    restored = row["close"] * factor
    reference = mark["reported_per_share_mark"]
    if not all(finite_positive(v) for v in (factor, restored, reference)):
        return {"status": "invalid-restored-point-basis"}
    limits = protocol["comparison_tolerance"]
    tolerance = max(limits["absolute_usd"], reference * limits["relative"])
    error = restored - reference
    return {"status": "point-compatible" if abs(error) <= tolerance else "point-price-discrepancy",
            "reference_day": reference_day, "reported_per_share_mark": reference,
            "reference_quantity": mark.get("balance"), "reference_value_usd": mark.get("value_usd"),
            "provider_close": row["close"], "declared_split_reversal_factor": factor,
            "restored_point_close": restored, "absolute_error": abs(error),
            "relative_error": error / reference, "tolerance_usd": tolerance,
            "reference_is_exchange_close_certified": False,
            "corporate_actions_authoritatively_verified": False}


def prepare_trailing_history(asset, origin, price_cut, protocol):
    """An explicit share basis preserves returns; no future rows or cash claims."""
    if not any(r["date"] == origin for r in asset["history"]):
        raise ValueError("missing-exact-origin-price")
    rows = [r for r in asset["history"] if r["date"] <= origin][-(protocol["maximum_return_intervals"] + 1):]
    if len(rows) - 1 < protocol["minimum_return_intervals"]:
        raise ValueError("insufficient-trailing-return-intervals")
    if any(rows[0]["date"] <= e["date"] <= price_cut for e in (asset.get("price_adjustments") or [])):
        raise ValueError("unreconciled-non-share-event-in-training-or-future-basis")
    factor = split_factor(asset, origin, price_cut)
    history = [{"date": r["date"], "close": r["close"] * factor, "adj_close": r["adj_close"] * factor} for r in rows]
    if not finite_positive(factor) or any(not finite_positive(r[k]) for r in history for k in ("close", "adj_close")):
        raise ValueError("invalid-restored-share-basis")
    return {"symbol": asset["symbol"], "origin": origin, "declared_split_reversal_factor": factor,
            "history": history, "history_sha256": sha(canonical(history)),
            "basis": "close-in-origin-share-units-and-scaled-provider-total-return-index",
            "total_return_index_is_original_vintage": False,
            "corporate_actions_authoritatively_verified": False,
            "execution_prices_verified": False, "production_eligible": False}


def load_frozen_market():
    return json.loads(subprocess.check_output(["git", "show", MARKET_COMMIT + ":dist/data/market.json"], cwd=ROOT))


def build_audit(provider_root, identifier_root, market, protocol):
    if protocol.get("protocol") != "historical-price-unit-audit-v1" or protocol.get("source_market_commit") != MARKET_COMMIT:
        raise ValueError("Price protocol identity mismatch")
    if protocol.get("canonical_market_sha256") != sha(canonical(market)):
        raise ValueError("Frozen market content mismatch")
    price_cut = iso(market["price_as_of"])
    identifiers = identifier_report(provider_root, identifier_root)
    assets = {}
    asset_errors = {}
    for asset in market["assets"]:
        symbol = asset["symbol"]
        if symbol in assets:
            raise ValueError("Duplicate frozen market symbol")
        assets[symbol] = asset
        try:
            validate_asset(asset, price_cut)
        except (ValueError, TypeError, KeyError) as error:
            asset_errors[symbol] = str(error)
    root = Path(provider_root)
    manifest_bytes = (root / "manifest.json").read_bytes()
    if sha(manifest_bytes) != identifiers["provider_manifest_sha256"]:
        raise ValueError("Provider manifest changed during price audit")
    manifest = json.loads(manifest_bytes)
    references = {}
    for pointer in manifest["sec"]["documents"]:
        if not pointer["form"].startswith("NPORT"):
            continue
        _, raw = read_record(root, pointer)
        references[pointer["accession"]] = {"marks": nport_marks(raw), "raw_sha256": pointer["raw_sha256"]}
    matrix, bundle = [], {}
    for origin in identifiers["matrix"]:
        cut = origin["cut"]
        source = origin["spy_source"]
        rows, histories = [], []
        reasons = Counter()
        ticker_cusips = {}
        for position in origin["positions"]:
            observation = position["ticker_observation"]
            if observation and position["weight"] > 0:
                ticker_cusips.setdefault(observation["source_ticker"], set()).add(position["cusip"])
        for position in origin["positions"]:
            if position["weight"] <= 0:
                continue
            row = {"cusip": position["cusip"], "name": position["name"], "weight": position["weight"],
                   "source_ticker": None, "status": "no-prior-explicit-ticker",
                   "continuous_price_identity_verified": False}
            ticker = position["ticker_observation"]
            if ticker:
                symbol = ticker["source_ticker"]
                row.update(source_ticker=symbol, ticker_evidence=ticker)
                if len(ticker_cusips[symbol]) > 1:
                    row["status"] = "ambiguous-ticker-to-multiple-cusips"
                elif symbol not in assets:
                    row["status"] = "ticker-not-in-frozen-catalogue-no-alias-guessed"
                elif symbol in asset_errors:
                    row["status"] = "invalid-frozen-asset"
                    row["detail"] = asset_errors[symbol]
                else:
                    ref = references[source["accession"]]
                    mark = ref["marks"].get(position["cusip"], {"reason": "missing-original-share-mark"})
                    row["reference_source_sha256"] = ref["raw_sha256"]
                    row["point_check"] = point_check(assets[symbol], mark, source["as_of"], price_cut, protocol)
                    row["status"] = row["point_check"]["status"]
                    if row["status"] == "point-compatible":
                        try:
                            prepared = prepare_trailing_history(assets[symbol], cut, price_cut, protocol)
                            histories.append(prepared)
                            row["trailing_history_status"] = "research-reconstruction"
                            row["trailing_history_sha256"] = prepared["history_sha256"]
                        except ValueError as error:
                            row["trailing_history_status"] = str(error)
            reasons[row["status"]] += 1
            rows.append(row)
        compatible_weight = sum(r["weight"] for r in rows if r["status"] == "point-compatible")
        prepared_weight = sum(r["weight"] for r in rows if r.get("trailing_history_status") == "research-reconstruction")
        matrix.append({"cut": cut, "spy_source_status": source["status"], "spy_accession": source.get("accession"),
                       "reference_day": source.get("as_of"), "positions": rows, "status_counts": dict(sorted(reasons.items())),
                       "explicit_ticker_weight": origin["mapped_positive_weight"], "point_compatible_weight": compatible_weight,
                       "research_history_weight": prepared_weight, "research_histories": len(histories),
                       "price_identity_certified": False, "full_engine_replay_eligible": False})
        bundle[cut] = histories
    totals = Counter()
    for row in matrix:
        totals.update(row["status_counts"])
    evidence = identifiers["identifier_audit"]
    report = {"protocol": protocol["protocol"], "source_market_commit": MARKET_COMMIT,
              "canonical_market_sha256": sha(canonical(market)), "frozen_price_cut": price_cut,
              "provider_manifest_sha256": identifiers["provider_manifest_sha256"], "identifier_audit": evidence,
              "identifier_resolver_sha256": identifiers["resolver_sha256"], "auditor_sha256": sha(Path(__file__).read_bytes()),
              "price_protocol_sha256": sha(canonical(protocol)), "matrix": matrix,
              "summary": {"cuts": len(matrix), "cuts_with_point_compatible_marks": sum(r["point_compatible_weight"] > 0 for r in matrix),
                          "cuts_with_research_histories": sum(r["research_histories"] > 0 for r in matrix),
                          "point_status_counts": dict(sorted(totals.items())),
                          "research_history_count": sum(r["research_histories"] for r in matrix),
                          "full_engine_eligible_cuts": 0},
              "current_catalogue_selection_bias": True, "continuous_price_identity_verified": False,
              "share_basis_reconstructed_ex_post": True,
              "original_price_vintages_verified": False,
              "unreconciled_event_inventory": {
                  symbol: [{k: event.get(k) for k in ("date", "ratio", "classification")}
                           for event in a.get("price_adjustments", [])]
                  for symbol, a in assets.items() if symbol not in asset_errors and a.get("price_adjustments")},
              "execution_cashflows_verified": False, "production_eligible": False, "predictive_validation": "not-established",
              "scope": protocol["scope"]}
    return report, {"protocol": "historical-common-share-unit-histories-v1", "origins": bundle,
                    "source_audit_sha256": sha(canonical(report)), "research_only": True, "production_eligible": False,
                    "predictive_validation": "not-established"}


def write_audit(report, bundle, output, bundle_output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "points.json.gz").write_bytes(gzip.compress(canonical(report) + b"\n", mtime=0))
    compact = {k: v for k, v in report.items() if k != "matrix"}
    compact["matrix"] = [{k: v for k, v in r.items() if k != "positions"} for r in report["matrix"]]
    (output / "coverage.json").write_bytes(canonical(compact) + b"\n")
    lines = ["# Precios históricos: contraste de unidades", "",
             "Compatibilidad puntual con valor razonable por acción en N-PORT; no certifica cotización de cierre ni continuidad de identidad.", "",
             "| Cierre | Fuente SPY | Peso con ticker | Peso compatible puntual | Peso con historia de investigación | Historias |",
             "|---|---|---:|---:|---:|---:|"]
    for r in report["matrix"]:
        lines.append(f'| {r["cut"]} | {r["spy_source_status"]} | {100*r["explicit_ticker_weight"]:.2f}% | '
                     f'{100*r["point_compatible_weight"]:.2f}% | {100*r["research_history_weight"]:.2f}% | {r["research_histories"]} |')
    lines += ["", "Las historias solo usan fechas hasta el cierre. La base de acciones se invierte mecánicamente con eventos declarados por el proveedor.",
              "No se usan adj_close como precios de ejecución ni se imputan fechas, símbolos, dividendos o eventos ausentes.",
              "El catálogo congelado es una selección actual con sesgo de supervivencia. Las coincidencias no validan retornos futuros ni habilitan el motor completo.", ""]
    (output / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    bundle_output = Path(bundle_output)
    bundle_output.parent.mkdir(parents=True, exist_ok=True)
    bundle_output.write_bytes(gzip.compress(canonical(bundle) + b"\n", mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-input", default="data/historical/provider-inputs-v1")
    parser.add_argument("--identifier-input", default="data/historical/identifier-sources-v1")
    parser.add_argument("--output", default="data/historical/price-reconciliation-v1")
    parser.add_argument("--bundle-output", default="out/historical-common-unit-histories-v1.json.gz")
    args = parser.parse_args()
    protocol = json.loads((ROOT / PROTOCOL_PATH).read_bytes())
    report, bundle = build_audit(args.provider_input, args.identifier_input, load_frozen_market(), protocol)
    write_audit(report, bundle, args.output, args.bundle_output)
    print(json.dumps(report["summary"], sort_keys=True))
    audit = report["identifier_audit"]
    return 2 if audit["missing_documents"] or audit["missing_discoveries"] or audit["collection_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
