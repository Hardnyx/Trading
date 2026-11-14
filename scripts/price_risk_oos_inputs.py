"""Build the registered 2008-2019 price-only market from the repository archive.

Closes are split-adjusted; a backward total-return factor applies each cash
dividend as (1 - dividend / previous close), the usual adjusted-close rule.
"""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-riesgo-precios-2008-2019-v1.json"


def read_csv(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return list(csv.DictReader(io.StringIO(handle.read())))


def adjusted_history(symbol, cut, archive=ROOT / "data/history/prices"):
    folder = archive / symbol
    rows = [r for f in sorted(folder.glob("[0-9]*.csv.gz")) for r in read_csv(f)]
    rows = sorted({r["date"]: r for r in rows if r["date"] <= cut and float(r["close"]) > 0}.values(),
                  key=lambda r: r["date"])
    dividends = {}
    events = folder / "events.csv.gz"
    if events.exists():
        for e in read_csv(events):
            if e["type"] == "dividend" and e["date"] <= cut:
                dividends[e["date"]] = dividends.get(e["date"], 0.0) + float(e["value"])
    closes = [float(r["close"]) for r in rows]
    factor, adjusted = 1.0, [0.0] * len(rows)
    for i in range(len(rows) - 1, -1, -1):
        adjusted[i] = closes[i] * factor
        amount = dividends.get(rows[i]["date"])
        if amount and i > 0:
            factor *= 1 - amount / closes[i - 1]
    return [{"date": r["date"], "close": c, "adj_close": a, "volume": int(float(r["volume"] or 0))}
            for r, c, a in zip(rows, closes, adjusted)]


def build(design, market):
    meta = {a["symbol"]: a for a in market["assets"]}
    cut = design["data"]["history_cut"]
    assets = [{"symbol": s, "type": meta[s]["type"], "sector": meta[s]["sector"],
               "history": adjusted_history(s, cut)} for s in design["instruments"]]
    return {"price_as_of": cut, "assets": assets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "out/price-risk-oos-market.json")
    options = parser.parse_args()
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    market = build(design, json.loads((ROOT / "dist/data/market.json").read_text(encoding="utf-8")))
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(market) + "\n", encoding="utf-8")
    print(json.dumps({a["symbol"]: [a["history"][0]["date"], len(a["history"])] for a in market["assets"]}))


if __name__ == "__main__":
    main()
