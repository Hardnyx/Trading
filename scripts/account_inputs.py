"""Rebuild every historical account review, irrespective of future maturity."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

try:
    from .ttm_signal_research import eps_at
except ImportError:
    from ttm_signal_research import eps_at

ROOT = Path(__file__).resolve().parents[1]


def account_origins(snapshot, minimum_training=252):
    spy = next(a for a in snapshot["assets"] if a["symbol"] == "SPY")
    dates = [r["date"] for r in spy["history"] if r["date"] <= snapshot["price_as_of"]]
    if dates != sorted(set(dates)):
        raise ValueError("Ambiguous benchmark calendar")
    ends = {day[:7]: (i, day) for i, day in enumerate(dates)}
    return [day for month, (i, day) in ends.items()
            if i >= minimum_training and month < snapshot["price_as_of"][:7]]


def prepare_account_inputs(snapshot, archived):
    if snapshot["price_as_of"] != archived["price_cut"]:
        raise ValueError("Mismatched frozen cut")
    origins, exclusions = [], Counter()
    assets = [a for a in snapshot["assets"] if a["type"] == "stock"]
    for day in account_origins(snapshot):
        rows, reasons = [], Counter()
        for asset in assets:
            source = archived["sources"].get(asset["symbol"])
            if source is None:
                reasons["missing_companyfacts"] += 1
                continue
            record, reason = eps_at(asset, source["rows"], day, snapshot["price_as_of"])
            if reason:
                reasons[reason] += 1
            else:
                rows.append({"symbol": asset["symbol"], "eps": record})
        exclusions.update(reasons)
        origins.append({"origin": day, "facts": rows, "accounting_exclusions": dict(reasons)})
    return {"calendar_protocol": "reconstructed-ttm-account-v2", "minimum_training": 252,
            "price_cut": snapshot["price_as_of"], "origins": origins,
            "exclusions": dict(exclusions), "production_eligible": False,
            "original_vintages_verified": False}


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    result = prepare_account_inputs(payload["market"], payload["archived"])
    hashes = {}
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).suffix == ".py" and Path(path).resolve().is_relative_to(ROOT / "scripts"):
            path = Path(path).resolve()
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["python_source_hashes"] = dict(sorted(hashes.items()))
    result["python_version"] = sys.version.split()[0]
    print(json.dumps(result, separators=(",", ":")))
