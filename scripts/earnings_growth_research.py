#!/usr/bin/env python3
"""Audit annual EPS growth without promoting reconstructed evidence to trading."""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .earnings_history import growth_replay, replay_metrics, MODEL_VERSION
else:
    from earnings_history import growth_replay, replay_metrics, MODEL_VERSION

ROOT = Path(__file__).resolve().parents[1]


def research_report(snapshot, source_sha256):
    assets, results = [], []
    stocks = [a for a in snapshot["assets"] if a.get("type") == "stock"]
    for asset in stocks:
        history = (asset.get("financials") or {}).get("earnings_history")
        if not isinstance(history, dict):
            assets.append({"symbol": asset["symbol"], "status": "missing_history"})
            continue
        replay = growth_replay(history, asset.get("assumptions", {}).get("growth"))
        assets.append(dict(replay, symbol=asset["symbol"], observed_at=history.get("observed_at"),
                           metrics=replay_metrics(replay["outcomes"])))
        results.extend(dict(row, symbol=asset["symbol"]) for row in replay["outcomes"])
    return {
        "schema_version": 1, "model_version": MODEL_VERSION,
        "status": "research_only_reconstructed", "production_eligible": False,
        "source_snapshot_sha256": source_sha256, "observed_at": snapshot["generated_at"],
        "stocks": len(stocks), "stocks_with_history": sum(a.get("annual_origins", 0) > 0 for a in assets),
        "stocks_with_outcomes": sum(bool(a.get("outcomes")) for a in assets),
        "reconstructed_outcomes": len(results), "prospective_outcomes": 0,
        "metrics": replay_metrics(results), "assets": assets,
        "note": "Forward chaining respects filing dates within today's SEC response. Original vintages, a historical universe and prospective economic utility remain unverified. No automatic parameter changes.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", type=Path, default=ROOT / "dist/data/market.json")
    parser.add_argument("--output", type=Path, default=ROOT / "out/earnings-growth-research.json")
    args = parser.parse_args()
    raw = args.market.read_bytes()
    report = research_report(json.loads(raw), hashlib.sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "stocks", "stocks_with_history", "stocks_with_outcomes", "reconstructed_outcomes", "metrics")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
