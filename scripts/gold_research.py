"""Gold, real yields and USD: lagged-factor forecasting research, no promotion."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def csv_history(path, field):
    with Path(path).open(encoding="utf-8-sig") as handle:
        return [{"date": r["observation_date"], "value": float(r[field])}
                for r in csv.DictReader(handle) if r.get(field) not in (None, "", ".")]


def evaluate(snapshot, real_history, dollar_history, step=21, train_origins=24):
    """Past 21-session factor changes predict the next interval; no future X."""
    gold = next(a for a in snapshot["assets"] if a["symbol"] == "GLD")
    prices = {r["date"]: r["adj_close"] for r in gold["history"] if r["date"] <= snapshot["price_as_of"]}
    real = {r["date"]: r["value"] for r in real_history}
    dollar = {r["date"]: r["value"] for r in dollar_history if r["value"] > 0}
    dates = sorted(set(prices) & set(real) & set(dollar))
    rows = []
    for i in range(step, len(dates)-step, step):
        before, origin, end = dates[i-step], dates[i], dates[i+step]
        rows.append({"origin": origin, "maturity": end,
                     "features": [1., (real[origin]-real[before])/100,
                                  float(np.log(dollar[origin]/dollar[before]))],
                     "target": float(np.log(prices[end]/prices[origin]))})
    outcomes = []
    for i in range(train_origins, len(rows)):
        origin = rows[i]["origin"]
        train = [r for r in rows[:i] if r["maturity"] <= origin][-train_origins:]
        if len(train) < train_origins:
            continue
        X = np.array([r["features"] for r in train])
        y = np.array([r["target"] for r in train])
        beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank != 3:
            continue
        predicted = float(np.array(rows[i]["features"]) @ beta)
        outcomes.append({**rows[i], "prediction": predicted, "baseline": float(y.mean()),
                         "trained_through": max(r["maturity"] for r in train),
                         "coefficients": beta.tolist()})
    metrics = {"origins": len(outcomes)}
    if outcomes:
        errors = np.array([r["target"]-r["prediction"] for r in outcomes])
        reference = np.array([r["target"]-r["baseline"] for r in outcomes])
        metrics.update(mse=float(np.mean(errors**2)), baseline_mse=float(np.mean(reference**2)),
                       oos_r2=float(1-np.mean(errors**2)/np.mean(reference**2)),
                       mean_squared_loss_gain=float(np.mean(reference**2-errors**2)))
    return {"status": "shadow_reconstructed_lagged_factors", "production_eligible": False,
            "original_vintages_verified": False, "as_of": snapshot["price_as_of"],
            "variables": {"real_yield": "DFII10 / 100", "dollar": "log(DTWEXBGS)",
                          "dependent": "GLD adjusted log return (fund expenses already embedded)"},
            "train_origins": train_origins, "step_common_observations": step,
            "common_dates": len(dates), "metrics": metrics, "outcomes": outcomes,
            "limitations": "Current FRED revisions and selected provider history, no original publication vintages. Lagged macro changes only; contemporaneous explanatory regressions do not predict future shocks. Inflation minus expenses is a separate unvalidated assumption, not an estimated gold mean. No gold purchases or live anchor changes."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", type=Path, default=ROOT / "dist/data/market.json")
    parser.add_argument("--real-csv", type=Path)
    parser.add_argument("--dollar-csv", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "out/gold-research.json")
    args = parser.parse_args()
    raw = args.market.read_bytes()
    snapshot = json.loads(raw)
    series = {r["id"]: r.get("history", []) for r in snapshot.get("macro", [])}
    real = csv_history(args.real_csv, "DFII10") if args.real_csv else series.get("DFII10", [])
    dollar = csv_history(args.dollar_csv, "DTWEXBGS") if args.dollar_csv else series.get("DTWEXBGS", [])
    report = evaluate(snapshot, real, dollar)
    report["source_snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    report["source_urls"] = ["https://fred.stlouisfed.org/series/DFII10", "https://fred.stlouisfed.org/series/DTWEXBGS"]
    report["external_csv_sha256"] = {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in [args.real_csv, args.dollar_csv] if p}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=1) + "\n")
    print(json.dumps({"status": report["status"], "production_eligible": False, "metrics": report["metrics"]}))


if __name__ == "__main__":
    main()
