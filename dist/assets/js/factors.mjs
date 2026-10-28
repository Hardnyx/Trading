import { finite, sum } from "./analytics.mjs?v=0.31.0";
import { estimateResidualDependence } from "./residual-dependence.mjs?v=0.31.0";

export function factorModel(assets, positions, asOf, lookback = 500,
                            lambda = 0.94, references = assets) {
  return estimateResidualDependence(assets, positions, asOf, lookback, lambda, references);
}
export function adjustedReturn(asset, from, to) {
  const first = asset.history.find((r) => r.date === from),
    last = asset.history.find((r) => r.date === to);
  return first?.adj_close > 0 && last?.adj_close > 0
    ? last.adj_close / first.adj_close - 1
    : null;
}
export function factorAttribution(snapshot, baseline) {
  const lookup = new Map(snapshot.assets.map((a) => [a.symbol, a])),
    end = snapshot.price_as_of,
    market = lookup.get("SPY"),
    marketReturn = market && adjustedReturn(market, baseline.as_of, end),
    exposures = baseline.factor_exposures;
  if (!finite(marketReturn) || !exposures?.rows?.length) return null;
  const rows = [];
  for (const position of baseline.positions) {
    const a = lookup.get(position.symbol),
      e = exposures.rows.find((r) => r.symbol === position.symbol),
      realized = a && adjustedReturn(a, baseline.as_of, end);
    if (!e || !finite(realized)) return null;
    const sectorReturn = e.sector
      ? adjustedReturn(
          lookup.get(e.sector) || { history: [] },
          baseline.as_of,
          end,
        )
      : 0;
    if (!finite(sectorReturn)) return null;
    const marketEffect = e.betaMarket * marketReturn,
      sectorEffect =
        e.betaSector * (sectorReturn - e.sectorMarketBeta * marketReturn),
      unexplained = realized - marketEffect - sectorEffect;
    rows.push({
      symbol: a.symbol,
      market: position.weight * marketEffect,
      sector: position.weight * sectorEffect,
      unexplained: position.weight * unexplained,
      total: position.weight * realized,
    });
  }
  return {
    rows,
    market: sum(rows.map((r) => r.market)),
    sector: sum(rows.map((r) => r.sector)),
    unexplained: sum(rows.map((r) => r.unexplained)),
    total: sum(rows.map((r) => r.total)),
    note: "Atribución aritmética aproximada en USD de la referencia registrada. Betas fijadas al registro; residual incluye no linealidad. No incorpora movimientos reales, impuestos ni FX posteriores.",
  };
}
