"""Registro diario sellado de pronósticos de riesgo a una sesión por activo.

Sella h_{t+1|t}, VaR95 y ES95 de GJR-GARCH-t y de la referencia EWMA antes de
la siguiente apertura, los puntúa en un archivo separado cuando existe la
primera sesión posterior y resume cobertura, agrupamiento de excepciones y
QLIKE por versión del modelo de riesgo (sección 8 del documento técnico).

No decide operaciones ni atribuye causas a noticias. Un pronóstico sellado
nunca se reescribe; un resultado ausente queda sin puntuar, no se vuelve cero.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import chi2, norm, t as student_t

if __package__:
    from .volatility_research import ewma_next, prices_to_returns
else:
    from volatility_research import ewma_next, prices_to_returns

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/risk-forecasts"
SUMMARY = ROOT / "dist/data/risk-calibration.json"

# Independent of the page engine version. Bump ONLY when the sealed variance
# forecasts, the quantile law or the EWMA reference change, so that evidence
# keeps accumulating across interface releases.
RISK_MODEL_VERSION = "1.0.0"
EWMA_DECAY = 0.94
TAIL = 0.05
# Operational thresholds, fixed before any outcome is observed. They are not
# a power analysis; below them the summary reports "accumulating".
MINIMUM_SESSIONS = 20
MINIMUM_OBSERVATIONS = 500
NEW_YORK = ZoneInfo("America/New_York")


def next_session_start(cut: str) -> str:
    """Conservative weekday calendar; it does not certify exchange holidays."""
    day = datetime.strptime(cut, "%Y-%m-%d") + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def prospective_eligibility(snapshot: dict, issued_at: str) -> dict:
    """Same window as scripts/seal_forecast.mjs: after the original close and
    before the first subsequent 09:30 New York opening."""
    try:
        now, collected = _instant(issued_at), _instant(snapshot["generated_at"])
    except (KeyError, TypeError, ValueError):
        return {"eligible": False, "reason": "Snapshot not captured before issuance"}
    cut = snapshot.get("price_as_of")
    if not cut or collected > now:
        return {"eligible": False, "reason": "Snapshot not captured before issuance"}
    local = now.astimezone(NEW_YORK)
    date, minutes = local.strftime("%Y-%m-%d"), local.hour * 60 + local.minute
    following = next_session_start(cut)
    if (date < cut or (date == cut and minutes < 16 * 60) or date > following
            or (date == following and minutes >= 9 * 60 + 30)):
        return {"eligible": False,
                "reason": "Issuer is outside first subsequent NYSE opening"}
    return {"eligible": True, "reason": "Original-close-to-next-session-window",
            "next_session_start_estimate": following + "T09:30 America/New_York",
            "warning": "Weekday calendar is conservative and does not certify exchange holidays."}


def tail_block(mean_pct: float, variance_pct2: float, nu: float | None) -> dict:
    """One-session lower-tail VaR/ES in log-return percent.

    Student-t is standardized to unit variance; ES uses the closed form
    E[T | T <= q] = -f(q)/alpha * (nu + q^2)/(nu - 1)."""
    if not (variance_pct2 > 0 and math.isfinite(variance_pct2) and math.isfinite(mean_pct)):
        raise ValueError("Pronóstico de varianza inválido")
    sd = math.sqrt(variance_pct2)
    if nu is None:
        q = float(norm.ppf(TAIL))
        es = -float(norm.pdf(q)) / TAIL
    else:
        if not 2 < nu < 1e6:
            raise ValueError("Grados de libertad fuera de rango")
        raw = float(student_t.ppf(TAIL, nu))
        scale = math.sqrt((nu - 2) / nu)
        q = raw * scale
        es = -float(student_t.pdf(raw, nu)) / TAIL * (nu + raw**2) / (nu - 1) * scale
    return {"mean_pct": mean_pct, "variance_pct2": variance_pct2,
            "var95_pct": mean_pct + sd * q, "es95_pct": mean_pct + sd * es}


def instrument_forecast(asset: dict, cut: str, record: dict | None,
                        train_window: int) -> dict:
    dates, returns = prices_to_returns(asset.get("history", []), cut)
    if not dates or dates[-1] != cut:
        raise ValueError("Sin cierre en el corte")
    if len(returns) < train_window:
        raise ValueError("Historia menor que la ventana de entrenamiento")
    training = returns[-train_window:]
    # Same definition as the walk-forward reference: centre = window mean.
    center = float(np.mean(training) * 100)
    ewma = tail_block(center, ewma_next(training, center, EWMA_DECAY), None)
    gjr = None
    params = [record.get(k) for k in ("variance_next_pct2", "nu", "mean_pct")] \
        if record else []
    if (record and record.get("status") in ("accepted", "research_only")
            and record.get("fitted_through") == cut
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in params)):
        gjr = {"status": record["status"],
               **tail_block(record["mean_pct"], record["variance_next_pct2"], record["nu"]),
               "nu": record["nu"]}
    return {"ewma": ewma, "gjr": gjr,
            # The model the page's hybrid mode uses for this instrument.
            "production": "gjr" if gjr and gjr["status"] == "accepted" else "ewma"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_seal(snapshot: dict, volatility: dict, market_bytes: bytes,
               volatility_bytes: bytes, issued_at: str) -> dict:
    gate = prospective_eligibility(snapshot, issued_at)
    if not gate["eligible"]:
        raise ValueError("Nonprospective origin: " + gate["reason"])
    if (volatility.get("as_of") != snapshot["price_as_of"] or
            volatility.get("source_market_generated_at") != snapshot["generated_at"]):
        raise ValueError("Market snapshot and GJR calibration are not same original cut")
    cut, window = snapshot["price_as_of"], int(volatility["training_window"])
    instruments, skipped = {}, {}
    for asset in snapshot.get("assets", []):
        if asset.get("type") == "cash":
            continue
        try:
            instruments[asset["symbol"]] = instrument_forecast(
                asset, cut, volatility["instruments"].get(asset["symbol"]), window)
        except (ValueError, IndexError) as exc:
            skipped[asset["symbol"]] = str(exc)[:120]
    return {
        "schema_version": 1,
        "ledger": "daily-one-session-risk",
        "risk_model_version": RISK_MODEL_VERSION,
        "research_only": True,
        "issued_at": issued_at,
        "original_price_as_of": cut,
        "market_collected_at": snapshot["generated_at"],
        "target": "first subsequent session close in a later published snapshot",
        "eligibility": gate,
        "market_sha256": _sha256(market_bytes),
        "volatility_sha256": _sha256(volatility_bytes),
        "method": {
            "unit": "daily log return in percent; variance in percent squared",
            "tail": TAIL,
            "gjr": "GJR-GARCH(1,1) standardized Student-t, parameters from volatility.json at the same cut",
            "ewma": f"EWMA({EWMA_DECAY}) over the previous {window} sessions centred on their mean; Gaussian quantiles",
        },
        "instruments": instruments,
        "skipped": skipped,
    }


def score_seal(seal: dict, snapshot: dict) -> dict | None:
    """Score the first session after the sealed cut. Returns None until a
    later snapshot exists. Errors are kept even when an event coincides."""
    cut = seal["original_price_as_of"]
    if snapshot["price_as_of"] <= cut:
        return None
    assets = {a["symbol"]: a for a in snapshot.get("assets", [])}
    rows = {}
    for symbol, forecast in seal["instruments"].items():
        history = sorted(assets.get(symbol, {}).get("history", []), key=lambda r: r["date"])
        base = next((r for r in history if r["date"] == cut), None)
        after = next((r for r in history if r["date"] > cut), None)
        try:
            ratio = float(after["adj_close"]) / float(base["adj_close"])
        except (TypeError, KeyError, ValueError, ZeroDivisionError):
            ratio = None
        if ratio is None or not (ratio > 0 and math.isfinite(ratio)):
            rows[symbol] = {"status": "missing_outcome"}
            continue
        observed = 100 * math.log(ratio)
        row = {"status": "scored", "session": after["date"], "return_pct": observed,
               "production": forecast["production"]}
        for model in ("ewma", "gjr"):
            block = forecast.get(model)
            if not block:
                continue
            error = observed - block["mean_pct"]
            h = block["variance_pct2"]
            row[model] = {
                "z": error / math.sqrt(h),
                "qlike": math.log(h) + error**2 / h,
                "var95_exception": observed < block["var95_pct"],
                "es95_pct": block["es95_pct"],
            }
        rows[symbol] = row
    return {"schema_version": 1, "seal_cut": cut,
            "risk_model_version": seal["risk_model_version"],
            "scoring_price_as_of": snapshot["price_as_of"],
            "instruments": rows,
            "warning": "Squared daily returns are a noisy variance proxy. Adjusted closes approximate total return; no broker execution."}


def _xlogy(x: float, y: float) -> float:
    return 0.0 if x == 0 else x * math.log(y)


def kupiec(exceptions: int, n: int, p: float = TAIL) -> dict:
    """Unconditional coverage likelihood ratio, chi-square(1)."""
    if n == 0:
        return {"lr": None, "p_value": None}
    rate = exceptions / n
    lr = -2 * (_xlogy(n - exceptions, 1 - p) + _xlogy(exceptions, p)
               - _xlogy(n - exceptions, 1 - rate) - _xlogy(exceptions, rate))
    return {"lr": lr, "p_value": float(chi2.sf(max(lr, 0.0), 1))}


def christoffersen(sequences: list[list[bool]]) -> dict:
    """Independence of exceptions from per-instrument consecutive sealed
    sessions, pooled transition counts, chi-square(1)."""
    n = {(0, 0): 0, (0, 1): 0, (1, 0): 0, (1, 1): 0}
    for sequence in sequences:
        for a, b in zip(sequence, sequence[1:]):
            n[(int(a), int(b))] += 1
    total = sum(n.values())
    leaving0, leaving1 = n[(0, 0)] + n[(0, 1)], n[(1, 0)] + n[(1, 1)]
    if total == 0 or leaving0 == 0 or leaving1 == 0:
        return {"lr": None, "p_value": None, "transitions": total}
    pi = (n[(0, 1)] + n[(1, 1)]) / total
    pi0, pi1 = n[(0, 1)] / leaving0, n[(1, 1)] / leaving1
    restricted = _xlogy(n[(0, 0)] + n[(1, 0)], 1 - pi) + _xlogy(n[(0, 1)] + n[(1, 1)], pi)
    free = (_xlogy(n[(0, 0)], 1 - pi0) + _xlogy(n[(0, 1)], pi0)
            + _xlogy(n[(1, 0)], 1 - pi1) + _xlogy(n[(1, 1)], pi1))
    lr = -2 * (restricted - free)
    return {"lr": lr, "p_value": float(chi2.sf(max(lr, 0.0), 1)), "transitions": total}


def _model_summary(rows: list[tuple[str, str, dict, float]]) -> dict:
    """rows: (cut, symbol, model score, observed return)."""
    if not rows:
        return {"observations": 0}
    exceptions = [r for r in rows if r[2]["var95_exception"]]
    by_symbol: dict[str, list[tuple[str, bool]]] = {}
    for cut, symbol, score, _ in rows:
        by_symbol.setdefault(symbol, []).append((cut, score["var95_exception"]))
    sequences = [[hit for _, hit in sorted(v)] for v in by_symbol.values()]
    shortfall = (sum(r[3] for r in exceptions) / sum(r[2]["es95_pct"] for r in exceptions)
                 if exceptions else None)
    return {
        "observations": len(rows),
        "mean_qlike": sum(r[2]["qlike"] for r in rows) / len(rows),
        "var95_exceptions": len(exceptions),
        "var95_exception_rate": len(exceptions) / len(rows),
        "kupiec": kupiec(len(exceptions), len(rows)),
        "christoffersen": christoffersen(sequences),
        # Mean realized loss on exception days over mean sealed ES: ~1 when
        # the tail depth is calibrated, >1 when losses exceed the ES.
        "es95_realized_ratio": shortfall,
    }


def summarize(seals: dict[str, dict], scores: dict[str, dict], generated_at: str) -> dict:
    versions: dict[str, dict] = {}
    for cut, seal in sorted(seals.items()):
        entry = versions.setdefault(seal["risk_model_version"], {
            "sealed_sessions": 0, "scored_sessions": 0, "pending": [],
            "rows": {"ewma": [], "gjr": [], "production": []}, "paired": []})
        entry["sealed_sessions"] += 1
        score = scores.get(cut)
        if not score:
            entry["pending"].append(cut)
            continue
        entry["scored_sessions"] += 1
        for symbol, row in score["instruments"].items():
            if row.get("status") != "scored":
                continue
            for model in ("ewma", "gjr"):
                if model in row:
                    entry["rows"][model].append((cut, symbol, row[model], row["return_pct"]))
            entry["rows"]["production"].append(
                (cut, symbol, row[row["production"]], row["return_pct"]))
            if "gjr" in row:
                entry["paired"].append(row["ewma"]["qlike"] - row["gjr"]["qlike"])
    result = {}
    for version, entry in versions.items():
        paired = entry["paired"]
        models = {name: _model_summary(rows) for name, rows in entry["rows"].items()}
        enough = (entry["scored_sessions"] >= MINIMUM_SESSIONS and
                  models["production"]["observations"] >= MINIMUM_OBSERVATIONS)
        result[version] = {
            "status": "evaluable" if enough else "accumulating",
            "sealed_sessions": entry["sealed_sessions"],
            "scored_sessions": entry["scored_sessions"],
            "pending": entry["pending"],
            "models": models,
            "paired_qlike_ewma_minus_gjr": {
                "observations": len(paired),
                "mean": sum(paired) / len(paired) if paired else None,
            },
        }
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "current_risk_model_version": RISK_MODEL_VERSION,
        "minimum_sessions": MINIMUM_SESSIONS,
        "minimum_observations": MINIMUM_OBSERVATIONS,
        "tail": TAIL,
        "versions": result,
        "warning": "Prospective one-session diagnostics. Pooled tests treat instruments as independent, which they are not; thresholds are operational rules, not power analyses. Nothing here promotes parameters automatically.",
    }


def _read_directory(directory: Path) -> dict[str, dict]:
    if not directory.is_dir():
        return {}
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("????-??-??.json"))}


def _write_once(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "score", "summary"])
    parser.add_argument("--skip-ineligible", action="store_true")
    parser.add_argument("--snapshot", default=str(ROOT / "dist/data/market.json"))
    parser.add_argument("--volatility", default=str(ROOT / "dist/data/volatility.json"))
    args = parser.parse_args()
    market_bytes = Path(args.snapshot).read_bytes()
    snapshot = json.loads(market_bytes)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if args.action == "seal":
        location = LEDGER / f"{snapshot['price_as_of']}.json"
        if location.exists():
            print("Existing immutable risk seal retained:", location)
            return
        gate = prospective_eligibility(snapshot, now)
        if not gate["eligible"] and args.skip_ineligible:
            print("No prospective risk seal:", gate["reason"])
            return
        volatility_bytes = Path(args.volatility).read_bytes()
        seal = build_seal(snapshot, json.loads(volatility_bytes), market_bytes,
                          volatility_bytes, now)
        _write_once(location, seal)
        print(f"Sealed one-session risk for {len(seal['instruments'])} instruments:", location)
    elif args.action == "score":
        for cut, seal in _read_directory(LEDGER).items():
            location = LEDGER / "scores" / f"{cut}.json"
            if location.exists():
                continue
            score = score_seal(seal, snapshot)
            if score is None:
                print("Awaiting next session for risk seal", cut)
                continue
            score["scored_at"] = now
            score["seal_sha256"] = _sha256((LEDGER / f"{cut}.json").read_bytes())
            _write_once(location, score)
            print("Scored risk seal", cut)
    else:
        summary = summarize(_read_directory(LEDGER),
                            _read_directory(LEDGER / "scores"), now)
        SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY.write_text(json.dumps(summary, ensure_ascii=False,
                                      separators=(",", ":"), allow_nan=False),
                           encoding="utf-8")
        print("Risk calibration summary:", {v: s["status"] for v, s in summary["versions"].items()})


if __name__ == "__main__":
    main()
