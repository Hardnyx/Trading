"""Diagnóstico de volatilidad a partir del corte público; nunca modifica señales."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from volatility_research import walk_forward


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="dist/data/market.json")
    parser.add_argument("--symbols", default="SPY,QQQ,TLT,GLD")
    parser.add_argument("--window", type=int, default=500)
    parser.add_argument("--test-days", type=int, default=63)
    parser.add_argument("--refit-every", type=int, default=21)
    parser.add_argument("--events", help="Registro JSON de eventos verificables (opcional)")
    parser.add_argument("--output", default="out/volatility-shadow.json")
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    assets = {a["symbol"]: a for a in snapshot["assets"]}
    events = json.loads(Path(args.events).read_text(encoding="utf-8")) if args.events else []
    if not isinstance(events, list):
        raise ValueError("--events requiere un arreglo JSON")
    symbols = list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    if not symbols:
        raise ValueError("Define al menos un símbolo")
    report = {
        "version": "shadow-volatility-1",
        "model_scope": "research_only_not_portfolio_decision",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_snapshot": snapshot.get("generated_at"),
        "cutoff": snapshot["price_as_of"],
        "evaluation": {
            "train_window": args.window, "test_days": args.test_days,
            "refit_every": args.refit_every,
            "note": "Sólo series publicadas y fechas previas al pronóstico. No certifica causalidad.",
        },
        "results": {}, "errors": {},
    }
    for symbol in symbols:
        asset = assets.get(symbol)
        if not asset:
            report["errors"][symbol] = "Activo no disponible"
            continue
        relevant_events = [
            e for e in events if symbol in e.get("asset_ids", [])
            or (e.get("scope") == "macro" and e.get("factor_ids"))
        ]
        try:
            report["results"][symbol] = walk_forward(
                asset["history"], snapshot["price_as_of"],
                train_window=args.window, test_days=args.test_days,
                refit_every=args.refit_every, events=relevant_events,
            )
        except (KeyError, ValueError, RuntimeError) as error:
            report["errors"][symbol] = str(error)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                      encoding="utf-8")
    for symbol, row in report["results"].items():
        print(f"{symbol}: {row['gjr_valid_days']} pronósticos · "
              f"QLIKE GJR={row['gjr_qlike']} EWMA={row['ewma_qlike']} · "
              f"excepciones VaR={row['gjr_var95_exceptions']}")
    for symbol, error in report["errors"].items():
        print(f"{symbol}: SIN ESTIMACIÓN ({error})")
    print(f"Diagnóstico guardado: {output}")
    if not report["results"]:
        raise SystemExit("Ningún activo permitió una evaluación válida")


if __name__ == "__main__":
    main()
