"""Rebuild every origin meeting the original coverage rule from public archives."""
import gzip
import json
from pathlib import Path
import subprocess

if __package__:
    from .scoped_engine_inputs import compile_inputs
    from .historical_sources import ROOT, MARKET_COMMIT, canonical, sha
    from .historical_price_audit import build_audit
    from .historical_identifiers import build_report as identifier_report
    from .historical_replay_inputs import materialize_macro_inputs
    from .audit_historical_inputs import read_record
else:
    from scoped_engine_inputs import compile_inputs
    from historical_sources import ROOT, MARKET_COMMIT, canonical, sha
    from historical_price_audit import build_audit
    from historical_identifiers import build_report as identifier_report
    from historical_replay_inputs import materialize_macro_inputs
    from audit_historical_inputs import read_record

PROTOCOL_PATH = "docs/protocolo-validacion-ampliada-v1.json"


def main(output="out/expanded-validation-inputs-v1.json.gz"):
    protocol_raw = (ROOT / PROTOCOL_PATH).read_bytes()
    protocol = json.loads(protocol_raw)
    if (protocol["source_market_commit"] != MARKET_COMMIT or
            protocol["selection"]["minimum_weight"] != .7 or
            protocol["selection"]["maximum_origins"] != 48):
        raise ValueError("Expanded input policy mismatch")
    raw_market = subprocess.check_output(["git", "show", MARKET_COMMIT + ":dist/data/market.json"], cwd=ROOT)
    market = json.loads(raw_market)
    facts_raw = (ROOT / protocol["eps_archive"]).read_bytes()
    facts = json.loads(gzip.decompress(facts_raw))
    if sha(raw_market) != facts["input_market_sha256"]:
        raise ValueError("Archived EPS and market mismatch")
    provider_root = ROOT / "data/historical/provider-inputs-v1"
    identifier_root = ROOT / "data/historical/identifier-sources-v1"
    price_protocol = json.loads((ROOT / "docs/protocolo-precios-historicos-v1.json").read_bytes())
    prices, histories = build_audit(provider_root, identifier_root, market, price_protocol)
    identifiers = identifier_report(provider_root, identifier_root)
    manifest = json.loads((provider_root / "manifest.json").read_bytes())
    retrievals = {ptr["accession"]: read_record(provider_root, ptr)[0]["retrieved_at"]
                  for ptr in manifest["sec"]["documents"] if ptr["form"].startswith("NPORT")}
    macro = materialize_macro_inputs(provider_root, [row["cut"] for row in prices["matrix"]])
    bundle = compile_inputs(market, facts, prices, histories, identifiers, macro,
                            protocol, protocol["reconstruction_clock"], retrievals)
    bundle.update(eps_archive_sha256=sha(facts_raw), protocol_sha256=sha(protocol_raw),
                  compiler_sha256=sha(Path(__file__).read_bytes()))
    path = ROOT / output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(canonical(bundle) + b"\n", mtime=0))
    print(json.dumps({"origins": [{k: row[k] for k in ("cut", "usable_stocks", "eps_exclusions")}
                                  for row in bundle["origins"]], "scheduled": len(bundle["schedule"])}))
    return bundle


if __name__ == "__main__":
    main()
