import {
  finite,
  sum,
  mean,
  quantile,
  normalizeWeights,
} from "./analytics.mjs?v=0.3.0";
import { seededRandom } from "./random.mjs?v=0.3.0";
import {
  preparePaths,
  generatePaths,
  evaluatePaths,
  marginalRisk,
} from "./path-model.mjs?v=0.3.0";
import {
  withCashAsset,
  mandate,
  execution,
  currentAccount,
  tradePlan,
  withdrawalSchedule,
  MODEL_VERSION,
} from "./policy.mjs?v=0.3.0";
import { buildReturnAnchors } from "./return-model.mjs?v=0.3.0";
import { assetAt, fundamentalForecast } from "./research-model.mjs?v=0.3.0";
import { selectCompositionUniverse } from "./universe.mjs?v=0.3.0";

export const DEFAULT_COMPOSITION_RULES = {
  maxPosition: 0.2,
  maxFund: 0.8,
  maxSector: 0.35,
  maxCorrelation: 0.95,
  cvarBudget: 0.2,
  maxLossProbability: 0.45,
  reserveCap: 1,
  maxPositions: 8,
};
function validateRules(rules) {
  for (const key of [
    "maxPosition",
    "maxFund",
    "maxSector",
    "maxCorrelation",
    "cvarBudget",
    "maxLossProbability",
    "reserveCap",
  ])
    if (!finite(rules[key]) || rules[key] <= 0 || rules[key] > 1)
      throw new Error("Revisa los límites de composición.");
  if (
    !Number.isInteger(rules.maxPositions) ||
    rules.maxPositions < 2 ||
    rules.maxPositions > 16
  )
    throw new Error("Revisa los límites de composición.");
}
export function prepareComposition(
  raw,
  settings = {},
  overrides = {},
  rules = {},
) {
  const snapshot = withCashAsset(raw),
    limits = { ...DEFAULT_COMPOSITION_RULES, ...rules };
  validateRules(limits);
  const asOf = snapshot.price_as_of,
    info = settings.informationAsOf || asOf;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf))
    throw new Error("El corte de precios no es válido.");
  const policy = mandate({
      ...settings.mandate,
      horizon: settings.horizon || settings.mandate?.horizon || 1,
    }),
    costs = execution(settings.execution);
  const current = currentAccount(
      snapshot,
      settings.account,
      settings.baseline,
      settings.capital || 100000,
    ),
    existing = new Set(current.positions.map((r) => r.symbol));
  const eligible = [],
    excluded = [],
    buyAllowed = [];
  for (const original of snapshot.assets) {
    const asset = assetAt(original, asOf, info);
    let reason = null;
    if (
      asset.history.length < 126 ||
      asset.history.at(-1)?.date !== asOf ||
      original.price_date !== asOf
    )
      reason = "Precio o historia común insuficiente al corte";
    if (!reason && asset.type === "stock") {
      const forecast = fundamentalForecast(
        asset,
        overrides[asset.symbol] || {},
        settings.research?.[asset.symbol] || {},
        { asOf: info, priceAsOf: asOf },
      );
      if (!forecast.valid) reason = forecast.error;
      else if (forecast.thesis.status === "contradicted")
        reason = "Tesis contradicha: revisar hipótesis antes de nuevas compras";
    }
    if (reason) excluded.push({ symbol: asset.symbol, reason });
    if (!reason || existing.has(asset.symbol)) {
      if (asset.history.length < 21)
        throw new Error(
          `Falta historia para valorar la posición actual ${asset.symbol}.`,
        );
      eligible.push(asset);
      buyAllowed.push(!reason);
    }
  }
  for (const row of current.positions)
    if (!eligible.some((a) => a.symbol === row.symbol))
      throw new Error(`Falta ${row.symbol} de la cuenta actual.`);
  const sampled = selectCompositionUniverse(
    eligible,
    current.positions.map((row) => row.symbol),
    policy.benchmark,
  );
  const permissionBySymbol = new Map(
    eligible.map((asset, index) => [asset.symbol, buyAllowed[index]]),
  );
  const yieldCurve = Object.fromEntries(
    (snapshot.macro || [])
      .filter((r) => r.date <= info)
      .map((r) => [r.id, r.value]),
  );
  const options = {
    ...settings,
    horizon: policy.horizon,
    driftMode: "fundamental",
    uncertainFundamentals: true,
    asOf,
    informationAsOf: info,
    yieldCurve,
    mandate: policy,
  };
  const paths = preparePaths(sampled.assets, options, overrides);
  const requiredCash = Math.max(
    policy.minimumCash,
    sum(withdrawalSchedule(policy, asOf).map((r) => r.amount)) /
      (current.capital * policy.fxSpot),
  );
  return {
    ...paths,
    rules: limits,
    policy,
    costs,
    current,
    asOf,
    informationAsOf: info,
    excluded,
    buyAllowed: sampled.assets.map((asset) => permissionBySymbol.get(asset.symbol)),
    selection: {
      published: raw.assets.length,
      eligible: eligible.length,
      simulated: sampled.assets.length,
      outsideSample: sampled.omitted,
    },
    requiredCash,
    snapshotGeneratedAt: snapshot.generated_at,
    riskFree: yieldCurve.DGS3MO / 100,
  };
}
export function terminalScenarios(inputs, paths, seed) {
  const sample = generatePaths(inputs, paths, seed, 1);
  return sample.gross.map((col) =>
    Float64Array.from(
      { length: paths },
      (_, p) => col[p * (sample.steps + 1) + sample.steps],
    ),
  );
}
export function evaluateWeights(weights, gross) {
  const returns = Array.from(
      { length: gross[0].length },
      (_, p) => sum(weights.map((w, i) => w * gross[i][p])) - 1,
    ),
    lossProbability = returns.filter((r) => r < 0).length / returns.length;
  const sorted = [...returns].sort((a, b) => a - b);
  return {
    expectedLogGrowth: mean(
      returns.map((r) => Math.log(Math.max(1e-12, 1 + r))),
    ),
    meanReturn: mean(returns),
    medianReturn: quantile(sorted, 0.5),
    p05: quantile(sorted, 0.05),
    p95: quantile(sorted, 0.95),
    cvar95: Math.max(
      0,
      -mean(sorted.slice(0, Math.max(1, Math.ceil(returns.length * 0.05)))),
    ),
    lossProbability,
    lossProbabilitySE: Math.sqrt(
      (lossProbability * (1 - lossProbability)) / returns.length,
    ),
    paths: returns.length,
  };
}
function corr(inputs, i, j) {
  const c = inputs.covariance;
  return c[i][i] > 0 && c[j][j] > 0
    ? c[i][j] / Math.sqrt(c[i][i] * c[j][j])
    : 0;
}
function validWeights(w, x) {
  if (
    Math.abs(sum(w) - 1) > 1e-7 ||
    w.filter((v) => v > 1e-8).length > x.rules.maxPositions
  )
    return false;
  const sectors = new Map();
  for (let i = 0; i < w.length; i++) {
    const a = x.assets[i],
      cap =
        a.type === "cash"
          ? 1
          : a.symbol === "SHY"
            ? x.rules.reserveCap
            : a.type === "stock"
              ? x.rules.maxPosition
              : x.rules.maxFund;
    if (
      !finite(w[i]) ||
      w[i] < -1e-8 ||
      w[i] > cap + 1e-8 ||
      (w[i] > 1e-8 && !x.buyAllowed[i])
    )
      return false;
    if (a.type === "cash" && w[i] < x.requiredCash - 1e-8) return false;
    if (a.type === "stock")
      sectors.set(a.sector, (sectors.get(a.sector) || 0) + w[i]);
    if (w[i] > 0.01)
      for (let j = 0; j < i; j++)
        if (
          w[j] > 0.01 &&
          a.type !== "cash" &&
          x.assets[j].type !== "cash" &&
          corr(x, i, j) > x.rules.maxCorrelation + 1e-8
        )
          return false;
  }
  return [...sectors.values()].every((v) => v <= x.rules.maxSector + 1e-8);
}
function passes(metrics, x) {
  return (
    metrics.cvar95 <= x.rules.cvarBudget &&
    metrics.lossProbability <= x.rules.maxLossProbability &&
    metrics.drawdownProbability <= x.policy.maxDrawdownProbability &&
    metrics.liquidityFailureProbability <= x.policy.maxLiquidityFailure &&
    (!x.policy.capitalFloor ||
      metrics.capitalFloorBreachProbability <= x.policy.maxLiquidityFailure)
  );
}
function candidate(x, random) {
  const cash = x.assets.findIndex((a) => a.symbol === "CASH"),
    w = Array(x.assets.length).fill(0),
    step = 0.05;
  w[cash] = Math.min(1, Math.ceil(x.requiredCash / step - 1e-9) * step);
  const order = x.assets
    .map((a, i) => ({ i, key: random() }))
    .filter((r) => r.i !== cash && x.buyAllowed[r.i])
    .sort((a, b) => a.key - b.key)
    .slice(0, x.rules.maxPositions - 1);
  let remaining = Math.round((1 - w[cash]) / step);
  for (; remaining > 0; remaining--) {
    const available = order.filter(({ i }) => {
      w[i] += step;
      w[cash] += Math.max(0, (remaining - 1) * step);
      const valid = validWeights(w, x);
      w[cash] -= Math.max(0, (remaining - 1) * step);
      w[i] -= step;
      return valid;
    });
    if (!available.length) {
      w[cash] += remaining * step;
      break;
    }
    const { i } = available[Math.floor(random() * available.length)];
    w[i] += step;
  }
  return validWeights(w, x) ? w : null;
}
// Test a small position in each available asset against the reserve baseline.
// This guarantees that the optimizer actually evaluates every shortlisted idea.
function reserveTilts(x) {
  const cash = x.assets.findIndex((a) => a.symbol === "CASH"),
    bond = x.assets.findIndex((a) => a.symbol === "SHY");
  if (cash < 0) return [];
  const minimum = Math.min(1, Math.ceil(x.requiredCash * 20 - 1e-9) / 20);
  const useBond = bond >= 0 && x.buyAllowed[bond],
    baseBond = useBond ? Math.min(x.rules.reserveCap, 1 - minimum) : 0;
  const result = [];
  for (let i = 0; i < x.assets.length; i++) {
    if (i === cash || (useBond && i === bond) || !x.buyAllowed[i]) continue;
    const w = Array(x.assets.length).fill(0);
    w[cash] = 1 - baseBond;
    if (useBond) w[bond] = baseBond;
    const invest = Math.min(0.2, Math.floor((1 - minimum) * 20 + 1e-9) / 20);
    if (invest < 0.05) continue;
    const fromBond = Math.min(invest, baseBond);
    if (useBond) w[bond] -= fromBond;
    w[cash] -= invest - fromBond;
    w[i] += invest;
    if (validWeights(w, x)) result.push(w);
  }
  return result;
}

// Deterministic, risk-constrained 5pp exchanges near the strongest candidates.
// No historical return enters the selection of recipient assets.
function neighborCandidate(x, parent, random) {
  const donors = parent.map((weight, i) => ({ weight, i }))
    .filter(({ weight }) => weight >= 0.05 - 1e-8);
  const recipients = x.assets.map((asset, i) => ({
    i,
    priority: x.anchors[i].annual -
      0.35 * Math.sqrt(Math.max(0, x.covariance[i][i])),
  })).filter(({ i }) => x.buyAllowed[i])
    .sort((a, b) => b.priority - a.priority || a.i - b.i);
  if (!donors.length || !recipients.length) return null;
  for (let attempt = 0; attempt < 35; attempt++) {
    const donor = donors[Math.floor(random() * donors.length)].i;
    const pool = attempt % 3 === 0 ? recipients.slice(0, 10) : recipients;
    const receiver = pool[Math.floor(random() * pool.length)].i;
    if (donor === receiver) continue;
    const w = parent.slice();
    w[donor] = Math.max(0, Math.round((w[donor] - 0.05) * 1000) / 1000);
    w[receiver] = Math.round((w[receiver] + 0.05) * 1000) / 1000;
    if (validWeights(w, x)) return w;
  }
  return null;
}

function assess(w, x, sample, hold = false, passive = false) {
  const positions = x.assets.flatMap((a, i) =>
      w[i] > 1e-9 ? [{ symbol: a.symbol, weight: w[i] }] : [],
    ),
    plan = tradePlan(
      x.assets,
      positions,
      x.current.positions,
      x.current.capital,
      x.costs,
    );
  const metrics = evaluatePaths(w, sample, {
    capital: x.current.capital,
    cost: plan.total,
  });
  const initial = x.current.source === "Capital inicial en efectivo";
  const existingMinimum =
    !hold || validWeights(w, { ...x, buyAllowed: x.assets.map(() => true) });
  const feasible =
    passes(metrics, x) &&
    plan.complete &&
    (!hold || existingMinimum) &&
    (hold || plan.smallTrades === 0) &&
    (initial || hold || plan.turnover <= x.costs.maxTurnover + 1e-8) &&
    (hold || validWeights(w, x));
  return {
    weights: w,
    positions,
    plan,
    metrics,
    feasible,
    kind: hold ? "hold" : passive ? "passive" : "active",
  };
}
function passiveCandidates(x) {
  const market = x.assets.findIndex((a) => a.symbol === x.policy.benchmark),
    cash = x.assets.findIndex((a) => a.symbol === "CASH"),
    bond = x.assets.findIndex((a) => a.symbol === "SHY"),
    result = [];
  if (market < 0) return result;
  for (let equity = 0; equity <= 1.0001; equity += 0.05)
    for (const bondShare of [0, 0.5, 1]) {
      const w = Array(x.assets.length).fill(0);
      w[market] = Math.round(equity * 100) / 100;
      const rest = 1 - w[market];
      w[cash] = Math.max(x.requiredCash, rest * (1 - bondShare));
      if (w[cash] > rest + 1e-8) continue;
      if (bond >= 0) w[bond] = rest - w[cash];
      else w[cash] = rest;
      if (validWeights(w, x)) result.push(w);
    }
  return result;
}
export function composePortfolio(
  snapshot,
  settings = {},
  overrides = {},
  rules = {},
  search = {},
) {
  const x = prepareComposition(snapshot, settings, overrides, rules),
    paths = search.paths ?? 600,
    finalPaths = search.finalPaths ?? 3000,
    target = search.candidates ?? 300,
    seed = x.options.seed >>> 0;
  if (!Number.isInteger(target) || target < 1 || target > 2000)
    throw new Error("Búsqueda fuera de rango.");
  const sample = generatePaths(x, paths, seed, 12),
    random = seededRandom(seed ^ 0x51a7c0de),
    seen = new Set(),
    ranked = [];
  const currentMap = new Map(
      x.current.positions.map((r) => [r.symbol, r.weight]),
    ),
    current = x.assets.map((a) => currentMap.get(a.symbol) || 0);
  const holding = assess(current, x, sample, true);
  let evaluated = 0,
    feasible = 0,
    bestPassive = null;
  const add = (w, passive = false) => {
    const key = w.map((v) => v.toFixed(5)).join();
    if (seen.has(key)) return;
    seen.add(key);
    const result = assess(w, x, sample, false, passive);
    evaluated++;
    if (!result.feasible) return;
    feasible++;
    ranked.push(result);
    if (
      passive &&
      (!bestPassive || result.metrics.score > bestPassive.metrics.score)
    )
      bestPassive = result;
  };
  for (const w of passiveCandidates(x)) add(w, true);
  const allCash = x.assets.map((a) => (a.symbol === "CASH" ? 1 : 0));
  if (validWeights(allCash, x)) add(allCash);
  const initialTilts = reserveTilts(x);
  for (const w of initialTilts) add(w);
  const randomBudget = Math.max(evaluated, Math.floor(target * 0.65));
  for (let attempt = 0; attempt < target * 25 && evaluated < randomBudget; attempt++) {
    const w = candidate(x, random);
    if (w) add(w);
  }
  ranked.sort((a, b) => b.metrics.score - a.metrics.score);
  for (let attempt = 0; attempt < target * 30 && evaluated < target; attempt++) {
    if (!ranked.length) {
      const w = candidate(x, random);
      if (w) add(w);
      continue;
    }
    const parent = ranked[Math.floor(random() * Math.min(8, ranked.length))];
    const neighbor = neighborCandidate(x, parent.weights, random);
    if (neighbor) add(neighbor);
    if (attempt % 20 === 19) ranked.sort((a, b) => b.metrics.score - a.metrics.score);
  }
  ranked.sort((a, b) => b.metrics.score - a.metrics.score);
  const verificationSeed = (seed + 0x6a09e667) >>> 0,
    verification = generatePaths(x, finalPaths, verificationSeed, 52);
  const holdVerified = assess(current, x, verification, true),
    verified = [];
  for (const row of ranked.slice(0, 10)) {
    const v = assess(
      row.weights,
      x,
      verification,
      false,
      row.kind === "passive",
    );
    if (v.feasible) verified.push(v);
  }
  const passiveVerified = bestPassive
    ? assess(bestPassive.weights, x, verification, false, true)
    : null;
  let best = verified.sort((a, b) => b.metrics.score - a.metrics.score)[0];
  // Counterfactual allocations use the same independent verification paths.
  // They are comparators, not transactions or recommendations.
  const cash = x.assets.findIndex((a) => a.symbol === "CASH"),
    shortBond = x.assets.findIndex((a) => a.symbol === "SHY"),
    equity = x.assets.findIndex((a) => a.symbol === x.policy.benchmark);
  const reserve = Array(x.assets.length).fill(0);
  const equityTilt = Array(x.assets.length).fill(0);
  if (cash >= 0) {
    const minCash = Math.min(1, Math.ceil(x.requiredCash * 20 - 1e-9) / 20);
    reserve[cash] = 1;
    if (shortBond >= 0) {
      reserve[shortBond] = Math.min(x.rules.reserveCap, 1 - minCash);
      reserve[cash] -= reserve[shortBond];
    }
    equityTilt.splice(0, equityTilt.length, ...reserve);
    if (equity >= 0) {
      const targetEquity = Math.min(0.2, 1 - minCash);
      const fromBond = shortBond >= 0
        ? Math.min(targetEquity, equityTilt[shortBond]) : 0;
      if (shortBond >= 0) equityTilt[shortBond] -= fromBond;
      const fromCash = targetEquity - fromBond;
      equityTilt[cash] -= fromCash;
      equityTilt[equity] += targetEquity;
    }
  }
  const references = Object.fromEntries([
    ["cash", allCash],
    ["reserve", shortBond >= 0 ? reserve : null],
    ["equity20", equity >= 0 && x.buyAllowed[equity] ? equityTilt : null],
  ].map(([name, w]) => {
    if (!w || !validWeights(w, x)) return [name, null];
    const check = assess(w, x, verification);
    return [name, {
      positions: check.positions,
      feasible: check.feasible,
      meanReturn: check.metrics.meanReturn,
      cvar95: check.metrics.cvar95,
      lossProbability: check.metrics.lossProbability,
      certaintyEquivalent: check.metrics.certaintyEquivalent,
    }];
  }));
  const riskDiagnostics = (row) => {
    if (!row) return null;
    const limits = [
      ["CVaR 95", row.metrics.cvar95, x.rules.cvarBudget],
      ["Prob. pérdida", row.metrics.lossProbability, x.rules.maxLossProbability],
      ["Prob. drawdown", row.metrics.drawdownProbability, x.policy.maxDrawdownProbability],
      ["Riesgo liquidez", row.metrics.liquidityFailureProbability, x.policy.maxLiquidityFailure],
    ];
    const nearby = limits.filter(([, used, limit]) => limit > 0 && used >= limit * 0.9)
      .map(([name, used, limit]) => ({
        name, observed: used, limit,
      }));
    return {
      largestPosition: [...row.positions].sort((a, b) => b.weight - a.weight)[0] || null,
      nearLimits: nearby,
      uncalibratedEtfs: x.anchors.filter((a) =>
        a.kind === "etf" && !a.bond && a.source === "Retorno y rango asumidos del ETF"
      ).map((a) => a.symbol),
    };
  };
  const diagnostics = {
    selected: riskDiagnostics(best),
    references,
    note: "Comparadores simulados con los mismos escenarios; ninguna restricción cercana prueba causalidad. Los retornos asumidos de ETF no son pronósticos calibrados.",
  };
  const {
    baseline: _baseline,
    account: _account,
    ...recordedOptions
  } = x.options;
  const metadata = {
    version: 2,
    model_version: MODEL_VERSION,
    method: "ex-ante-fundamental-monte-carlo",
    as_of: x.asOf,
    information_as_of: x.informationAsOf,
    generated_at: new Date().toISOString(),
    snapshot_generated_at: x.snapshotGeneratedAt,
    calibration_end: x.calibrationEnd,
    observations: x.observations,
    settings: recordedOptions,
    current_account: {
      positions: x.current.positions,
      capital: x.current.capital,
    },
    rules: x.rules,
    mandate: x.policy,
    execution: x.costs,
    account_source: x.current.source,
    capital: x.current.capital,
    excluded: x.excluded,
    selection: x.selection,
    diagnostics,
    search: {
      evaluated, feasible, paths, allocationStep: 0.05,
      reserveTiltsEvaluated: initialTilts.length,
      method: "reserve-tilts-random-local-exchanges",
      exhaustive: false,
    },
    verification: {
      seed: verificationSeed,
      paths: finalPaths,
      stepsPerYear: 52,
    },
    alternatives: {
      hold: { metrics: holdVerified.metrics, feasible: holdVerified.feasible },
      passive: passiveVerified
        ? {
            metrics: passiveVerified.metrics,
            feasible: passiveVerified.feasible,
            positions: passiveVerified.positions,
            cost: passiveVerified.plan.total,
          }
        : null,
    },
  };
  if (!best)
    return {
      ...metadata,
      status: "no_feasible",
      reason:
        "Ninguna propuesta pasó los límites semanales, de liquidez y de costos. La cartera actual se conserva; revisa el mandato y los supuestos.",
    };
  const benefit =
      best.metrics.certaintyEquivalent -
      holdVerified.metrics.certaintyEquivalent,
    hurdle = Math.max(
      x.costs.minBenefit,
      best.plan.total * x.costs.benefitCostRatio,
    );
  if (
    holdVerified.feasible &&
    (best.metrics.score <= holdVerified.metrics.score || benefit < hurdle)
  )
    return {
      ...metadata,
      status: "hold",
      reason: `Mantener: mejora equivalente estimada USD ${benefit.toFixed(0)}; umbral USD ${hurdle.toFixed(0)}.`,
      metrics: holdVerified.metrics,
      positions: holdVerified.positions,
      trade_plan: holdVerified.plan,
      benefit,
      hurdle,
    };
  const risks = marginalRisk(best.weights, x.covariance);
  const signals = best.positions.map((p) => {
    const i = x.assets.findIndex((a) => a.symbol === p.symbol),
      a = x.assets[i],
      anchor = x.anchors[i];
    return {
      ...p,
      sector: a.sector,
      price: a.price,
      price_date: a.price_date,
      eps: a.financials?.eps?.value ?? null,
      filed: a.financials?.eps?.filed ?? null,
      anchor: anchor.annual,
      adverseAnchor: anchor.low,
      favorableAnchor: anchor.high,
      confidence: anchor.confidence,
      source: anchor.source,
      risk: risks[i],
      assumptions: { ...a.assumptions, ...overrides[a.symbol] },
    };
  });
  const stress = [
    {
      label: "Crecimiento −3 pp / margen neto −2 pp",
      growth: -0.03,
      margin: -0.02,
    },
    { label: "Múltiplos −15%", multiple: 0.85 },
    { label: "Correlaciones hacia 1 · mezcla 25%", correlation: 0.25 },
    { label: "Confianza subjetiva −20 pp", confidence: -0.2 },
  ].map((test) => {
    const changedOverrides = structuredClone(overrides),
      changedResearch = structuredClone(x.options.research || {});
    for (const a of x.assets)
      if (a.type === "stock") {
        const own = { ...a.assumptions, ...changedOverrides[a.symbol] };
        if (test.growth) own.growth = Math.max(-0.8, own.growth + test.growth);
        if (test.multiple) own.multiple *= test.multiple;
        changedOverrides[a.symbol] = own;
        const research = { ...changedResearch[a.symbol] };
        if (test.margin && finite(research.targetMargin))
          research.targetMargin = Math.max(
            0.001,
            research.targetMargin + test.margin,
          );
        if (test.confidence)
          research.confidence = Math.max(
            0,
            (research.confidence ?? 0.6) + test.confidence,
          );
        changedResearch[a.symbol] = research;
      }
    const options = { ...x.options, research: changedResearch };
    const covariance = test.correlation
      ? x.covariance.map((row, i) =>
          row.map(
            (v, j) =>
              (1 - test.correlation) * v +
              test.correlation *
                Math.sqrt(x.covariance[i][i] * x.covariance[j][j]),
          ),
        )
      : x.covariance;
    const altered = {
      ...x,
      options,
      covariance,
      anchors: buildReturnAnchors(x.assets, options, changedOverrides),
    };
    const draws = generatePaths(altered, Math.min(paths, 600), seed, 12);
    const choices = [...ranked.slice(0, 20), { weights: current }]
      .map((r) => assess(r.weights, altered, draws, r.weights === current))
      .filter((r) => r.feasible)
      .sort((a, b) => b.metrics.score - a.metrics.score);
    const selected = choices[0],
      delta = selected
        ? selected.weights.map((w, i) => w - best.weights[i])
        : [];
    const largest = delta.length
      ? delta.reduce(
          (bestIndex, d, i) =>
            Math.abs(d) > Math.abs(delta[bestIndex]) ? i : bestIndex,
          0,
        )
      : -1;
    return {
      label: test.label,
      feasible: !!selected,
      turnover: selected ? sum(delta.map(Math.abs)) / 2 : null,
      largestChange:
        largest >= 0 && Math.abs(delta[largest]) > 1e-8
          ? `${x.assets[largest].symbol} ${(delta[largest] * 100).toFixed(1)} pp`
          : "Sin cambios",
      positions: selected?.positions || [],
      note: "Reelección entre las 20 candidatas base y mantener; sensibilidad local, sin promesa de robustez global.",
    };
  });
  return {
    ...metadata,
    status: "proposed",
    positions: best.positions,
    signals,
    metrics: best.metrics,
    trade_plan: best.plan,
    benefit,
    hurdle,
    selected_kind: best.kind,
    sensitivity: stress,
    model_inputs: {
      assets: x.assets.map((a) => ({
        symbol: a.symbol,
        type: a.type,
        sector: a.sector,
        price: a.price,
        price_date: a.price_date,
        financials: a.financials,
        analyst_estimates: a.analyst_estimates || null,
        bond_profile: a.bond_profile || null,
        assumptions: { ...a.assumptions, ...overrides[a.symbol] },
      })),
      covariance: x.covariance,
      anchors: x.anchors,
      regimes: x.regimes,
    },
    objective: x.policy.objective,
    notes: [
      "Probabilidades y confianza son supuestos sin calibración predictiva demostrada.",
      "Sectores: límites sobre acciones directas; sin composición interna de ETFs.",
      "Retiros prefundados con efectivo; no se suponen ventas gratuitas durante las trayectorias.",
      "Duración de bonos es una aproximación local; sin convexidad ni reinversión detallada.",
    ],
  };
}
