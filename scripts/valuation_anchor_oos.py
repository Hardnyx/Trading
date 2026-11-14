"""Apply the registered out-of-sample test of the index and bond return anchors."""
import argparse
import csv
import gzip
import io
import json
import math
from pathlib import Path

from scipy.stats import t as student

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/estudio-anclas-valoracion-v1.json"


def load(path=ROOT / "data/history/valuation/shiller-monthly.csv.gz"):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = list(csv.DictReader(io.StringIO(handle.read())))
    out = []
    for r in rows:
        try:
            out.append({k: float(r[k]) for k in ("price", "dividend", "earnings", "cpi", "gs10")} | {"date": r["date"]})
        except ValueError:
            break
    return out


def equity_realized(rows, i):
    value = 1.0
    for k in range(12):
        value *= (rows[i + k + 1]["price"] + rows[i + k]["dividend"] / 12) / rows[i + k]["price"]
    return value - 1


def bond_realized(rows, i):
    coupon, later = rows[i]["gs10"] / 100, rows[i + 12]["gs10"] / 100
    price = sum(coupon / (1 + later) ** n for n in range(1, 10)) + 1 / (1 + later) ** 9
    return price + coupon - 1


def equity_anchor(rows, i, prior, confidence):
    earnings_yield = rows[i - 3]["earnings"] / rows[i]["price"]
    inflation = rows[i - 1]["cpi"] / rows[i - 13]["cpi"] - 1
    return prior + confidence * (earnings_yield + inflation - prior)


def evaluate(rows, origins, anchor, realized, start=13):
    """Expanding mean uses only 12-month returns that matured by the origin."""
    out = []
    for i in origins:
        known = [realized(rows, j) for j in range(start, i - 11)]
        out.append((rows[i]["date"], anchor(i), sum(known) / len(known), realized(rows, i)))
    return out


def score(records, constant=None):
    e_a = [r - f for _, f, _, r in records]
    e_b = [r - (constant if constant is not None else h) for _, _, h, r in records]
    r2 = 1 - sum(e * e for e in e_a) / sum(e * e for e in e_b)
    # Clark-West: adjusted difference for nested comparisons.
    adj = [eb * eb - (ea * ea - (fa - (constant if constant is not None else h)) ** 2)
           for (ea, eb, (_, fa, h, _)) in zip(e_a, e_b, records)]
    n = len(adj)
    mean = sum(adj) / n
    sd = math.sqrt(sum((a - mean) ** 2 for a in adj) / (n - 1))
    tstat = mean / (sd / math.sqrt(n))
    return {"n": n, "r2_os": r2, "clark_west_t": tstat, "p_one_sided": float(student.sf(tstat, n - 1)),
            "mean_error_anchor": sum(e_a) / n, "mean_error_benchmark": sum(e_b) / n}


def verdict(s):
    if s["r2_os"] <= 0:
        return "not-supported"
    return "supported" if s["p_one_sided"] < 0.05 else "inconclusive"


def run(design):
    rows = load()
    index = {r["date"][:7]: i for i, r in enumerate(rows)}
    eq = design["equity_anchor"]
    anchors = {
        "equity_anchor": (lambda i: equity_anchor(rows, i, eq["prior"], eq["confidence"]), lambda r, i: equity_realized(r, i)),
        "bond_anchor": (lambda i: rows[i]["gs10"] / 100, lambda r, i: bond_realized(r, i)),
    }
    sample = design["primary_sample"]
    result = {"schema": "valuation-anchor-out-of-sample-result-v1", "design": DESIGN.name}
    for name, (anchor, realized) in anchors.items():
        primary = [index[f"{y}-01"] for y in range(sample["first_origin_year"], sample["last_origin_year"] + 1)]
        records = evaluate(rows, primary, anchor, realized)
        s = score(records)
        offsets = {}
        for month in range(1, 13):
            origins = [index[f"{y}-{month:02d}"] for y in range(sample["first_origin_year"], sample["last_origin_year"] + 1)]
            offsets[month] = round(score(evaluate(rows, origins, anchor, realized))["r2_os"], 4)
        periods = {}
        for label, (a, b) in {"1900-1959": (1900, 1959), "1960-1989": (1960, 1989), "1990-2018": (1990, 2018)}.items():
            periods[label] = {k: round(v, 4) for k, v in score([r for r in records if a <= int(r[0][:4]) <= b]).items()
                              if k in ("n", "r2_os", "p_one_sided")}
        result[name] = {"verdict": verdict(s), "primary": s,
                        "versus_constant_6pct": round(score(records, constant=0.06)["r2_os"], 4),
                        "r2_os_by_origin_month": offsets, "subperiods": periods}
    result["limits"] = design["limits"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/auditorias/valuation-anchor-oos-1900-2018.json")
    options = parser.parse_args()
    result = run(json.loads(DESIGN.read_text(encoding="utf-8")))
    options.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: (v["verdict"], round(v["primary"]["r2_os"], 4), round(v["primary"]["p_one_sided"], 4))
                      for k, v in result.items() if isinstance(v, dict) and "verdict" in v}))


if __name__ == "__main__":
    main()
