import {
  finite,
  sum,
  mean,
  quantile,
  normalizeWeights,
} from "./analytics.mjs?v=0.34.1";
import { seededRandom } from "./random.mjs?v=0.34.1";
import { portfolioAttribution } from "./attribution.mjs?v=0.34.1";
import { selectReliableCandidate } from "./reliable-selection.mjs?v=0.34.1";
import { riskSamplingEvidence } from "./simulation-evidence.mjs?v=0.34.1";
import { reviewRobustDecision, DECISION_MODEL_LABELS, DECISION_EXPERIMENT_SEEDS } from "./robust-decision.mjs?v=0.34.1";
import {
  preparePaths,
  generatePaths,
  evaluatePaths,
  marginalRisk,
  centeredRegimeConditions,
} from "./path-model.mjs?v=0.34.1";
import {
  withCashAsset,
  mandate,
  execution,
  currentAccount,
  tradePlan,
  withdrawalSchedule,
  effectiveRegimes,
  DEFAULT_REGIMES,
  MODEL_VERSION,
} from "./policy.mjs?v=0.34.1";
import { buildReturnAnchors, constituentForecasts, holdingsAnchor, valuationAnchor } from "./return-model.mjs?v=0.34.1";
import { assetAt, fundamentalForecast, bondAssumptions } from "./research-model.mjs?v=0.34.1";
import { selectCompositionUniverse } from "./universe.mjs?v=0.34.1";
import { factorizeStressedCovariance } from "./factor-covariance.mjs?v=0.34.1";
import { economicClass, outsideUS, exposureReport, rawCorrelation, qualifiedOpportunity, holdingsOverlap, knownFundOverlap } from "./economic-exposure.mjs?v=0.34.1";

export const DEFAULT_COMPOSITION_RULES = {
  maxPosition: 0.2,
  maxFund: 0.8,
  maxGlobal: 0.35,
  maxOpportunity: 0.5,
  maxTreasury: 0.6,
  maxEquity: 0.5,
  // High-yield and EM debt combined: a prudential policy limit, not an
  // estimate. Their volatility is measured over two years without an EM or
  // default crisis.
  maxRiskyCredit: 0.2,
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
    "maxGlobal",
    "maxOpportunity",
    "maxTreasury",
    "maxEquity",
    "maxRiskyCredit",
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
export function compositionUniverseLimit(settings={}){
  const value=settings.compositionUniverseLimit??settings.researchUniverseLimit??40;
  if(!Number.isInteger(value)||value<20||value>80)
    throw new Error('La muestra de composición debe estar entre 20 y 80 activos');
  return value;
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
    buyAllowed = [],
    forwardPriority = {};
  let benchmarkOnlyProxy = false;
  const historicalVolatility = (asset) => {
    const rows = (asset.history || []).slice(-127);
    let squared = 0, observations = 0;
    for (let k = 1; k < rows.length; k++) {
      const previous = rows[k-1].adj_close, current = rows[k].adj_close;
      if (!(previous > 0 && current > 0)) continue;
      squared += Math.log(current / previous) ** 2;
      observations++;
    }
    return observations >= 60 ? Math.sqrt(252 * squared / observations) : 1;
  };
  const yieldCurve = Object.fromEntries(
    (snapshot.macro || [])
      .filter((r) => r.date <= info)
      .map((r) => [r.id, r.value]),
  );
  // Same context as the simulated anchors, so preselection ranks stocks on
  // their cross-sectionally refined anchors.
  const anchorContext = { asOf, informationAsOf: info, research: settings.research || {},
    yieldCurve, mandate: policy, driftMode: "fundamental",
    informationCoefficient: settings.informationCoefficient };
  const constituents = constituentForecasts(snapshot.assets, anchorContext, overrides);
  for (const original of snapshot.assets) {
    const asset = assetAt(original, asOf, info);
    let reason = null;
    if (
      asset.history.length < 126 ||
      asset.history.at(-1)?.date !== asOf ||
      original.price_date !== asOf
    )
      reason = "Precio o historia común insuficiente al corte";
    if (!reason && policy.region === "us" && outsideUS(asset))
      reason = "Fuera del mandato: inversión limitada a EE. UU.";
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
      else forwardPriority[asset.symbol] = forecast.central +
        (constituents.refinement?.get(asset.symbol)?.shift ?? 0) -
        0.15 * Math.max(0, forecast.high - forecast.low) -
        0.04 * historicalVolatility(asset);
    }
    if (!reason && asset.type === "etf") {
      if(economicClass(asset)==="unclassified-etf")
        reason="ETF sin clasificación económica verificada: revisar su mandato antes de nuevas compras.";
      const own = settings.assetAssumptions?.[asset.symbol];
      const hasExplicitReturn = finite(own?.expectedReturn) &&
        finite(own?.uncertainty) && own.uncertainty > 0 && own.uncertainty <= 1;
      const isBondPriced = !!bondAssumptions(asset, {
        ...settings, asOf, informationAsOf: info,
        yieldCurve: Object.fromEntries((snapshot.macro || [])
          .filter((row) => row.date <= info)
          .map((row) => [row.id, row.value])),
      });
      const composite = !reason && !isBondPriced && !hasExplicitReturn
        ? holdingsAnchor(asset, constituents, anchorContext) ??
          valuationAnchor(asset, anchorContext) : null;
      if (!reason && !isBondPriced && !hasExplicitReturn && !composite)
        reason = "ETF sin retorno esperado fundamentado: holdings insuficientes o antiguas para un ancla compuesta, sin valoración fechada del emisor y sin expectativa explícita. Introduce una expectativa y una incertidumbre explícitas.";
      else if (!reason && composite)
        forwardPriority[asset.symbol] = composite.annual -
          0.15 * Math.max(0, composite.high - composite.low) -
          0.04 * historicalVolatility(asset);
      else if(!reason && !composite) {
        const bond = bondAssumptions(asset, {
          ...settings, asOf, informationAsOf: info,
          yieldCurve: Object.fromEntries((snapshot.macro || [])
            .filter((row) => row.date <= info)
            .map((row) => [row.id, row.value])),
        });
        const base = bond?.carry ?? own.expectedReturn;
        const dispersion = bond ? 0 : own.uncertainty;
        forwardPriority[asset.symbol] = base - 0.15 * dispersion -
          0.04 * historicalVolatility(asset);
      }
    }
    const benchmarkProxy = !!reason &&
      asset.symbol === policy.benchmark && asset.type === "etf" &&
      reason.startsWith("ETF sin retorno esperado fundamentado");
    if (benchmarkProxy) benchmarkOnlyProxy = true;
    if (reason && !benchmarkProxy)
      excluded.push({ symbol: asset.symbol, reason });
    if (!reason || existing.has(asset.symbol) || benchmarkProxy) {
      if (asset.history.length < 21)
        throw new Error(
          `Falta historia para valorar la posición actual ${asset.symbol}.`,
        );
      eligible.push(asset);
      buyAllowed.push(!reason); // SPY proxy is available for comparison, NOT trade.
    }
  }
  for (const row of current.positions)
    if (!eligible.some((a) => a.symbol === row.symbol))
      throw new Error(`Falta ${row.symbol} de la cuenta actual.`);
  const forcedResearch = settings.researchShadowMode === true &&
    Array.isArray(settings.researchForceInclude)
    ? [...new Set(settings.researchForceInclude)]
      .filter(symbol => typeof symbol === "string" &&
        /^[A-Z0-9.\-]{1,15}$/.test(symbol) &&
        eligible.some(a => a.symbol === symbol)).slice(0, 8)
    : [];
  const sampled = selectCompositionUniverse(
    eligible,
    [...current.positions.map((row) => row.symbol), ...forcedResearch],
    policy.benchmark,
    compositionUniverseLimit(settings),
    forwardPriority,
  );
  const permissionBySymbol = new Map(
    eligible.map((asset, index) => [asset.symbol, buyAllowed[index]]),
  );
  const proxyRate = finite(yieldCurve.DGS3MO) ? yieldCurve.DGS3MO / 100 : 0;
  const proxyAssetAssumptions = benchmarkOnlyProxy
    ? {
        ...(settings.assetAssumptions || {}),
        [policy.benchmark]: {
          expectedReturn: proxyRate + 0.035,
          uncertainty: 0.15,
          benchmarkOnlyProxy: true,
        },
      }
    : settings.assetAssumptions;
  // Scenario probabilities: recession from the yield curve known at the
  // information cut, unless the user fixed them by hand.
  const macro = effectiveRegimes(settings.macroRegimes || DEFAULT_REGIMES,
    settings.regimeProbabilities, snapshot.macro, info);
  const options = {
    ...settings,
    assetAssumptions: proxyAssetAssumptions,
    horizon: policy.horizon,
    driftMode: "fundamental",
    uncertainFundamentals: true,
    asOf,
    informationAsOf: info,
    yieldCurve,
    mandate: policy,
    macroRegimes: macro.rows,
  };
  const paths = preparePaths(sampled.assets, options, overrides, snapshot.assets);
  const requiredCash = Math.max(
    policy.minimumCash,
    sum(withdrawalSchedule(policy, asOf).map((r) => r.amount)) /
      (current.capital * policy.fxSpot),
  );
  return {
    ...paths,
    valuationOverrides: overrides,
    rules: limits,
    securitySectors:Object.fromEntries(snapshot.assets.filter(a=>a.type==="stock")
      .map(a=>[a.symbol,a.sector])),
    // Only signed/reviewed evidence published with the market snapshot may
    // lift a global concentration cap; session values are not certification.
    opportunityEvidence: snapshot.validated_opportunities || {},
    policy,
    costs,
    current,
    asOf,
    informationAsOf: info,
    excluded,
    buyAllowed: sampled.assets.map((asset) => permissionBySymbol.get(asset.symbol)),
    selection: {
      published: raw.assets.filter(a=>a.type!=="cash"&&a.symbol!=="CASH").length,
      eligible: eligible.length,
      simulated: sampled.assets.length,
      forcedResearchCandidates: forcedResearch,
      benchmarkOnlyProxy: benchmarkOnlyProxy ? policy.benchmark : null,
      benchmarkProxyAssumption: benchmarkOnlyProxy
        ? "Solo comparación: tasa corta al corte + prima hipotética de 3,5 pp; banda ±15 pp, NO estimación validada ni compra autorizada"
        : null,
      outsideSample: sampled.omitted,
      preselectionMethod: sampled.method,
      outsideWithHigherPriority: sampled.omitted
        .filter(symbol => Number.isFinite(forwardPriority[symbol]))
        .sort((a,b) => forwardPriority[b] - forwardPriority[a])
        .slice(0,8).map(symbol => ({
          symbol, score: forwardPriority[symbol],
          reason: "Fuera de la muestra; todavía no optimizado",
        })),
    },
    requiredCash,
    regimeProbabilities: { source: macro.source, curve: macro.curve,
      probabilities: Object.fromEntries(macro.rows.map((r) => [r.id, r.probability])) },
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
  // Compare idiosyncratic dependence after removing observed SPY bull/bear
  // and sector proxy effects; the Monte Carlo still uses TOTAL covariance.
  const residual = inputs.residualCorrelation?.[i]?.[j];
  if (Number.isFinite(residual)) return residual;
  const c = inputs.covariance;
  return c[i][i] > 0 && c[j][j] > 0
    ? c[i][j] / Math.sqrt(c[i][i] * c[j][j])
    : 0;
}
function positionLimit(a,x){
 const legacy=a.type==="cash"?1:a.type==="stock"?x.rules.maxPosition:a.symbol==="SHY"?x.rules.reserveCap:x.rules.maxFund;
 const exception=qualifiedOpportunity(a,x.opportunityEvidence?.[a.symbol],x.asOf);
 const global=a.type==="cash"?1:(exception?x.rules.maxOpportunity:x.rules.maxGlobal);
 return Math.min(legacy,global);
}
export function validWeights(w,x){
 if(Math.abs(sum(w)-1)>1e-7 || w.filter(v=>v>1e-8).length>x.rules.maxPositions)return false;
 for(let i=0;i<w.length;i++){
  const a=x.assets[i];
  if(!finite(w[i])||w[i]<-1e-8||w[i]>positionLimit(a,x)+1e-8||
     (w[i]>1e-8&&!x.buyAllowed[i]))return false;
  if(a.type==="cash"&&w[i]<x.requiredCash-1e-8)return false;
  if(w[i]>.01)for(let j=0;j<i;j++){
   if(w[j]<=.01||a.type==="cash"||x.assets[j].type==="cash")continue;
   const etfPair=a.type==="etf"||x.assets[j].type==="etf";
   const overlap=etfPair?rawCorrelation(x.covariance,i,j):corr(x,i,j);
   if(overlap>x.rules.maxCorrelation+1e-8)return false;
  }
 }
 const exposure=exposureReport(x.assets,w,x.asOf,x.informationAsOf,x.securitySectors);
 if(exposure.sleeves.unknownEtf>1e-8)return false;
 if(exposure.sleeves.treasury>x.rules.maxTreasury+1e-8)return false;
 if(exposure.sleeves.usEquity+exposure.sleeves.globalEquity>x.rules.maxEquity+1e-8)return false;
 if(exposure.sleeves.riskyCredit>(x.rules.maxRiskyCredit??DEFAULT_COMPOSITION_RULES.maxRiskyCredit)+1e-8)return false;
 if(exposure.unclassifiedSectorWeight>x.rules.maxSector+1e-8 ||
    Object.values(exposure.sectorUpperBounds).some(v=>v>x.rules.maxSector+1e-8))return false;
 if(exposure.unclassifiedIssuerWeight>Math.min(x.rules.maxPosition,x.rules.maxGlobal)+1e-8)return false;
 for(const [issuer,weight] of Object.entries(exposure.issuerUpperBounds)){
   const stock=x.assets.find(a=>a.symbol===issuer && a.type==="stock");
   const exception=stock && qualifiedOpportunity(
     stock,x.opportunityEvidence?.[issuer],x.asOf);
   if(weight>Math.min(x.rules.maxPosition,exception?x.rules.maxOpportunity:x.rules.maxGlobal)+1e-8)
     return false;
 }
 return true;
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
    baseBond = useBond ? Math.min(x.rules.reserveCap,x.rules.maxGlobal,x.rules.maxTreasury,1-minimum) : 0;
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

// Complete the immediate cash neighborhood on the same finalist sample.
// This is local search, not a new independent validation or a global optimum.
export function reviewCashAllocation(initial, x, sample, maxRounds = 4) {
  if (!initial) return {best: initial, finalists: [], audit: null};
  const cash = x.assets.findIndex(a => a.symbol === 'CASH');
  if (cash < 0) return {best: initial, finalists: [], audit: null};
  let best = initial, finalComparisons = [], exhausted = false;
  const finalists = [], improvements = [], assessed = new Map(), allComparisons = [];
  let evaluated = 0, structurallyBlocked = 0;
  for (let round = 0; round < maxRounds; round++) {
    const available = best.weights[cash] - x.requiredCash;
    if (available < .05 - 1e-8) break;
    const transfers = [.05, .10].filter(amount => amount <= available + 1e-8);
    const comparisons = [];
    let winner = best;
    for (const amount of transfers) for (let i = 0; i < x.assets.length; i++) {
      if (i === cash || !x.buyAllowed[i]) continue;
      const w = best.weights.slice();
      w[cash] = Math.round((w[cash] - amount) * 1e12) / 1e12;
      w[i] = Math.round((w[i] + amount) * 1e12) / 1e12;
      if (!validWeights(w, x)) {structurallyBlocked++; continue;}
      const key = w.map(v => v.toFixed(10)).join(',');
      const cached = assessed.has(key);
      const result = cached ? assessed.get(key) : assess(w, x, sample);
      if (!cached) {assessed.set(key, result); evaluated++;}
      const failures = [];
      for (const [name, used, limit] of [
        ['CVaR', result.metrics.cvar95, x.rules.cvarBudget],
        ['Probabilidad de pérdida', result.metrics.lossProbability, x.rules.maxLossProbability],
        ['Probabilidad de drawdown', result.metrics.drawdownProbability, x.policy.maxDrawdownProbability],
        ['Liquidez', result.metrics.liquidityFailureProbability, x.policy.maxLiquidityFailure],
      ]) if (used > limit) failures.push(name);
      if (!result.feasible && !failures.length) failures.push('Mandato, costes u operativa');
      const comparison={symbol:x.assets[i].symbol, transfer:amount,
        fromCash:best.weights[cash], toCash:w[cash], feasible:result.feasible,
        failures, score:result.metrics.score,
        certaintyEquivalent:result.metrics.certaintyEquivalent,
        medianReturn:result.metrics.medianReturn, cvar95:result.metrics.cvar95};
      comparisons.push(comparison);
      if (!cached) allComparisons.push(comparison);
      if (result.feasible) {
        if (!cached) finalists.push(result);
        if (result.metrics.score > winner.metrics.score + 1e-12) winner = result;
      }
    }
    finalComparisons = comparisons;
    if (winner === best) break;
    improvements.push({fromCash:best.weights[cash], toCash:winner.weights[cash],
      transfers:x.assets.flatMap((a,i) => i !== cash && winner.weights[i] > best.weights[i] + 1e-8
        ? [{symbol:a.symbol, weight:winner.weights[i]-best.weights[i]}] : []),
      certaintyEquivalentGain:winner.metrics.certaintyEquivalent-best.metrics.certaintyEquivalent});
    best = winner;
    exhausted = round === maxRounds - 1;
  }
  const excess = Math.max(0, best.weights[cash] - x.requiredCash);
  const status = excess < 1e-8 ? 'required_reserve' : excess < .05 - 1e-8
    ? 'allocation_step' : exhausted ? 'search_budget' : !finalComparisons.length
      ? 'structural_limits' : !finalComparisons.some(r => r.feasible)
        ? 'risk_or_execution_limits' : 'no_local_improvement';
  return {best, finalists, audit:{status,
    initialCashWeight:initial.weights[cash], cashWeight:best.weights[cash],
    minimumCash:x.policy.minimumCash, requiredCash:x.requiredCash, excessCash:excess,
    cashYield:x.policy.cashYield, evaluated, structurallyBlocked,
    step:.05, improvements, comparisons:allComparisons.sort((a,b)=>b.score-a.score).slice(0,32),
    scope:'Local reallocations of 5 and 10 percentage points on the finalist simulation; not a global or prospectively validated optimum'}};
}
// One-sided 95% threshold for the paired per-path utility gain.
export const SUBSTITUTION_Z = 1.645;
/**
 * Exchanges of 5 points between any two positions (cash above its reserve
 * included) and full substitutions of a holding by any simulated instrument.
 * Screened on the search sample; the best few are re-run on the verification
 * paths and accepted only if the paired per-path utility gain is significant
 * (one-sided 95%). Otherwise the incumbent stays, so statistically equivalent
 * candidates never add trades. Same model and data: this measures Monte Carlo
 * error, not parameter error.
 */
function pathUtilities(row, x, verification) {
  return evaluatePaths(row.weights, verification, {
    capital: x.current.capital, cost: row.plan.total, pathUtilities: true }).pathUtilities;
}
/** Paired mean and z statistic of candidate minus incumbent per-path utility. */
export function pairedUtilityTest(candidate, incumbent) {
  const n = candidate.length;
  let total = 0, squares = 0;
  for (let p = 0; p < n; p++) {
    const d = candidate[p] - incumbent[p];
    total += d; squares += d * d;
  }
  const mean = total / n, sd = Math.sqrt(Math.max(0, squares / n - mean * mean) * n / (n - 1));
  return { mean, z: sd > 0 ? mean / (sd / Math.sqrt(n)) : mean > 0 ? Infinity : mean < 0 ? -Infinity : 0 };
}
/** Weight two portfolios hold in common: sum of the smaller weights. */
export function weightOverlap(a, b) {
  return a.reduce((total, w, i) => total + Math.min(w, b[i]), 0);
}
export function reviewSubstitutions(initial, x, sample, verification, maxRounds = 3, verifyTop = 5) {
  if (!initial) return { best: initial, finalists: [], audit: null };
  const cash = x.assets.findIndex(a => a.symbol === "CASH");
  const utilities = (row) => pathUtilities(row, x, verification);
  const paired = pairedUtilityTest;
  const describe = (move, result, test) => ({
    from: x.assets[move.i].symbol, to: x.assets[move.j].symbol, transfer: move.amount,
    full: move.full, certaintyEquivalentGain:
      result.metrics.certaintyEquivalent - best.metrics.certaintyEquivalent,
    z: test.z,
  });
  let best = initial, incumbent = utilities(initial), screened = 0, verified = 0,
    blocked = 0, rounds = 0, status = "no_significant_improvement", closest = null;
  const accepted = [], finalists = [], seen = new Set();
  for (let round = 0; round < maxRounds; round++) {
    rounds++;
    const base = best.weights, moves = [];
    const reference = assess(base, x, sample).metrics.score;
    for (let i = 0; i < base.length; i++) {
      const free = i === cash ? base[i] - x.requiredCash : base[i];
      if (free < .05 - 1e-8) continue;
      for (let j = 0; j < base.length; j++) {
        if (j === i || !x.buyAllowed[j]) continue;
        for (const [amount, full] of i === cash || base[i] <= .05 + 1e-8
          ? [[.05, base[i] <= .05 + 1e-8 && i !== cash]] : [[.05, false], [base[i], true]]) {
          const w = base.slice();
          w[i] = Math.round((w[i] - amount) * 1e12) / 1e12;
          w[j] = Math.round((w[j] + amount) * 1e12) / 1e12;
          const key = w.map(v => v.toFixed(6)).join();
          if (seen.has(key)) continue;
          seen.add(key);
          if (!validWeights(w, x)) { blocked++; continue; }
          const result = assess(w, x, sample);
          screened++;
          if (result.feasible && result.metrics.score > reference + 1e-12)
            moves.push({ i, j, amount, full, w, score: result.metrics.score });
        }
      }
    }
    moves.sort((a, b) => b.score - a.score);
    let winner = null;
    for (const move of moves.slice(0, verifyTop)) {
      const result = assess(move.w, x, verification);
      if (!result.feasible) continue;
      verified++;
      finalists.push(result);
      const own = utilities(result), test = paired(own, incumbent);
      const row = { move, result, own, test };
      if (test.mean > 0 && test.z >= SUBSTITUTION_Z) {
        if (!winner || test.mean > winner.test.mean) winner = row;
      } else if (!closest || test.z > closest.z) closest = describe(move, result, test);
    }
    if (!winner) { status = round ? "converged" : "no_significant_improvement"; break; }
    accepted.push(describe(winner.move, winner.result, winner.test));
    best = winner.result;
    incumbent = winner.own;
    if (round === maxRounds - 1) status = "search_budget";
  }
  return { best, finalists, audit: { status, rounds, screened, verified,
    structurallyBlocked: blocked, accepted, closestRejected: closest, threshold: SUBSTITUTION_Z,
    scope: "5-point exchanges and full substitutions within the simulated sample; paired one-sided 95% test on the verification paths; Monte Carlo error only, not a global optimum" } };
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
// Independent searches per proposal. The objective is flat near its optimum:
// on the 27-Oct cut, four seeds gave winners sharing 45-65% of their weights
// yet within USD 184 of each other on common paths.
export const MULTI_START_COUNT = 3;

export function compositionSignals(x, positions, overrides = x.valuationOverrides || {}) {
  const weights = x.assets.map(a => positions.find(p=>p.symbol===a.symbol)?.weight || 0);
  const risks = marginalRisk(weights, x.innovationCovariance||x.covariance);
  // Bond scenario anchors as simulated: regime effects centered on the carry.
  const bondScenarioAnchors = (asset, anchor) =>
    centeredRegimeConditions(asset, anchor, x.regimes, x.options.horizon)
      .map((condition) => Math.expm1(Math.log1p(anchor.annual) + condition));
  const signals = positions.map((p) => {
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
      financialPeriod: a.financials?.eps?.period_end ?? null,
      financialMethod: a.financials?.eps?.method ?? null,
      financialObservedAt: a.financials?.observed_at ?? null,
      bondDate: anchor.bond?.date ?? a.bond_profile?.date ?? null,
      holdingsCoverage: anchor.holdingsCoverage ?? null,
      valuationDate: anchor.valuationDate ?? null,
      anchor: anchor.annual,
      adverseAnchor: anchor.bond ? Math.min(...bondScenarioAnchors(a, anchor)) : anchor.low,
      favorableAnchor: anchor.bond ? Math.max(...bondScenarioAnchors(a, anchor)) : anchor.high,
      confidence: anchor.confidence,
      valuationEvidence: anchor.forecast?.valid ? {
        source: anchor.forecast.source,
        assumptions: { ...anchor.forecast.assumptions },
        rawAnnualReturn: anchor.forecast.model.annualReturn,
        effectiveBaseEPS: anchor.forecast.effectiveBaseEPS,
        earningsBasis: anchor.forecast.earningsBasis,
        accountingSensitivity: anchor.forecast.accountingSensitivity,
        confidence: anchor.forecast.confidence,
        prior: anchor.forecast.prior,
        rerating: anchor.forecast.rerating,
        decomposition: anchor.forecast.decomposition,
        growthEvidence: anchor.forecast.growthEvidence,
        refinement: anchor.refinement,
      } : null,
      source: anchor.bond
        ? anchor.source + " · sensibilidad duración/convexidad por régimen; reinversión y curva completa no modeladas"
        : anchor.source,
      risk: risks[i],
      assumptions: { ...a.assumptions, ...overrides[a.symbol] },
    };
  });
  return signals;
}

export function compositionRiskDiagnostics(x, row) {
    if (!row) return null;
    const economic=exposureReport(x.assets,row.weights,x.asOf,x.informationAsOf,x.securitySectors);
    const limits = [
      ["CVaR 95", row.metrics.cvar95, x.rules.cvarBudget],
      ["Prob. pérdida", row.metrics.lossProbability, x.rules.maxLossProbability],
      ["Prob. drawdown", row.metrics.drawdownProbability, x.policy.maxDrawdownProbability],
      ["Riesgo liquidez", row.metrics.liquidityFailureProbability, x.policy.maxLiquidityFailure],
      ["Treasuries combinados",economic.sleeves.treasury,x.rules.maxTreasury],
      ["Acciones combinadas",economic.sleeves.usEquity+economic.sleeves.globalEquity,x.rules.maxEquity],
      ["Alto rendimiento y emergente",economic.sleeves.riskyCredit,x.rules.maxRiskyCredit],
      ...x.assets.flatMap((a,i)=>a.type!=="cash"&&row.weights[i]>1e-8
        ? [["Tope "+a.symbol,row.weights[i],positionLimit(a,x)]]:[]),
      ...Object.entries(economic.sectorUpperBounds).map(([s,w])=>
        ["Sector "+s+" (cota)",w,x.rules.maxSector]),
      ["Emisores no identificados (cota)",economic.unclassifiedIssuerWeight,
        Math.min(x.rules.maxPosition,x.rules.maxGlobal)],
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
  }

/** Ordinary proposals pass the same model-uncertainty rule as transitions. */
export function finalizeCompositionDecision(proposal, inputs, paths = 1000, proposals = [proposal]) {
  if (!proposal) return proposal;
  const x=inputs, count=Math.max(100,Math.min(1000,paths));
  const hasPool=proposals.some(p=>p?.candidate_pool?.length);
  const missing=!Number.isFinite(x.riskFree)||x.assets.some((a,i)=>a.type!=='cash'&&x.current.positions.some(p=>p.symbol===a.symbol&&p.weight>0)&&
    !x.anchors[i].fundamental&&!x.anchors[i].bond&&
    !(Number.isFinite(x.options.assetAssumptions?.[a.symbol]?.expectedReturn)&&x.options.assetAssumptions[a.symbol].uncertainty>0));
  if(proposal.status!=='proposed'&&!hasPool)return proposal;
  let chosen=proposal.positions, selection=null;
  if(hasPool&&!missing){
    const candidates=proposals.flatMap(p=>[p?.positions,...(p?.candidate_pool||[])]).filter(Boolean);
    for(const w of passiveCandidates(x))candidates.push(x.assets.flatMap((a,i)=>w[i]>1e-9?[{symbol:a.symbol,weight:w[i]}]:[]));
    // Deterministic reference combinations diversify the opportunity set; the
    // economics of these references is tested, never presumed superior.
    const funds=x.assets.map((a,i)=>i).filter(i=>x.buyAllowed[i]&&
      (x.anchors[i].bond||x.assets[i].symbol===x.policy.benchmark));
    const cash=x.assets.findIndex(a=>a.symbol==='CASH');
    for(let a=0;a<funds.length;a++)for(let b=a+1;b<funds.length;b++){
      const w=Array(x.assets.length).fill(0);w[funds[a]]=Math.min(.35,positionLimit(x.assets[funds[a]],x));
      w[funds[b]]=Math.min(.35,positionLimit(x.assets[funds[b]],x));w[cash]=1-w[funds[a]]-w[funds[b]];
      if(validWeights(w,x))candidates.push(x.assets.flatMap((asset,i)=>w[i]>1e-9?[{symbol:asset.symbol,weight:w[i]}]:[]));
      for(let c=b+1;c<funds.length;c++){
        const v=w.slice(),add=Math.max(0,Math.min(.25,positionLimit(x.assets[funds[c]],x),v[cash]-x.requiredCash));
        v[funds[c]]=add;v[cash]-=add;
        if(add>0&&validWeights(v,x))candidates.push(x.assets.flatMap((asset,i)=>v[i]>1e-9?[{symbol:asset.symbol,weight:v[i]}]:[]));
      }
    }
    selection=selectReliableCandidate(x,candidates,{paths:count,validWeights,starts:proposals.length});
    chosen=selection.positions;
  }
  const audit=selection?.audit||reviewRobustDecision(x,chosen,{paths:count,validWeights});
  const {candidate_pool:_pool,...base}=proposal;
  const diagnostics={...base.diagnostics,robustDecision:audit,
    ...(selection?{stability:selection.stability,reliableSelection:selection.selection}:{} )};
  const candidatePlan=tradePlan(x.assets,chosen,x.current.positions,x.current.capital,x.costs);
  const confirmedBase=audit.models.find(r=>r.id==='original');
  const confirmedAlternatives=(sample=null)=>{
    if(!confirmedBase)return {hold:{metrics:null,feasible:null},passive:null};
    const passive=base.alternatives?.passive?.positions,
      plan=passive?tradePlan(x.assets,passive,x.current.positions,x.current.capital,x.costs):null,
      weights=passive?x.assets.map(a=>passive.find(p=>p.symbol===a.symbol)?.weight||0):null,
      metrics=passive?evaluatePaths(weights,sample||generatePaths(x,count,audit.seed,52),
        {capital:x.current.capital,cost:plan.total}):null;
    return {hold:{metrics:confirmedBase.hold,feasible:!confirmedBase.holdFailures.length},
      passive:passive?{positions:passive,metrics,cost:plan.total,
        feasible:validWeights(weights,x)&&!riskSamplingEvidence(metrics,x.rules,x.policy).failures.length}:null,
      feasibilityScope:'base-model-on-confirmation-paths'};
  };
  if(audit.status==='passed'){
    const metrics=audit.models.find(r=>r.id==='original').candidate,
      sample=generatePaths(x,count,audit.seed,52),weights=x.assets.map(a=>chosen.find(p=>p.symbol===a.symbol)?.weight||0),
      row={weights,positions:chosen,metrics,plan:candidatePlan};
    const cashWeight=chosen.find(p=>p.symbol==='CASH')?.weight||0;
    const shy=x.assets.findIndex(a=>a.symbol==='SHY');
    return {...base,status:'proposed',reason:null,research_only:false,objective:x.policy.objective,positions:chosen,
      signals:compositionSignals(x,chosen),metrics,trade_plan:candidatePlan,
      benefit:audit.models.find(r=>r.id==='original').evidence.gain,hurdle:audit.hurdle,
      selected_kind:'robust-finite-pool',sensitivity:[],
      alternatives:confirmedAlternatives(sample),
      verification:{seed:audit.seed,paths:count,stepsPerYear:52,stage:'independent-confirmation'},
      diagnostics:{...diagnostics,selected:compositionRiskDiagnostics(x,row),
        attribution:portfolioAttribution(x.assets,weights,sample,candidatePlan.total,x.current.capital),
        economicExposure:exposureReport(x.assets,weights,x.asOf,x.informationAsOf,x.securitySectors),
        etfCorrelations:[],substitutions:null,concentrationAudit:{
          shyAnnualAnchor:shy>=0?x.anchors[shy].annual:null,shyAnchorSource:shy>=0?x.anchors[shy].source:null,
          shyAnnualVolatility:shy>=0?Math.sqrt(x.covariance[shy][shy]):null,
          shyMaxAllowed:x.rules.reserveCap,actualShyWeight:shy>=0?weights[shy]:0,
          maximumStockPosition:x.rules.maxPosition,eligibleButNotSimulated:x.selection?.outsideSample?.length||0,
          selectionMethod:x.selection?.preselectionMethod,comparedCaps:[],
          note:'The base-model cap frontier is research only; the selected portfolio uses robust finite-pool evidence'},
        cashAllocation:{status:cashWeight-x.requiredCash<1e-8?'required_reserve':'robust_pool',cashWeight,
          initialCashWeight:cashWeight,minimumCash:x.policy.minimumCash,requiredCash:x.requiredCash,
          excessCash:Math.max(0,cashWeight-x.requiredCash),cashYield:x.policy.cashYield,
          evaluated:selection?.selection.discovered||1,structurallyBlocked:0,improvements:[],comparisons:[]}}};
  }
  const holdPlan=tradePlan(x.assets,x.current.positions,x.current.positions,x.current.capital,x.costs);
  const reasons=audit.models.filter(r=>!r.passes).map(r=>`${DECISION_MODEL_LABELS[r.id]} (${r.failures.length?r.failures.join(', '):'mejora insuficiente'})`);
  if(audit.tailStress?.passes===false)reasons.push(`Colas Student (${audit.tailStress.riskEvidence.failures.join(', ')})`);
  return {...base,status:'hold',research_only:false,objective:x.policy.objective,
    diagnostics:{...diagnostics,attribution:null,cashAllocation:null},
    reason:(audit.status==='incomplete'
      ?(audit.missingEconomicInputs?.length?`Mantener: falta ${audit.missingEconomicInputs.join(', ')}; comparación económica incompleta.`:
        `Mantener: faltan anclas fundamentadas o expectativas explícitas para ${audit.unanchoredIncumbents.join(', ')}. Completar Research antes de evaluar una transición.`)
      :`Mantener: ${selection&&!selection.selection.admissible?'ninguna transición del conjunto comprobado superó los controles. ':''}transición descartada en ${reasons.join('; ')}.`)+
      (audit.currentViolatesRisk?' La cartera actual también excede límites: requiere revisión del mandato o del riesgo.':''),
    candidate_review:{positions:chosen,metrics:audit.models.find(r=>r.id==='original')?.candidate??null,
      benefit:audit.minimumGain,trade_plan:candidatePlan},
    positions:x.current.positions.map(p=>({...p})),signals:[],
    metrics:audit.models.find(r=>r.id==='original')?.hold??null,trade_plan:holdPlan,
    alternatives:confirmedAlternatives(),
    benefit:0,hurdle:audit.hurdle,selected_kind:'hold'};
}
export function startSeeds(seed, count = MULTI_START_COUNT) {
  return Array.from({ length: count }, (_, k) => (seed + k * 0x9e3779b9) >>> 0);
}
/**
 * Re-run the winners of independent searches on fresh common paths. Among
 * those not significantly worse than the best (paired one-sided 95%), the
 * one with the least turnover is kept, then the higher utility. Its weight
 * overlap with the other winners measures how much the proposal depends on
 * the search's random draws.
 */
export function reconcileBaseStarts(snapshot, settings = {}, overrides = {}, rules = {}, proposals = [], finalPaths = 3000) {
  const x = prepareComposition(snapshot, settings, overrides, rules);
  const finalize = p => ({...p,research_only:true});
  const usable = proposals.map((proposal, k) => ({ proposal, k }))
    .filter(({ proposal }) => proposal?.positions?.length);
  if (usable.length < 2) return finalize(proposals.find(p => p?.positions?.length) || proposals[0]);
  const common = generatePaths(x, finalPaths, ((x.options.seed >>> 0) ^ 0x2545f491) >>> 0, 52);
  const rows = usable.map(({ proposal, k }) => {
    const bySymbol = new Map(proposal.positions.map(p => [p.symbol, p.weight]));
    const weights = x.assets.map(a => bySymbol.get(a.symbol) || 0);
    const covered = proposal.positions.every(p => x.assets.some(a => a.symbol === p.symbol));
    const result = assess(weights, x, common, proposal.status === "hold");
    return { proposal, k, weights, covered, result, utilities: pathUtilities(result, x, common) };
  }).filter(row => row.covered);
  if (rows.length < 2) return finalize(usable[0].proposal);
  const top = rows.reduce((a, b) => b.result.metrics.score > a.result.metrics.score ? b : a);
  for (const row of rows)
    row.z = row === top ? 0 : pairedUtilityTest(top.utilities, row.utilities).z;
  const equivalent = rows.filter(row => row.z < SUBSTITUTION_Z);
  const chosen = equivalent.reduce((a, b) => {
    const d = b.result.plan.turnover - a.result.plan.turnover;
    return d < -1e-9 || (Math.abs(d) <= 1e-9 && b.result.metrics.score > a.result.metrics.score) ? b : a;
  });
  const winners = rows.map(row => ({
    seed: startSeeds(x.options.seed >>> 0, proposals.length)[row.k],
    positions: row.proposal.positions, status: row.proposal.status,
    certaintyEquivalent: row.result.metrics.certaintyEquivalent,
    turnover: row.result.plan.turnover, z: row.z, equivalent: row.z < SUBSTITUTION_Z,
    overlap: weightOverlap(chosen.weights, row.weights), chosen: row === chosen,
  }));
  // Fragility is measured against equivalent winners only: a significantly
  // worse winner is a failed search that the reconciliation already discards.
  const others = winners.filter(w => !w.chosen), peers = others.filter(w => w.equivalent);
  const minimumOverlap = peers.length ? Math.min(...peers.map(w => w.overlap)) : 1;
  const stability = {
    method: "multi-start", starts: proposals.length, compared: rows.length, commonPaths: finalPaths,
    equivalent: peers.length, worse: others.length - peers.length, minimumOverlap,
    level: minimumOverlap >= .8 ? "high" : minimumOverlap >= .6 ? "medium" : "low",
    certaintyEquivalentRange: Math.max(...winners.map(w => w.certaintyEquivalent)) -
      Math.min(...winners.map(w => w.certaintyEquivalent)),
    threshold: SUBSTITUTION_Z, winners,
    scope: "Winners of independent searches on fresh common paths; Monte Carlo error of the same model and data, not parameter error",
  };
  const proposal = chosen.proposal;
  return finalize({ ...proposal, diagnostics: { ...proposal.diagnostics, stability },
    search: { ...proposal.search, starts: proposals.length } });
}
export function reconcileStarts(snapshot, settings = {}, overrides = {}, rules = {}, proposals = [], finalPaths = 3000) {
  const x=prepareComposition(snapshot,settings,overrides,rules),
    prototype=proposals.find(p=>p?.model_inputs)||proposals.find(p=>p?.positions?.length)||proposals[0];
  if(!prototype)return null;
  return finalizeCompositionDecision(prototype,x,finalPaths,proposals);
}
export function composePortfolio(snapshot, settings = {}, overrides = {}, rules = {}, search = {}) {
  const base=composeBasePortfolio(snapshot,settings,overrides,rules,search);
  if(search.deferRobustDecision)return base;
  return finalizeCompositionDecision(base,prepareComposition(snapshot,settings,overrides,rules),search.finalPaths??3000);
}
/** Sequential multi-start (Node, tests); the browser runs the starts in parallel workers. */
export function composeMultiStart(snapshot, settings = {}, overrides = {}, rules = {}, search = {}, count = MULTI_START_COUNT) {
  const seed = (settings.seed ?? 20261024) >>> 0;
  const proposals = startSeeds(seed, count).map(start =>
    composePortfolio(snapshot, { ...settings, seed: start }, overrides, rules,
      { ...search, deferRobustDecision: true }));
  return reconcileStarts(snapshot, { ...settings, seed }, overrides, rules, proposals, search.finalPaths ?? 3000);
}
export function composeBasePortfolio(
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
      reserve[shortBond] = Math.min(x.rules.reserveCap,x.rules.maxGlobal,x.rules.maxTreasury,1-minCash);
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
  // A passive index is a comparison, not an instruction to buy without a
  // calibrated ex-ante return. Temporarily allow only that evaluation.
  const benchmarkComparison = x.selection.benchmarkOnlyProxy === x.policy.benchmark;
  const benchmarkInputs = benchmarkComparison ? {
    ...x,
    buyAllowed: x.buyAllowed.map((allowed, i) =>
      allowed || x.assets[i].symbol === x.policy.benchmark),
  } : x;
  const references = Object.fromEntries([
    ["cash", allCash],
    ["reserve", shortBond >= 0 ? reserve : null],
    ["equity20", equity >= 0 &&
      benchmarkInputs.buyAllowed[equity] ? equityTilt : null],
  ].map(([name, w]) => {
    const comparator = name === "equity20" ? benchmarkInputs : x;
    if (!w || !validWeights(w, comparator)) return [name, null];
    const check = assess(w, comparator, verification);
    return [name, {
      positions: check.positions,
      feasible: check.feasible,
      meanReturn: check.metrics.meanReturn,
      cvar95: check.metrics.cvar95,
      lossProbability: check.metrics.lossProbability,
      certaintyEquivalent: check.metrics.certaintyEquivalent,
      researchOnly: name === "equity20" && benchmarkComparison,
      assumption: name === "equity20" && benchmarkComparison
        ? x.selection.benchmarkProxyAssumption : null,
    }];
  }));
  // Independently search lower-SHY alternatives on the SAME training and
  // verification scenarios. Restricting only the original ranked list
  // incorrectly compared 100% cash against an optimized high-SHY portfolio.
  const shyIndex = x.assets.findIndex(a => a.symbol === "SHY");
  const cashIndex = x.assets.findIndex(a => a.symbol === "CASH");
  const verifiedCapCandidates = [];
  // A tighter user mandate must never be loosened by a diagnostic frontier.
  // Keep the domains nested: C_25 subset C_50 subset C_75 subset C_mandate.
  const capLevels = [...new Set([0.25, 0.50, 0.75]
    .map(cap => Math.min(cap, x.rules.reserveCap)))];
  const capAlternatives = capLevels.map(cap => {
    const cappedX = { ...x, rules: { ...x.rules, reserveCap: cap } };
    const alternatives = [];
    const seenCapped = new Set();
    let examined = 0;
    const addCap = (w, passive = false) => {
      if (!w || !validWeights(w, cappedX)) return;
      const key = w.map(v=>v.toFixed(5)).join(",");
      if (seenCapped.has(key)) return;
      seenCapped.add(key);
      examined++;
      const proposal = assess(w, cappedX, sample, false, passive);
      if (proposal.feasible) alternatives.push(proposal);
    };
    // Direct counterfactuals of each finalist: move only the prohibited SHY
    // fraction to cash, never assume a favorable stock-return forecast.
    for (const row of ranked.slice(0, 16)) {
      const w = row.weights.slice();
      if (shyIndex >= 0 && cashIndex >= 0 && w[shyIndex] > cap) {
        const excess = w[shyIndex] - cap;
        w[shyIndex] = cap;
        w[cashIndex] += excess;
      }
      addCap(w, row.kind === "passive");
    }
    // The all-cash comparator is known to satisfy reserve caps and must
    // never disappear from the constrained frontier.
    if (cashIndex >= 0) addCap(allCash);
    // Deterministic cash+reserve holdings ensure each cap is actually tested.
    if (shyIndex >= 0 && cashIndex >= 0 && cappedX.buyAllowed[shyIndex]) {
      for (let bondWeight = 0.05; bondWeight <= cap + 1e-8; bondWeight += 0.05) {
        const w = allCash.slice();
        w[shyIndex] = Math.round(bondWeight * 100) / 100;
        w[cashIndex] = 1 - w[shyIndex];
        addCap(w);
      }
    }
    for (const w of passiveCandidates(cappedX)) addCap(w, true);
    for (const w of reserveTilts(cappedX)) addCap(w);
    // Additional search is conditioned on this specific cap rather than
    // recycling the weights selected under the unrestricted SHY constraint.
    const rng = seededRandom((seed ^ 0x73594acd ^ Math.round(cap*1000)) >>> 0);
    for (let attempts=0; attempts<1800 && examined<150; attempts++)
      addCap(candidate(cappedX, rng));
    alternatives.sort((a,b)=>b.metrics.score-a.metrics.score);
    for (let attempts=0; attempts<280 && examined<220; attempts++) {
      if (!alternatives.length) break;
      const parent = alternatives[Math.floor(rng()*Math.min(6,alternatives.length))];
      addCap(neighborCandidate(cappedX, parent.weights, rng));
      if (attempts%25===24)
        alternatives.sort((a,b)=>b.metrics.score-a.metrics.score);
    }
    alternatives.sort((a,b)=>b.metrics.score-a.metrics.score);
    let bestCap = null;
    // Always verify the zero-risk / reserve-only baselines, even if their
    // exploratory score ranks below riskier candidates in a smaller sample.
    const conservative = alternatives.filter(r =>
      r.positions.every(p => p.symbol === "CASH" || p.symbol === "SHY"));
    const finalReview = [...conservative,
      ...alternatives.filter(r => !conservative.includes(r)).slice(0,10)];
    for (const row of finalReview) {
      const v = assess(row.weights, cappedX, verification, false,
        row.kind === "passive");
      if (v.feasible &&
          (!bestCap || v.metrics.score > bestCap.metrics.score)) bestCap = v;
    }
    if (bestCap) verifiedCapCandidates.push(bestCap);
    return {
      cap, compared: examined,
      verified: finalReview.length,
      feasible: !!bestCap,
      positions: bestCap?.positions ?? [],
      meanReturn: bestCap?.metrics.meanReturn ?? null,
      cvar95: bestCap?.metrics.cvar95 ?? null,
      certaintyEquivalent: bestCap?.metrics.certaintyEquivalent ?? null,
      certaintyGapVsSelected: null,
    };
  });
  // Search under the 25/50/75% caps explores candidates the unrestricted
  // pass can miss. Never ignore a verified, feasible improvement.
  for (const proposal of verifiedCapCandidates)
    if (validWeights(proposal.weights, x) &&
        (!best || proposal.metrics.score > best.metrics.score))
      best = proposal;
  const cashReview = reviewCashAllocation(best, x, verification);
  best = cashReview.best;
  const substitutionReview = reviewSubstitutions(best, x, sample, verification);
  best = substitutionReview.best;
  // The independent cap searches discover candidates in different orders.
  // Reconcile ALL verified finalists against EACH nested feasible set,
  // including the final selected portfolio. The displayed frontier must
  // measure the same opportunity set, not three unrelated random searches.
  const pooledFinalists = [...verified, ...verifiedCapCandidates, ...cashReview.finalists,
    ...substitutionReview.finalists,
    ...(best ? [best] : [])];
  let previousFrontierScore = -Infinity;
  for (const row of capAlternatives) {
    const cappedX = { ...x, rules: { ...x.rules, reserveCap: row.cap } };
    let winner = null;
    for (const finalist of pooledFinalists) {
      if (!validWeights(finalist.weights, cappedX)) continue;
      const comparison = assess(finalist.weights, cappedX, verification,
        false, finalist.kind === "passive");
      if (comparison.feasible &&
          (!winner || comparison.metrics.score > winner.metrics.score))
        winner = comparison;
    }
    if (winner) {
      if (winner.metrics.score + 1e-10 < previousFrontierScore)
        throw new Error("Fronteras SHY no monótonas: revisar el conjunto acumulativo");
      previousFrontierScore = winner.metrics.score;
    }
    row.feasible = !!winner;
    row.positions = winner?.positions ?? [];
    row.meanReturn = winner?.metrics.meanReturn ?? null;
    row.cvar95 = winner?.metrics.cvar95 ?? null;
    row.certaintyEquivalent = winner?.metrics.certaintyEquivalent ?? null;
    row.score = winner?.metrics.score ?? null;
    row.verifiedPoolSize = pooledFinalists.length;
    row.certaintyGapVsSelected = winner && best
      ? Math.max(0, best.metrics.certaintyEquivalent -
        winner.metrics.certaintyEquivalent) : null;
  }
  const shyAnchor = shyIndex >= 0 ? x.anchors[shyIndex] : null;
  const concentrationAudit = {
    shyAnnualAnchor: shyAnchor?.annual ?? null,
    shyAnchorSource: shyAnchor?.source ?? "No disponible",
    shyAnnualVolatility: shyIndex >= 0
      ? Math.sqrt(Math.max(0,x.covariance[shyIndex][shyIndex])) : null,
    shyMaxAllowed: x.rules.reserveCap,
    actualShyWeight: best?.positions.find(p=>p.symbol==="SHY")?.weight ?? 0,
    maximumStockPosition: x.rules.maxPosition,
    eligibleButNotSimulated: x.selection.outsideSample.length,
    selectionMethod: x.selection.preselectionMethod,
    comparedCaps: capAlternatives,
    note: "Fronteras anidadas sobre la misma muestra acumulativa de finalistas verificados; la cartera seleccionada se incorpora a cada tope que cumple. Ninguna frontera afirma optimalidad global. SHY puede prevalecer con mejor utilidad ajustada por riesgo.",
  };
  const exposure = best ? exposureReport(x.assets,best.weights,
    x.asOf,x.informationAsOf,x.securitySectors) : null;
  const etfCorrelations = best ? x.assets.flatMap((a,i)=>{
    if(!(best.weights[i]>.001))return [];
    return x.assets.slice(i+1).flatMap((b,k)=>{
      const j=i+k+1;
      if(!(best.weights[j]>.001) ||
         (a.type!=="etf"&&b.type!=="etf"))return [];
      const total=rawCorrelation(x.covariance,i,j);
      const residual=x.residualCorrelation?.[i]?.[j];
      const overlap=holdingsOverlap(a,b,x.asOf,x.informationAsOf);
      return [{
        pair:a.symbol+"/"+b.symbol,
        totalCorrelation:total,
        residualCorrelation:Number.isFinite(residual)?residual:null,
        positionPairWeight:best.weights[i]*best.weights[j],
        holdingsOverlap:a.type==="etf"&&b.type==="etf"
          ? knownFundOverlap(a,b,x.asOf,x.informationAsOf):null,
        knownHoldingsOverlap:overlap?.knownOverlap??null,
        knownSharedPortfolioWeight:overlap?overlap.shared.reduce((s,p)=>s+
          Math.min(best.weights[i]*p.leftWeight,best.weights[j]*p.rightWeight),0):null,
        holdingsCoverage:overlap?[overlap.leftCoverage,overlap.rightCoverage]:null,
        warning:total>.8?"Dependencia total elevada":"Dependencia observada",
      }];
    });
  }).sort((a,b)=>b.positionPairWeight*Math.abs(b.totalCorrelation)-
                   a.positionPairWeight*Math.abs(a.totalCorrelation)).slice(0,12) : [];
  const attribution = best ? portfolioAttribution(
    x.assets, best.weights, verification,
    best.plan.total, x.current.capital) : {available:false};
  const diagnostics = {
    regimeProbabilities: x.regimeProbabilities,
    cashAllocation: cashReview.audit,
    substitutions: substitutionReview.audit,
    selected: compositionRiskDiagnostics(x, best),
    attribution,
    economicExposure: exposure,
    etfCorrelations,
    concentrationPolicy: {
      global:x.rules.maxGlobal,
      opportunity:x.rules.maxOpportunity,
      treasury:x.rules.maxTreasury,
      equity:x.rules.maxEquity,
      riskyCredit:x.rules.maxRiskyCredit,
      qualified:best?.positions.filter(p=>qualifiedOpportunity(
        x.assets.find(a=>a.symbol===p.symbol),
        x.opportunityEvidence[p.symbol],x.asOf)).map(p=>p.symbol)||[],
      note:"Solo evidencia prospectiva revisada y publicada con el corte puede superar el límite global. Sin validación, no hay excepciones.",
    },
    references,
    concentrationAudit,
    dependence: x.dependence,
    volatility: {
      mode: x.conditional.enabled ? "Varianza GJR (ajuste t) / EWMA" : "EWMA",
      accepted: x.conditional.active,
      fallback: x.conditional.fallback,
      studentNu: null,
      innovationLaw: x.conditional.dynamic
        ? "Conditional Gaussian price innovations; GJR/EWMA daily variance; Student-t risk stress is separate"
        : "Legacy Merton diffusion with EWMA initialization",
      factorMethod: x.factorCovariance.method,
      factorObservations: x.factorCovariance.observations,
      covarianceBasis: x.innovationMoments.method,
      maxLinearCorrelationShift: x.innovationMoments.maxCorrelationShift,
      projectionRemainderMaximum: x.innovationMoments.projectionRemainderMaximum,
      residualGarchValidated: false,
      reason: x.conditional.reason,
      asOf: x.conditional.asOf,
      additionalMertonJumps: !x.conditional.dynamic && x.options.model==="merton",
    },
    note: "Pares con ETF: correlación total; acciones: residual tras SPY alcista/bajista y sector, con respaldo total si falta historia. Holdings compartidas y correlación son medidas distintas. CVaR conserva el riesgo sistémico; los residuos no prueban causalidad.",
  };
  const {
    baseline: _baseline,
    account: _account,
    volatilityData: _volatilityData,
    ...recordedOptions
  } = x.options;
  const metadata = {
    version: 2,
    research_only: true,
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
      method: "reserve-tilts-random-local-exchanges-with-capped-challengers",
      capChallengersExamined: capAlternatives.reduce((total,row)=>total+row.compared,0),
      cashReallocationsEvaluated: cashReview.audit?.evaluated || 0,
      substitutionsScreened: substitutionReview.audit?.screened || 0,
      exhaustive: false,
    },
    verification: {
      seed: verificationSeed,
      paths: finalPaths,
      stepsPerYear: 52,
    },
    candidate_pool: [...ranked, ...pooledFinalists].map(r=>r.positions),
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
  const signals = compositionSignals(x, best.positions, overrides);
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
      // Rebuild decomposition from the stressed covariance. Reusing the
      // original factorization made correlation sensitivity ineffective.
      factorization: test.correlation
        ? factorizeStressedCovariance(covariance, x.assets)
        : x.factorization,
      anchors: buildReturnAnchors(x.assets, options, changedOverrides, x.anchorUniverse || x.assets),
    };
    const draws = generatePaths(altered, Math.min(paths, 600), seed, 12);
    const choices = [...ranked.slice(0, 20), {weights:best.weights}, { weights: current }]
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
  const proposal = {
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
        holdings: a.holdings || null,
        dividend_per_share: a.dividend_per_share ?? null,
        distribution_calendar: a.distribution_calendar || null,
        issuer_distributions: Array.isArray(a.issuer_distributions?.records) ? {...a.issuer_distributions,
          records:a.issuer_distributions.records.filter(r=>r.ex_date>x.asOf)} : null,
        assumptions: { ...a.assumptions, ...overrides[a.symbol] },
      })),
      covariance: x.covariance,
      innovationCovariance: x.innovationCovariance,
      securitySectors: x.securitySectors,
      residualCorrelation: x.residualCorrelation,
      dependence: x.dependence,
      anchors: x.anchors,
      regimes: x.regimes,
    },
    objective: x.policy.objective,
    notes: [
      "Dividendos: los ajustes de precios ya incluyen rentabilidad total; las distribuciones en efectivo se extraen sin duplicar el rendimiento. Retención asumida configurable; no es cálculo tributario individual.",
      "ETF: límites por exposición a Treasuries y holdings fechados cuando disponibles; no se simulan composiciones internas que no publica el proveedor.",
      "Probabilidades y confianza son supuestos sin calibración predictiva demostrada.",
      "Sectores: se acumulan acciones y ETF sectoriales, además de holdings verificadas cuando disponibles.",
      "Retiros prefundados con efectivo; no se suponen ventas gratuitas durante las trayectorias.",
      "Duración y convexidad proxy bajo shocks paralelos; no son curva completa, rolldown ni reinversión observada.",
    ],
  };
  return { ...proposal, research_only: true };
}
