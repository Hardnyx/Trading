import {
  alignReturns,
  finite,
  mean,
  quantile,
  sum,
  valuation,
} from "./analytics.mjs";
import {
  seededRandom,
  normalGenerator,
  poisson,
  ewmaCovariance,
  cholesky,
} from "./forecast.mjs";
import { buildReturnAnchors, sampleDrifts } from "./return-model.mjs";

export const DEFAULT_COMPOSITION_RULES = {
  maxPosition: 0.2,
  maxSector: 0.35,
  maxCorrelation: 0.85,
  cvarBudget: 0.2,
  maxLossProbability: 0.45,
  reserveCap: 0.5,
  maxPositions: 6,
};

function validateRules(rules) {
  for (const key of [
    "maxPosition",
    "maxSector",
    "cvarBudget",
    "maxLossProbability",
    "reserveCap",
  ]) {
    if (!finite(rules[key]) || rules[key] <= 0 || rules[key] > 1)
      throw new Error("Revisa los límites de composición.");
  }
  if (
    !(rules.maxCorrelation > 0 && rules.maxCorrelation <= 1) ||
    !Number.isInteger(rules.maxPositions) ||
    rules.maxPositions < 2 ||
    rules.maxPositions > 12
  ) {
    throw new Error("Revisa los límites de composición.");
  }
}

// A historical mean return is deliberately absent from the return anchors.
// Past prices enter only the covariance and eligibility checks.
export function prepareComposition(
  snapshot,
  settings = {},
  overrides = {},
  rules = {},
) {
  const limits = { ...DEFAULT_COMPOSITION_RULES, ...rules };
  validateRules(limits);
  const asOf = snapshot.price_as_of;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf))
    throw new Error("El corte de precios no es válido.");
  const rate = snapshot.macro?.find(
    (s) => s.id === "DGS3MO" && s.date <= asOf,
  )?.value;
  const riskFree = finite(rate) ? rate / 100 : null;
  if (riskFree === null)
    throw new Error(
      "Falta una tasa Treasury 3M conocida al corte para valorar la reserva.",
    );
  const options = {
    model: "merton",
    horizon: 1,
    paths: 3000,
    seed: 20261024,
    lambda: 0.94,
    manualReturn: 0.06,
    jumpIntensity: 0.35,
    jumpMean: -0.12,
    jumpVol: 0.08,
    ...settings,
    driftMode: "fundamental",
    uncertainFundamentals: true,
    reserveReturn: riskFree,
  };
  if (
    !["gbm", "merton"].includes(options.model) ||
    ![0.25, 0.5, 1, 3].includes(options.horizon) ||
    !(options.lambda > 0 && options.lambda < 1) ||
    !(options.jumpIntensity >= 0 && options.jumpIntensity <= 5) ||
    !(options.jumpMean >= -0.8 && options.jumpMean <= 0.5) ||
    !(options.jumpVol >= 0 && options.jumpVol <= 1)
  ) {
    throw new Error("Parámetros de proyección fuera de rango.");
  }
  const eligible = [],
    excluded = [];
  for (const original of snapshot.assets) {
    if (original.type !== "stock" && original.symbol !== "SHY") continue;
    const history = original.history.filter((r) => r.date <= asOf);
    const financials = Object.fromEntries(
      Object.entries(original.financials || {}).filter(
        ([, r]) =>
          typeof r !== "object" ||
          r === null ||
          ((!r.filed || r.filed <= asOf) &&
            (!r.period_end || r.period_end <= asOf)),
      ),
    );
    const asset = { ...original, history, financials };
    let reason;
    if (
      original.price_date !== asOf ||
      history.at(-1)?.date !== asOf ||
      history.length < 252
    )
      reason = "Precio al corte o historia insuficiente";
    const model = valuation(asset, overrides[asset.symbol] || {});
    if (
      !reason &&
      asset.type === "stock" &&
      (!asset.financials.eps?.filed || !model)
    )
      reason = "Sin BPA conocido y comparable al corte";
    if (!reason && asset.type === "stock" && model.annualReturn <= riskFree)
      reason = "Ancla fundamental inferior a la reserva";
    if (reason) excluded.push({ symbol: asset.symbol, reason });
    else eligible.push(asset);
  }
  eligible.sort((a, b) => a.symbol.localeCompare(b.symbol));
  if (!eligible.some((a) => a.symbol === "SHY"))
    throw new Error(
      "Falta SHY con historia y precio al corte para la reserva.",
    );
  if (eligible.filter((a) => a.type === "stock").length < 2)
    throw new Error(
      "No hay suficientes acciones con fundamento disponible y retorno del modelo superior a la reserva.",
    );
  const aligned = alignReturns(eligible, 500);
  if (aligned.dates.length < 126 || aligned.dates.at(-1) > asOf)
    throw new Error("Historia común insuficiente al corte.");
  const covariance = ewmaCovariance(
    aligned.columns.map((col) => col.map(Math.log1p)),
    options.lambda,
  );
  const anchors = buildReturnAnchors(eligible, options, overrides);
  return {
    assets: eligible,
    options,
    rules: limits,
    covariance,
    anchors,
    asOf,
    excluded,
    calibrationEnd: aligned.dates.at(-1),
    observations: aligned.dates.length,
    snapshotGeneratedAt: snapshot.generated_at,
    riskFree,
  };
}

export function terminalScenarios(inputs, paths, seed) {
  const { assets, options, anchors, covariance } = inputs;
  if (!Number.isInteger(paths) || paths < 100 || paths > 15000)
    throw new Error("Cantidad de escenarios fuera de rango.");
  const random = seededRandom(seed),
    normal = normalGenerator(random),
    factor = cholesky(covariance);
  const n = assets.length,
    horizon = options.horizon,
    rootTime = Math.sqrt(horizon);
  const intensity = options.model === "merton" ? options.jumpIntensity : 0;
  const kappa = Math.exp(options.jumpMean + options.jumpVol ** 2 / 2) - 1;
  const gross = Array.from({ length: n }, () => new Float64Array(paths));
  for (let p = 0; p < paths; p++) {
    const mu = sampleDrifts(anchors, options, random);
    const z = Array.from({ length: n }, normal);
    const count = intensity > 0 ? poisson(random, intensity * horizon) : 0;
    const jump = count
      ? count * options.jumpMean + Math.sqrt(count) * options.jumpVol * normal()
      : 0;
    for (let i = 0; i < n; i++) {
      let diffusion = 0;
      for (let j = 0; j <= i; j++) diffusion += factor[i][j] * z[j];
      gross[i][p] = Math.exp(
        (mu[i] - covariance[i][i] / 2 - intensity * kappa) * horizon +
          rootTime * diffusion +
          jump,
      );
    }
  }
  return gross;
}

export function evaluateWeights(weights, gross) {
  const paths = gross[0].length;
  const returns = new Array(paths);
  let utility = 0,
    losses = 0;
  for (let p = 0; p < paths; p++) {
    let wealth = 0;
    for (let i = 0; i < weights.length; i++) wealth += weights[i] * gross[i][p];
    returns[p] = wealth - 1;
    utility += Math.log(Math.max(Number.MIN_VALUE, wealth));
    if (wealth < 1) losses++;
  }
  returns.sort((a, b) => a - b);
  const tailCount = Math.max(1, Math.ceil(paths * 0.05));
  const lossProbability = losses / paths;
  return {
    expectedLogGrowth: utility / paths,
    meanReturn: mean(returns),
    medianReturn: quantile(returns, 0.5),
    p05: quantile(returns, 0.05),
    p95: quantile(returns, 0.95),
    cvar95: Math.max(0, -mean(returns.slice(0, tailCount))),
    lossProbability,
    lossProbabilitySE: Math.sqrt(
      (lossProbability * (1 - lossProbability)) / paths,
    ),
    paths,
  };
}

function correlation(inputs, i, j) {
  const c = inputs.covariance;
  return c[i][i] > 0 && c[j][j] > 0
    ? c[i][j] / Math.sqrt(c[i][i] * c[j][j])
    : 0;
}

function feasibleWeights(weights, inputs) {
  const { assets, rules } = inputs;
  if (
    Math.abs(sum(weights) - 1) > 1e-8 ||
    weights.filter((w) => w > 0).length > rules.maxPositions
  )
    return false;
  const sectors = new Map();
  for (let i = 0; i < weights.length; i++) {
    const w = weights[i],
      asset = assets[i];
    if (
      w < 0 ||
      w > (asset.symbol === "SHY" ? rules.reserveCap : rules.maxPosition) + 1e-8
    )
      return false;
    if (w <= 0) continue;
    if (asset.type === "stock")
      sectors.set(asset.sector, (sectors.get(asset.sector) || 0) + w);
    for (let j = 0; j < i; j++)
      if (
        weights[j] > 0 &&
        correlation(inputs, i, j) > rules.maxCorrelation + 1e-8
      )
        return false;
  }
  return [...sectors.values()].every((w) => w <= rules.maxSector + 1e-8);
}

function generateCandidate(inputs, random) {
  const { assets, anchors, rules } = inputs;
  const reserve = assets.findIndex((a) => a.symbol === "SHY");
  const stocks = assets
    .map((a, i) => i)
    .filter((i) => assets[i].type === "stock");
  const maxStocks = Math.min(stocks.length, rules.maxPositions - 1);
  if (maxStocks < 2) return null;
  const count = 2 + Math.floor(random() * (maxStocks - 1));
  const preference = (i) =>
    Math.exp(
      Math.max(
        -3,
        Math.min(
          3,
          anchors[i].mu / Math.max(0.1, Math.sqrt(inputs.covariance[i][i])),
        ),
      ),
    );
  const order = stocks
    .map((i) => ({
      i,
      key: -Math.log(Math.max(1e-15, random())) / preference(i),
    }))
    .sort((a, b) => a.key - b.key);
  const chosen = [];
  for (const { i } of order) {
    if (chosen.every((j) => correlation(inputs, i, j) <= rules.maxCorrelation))
      chosen.push(i);
    if (chosen.length === count) break;
  }
  if (chosen.length !== count) return null;
  const step = 0.05;
  const reserveMin = Math.max(0, 1 - count * rules.maxPosition);
  const low = Math.ceil((reserveMin - 1e-8) / step),
    high = Math.floor(rules.reserveCap / step + 1e-8);
  if (low > high) return null;
  const weights = Array(assets.length).fill(0);
  weights[reserve] = (low + Math.floor(random() * (high - low + 1))) * step;
  for (const i of chosen) weights[i] = step;
  let remaining = Math.round((1 - sum(weights)) / step);
  for (; remaining > 0; remaining--) {
    const available = chosen.filter((i) => {
      const sector = sum(
        chosen
          .filter((j) => assets[j].sector === assets[i].sector)
          .map((j) => weights[j]),
      );
      return (
        weights[i] + step <= rules.maxPosition + 1e-8 &&
        sector + step <= rules.maxSector + 1e-8
      );
    });
    if (!available.length) return null;
    const i = available[Math.floor(random() * available.length)];
    weights[i] = Math.round((weights[i] + step) * 100) / 100;
  }
  // Exact basis-point weights avoid accumulating floating-point drift.
  weights[reserve] = Math.round(weights[reserve] * 100) / 100;
  return feasibleWeights(weights, inputs) ? weights : null;
}

export function composePortfolio(
  snapshot,
  settings = {},
  overrides = {},
  rules = {},
  search = {},
) {
  const inputs = prepareComposition(snapshot, settings, overrides, rules);
  const paths = search.paths ?? 1000,
    finalPaths = search.finalPaths ?? 5000,
    target = search.candidates ?? 400;
  if (!Number.isInteger(target) || target < 1 || target > 2000)
    throw new Error("Búsqueda fuera de rango.");
  const seed = inputs.options.seed >>> 0;
  const random = seededRandom(seed ^ 0x51a7c0de);
  const sample = terminalScenarios(inputs, paths, seed);
  const seen = new Set();
  let best = null,
    evaluated = 0,
    feasible = 0;
  for (
    let attempt = 0;
    attempt < target * 40 && evaluated < target;
    attempt++
  ) {
    const weights = generateCandidate(inputs, random);
    if (!weights) continue;
    const key = weights.join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    const metrics = evaluateWeights(weights, sample);
    evaluated++;
    // Leave room for Monte Carlo error before evaluating the chosen candidate
    // on fresh random draws. These draws are not future market observations.
    if (
      metrics.cvar95 > inputs.rules.cvarBudget * 0.95 ||
      metrics.lossProbability + 2 * metrics.lossProbabilitySE >
        inputs.rules.maxLossProbability
    )
      continue;
    feasible++;
    if (
      !best ||
      metrics.expectedLogGrowth > best.searchMetrics.expectedLogGrowth
    )
      best = { weights, searchMetrics: metrics };
  }
  const metadata = {
    version: 1,
    method: "ex-ante-fundamental-monte-carlo",
    as_of: inputs.asOf,
    generated_at: new Date().toISOString(),
    snapshot_generated_at: inputs.snapshotGeneratedAt,
    calibration_end: inputs.calibrationEnd,
    observations: inputs.observations,
    settings: inputs.options,
    rules: inputs.rules,
    excluded: inputs.excluded,
    search: { evaluated, feasible, paths, allocationStep: 0.05 },
  };
  if (!best)
    return {
      ...metadata,
      status: "no_feasible",
      reason:
        "Ninguna candidata satisface los límites de pérdida y CVaR con estos supuestos. Ajusta los límites o revisa la valoración; la cartera actual se conserva.",
    };
  const verificationSeed = (seed + 0x6a09e667) >>> 0;
  const metrics = evaluateWeights(
    best.weights,
    terminalScenarios(inputs, finalPaths, verificationSeed),
  );
  if (
    metrics.cvar95 > inputs.rules.cvarBudget ||
    metrics.lossProbability > inputs.rules.maxLossProbability
  ) {
    return {
      ...metadata,
      status: "no_feasible",
      reason:
        "La candidata no pasó los límites en la segunda simulación independiente. La cartera actual se conserva.",
      metrics,
    };
  }
  const positions = inputs.assets.flatMap((asset, i) =>
    best.weights[i] > 0
      ? [{ symbol: asset.symbol, weight: best.weights[i] }]
      : [],
  );
  const signals = positions.map((p) => {
    const index = inputs.assets.findIndex((a) => a.symbol === p.symbol),
      asset = inputs.assets[index],
      anchor = inputs.anchors[index];
    return {
      ...p,
      sector: asset.sector,
      price: asset.price,
      price_date: asset.price_date,
      eps: asset.financials?.eps?.value ?? null,
      filed: asset.financials?.eps?.filed ?? null,
      anchor: anchor.annual,
      adverseAnchor: anchor.low,
      favorableAnchor: anchor.high,
      assumptions: { ...asset.assumptions, ...overrides[asset.symbol] },
      source: anchor.source,
    };
  });
  return {
    ...metadata,
    status: "proposed",
    search: { ...metadata.search, selectedMetrics: best.searchMetrics },
    model_inputs: {
      assets: inputs.assets.map((a) => ({
        symbol: a.symbol,
        type: a.type,
        sector: a.sector,
        price: a.price,
        price_date: a.price_date,
        eps: a.financials?.eps ?? null,
        assumptions: { ...a.assumptions, ...overrides[a.symbol] },
      })),
      covariance: inputs.covariance,
      anchors: inputs.anchors,
      risk_free: inputs.riskFree,
    },
    positions,
    signals,
    metrics,
    verification: { seed: verificationSeed, paths: finalPaths },
    objective:
      "Mayor crecimiento logarítmico esperado entre las candidatas que cumplen los límites",
  };
}
