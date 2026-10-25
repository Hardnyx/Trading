import {
  mean,
  covariance,
  quantile,
  sum,
  finite,
  valuation,
  normalizeWeights,
  alignReturns,
} from "./analytics.mjs";
import { buildReturnAnchors, sampleDrifts } from "./return-model.mjs";

export function seededRandom(seed = 20261024) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function normalGenerator(random) {
  let spare = null;
  return () => {
    if (spare !== null) {
      const value = spare;
      spare = null;
      return value;
    }
    const r = Math.sqrt(-2 * Math.log(Math.max(1e-15, random()))),
      theta = 2 * Math.PI * random();
    spare = r * Math.sin(theta);
    return r * Math.cos(theta);
  };
}
export function poisson(random, lambda) {
  const limit = Math.exp(-lambda);
  let value = 1,
    count = 0;
  do {
    count++;
    value *= random();
  } while (value > limit);
  return count - 1;
}
export function ewmaCovariance(columns, lambda = 0.94) {
  if (!columns.length || columns[0].length < 20 || !(lambda > 0 && lambda < 1))
    throw new Error("Historia insuficiente para EWMA.");
  const n = columns.length,
    initial = Math.min(60, columns[0].length);
  let c = columns.map((a) =>
    columns.map(
      (b) => covariance(a.slice(0, initial), b.slice(0, initial)) || 0,
    ),
  );
  for (let t = initial; t < columns[0].length; t++) {
    c = c.map((row, i) =>
      row.map(
        (v, j) => lambda * v + (1 - lambda) * columns[i][t] * columns[j][t],
      ),
    );
  }
  // Shrink off-diagonal covariances by 5%, preserving variances and PSD.
  return c.map((row, i) => row.map((v, j) => v * 252 * (i === j ? 1 : 0.95)));
}
export function cholesky(matrix) {
  const n = matrix.length,
    l = Array.from({ length: n }, () => Array(n).fill(0));
  for (let i = 0; i < n; i++)
    for (let j = 0; j <= i; j++) {
      let value = matrix[i][j];
      for (let k = 0; k < j; k++) value -= l[i][k] * l[j][k];
      if (i === j) {
        if (value < -1e-9)
          throw new Error("La matriz no es semidefinida positiva.");
        l[i][j] = Math.sqrt(Math.max(0, value));
      } else l[i][j] = l[j][j] > 1e-12 ? value / l[j][j] : 0;
    }
  return l;
}
export function simulateForecast(
  assets,
  positions,
  options = {},
  overrides = {},
) {
  const settings = {
    model: "merton",
    horizon: 1,
    paths: 3000,
    seed: 20261024,
    driftMode: "fundamental",
    manualReturn: 0.06,
    lambda: 0.94,
    jumpIntensity: 0.35,
    jumpMean: -0.12,
    jumpVol: 0.08,
    uncertainFundamentals: true,
    ...options,
  };
  if (
    !["gbm", "merton"].includes(settings.model) ||
    !["fundamental", "manual"].includes(settings.driftMode) ||
    !(settings.horizon >= 0.25 && settings.horizon <= 5) ||
    !Number.isInteger(settings.paths) ||
    settings.paths < 100 ||
    settings.paths > 15000 ||
    !(settings.manualReturn > -0.9 && settings.manualReturn <= 2) ||
    !(settings.jumpIntensity >= 0 && settings.jumpIntensity <= 5) ||
    !(settings.jumpMean >= -0.8 && settings.jumpMean <= 0.5) ||
    !(settings.jumpVol >= 0 && settings.jumpVol <= 1)
  )
    throw new Error("Parámetros de simulación fuera de rango.");
  const lookup = new Map(assets.map((a) => [a.symbol, a]));
  const weights = normalizeWeights(
    positions.filter((p) => lookup.has(p.symbol)),
  );
  if (!weights.length)
    throw new Error("Agrega activos a la cartera para simular.");
  const selected = weights.map((p) => lookup.get(p.symbol));
  const aligned = alignReturns(selected, 500);
  const logs = aligned.columns.map((col) => col.map(Math.log1p));
  const cov = ewmaCovariance(logs, settings.lambda),
    l = cholesky(cov);
  const drifts = buildReturnAnchors(selected, settings, overrides);
  const coverage = sum(
    weights.filter((_, i) => drifts[i].fundamental).map((p) => p.weight),
  );
  const steps = Math.round(52 * settings.horizon),
    dt = settings.horizon / steps;
  const random = seededRandom(settings.seed),
    normal = normalGenerator(random),
    n = selected.length;
  const observations = Array.from({ length: steps + 1 }, () => []),
    terminal = [],
    maxDrawdowns = [],
    samplePaths = [];
  const intensity = settings.model === "merton" ? settings.jumpIntensity : 0;
  const kappa = Math.exp(settings.jumpMean + settings.jumpVol ** 2 / 2) - 1;
  const vols = cov.map((row, i) => row[i]);
  for (let p = 0; p < settings.paths; p++) {
    const means = sampleDrifts(drifts, settings, random);
    const logDrift = means.map(
      (mu, i) => (mu - vols[i] / 2 - intensity * kappa) * dt,
    );
    const prices = Array(n).fill(1),
      path = [100];
    let peak = 1,
      worst = 0;
    observations[0].push(100);
    for (let t = 1; t <= steps; t++) {
      const z = Array.from({ length: n }, normal);
      let jump = 0;
      if (intensity > 0) {
        const count = poisson(random, intensity * dt);
        if (count)
          jump =
            count * settings.jumpMean +
            Math.sqrt(count) * settings.jumpVol * normal();
      }
      for (let i = 0; i < n; i++) {
        let shock = 0;
        for (let j = 0; j <= i; j++) shock += l[i][j] * z[j];
        prices[i] *= Math.exp(logDrift[i] + Math.sqrt(dt) * shock + jump);
      }
      // Initial units are held through the horizon: buy-and-hold simulated wealth.
      const total = sum(prices.map((price, i) => price * weights[i].weight));
      peak = Math.max(peak, total);
      worst = Math.min(worst, total / peak - 1);
      observations[t].push(total * 100);
      if (p < 12) path.push(total * 100);
    }
    terminal.push(observations[steps].at(-1) / 100 - 1);
    maxDrawdowns.push(worst);
    if (p < 12) samplePaths.push(path);
  }
  const bands = observations.map((values, step) => ({
    year: step * dt,
    p05: quantile(values, 0.05),
    p25: quantile(values, 0.25),
    p50: quantile(values, 0.5),
    p75: quantile(values, 0.75),
    p95: quantile(values, 0.95),
  }));
  const threshold = quantile(terminal, 0.05),
    tail = terminal.filter((r) => r <= threshold);
  const lossProbability =
    terminal.filter((r) => r < 0).length / terminal.length;
  const min = quantile(terminal, 0.005),
    max = quantile(terminal, 0.995),
    bins = Array(26).fill(0),
    width = (max - min) / bins.length || 0.01;
  for (const r of terminal)
    bins[
      Math.min(bins.length - 1, Math.max(0, Math.floor((r - min) / width)))
    ]++;
  return {
    settings,
    bands,
    samplePaths,
    drifts,
    coverage,
    covariance: cov,
    terminal,
    histogram: bins.map((count, i) => ({
      low: min + i * width,
      high: min + (i + 1) * width,
      count,
    })),
    lossProbability,
    lossProbabilitySE: Math.sqrt(
      (lossProbability * (1 - lossProbability)) / settings.paths,
    ),
    severeLossProbability:
      terminal.filter((r) => r < -0.2).length / terminal.length,
    drawdownProbability:
      maxDrawdowns.filter((r) => r < -0.2).length / terminal.length,
    meanReturn: mean(terminal),
    medianReturn: quantile(terminal, 0.5),
    p05: threshold,
    p95: quantile(terminal, 0.95),
    var95: Math.max(0, -threshold),
    cvar95: Math.max(0, -mean(tail)),
    historicalObservations: aligned.dates.length,
    inputEnd: aligned.dates.at(-1),
    horizonYears: settings.horizon,
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
    500,
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
