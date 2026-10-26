import {
  mean,
  quantile,
  sum,
  finite,
  normalizeWeights,
  alignReturns,
} from "./analytics.mjs?v=0.8.3";
import { ewmaCovariance } from "./risk-math.mjs?v=0.8.3";
import { preparePaths, generatePaths, evaluatePaths } from "./path-model.mjs?v=0.8.3";
import { factorModel } from "./factors.mjs?v=0.8.3";
export { seededRandom, normalGenerator, poisson } from "./random.mjs?v=0.8.3";
export { ewmaCovariance, cholesky } from "./risk-math.mjs?v=0.8.3";

export function simulateForecast(
  assets,
  positions,
  options = {},
  overrides = {},
) {
  const lookup = new Map(assets.map((a) => [a.symbol, a])),
    weights = normalizeWeights(positions.filter((p) => lookup.has(p.symbol)));
  if (!weights.length)
    throw new Error("Agrega activos a la cartera para simular.");
  const exposures = factorModel(
    assets,
    weights,
    options.asOf ||
      assets.map((a) => a.price_date || a.history.at(-1).date).sort()[0],
  );
  const marketLoadings =
    options.marketLoadings ||
    Object.fromEntries(
      exposures.rows.map((r) => [
        r.symbol,
        Math.max(-3, Math.min(3, r.betaMarket)),
      ]),
    );
  const inputs = preparePaths(
    [
      ...weights.map((p) => lookup.get(p.symbol)),
      ...(!weights.some((p) => p.symbol === "SPY") && lookup.has("SPY")
        ? [lookup.get("SPY")]
        : []),
    ],
    { ...options, marketLoadings },
    overrides,
    assets,
  );
  const sample = generatePaths(
    inputs,
    inputs.options.paths,
    inputs.options.seed,
    52,
  );
  const metrics = evaluatePaths(
    inputs.assets.map(
      (a) => weights.find((p) => p.symbol === a.symbol)?.weight || 0,
    ),
    sample,
    {
      capital: options.capital || 100000,
      cost: options.initialCost || 0,
      details: true,
    },
  );
  const values = metrics.terminal,
    min = quantile(values, 0.005),
    max = quantile(values, 0.995),
    bins = Array(26).fill(0),
    width = (max - min) / 26 || 0.01;
  for (const value of values)
    bins[Math.max(0, Math.min(25, Math.floor((value - min) / width)))]++;
  return {
    ...metrics,
    settings: (()=> {
      const { volatilityData: _source, ...kept }=inputs.options;
      return kept;
    })(),
    volatility: {
      mode: inputs.conditional.enabled ? "GJR-GARCH-t / EWMA" : "EWMA",
      accepted: inputs.conditional.active,
      fallback: inputs.conditional.fallback,
      reason: inputs.conditional.reason,
      studentNu: null,
      innovationLaw: inputs.conditional.dynamic
        ? "Gaussian common-market plus residual innovations"
        : "Legacy covariance/Merton",
      factorMethod: inputs.factorCovariance.method,
      residualGarchValidated: false,
      additionalMertonJumps: !inputs.conditional.dynamic && inputs.options.model==="merton",
    },
    drifts: inputs.anchors,
    coverage: sum(
      weights
        .filter((p, i) => inputs.anchors[i].fundamental)
        .map((p) => p.weight),
    ),
    covariance: inputs.covariance,
    residualCorrelation: inputs.residualCorrelation,
    dependence: inputs.dependence,
    histogram: bins.map((count, i) => ({
      low: min + i * width,
      high: min + (i + 1) * width,
      count,
    })),
    severeLossProbability:
      values.filter((r) => r < -0.2).length / values.length,
    historicalObservations: inputs.observations,
    inputEnd: inputs.calibrationEnd,
    horizonYears: inputs.options.horizon,
    policy: sample.policy,
    scenarioCounts: sample.scenarioCounts,
  };
}

export function validateRiskBands(assets, positions, lambda = 0.94) {
  // Walk forward: only past returns enter each one-month forecast. No fitting to future data.
  const lookup = new Map(assets.map((a) => [a.symbol, a]));
  const weights = normalizeWeights(
    positions.filter((p) => lookup.has(p.symbol)),
  );
  if (!weights.length) return null;
  const alignment = alignReturns(
    weights.map((p) => lookup.get(p.symbol)),
    1260,
  );
  const observations = alignment.dates.map((_, t) =>
    sum(weights.map((p, i) => alignment.columns[i][t] * p.weight)),
  );
  const logs = observations.map(Math.log1p),
    train = 126,
    horizon = 21,
    results = [];
  for (let end = train; end + horizon <= logs.length; end += horizon) {
    const past = logs.slice(end - train, end);
    const cov = ewmaCovariance([past], lambda);
    const std = Math.sqrt((cov[0][0] * horizon) / 252);
    const low = -1.644853626951 * std,
      high = 1.644853626951 * std;
    const realized = sum(logs.slice(end, end + horizon));
    results.push({
      date: alignment.dates[end + horizon - 1],
      low: Math.expm1(low),
      high: Math.expm1(high),
      realized: Math.expm1(realized),
      covered: realized >= low && realized <= high,
    });
  }
  return {
    results,
    coverage: results.length
      ? results.filter((r) => r.covered).length / results.length
      : null,
    count: results.length,
    target: 0.9,
    train,
    horizon,
    note: "Bandas EWMA al 90%, centro de retorno logarítmico cero, ventanas futuras no solapadas de 21 sesiones. Cartera histórica de pesos constantes. No valida el ancla fundamental ni los saltos.",
  };
}
