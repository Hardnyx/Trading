import { alignReturns, covariance, variance, mean, finite } from "./analytics.mjs?v=0.18.0";
import { SECTOR_PROXIES } from "./policy.mjs?v=0.18.0";
import { ewmaCovariance } from "./risk-math.mjs?v=0.18.0";

const clamp = (x, low, high) => Math.max(low, Math.min(high, x));
const toCorrelation = (matrix) => matrix.map((row, i) =>
  row.map((value, j) => {
    const di = matrix[i][i], dj = matrix[j][j];
    if (!(di > 1e-12) || !(dj > 1e-12)) return i === j ? 1 : 0;
    return clamp(value / Math.sqrt(di * dj), -1, 1);
  }));

/**
 * Remove observed market regime and sector proxy movements from pairwise
 * dependence. Regimes are defined using SPY returns known BEFORE each day.
 * This is a linear statistical residual, NOT a causal or "true" correlation.
 * Always keep total historical covariance for portfolio simulations.
 */
export function estimateResidualDependence(assets, positions, asOf, lookback = 500,
                                           lambda = 0.94, references = assets) {
  const selected = positions.map((p) => assets.find((a) => a.symbol === p.symbol))
    .filter(Boolean);
  const refs = new Map(references.map((a) => [a.symbol, a]));
  const own = new Map(assets.map((a) => [a.symbol, a]));
  const market = own.get("SPY") || refs.get("SPY");
  const unavailable = (reason) => ({
    rows: [], residualCorrelation: null, residualCovariance: null,
    available: false, note: reason, observations: 0,
  });
  if (!market || !selected.length)
    return unavailable("Sin SPY o sin instrumentos para estimar dependencia residual.");
  const needed = new Map();
  for (const asset of [market, ...selected]) needed.set(asset.symbol, asset);
  for (const asset of selected) {
    const proxy = SECTOR_PROXIES[asset.sector];
    const ref = own.get(proxy) || refs.get(proxy);
    if (ref) needed.set(proxy, ref);
  }
  const prepared = [...needed.values()].map((a) => ({
    ...a,
    history: (a.history || []).filter((r) => r.date <= asOf),
  }));
  const aligned = alignReturns(prepared, lookback);
  if (aligned.dates.length < 126)
    return unavailable("Menos de 126 observaciones comunes; usar correlación total.");
  const bySymbol = new Map(prepared.map((a, i) => [
    a.symbol, aligned.columns[i].map((r) => Math.log1p(r)),
  ]));
  const marketSeries = bySymbol.get("SPY"), n = marketSeries.length;
  const regimes = marketSeries.map((_, t) => {
    if (t < 21) return "warmup";
    let trailing = 0;
    for (let k = Math.max(0, t - 63); k < t; k++) trailing += marketSeries[k];
    return trailing >= 0 ? "bull" : "bear";
  });
  const regimeCounts = Object.fromEntries(
    ["warmup", "bull", "bear"].map((id) => [id, regimes.filter((r) => r === id).length]),
  );
  const indexes = {
    all: Array.from({ length: n }, (_, i) => i),
    bull: regimes.flatMap((r, i) => r === "bull" ? [i] : []),
    bear: regimes.flatMap((r, i) => r === "bear" ? [i] : []),
  };
  const subset = (arr, ids) => ids.map((i) => arr[i]);
  const params = (y, m, ids) => {
    const yy = subset(y, ids), mm = subset(m, ids),
      vm = variance(mm), beta = vm > 1e-14 ? covariance(yy, mm) / vm : 0;
    return { intercept: mean(yy), marketMean: mean(mm), beta: clamp(beta, -5, 5) };
  };
  const residualizeMarket = (y) => {
    const fallback = params(y, marketSeries, indexes.all);
    const bull = indexes.bull.length >= 40
      ? params(y, marketSeries, indexes.bull) : fallback;
    const bear = indexes.bear.length >= 40
      ? params(y, marketSeries, indexes.bear) : fallback;
    const parts = { bull, bear, warmup: fallback };
    return {
      series: y.map((v, t) => {
        const p = parts[regimes[t]];
        return v - p.intercept - p.beta * (marketSeries[t] - p.marketMean);
      }),
      beta: (bull.beta * indexes.bull.length +
        bear.beta * indexes.bear.length +
        fallback.beta * regimeCounts.warmup) / n,
      betas: { bull: bull.beta, bear: bear.beta },
    };
  };
  const marketResiduals = new Map();
  const getMarketResidual = (ticker) => {
    if (!marketResiduals.has(ticker))
      marketResiduals.set(ticker, residualizeMarket(bySymbol.get(ticker)));
    return marketResiduals.get(ticker);
  };
  const rows = selected.map((asset, index) => {
    const original = bySymbol.get(asset.symbol);
    const marketRemoved = getMarketResidual(asset.symbol);
    const proxy = SECTOR_PROXIES[asset.sector];
    const sectorRemoved = proxy && bySymbol.has(proxy) ? getMarketResidual(proxy) : null;
    const vs = sectorRemoved ? variance(sectorRemoved.series) : 0;
    const betaSector = vs > 1e-14
      ? clamp(covariance(marketRemoved.series, sectorRemoved.series) / vs, -5, 5)
      : 0;
    const residual = marketRemoved.series.map((v, t) =>
      v - (sectorRemoved ? betaSector * sectorRemoved.series[t] : 0)
    );
    const rawVariance = variance(original), residualVariance = variance(residual);
    return {
      symbol: asset.symbol,
      weight: positions.find((p) => p.symbol === asset.symbol)?.weight ?? 0,
      sector: sectorRemoved ? proxy : null,
      sectorMarketBeta: sectorRemoved?.beta ?? 0,
      betaMarket: marketRemoved.beta,
      betaMarketBull: marketRemoved.betas.bull,
      betaMarketBear: marketRemoved.betas.bear,
      betaSector,
      rSquared: rawVariance > 1e-14
        ? clamp(1 - residualVariance / rawVariance, 0, 1) : null,
      residualVolatility: Math.sqrt(Math.max(0, residualVariance) * 252),
      residual,
      index,
    };
  });
  // The residual matrix uses the SAME equally weighted window as the total
  // correlation, so both are comparable. A lambda=0.94 EWMA has an effective
  // sample of (1+lambda)/(1-lambda) ~ 32 sessions: it is kept only as a recent
  // diagnostic and never feeds pair constraints.
  const series = rows.map((row) => row.residual);
  const residualCovariance = series.map((x) => series.map((y) => covariance(x, y)));
  const residualCorrelation = toCorrelation(residualCovariance);
  const recentResidualCorrelation = toCorrelation(ewmaCovariance(series, lambda));
  let recentDivergence = 0;
  for (let i = 0; i < series.length; i++)
    for (let j = 0; j < i; j++)
      recentDivergence = Math.max(recentDivergence,
        Math.abs(recentResidualCorrelation[i][j] - residualCorrelation[i][j]));
  return {
    rows: rows.map(({ index, ...row }) => row),
    residualCorrelation, residualCovariance,
    recentResidualCorrelation, recentDivergence,
    recentHalfLife: Math.log(.5) / Math.log(lambda),
    available: true, asOf, inputEnd: aligned.dates.at(-1),
    observations: n, regimeCounts,
    method: "trailing-63d-SPY-bull-bear-sector-OLS-equal-weight",
    note: `Correlación residual equiponderada en ${n} sesiones, tras regresión con betas SPY por régimen definido con 63 sesiones PREVIAS, más proxy sectorial ortogonal al mercado. La EWMA reciente (vida media ${(Math.log(.5) / Math.log(lambda)).toFixed(0)} sesiones) se conserva solo como diagnóstico. No elimina riesgo sistémico ni equivale a causalidad. La covarianza total alimenta el espacio gaussiano latente; las marginales Student-t modifican sus correlaciones lineales.`,
  };
}
