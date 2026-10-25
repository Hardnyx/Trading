import {
  alignReturns,
  covariance,
  variance,
  mean,
  finite,
  sum,
  correlation,
  normalizeWeights,
} from "./analytics.mjs?v=0.3.0";
import { SECTOR_PROXIES } from "./policy.mjs?v=0.3.0";
export function factorModel(assets, positions, asOf, lookback = 500) {
  const lookup = new Map(assets.map((a) => [a.symbol, a])),
    market = lookup.get("SPY");
  if (!market)
    return {
      rows: [],
      residualCorrelation: [],
      note: "Falta SPY para estimar exposiciones.",
    };
  const selected = normalizeWeights(positions)
    .map((p) => ({ p, asset: lookup.get(p.symbol) }))
    .filter((r) => r.asset);
  const all = [
    ...new Map(
      [
        market,
        ...selected
          .flatMap((r) => [r.asset, lookup.get(SECTOR_PROXIES[r.asset.sector])])
          .filter(Boolean),
      ].map((a) => [
        a.symbol,
        { ...a, history: a.history.filter((r) => r.date <= asOf) },
      ]),
    ).values(),
  ];
  const aligned = alignReturns(all, lookback),
    columns = new Map(all.map((a, i) => [a.symbol, aligned.columns[i]])),
    m = columns.get("SPY"),
    vm = variance(m);
  if (aligned.dates.length < 63 || !(vm > 0))
    return {
      rows: [],
      residualCorrelation: [],
      note: "Historia común insuficiente para factores.",
    };
  const rows = selected.map(({ p, asset }) => {
    const y = columns.get(asset.symbol),
      sector = SECTOR_PROXIES[asset.sector],
      s = columns.get(sector);
    const sectorBeta = s ? covariance(s, m) / vm : 0,
      sectorOrthogonal = s ? s.map((v, t) => v - sectorBeta * m[t]) : null;
    const vs = sectorOrthogonal ? variance(sectorOrthogonal) : 0,
      betaMarket = covariance(y, m) / vm,
      betaSector = vs > 1e-14 ? covariance(y, sectorOrthogonal) / vs : 0;
    const residual = y.map(
        (v, t) =>
          v -
          betaMarket * m[t] -
          (sectorOrthogonal ? betaSector * sectorOrthogonal[t] : 0),
      ),
      vy = variance(y),
      vr = variance(residual);
    return {
      symbol: asset.symbol,
      weight: p.weight,
      sector: sector || null,
      sectorMarketBeta: sectorBeta,
      betaMarket,
      betaSector,
      rSquared: vy > 0 ? Math.max(0, Math.min(1, 1 - vr / vy)) : null,
      residualVolatility: Math.sqrt(vr * 252),
      residual,
    };
  });
  return {
    rows,
    residualCorrelation: rows.map((a) =>
      rows.map((b) => correlation(a.residual, b.residual)),
    ),
    asOf,
    inputEnd: aligned.dates.at(-1),
    observations: aligned.dates.length,
    note: "Regresión con mercado SPY y sector ortogonal al mercado. El residual es lo no explicado; no mide habilidad. ETFs sin desglose sectorial.",
  };
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
