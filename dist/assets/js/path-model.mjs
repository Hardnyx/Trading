import {
  alignReturns,
  finite,
  mean,
  quantile,
  sum,
  normalizeWeights,
} from "./analytics.mjs?v=0.8.0";
import { seededRandom, normalGenerator, poisson } from "./random.mjs?v=0.8.0";
import { ewmaCovariance, cholesky } from "./risk-math.mjs?v=0.8.0";
import { buildReturnAnchors, sampleDrifts, bondScenarioAnnualReturn } from "./return-model.mjs?v=0.8.0";
import { annualDistributionYield, dividendStep } from "./cashflows.mjs?v=0.8.0";
import { assetAt } from "./research-model.mjs?v=0.8.0";
import { factorModel } from "./factors.mjs?v=0.8.0";
import { conditionalRisk, updateGjrVariance, updateEwmaVariance } from "./conditional-risk.mjs?v=0.8.0";
import { marketFactorCovariance, conditionalFactorization } from "./factor-covariance.mjs?v=0.8.0";
import {
  mandate,
  regimes,
  withdrawalSchedule,
  DEFAULT_REGIMES,
} from "./policy.mjs?v=0.8.0";

export const BASE_REGIME = {
  id: "base",
  label: "Continuidad",
  probability: 1,
  earningsShift: 0,
  multipleShift: 0,
  rateShift: 0,
  rateJumpBps: 0,
};
export function pathSettings(input = {}) {
  const s = {
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
    volatilityMode: "hybrid",
    ...input,
  };
  if (
    !["gbm", "merton"].includes(s.model) ||
    !["ewma", "hybrid", "legacy"].includes(s.volatilityMode) ||
    !["fundamental", "manual"].includes(s.driftMode) ||
    !finite(s.horizon) ||
    s.horizon < 0.25 ||
    s.horizon > 5 ||
    !finite(s.lambda) ||
    s.lambda <= 0 ||
    s.lambda >= 1 ||
    !finite(s.manualReturn) ||
    s.manualReturn <= -0.9 ||
    s.manualReturn > 2 ||
    !finite(s.jumpIntensity) ||
    s.jumpIntensity < 0 ||
    s.jumpIntensity > 5 ||
    !finite(s.jumpMean) ||
    s.jumpMean < -0.8 ||
    s.jumpMean > 0.5 ||
    !finite(s.jumpVol) ||
    s.jumpVol < 0 ||
    s.jumpVol > 1
  )
    throw new Error("Parámetros de simulación fuera de rango.");
  return s;
}
export function preparePaths(assets, options = {}, overrides = {}, references = assets) {
  const settings = pathSettings(options),
    asOf =
      settings.asOf ||
      assets.map((a) => a.price_date || a.history?.at(-1)?.date).sort()[0];
  const clean = assets.map((a) =>
    assetAt(a, asOf, settings.informationAsOf || asOf),
  );
  const aligned = alignReturns(clean, 500);
  if (aligned.dates.length < 20)
    throw new Error("Historia común insuficiente para la simulación.");
  const riskFactor = marketFactorCovariance(clean, references, asOf, settings.lambda);
  const baselineCovariance = riskFactor.available
    ? riskFactor.covariance
    : ewmaCovariance(aligned.columns.map((c) => c.map(Math.log1p)), settings.lambda);
  const conditional = conditionalRisk(clean, baselineCovariance,
    { ...settings, asOf });
  const covariance = conditional.covariance,
    factorization = conditionalFactorization(riskFactor, conditional.multipliers);
  const exposures = factorModel(
    clean,
    clean.map((a) => ({ symbol: a.symbol, weight: 1 / clean.length })),
    asOf, 500, settings.lambda, references,
  );
  const marketLoadings =
    settings.marketLoadings ||
    Object.fromEntries(
      (exposures.rows || []).map((r) => [
        r.symbol,
        Math.max(-3, Math.min(3, r.betaMarket)),
      ]),
    );
  return {
    assets: clean,
    options: { ...settings, asOf, marketLoadings },
    covariance,
    factorization,
    factorCovariance: {
      available: !!factorization,
      method: factorization?.method || "joint-Gaussian-total-covariance",
      observations: factorization?.observations || 0,
      note: riskFactor.note || riskFactor.reason,
      conditionalResidualGarch: false,
    },
    conditional: {
      ...conditional,
      // The raw fit data is internal, but a concise summary is shown in reports.
      asOf,
    },
    residualCorrelation: exposures.available ? exposures.residualCorrelation : null,
    dependence: {
      available: exposures.available,
      method: exposures.method || "total-correlation-fallback",
      observations: exposures.observations,
      regimeCounts: exposures.regimeCounts || null,
      explanation: exposures.note,
      residualMarketRiskExcluded: false,
    },
    anchors: buildReturnAnchors(clean, { ...settings, asOf }, overrides),
    observations: aligned.dates.length,
    calibrationEnd: aligned.dates.at(-1),
    regimes: regimes(
      settings.macroRegimes ||
        (settings.driftMode === "manual" ? [BASE_REGIME] : DEFAULT_REGIMES),
    ),
  };
}
export function jumpParameters(asset, anchor, options, regime) {
  if (asset.type === "cash" || asset.symbol === "CASH")
    return { mean: 0, vol: 0, compensator: 0 };
  const supplied = options.assetAssumptions?.[asset.symbol]?.jumpLoading;
  let jumpMean, jumpVol;
  if (anchor.bond) {
    jumpMean = (-anchor.bond.duration * regime.rateJumpBps) / 1e4;
    jumpVol =
      Math.sign(jumpMean / (options.jumpMean || -0.12)) *
      ((anchor.bond.duration * Math.abs(regime.rateJumpBps)) / 1e4) *
      0.35;
  } else {
    const loading = finite(supplied)
      ? supplied
      : asset.symbol === "GLD"
        ? -0.25
        : (options.marketLoadings?.[asset.symbol] ?? 1);
    if (Math.abs(loading) > 5)
      throw new Error("Carga de salto fuera de rango.");
    jumpMean = loading * options.jumpMean;
    jumpVol = loading * options.jumpVol;
  }
  return {
    mean: jumpMean,
    vol: jumpVol,
    compensator: Math.expm1(jumpMean + jumpVol ** 2 / 2),
  };
}
export function generatePaths(inputs, paths, seed, stepsPerYear = 52) {
  if (!Number.isInteger(paths) || paths < 100 || paths > 15000)
    throw new Error("Cantidad de escenarios fuera de rango.");
  const { assets, covariance, anchors } = inputs,
    options = pathSettings(inputs.options),
    n = assets.length,
    H = options.horizon,
    steps = Math.max(1, Math.ceil(stepsPerYear * H)),
    dt = H / steps;
  if (n * (steps + 1) * paths > 35000000)
    throw new Error(
      "Reduce las trayectorias o el horizonte para esta cantidad de activos.",
    );
  const policy = mandate({ ...options.mandate, horizon: H }),
    macro = regimes(inputs.regimes || [BASE_REGIME]),
    factor = cholesky(covariance),
    conditional = inputs.conditional,
    dynamic = conditional?.dynamic === true,
    factorization = inputs.factorization;
  // Preserve total covariance and correlation: only the conditional diagonal
  // dynamics change. Every shocked return still carries systematic exposure.
  const correlation = dynamic
    ? covariance.map((row, i) => row.map((v, j) =>
        covariance[i][i] > 0 && covariance[j][j] > 0
          ? v / Math.sqrt(covariance[i][i]*covariance[j][j]) : 0))
    : null;
  const correlationFactor = dynamic ? cholesky(correlation) : null;
  const random = seededRandom(seed),
    normal = normalGenerator(random),
    intensity = dynamic ? 0 : options.model === "merton"
      ? options.jumpIntensity : 0;
  const marketIndex = assets.findIndex((a) => a.symbol === "SPY");
  if (
    policy.fxVolatility > 0 &&
    policy.fxMarketCorrelation !== 0 &&
    marketIndex < 0
  )
    throw new Error(
      "La correlación FX requiere SPY como factor de mercado observado.",
    );
  const gross = Array.from(
      { length: n },
      () => new Float64Array(paths * (steps + 1)),
    ),
    fx = new Float64Array(paths * (steps + 1));
  const scenarioCounts = Object.fromEntries(macro.map((r) => [r.id, 0]));
  for (let p = 0; p < paths; p++) {
    let u = random(),
      regime = macro.at(-1);
    for (const row of macro) {
      u -= row.probability;
      if (u <= 0) {
        regime = row;
        break;
      }
    }
    scenarioCounts[regime.id]++;
    const mu = sampleDrifts(anchors, options, random, normal),
      jumps = assets.map((a, i) =>
        jumpParameters(a, anchors[i], options, regime),
      );
    const drift = mu.map((v, i) => {
      const bond = anchors[i].bond;
      const baseGrowth = anchors[i].forecast?.equivalentGrowth ?? 0;
      const condition =
        assets[i].type === "cash"
          ? 0
          : bond
            ? (Math.log1p(bondScenarioAnnualReturn(bond, regime.rateShift, H)) -
                Math.log1p(finite(bond.carry) ? bond.carry : 0))
            : assets[i].symbol === "GLD"
              ? -regime.rateShift * 0.5
              : Math.log(
                  Math.max(0.01, 1 + baseGrowth + regime.earningsShift) /
                    (1 + baseGrowth),
                ) +
                Math.log1p(regime.multipleShift) / H;
      return (
        (v +
          condition -
          covariance[i][i] / 2 -
          intensity * jumps[i].compensator) *
        dt
      );
    });
    const values = Array(n).fill(1);
    const variances = dynamic
      ? assets.map((a,i) => conditional.fits[i]?.hInitial ?? Math.max(0,covariance[i][i]/252))
      : null;
    const baseDailyVariances = covariance.map((row,i)=>Math.max(0,row[i]/252));
    const annualLogDrift = dynamic
      ? drift.map((v,i) => v/dt + covariance[i][i]/2) : null;
    let exchange = policy.fxSpot;
    for (let i = 0; i < n; i++) gross[i][p * (steps + 1)] = 1;
    fx[p * (steps + 1)] = exchange;
    for (let t = 1; t <= steps; t++) {
      if (dynamic) {
        // Exact daily GJR recursion; store values at the existing weekly/monthly
        // reporting grid. This avoids using weekly shocks in a daily equation.
        const dayStart = Math.round((t-1) * 252 * dt);
        const dayEnd = Math.round(t * 252 * dt);
        const days = Math.max(1, dayEnd-dayStart);
        let marketSum = 0;
        for (let day = 0; day < days; day++) {
          // A single Gaussian SPY factor and PSD residual covariance are
          // estimated on the same historical dates. There is NO global
          // Student-t radial shock: its tail dependence was not calibrated.
          const z = Array.from({ length:n }, normal),
            marketZ = factorization ? normal() : 0;
          for (let i = 0; i < n; i++) {
            let shock = factorization ? factorization.loading[i]*marketZ : 0;
            const lower = factorization
              ? factorization.residualFactor[i] : correlationFactor[i];
            for (let j = 0; j <= i; j++) shock += lower[j]*z[j];
            const h = variances[i];
            const innovation = factorization
              ? shock/Math.sqrt(252) *
                (baseDailyVariances[i]>0
                  ? Math.sqrt(Math.max(0,h)/baseDailyVariances[i]) : 0)
              : Math.sqrt(Math.max(0,h))*shock;
            values[i] *= Math.exp(annualLogDrift[i]/252-h/2+innovation);
            variances[i] = conditional.fits[i]
              ? updateGjrVariance(conditional.fits[i],h,innovation)
              : updateEwmaVariance(h,innovation,options.lambda);
            if (i === marketIndex && baseDailyVariances[i]>0)
              marketSum += innovation/Math.sqrt(Math.max(h,1e-18));
          }
          if (marketIndex < 0 && factorization) marketSum += marketZ;
        }
        for (let i=0;i<n;i++)
          gross[i][p*(steps+1)+t] = values[i];
        const fxZ = policy.fxMarketCorrelation * (marketSum / Math.sqrt(days)) +
          Math.sqrt(1-policy.fxMarketCorrelation**2)*normal();
        exchange *= Math.exp(
          (Math.log1p(policy.fxAnnualChange)-policy.fxVolatility**2/2)*dt +
          policy.fxVolatility*Math.sqrt(dt)*fxZ);
        fx[p*(steps+1)+t]=exchange;
        continue;
      }
      const z = Array.from({ length: n }, normal),
        count = intensity ? poisson(random, intensity * dt) : 0,
        jumpZ = count ? normal() : 0;
      for (let i = 0; i < n; i++) {
        let diffusion = 0;
        for (let j = 0; j <= i; j++) diffusion += factor[i][j] * z[j];
        values[i] *= Math.exp(
          drift[i] +
            Math.sqrt(dt) * diffusion +
            count * jumps[i].mean +
            Math.sqrt(count) * jumps[i].vol * jumpZ,
        );
        gross[i][p * (steps + 1) + t] = values[i];
      }
      const k = marketIndex >= 0 ? marketIndex : 0;
      let marketZ = 0;
      for (let j = 0; j <= k; j++) marketZ += factor[k][j] * z[j];
      marketZ =
        covariance[k][k] > 0 ? marketZ / Math.sqrt(covariance[k][k]) : normal();
      const fxZ =
        policy.fxMarketCorrelation * marketZ +
        Math.sqrt(1 - policy.fxMarketCorrelation ** 2) * normal();
      exchange *= Math.exp(
        (Math.log1p(policy.fxAnnualChange) - policy.fxVolatility ** 2 / 2) *
          dt +
          policy.fxVolatility * Math.sqrt(dt) * fxZ,
      );
      fx[p * (steps + 1) + t] = exchange;
    }
  }
  return {
    gross,
    fx,
    assets,
    steps,
    dt,
    paths,
    seed,
    policy,
    asOf: options.asOf || assets[0].price_date,
    scenarioCounts,
  };
}
export function evaluatePaths(weights, sample, options = {}) {
  const { assets, gross, fx, steps, paths, dt, policy } = sample,
    capital = options.capital ?? 100000,
    cost = options.cost ?? 0;
  if (!(capital > cost) || cost < 0)
    throw new Error("Capital neto de costos no válido.");
  const initial = capital - cost,
    startFX = policy.fxSpot,
    cashIndex = assets.findIndex(
      (a) => a.type === "cash" || a.symbol === "CASH",
    );
  const schedule = withdrawalSchedule(policy, sample.asOf),
    flows = Array(steps + 1).fill(0);
  for (const row of schedule)
    flows[Math.min(steps, Math.max(1, Math.ceil(row.year / dt - 1e-8)))] +=
      row.amount;
  const returns = [],
    terminalWealth = [],
    drawdowns = [],
    underwater = [],
    observations = options.details
      ? Array.from({ length: steps + 1 }, () => [])
      : null,
    samplePaths = [];
  let utility = 0,
    losses = 0,
    failures = 0,
    goalSuccess = 0,
    floorBreaches = 0,
    recoveries = 0,
    unfinishedRecoveries = 0;
  const selected = weights.map((w, i) => ({ w, i })).filter((r) => r.w > 0),
    gamma = policy.riskAversion,
    dividendYields=assets.map(annualDistributionYield),
    cashDividends=policy.dividendPolicy==="cash",
    withholding=policy.dividendWithholding || 0;
  let distributionGrossSum=0, distributionNetSum=0;
  for (let p = 0; p < paths; p++) {
    let previous = initial,
      cashWithdrawn = 0,
      nav = initial / capital,
      peak = 1,
      worst = nav - 1,
      failed = false,
      floorBroken = initial * startFX < policy.capitalFloor,
      longest = 0,
      run = 0,
      everUnder = false,
      dividendsGross=0,
      dividendsNet=0;
    const path = options.details && p < 12 ? [nav * 100] : null;
    if (observations) observations[0].push(nav * 100);
    for (let t = 1; t <= steps; t++) {
      const offset = p * (steps + 1) + t;
      const cashGross = cashIndex >= 0 ? gross[cashIndex][offset] : 1;
      let total = 0;
      for(const {w,i} of selected) {
        const dist=cashDividends
          ? dividendStep(gross[i][offset-1],gross[i][offset],dividendYields[i],t,dt,withholding)
          : {priceGross:gross[i][offset],grossCash:0,netCash:0};
        total+=w*dist.priceGross*initial;
        dividendsGross+=w*dist.grossCash*initial;
        dividendsNet+=w*dist.netCash*initial;
      }
      total += dividendsNet-cashWithdrawn;
      const priorFX = fx[offset - 1],
        currentFX = fx[offset];
      nav *=
        previous > 0
          ? ((Math.max(0, total) / previous) * currentFX) / priorFX
          : 1;
      peak = Math.max(peak, nav);
      worst = Math.min(worst, nav / peak - 1);
      if (nav < peak * (1 - 1e-8)) {
        run++;
        longest = Math.max(longest, run);
        everUnder = true;
      } else run = 0;
      if (total * currentFX < policy.capitalFloor) floorBroken = true;
      const withdrawal = flows[t] / currentFX,
        cash =
          (cashIndex >= 0 ? weights[cashIndex] * cashGross * initial : 0) +
          dividendsNet - cashWithdrawn;
      if (cash + 1e-8 < withdrawal || total + 1e-8 < withdrawal) failed = true;
      cashWithdrawn += withdrawal;
      previous = Math.max(0, total - withdrawal);
      if (previous * currentFX < policy.capitalFloor) floorBroken = true;
      if (observations) observations[t].push(nav * 100);
      if (path) path.push(nav * 100);
    }
    distributionGrossSum+=dividendsGross;
    distributionNetSum+=dividendsNet;
    const remaining = previous * fx[p * (steps + 1) + steps],
      ratio = nav;
    returns.push(ratio - 1);
    terminalWealth.push(remaining);
    drawdowns.push(worst);
    underwater.push(longest * dt);
    if (ratio < 1) losses++;
    if (failed) failures++;
    if (floorBroken) floorBreaches++;
    if (everUnder && run === 0) recoveries++;
    if (run > 0) unfinishedRecoveries++;
    if (remaining >= policy.terminalTarget && !failed) goalSuccess++;
    const safe = Math.max(1e-5, ratio);
    utility +=
      policy.objective === "target"
        ? -(
            Math.max(
              0,
              (policy.terminalTarget - remaining) / (capital * startFX),
            ) ** 2
          )
        : policy.objective === "preservation"
          ? gamma === 1
            ? Math.log(safe)
            : (safe ** (1 - gamma) - 1) / (1 - gamma)
          : Math.log(safe);
    if (path) samplePaths.push(path);
  }
  const sorted = [...returns].sort((a, b) => a - b),
    tail = sorted.slice(0, Math.max(1, Math.ceil(paths * 0.05))),
    lossProbability = losses / paths;
  const score = utility / paths,
    certaintyEquivalent =
      policy.objective === "target"
        ? policy.terminalTarget / startFX -
          capital * Math.sqrt(Math.max(0, -score))
        : policy.objective === "preservation" && gamma !== 1
          ? capital *
            Math.max(1e-12, 1 + (1 - gamma) * score) ** (1 / (1 - gamma))
          : capital * Math.exp(score);
  const result = {
    score,
    certaintyEquivalent,
    dividendPolicy:policy.dividendPolicy,
    dividendWithholding:withholding,
    expectedGrossDividendCash:distributionGrossSum/paths,
    expectedNetDividendCash:distributionNetSum/paths,
    expectedLogGrowth: mean(
      returns.map((r) => Math.log(Math.max(1e-5, 1 + r))),
    ),
    meanReturn: mean(returns),
    medianReturn: quantile(sorted, 0.5),
    p05: quantile(sorted, 0.05),
    p95: quantile(sorted, 0.95),
    cvar95: Math.max(0, -mean(tail)),
    var95: Math.max(0, -quantile(sorted, 0.05)),
    lossProbability,
    lossProbabilitySE: Math.sqrt(
      (lossProbability * (1 - lossProbability)) / paths,
    ),
    drawdownProbability:
      drawdowns.filter((d) => d < -policy.maxDrawdown).length / paths,
    worstDrawdownP05: quantile(drawdowns, 0.05),
    medianUnderwaterYears: quantile(underwater, 0.5),
    recoveryProbability: recoveries / paths,
    underwaterAtHorizonProbability: unfinishedRecoveries / paths,
    liquidityFailureProbability: failures / paths,
    capitalFloorBreachProbability: floorBreaches / paths,
    goalProbability: goalSuccess / paths,
    medianTerminalWealth: quantile(terminalWealth, 0.5),
    p05TerminalWealth: quantile(terminalWealth, 0.05),
    p95TerminalWealth: quantile(terminalWealth, 0.95),
    paths,
  };
  if (options.details)
    Object.assign(result, {
      terminal: returns,
      bands: observations.map((v, t) => ({
        year: t * dt,
        p05: quantile(v, 0.05),
        p25: quantile(v, 0.25),
        p50: quantile(v, 0.5),
        p75: quantile(v, 0.75),
        p95: quantile(v, 0.95),
      })),
      samplePaths,
    });
  return result;
}
export function marginalRisk(weights, covariance) {
  const gradient = weights.map((_, i) =>
      sum(covariance[i].map((c, j) => c * weights[j])),
    ),
    variance = sum(weights.map((w, i) => w * gradient[i])),
    volatility = Math.sqrt(Math.max(0, variance));
  return weights.map((w, i) => ({
    marginal: volatility > 0 ? gradient[i] / volatility : 0,
    contribution: volatility > 0 ? (w * gradient[i]) / volatility : 0,
    fraction: variance > 0 ? (w * gradient[i]) / variance : 0,
  }));
}
