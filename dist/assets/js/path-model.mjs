import {
  alignReturns,
  finite,
  mean,
  quantile,
  sum,
  normalizeWeights,
} from "./analytics.mjs?v=0.31.0";
import { seededRandom, normalGenerator, poisson } from "./random.mjs?v=0.31.0";
import { ewmaCovariance, cholesky } from "./risk-math.mjs?v=0.31.0";
import { buildReturnAnchors, sampleDrifts, bondScenarioAnnualReturn, bondRegimeShift } from "./return-model.mjs?v=0.31.0";
import { distributionAccounting } from "./distribution-ledger.mjs?v=0.31.0";
import { cashGrowth, uniformCashGrowth } from "./cashflows.mjs?v=0.31.0";
import { copulaInnovationCovariance } from './copula-covariance.mjs?v=0.31.0';
import { assetAt } from "./research-model.mjs?v=0.31.0";
import { factorModel } from "./factors.mjs?v=0.31.0";
import { conditionalRisk, updateGjrVariance, updateEwmaVariance, updateTargetedVariance, studentMarginal, HORIZON_PERSISTENCE } from "./conditional-risk.mjs?v=0.31.0";
import { marketFactorCovariance, conditionalFactorization } from "./factor-covariance.mjs?v=0.31.0";
import {
  mandate,
  regimes,
  withdrawalSchedule,
  DEFAULT_REGIMES,
} from "./policy.mjs?v=0.31.0";

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
  const innovationMoments=copulaInnovationCovariance(covariance,conditional.dynamic?conditional.fits:[]);
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
    innovationCovariance:innovationMoments.covariance,
    innovationMoments,
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
    horizonVariance: longRunVariances(clean, asOf),
    anchors: buildReturnAnchors(clean, { ...settings, asOf }, overrides, references),
    // Constituents outside the simulated sample still anchor ETF holdings.
    anchorUniverse: references,
    observations: aligned.dates.length,
    calibrationEnd: aligned.dates.at(-1),
    regimes: regimes(
      settings.macroRegimes ||
        (settings.driftMode === "manual" ? [BASE_REGIME] : DEFAULT_REGIMES),
    ),
  };
}
/**
 * Long-run daily variance per instrument from its own last 500 log returns
 * known at the cut: the level toward which fallback variances revert.
 */
export function longRunVariances(assets, asOf, window = 500) {
  const longRunDaily = assets.map((asset) => {
    if (asset.type === "cash" || asset.symbol === "CASH") return 0;
    const closes = (asset.history || []).filter((row) => row.date <= asOf)
      .map((row) => row.adj_close).filter((v) => v > 0).slice(-(window + 1));
    if (closes.length < 61) return null;
    const r = closes.slice(1).map((v, i) => Math.log(v / closes[i]));
    const m = r.reduce((s, v) => s + v, 0) / r.length;
    return r.reduce((s, v) => s + (v - m) ** 2, 0) / (r.length - 1);
  });
  return {
    method: "variance-targeted EWMA: alpha = 1 - lambda, persistence " + HORIZON_PERSISTENCE,
    persistence: HORIZON_PERSISTENCE, window, longRunDaily,
  };
}
/**
 * Log-drift adjustment a macro scenario applies to one instrument. Scenarios
 * are applied as deviations from their probability-weighted mean (see
 * generatePaths): they add dispersion, not a shift of the stated expectation.
 */
export function regimeCondition(asset, anchor, regime, H) {
  if (asset.type === "cash" || asset.symbol === "CASH") return 0;
  const bond = anchor.bond;
  if (bond)
    return Math.log1p(bondScenarioAnnualReturn(bond, bondRegimeShift(bond, regime), H)) -
      Math.log1p(finite(bond.carry) ? bond.carry : 0) +
      // Realized inflation above or below the breakeven accrues to principal.
      (bond.inflationLinked ? Math.log1p(regime.inflationShift || 0) : 0);
  if (asset.symbol === "GLD") return -regime.rateShift * 0.5;
  const baseGrowth = anchor.forecast?.equivalentGrowth ?? 0;
  return Math.log(Math.max(0.01, 1 + baseGrowth + regime.earningsShift) / (1 + baseGrowth)) +
    Math.log1p(regime.multipleShift) / H;
}
/**
 * Scenario log-drift adjustments as the simulation applies them: annual
 * conditions accumulated over the horizon H, centered so the probability-
 * weighted terminal gross return of the scenarios is exactly one at H
 * (centering exp(c) instead of exp(H c) is exact only at one year).
 */
export function centeredRegimeConditions(asset, anchor, macro, H) {
  const raw = macro.map((row) => regimeCondition(asset, anchor, row, H));
  const mean = Math.log(macro.reduce((total, row, k) =>
    total + row.probability * Math.exp(H * raw[k]), 0)) / H;
  return raw.map((value) => value - mean);
}
export function jumpParameters(asset, anchor, options, regime) {
  if (asset.type === "cash" || asset.symbol === "CASH")
    return { mean: 0, vol: 0, compensator: 0 };
  const supplied = options.assetAssumptions?.[asset.symbol]?.jumpLoading;
  let jumpMean, jumpVol;
  if (anchor.bond) {
    // In a market jump, credit spreads widen with the fund's spread beta while
    // Treasury yields fall: credit is not a flight-to-quality asset.
    const bps = regime.rateJumpBps +
      (anchor.bond.inflationLinked ? 0 : (anchor.bond.spreadBeta || 0) * (regime.spreadJumpBps || 0));
    jumpMean = (-anchor.bond.duration * bps) / 1e4;
    jumpVol =
      Math.sign(jumpMean / (options.jumpMean || -0.12)) *
      ((anchor.bond.duration * Math.abs(bps)) / 1e4) *
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
  // Factorize the latent Gaussian covariance. Student-t marginal transforms
  // change linear correlations; innovationCovariance reports their initial
  // induced moments separately. Systematic exposure is never removed.
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
  // Probability-weighted scenario effect per instrument, removed so that the
  // anchor stays the expected return (uncentered scenarios cut the simulated
  // equity mean by about 6 pp and acted as an undeclared pessimistic prior).
  // Centered in terminal gross-return space: E[exp(H (condition - mean))] = 1.
  const centered = assets.map((a, i) => centeredRegimeConditions(a, anchors[i], macro, H));
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
    const regimeIndex = macro.indexOf(regime);
    const drift = mu.map((v, i) => {
      const condition = centered[i][regimeIndex];
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
    const longRun = inputs.horizonVariance?.longRunDaily;
    // Accepted GJR fits were estimated and screened with standardized
    // Student-t innovations; simulate that same marginal law. Fallback
    // instruments keep Gaussian innovations.
    const studentLaws = dynamic
      ? assets.map((a,i) => conditional.fits[i]?.nu ? studentMarginal(conditional.fits[i].nu) : null)
      : null;
    const shockScale = dynamic
      ? assets.map((a,i) => factorization
          ? Math.sqrt(factorization.loading[i]**2 + factorization.residualCovariance[i][i])
          : 1)
      : null;
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
            const innovation = studentLaws[i] && shockScale[i] > 0
              ? Math.sqrt(Math.max(0,h))*studentLaws[i](shock/shockScale[i])
              : factorization
                ? shock/Math.sqrt(252) *
                  (baseDailyVariances[i]>0
                    ? Math.sqrt(Math.max(0,h)/baseDailyVariances[i]) : 0)
                : Math.sqrt(Math.max(0,h))*shock;
            values[i] *= Math.exp(annualLogDrift[i]/252-h/2+innovation);
            variances[i] = conditional.fits[i]
              ? updateGjrVariance(conditional.fits[i],h,innovation)
              : Number.isFinite(longRun?.[i])
                ? updateTargetedVariance(h,innovation,longRun[i],options.lambda,inputs.horizonVariance.persistence)
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
    informationAsOf: options.informationAsOf || options.asOf || assets[0].price_date,
    scenarioCounts,
    riskFreeRate: finite(options.yieldCurve?.DGS3MO) ? options.yieldCurve.DGS3MO / 100 : null,
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
    flows = Array.from({length:steps+1},()=>[]);
  for (const row of schedule)
    flows[Math.min(steps, Math.max(1, Math.ceil(row.year / dt - 1e-8)))].push(row);
  const returns = [],
    terminalWealth = [],
    drawdowns = [],
    underwater = [],
    observations = options.details
      ? Array.from({ length: steps + 1 }, () => [])
      : null,
    samplePaths = [];
  // Alternative without market risk: the 3-month bill at the cut, held at
  // that rate over the horizon, or the declared cash yield if it pays more.
  const billRate = finite(sample.riskFreeRate) ? sample.riskFreeRate : null,
    cashRate = policy.cashYield || 0,
    alternativeRate = Math.max(billRate ?? 0, cashRate),
    alternativeGross = (1 + alternativeRate) ** policy.horizon;
  // Per-path utilities only on request: paired comparisons of candidates.
  const utilities = options.pathUtilities ? new Float64Array(paths) : null;
  let utility = 0,
    shortfalls = 0,
    losses = 0,
    failures = 0,
    goalSuccess = 0,
    floorBreaches = 0,
    recoveries = 0,
    unfinishedRecoveries = 0;
  const selected = weights.map((w, i) => ({ w, i })).filter((r) => r.w > 0),
    gamma = policy.riskAversion,
    distributions=distributionAccounting(sample),
    cashDividends=policy.dividendPolicy==="cash",
    withholding=policy.dividendWithholding || 0,
    cashStepGrowth=cashGrowth(policy.cashYield,dt),cashDepositGrowth=uniformCashGrowth(policy.cashYield,dt);
  let distributionGrossSum=0, distributionNetSum=0, reinvestedSum=0, withheldSum=0,
    receivableSum=0, paidGrossSum=0, cashInterestSum=0;
  for (let p = 0; p < paths; p++) {
    let previous = initial,
      cashWithdrawn = 0,
      nominalWithdrawn = 0,
      nav = initial / capital,
      peak = 1,
      worst = nav - 1,
      failed = false,
      floorBroken = initial * startFX < policy.capitalFloor,
      longest = 0,
      run = 0,
      everUnder = false,
      dividendsGross=0,
      dividendsNet=0,
      reinvested=0,
      withheld=0,uniformPaidPrincipal=0,paidCash=0;
    const uniformCash=new Float64Array(assets.length);
    const path = options.details && p < 12 ? [nav * 100] : null;
    if (observations) observations[0].push(nav * 100);
    for (let t = 1; t <= steps; t++) {
      const offset = p * (steps + 1) + t;
      let total = 0,uniformPrior=0,uniformStep=0;
      paidCash=0;
      for(const {w,i} of selected) {
        const view=distributions[i];
        if(view.dated){
          total+=w*(view.values[offset]+view.cash[offset])*initial;
          paidCash+=w*view.cash[offset]*initial;
        }else{
          const dist=view.factors,value=w*gross[i][offset]*initial;
          const net=value*dist.netCash[t];
          uniformPrior+=uniformCash[i];uniformStep+=net;uniformPaidPrincipal+=net;
          uniformCash[i]=uniformCash[i]*cashStepGrowth+net*cashDepositGrowth;
          total+=value*dist.marketValue[t]+uniformCash[i];
          paidCash+=uniformCash[i];
          dividendsGross+=value*dist.grossDistribution[t];
          reinvested+=value*dist.netReinvested[t];
          withheld+=value*dist.withheld[t];
        }
      }
      const priorWithdrawals=cashWithdrawn;
      cashWithdrawn*=cashStepGrowth;
      total-=cashWithdrawn;
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
      let withdrawal=0;
      const currentWithdrawals=[];
      for(const row of flows[t]){
        const u=Math.max(0,Math.min(steps,row.year/dt)),lo=Math.floor(u),hi=Math.min(steps,lo+1);
        const base=p*(steps+1),loFX=fx[base+lo],hiFX=fx[base+hi];
        const withdrawalFX=Math.exp(Math.log(loFX)+(Math.log(hiFX)-Math.log(loFX))*(u-lo));
        const due=row.amount/withdrawalFX;
        const elapsed=Math.max(0,Math.min(dt,row.year-(t-1)*dt));
        const datedCash=selected.reduce((s,{w,i})=>s+(distributions[i].dated
          ?w*initial*distributions[i].cashAt(p,row.year):0),0);
        const cashLevel=cashIndex>=0?Math.exp(Math.log(gross[cashIndex][base+lo])+
          (Math.log(gross[cashIndex][base+hi])-Math.log(gross[cashIndex][base+lo]))*(u-lo)):0;
        const previousInStep=currentWithdrawals.reduce((s,r)=>s+r.due*cashGrowth(policy.cashYield,row.year-r.year),0);
        const cash=(cashIndex>=0?weights[cashIndex]*cashLevel*initial:0)+
          uniformPrior*cashGrowth(policy.cashYield,elapsed)+uniformStep*uniformCashGrowth(policy.cashYield,elapsed,dt)+
          datedCash-priorWithdrawals*cashGrowth(policy.cashYield,elapsed)-previousInStep;
        if(cash+1e-8<due || total-withdrawal+1e-8<due)failed=true;
        const dueAtEnd=due*cashGrowth(policy.cashYield,t*dt-row.year);
        cashWithdrawn+=dueAtEnd;withdrawal+=dueAtEnd;nominalWithdrawn+=due;
        currentWithdrawals.push({year:row.year,due});
      }
      previous = Math.max(0, total-withdrawal);
      if (previous * currentFX < policy.capitalFloor) floorBroken = true;
      if (observations) observations[t].push(nav * 100);
      if (path) path.push(nav * 100);
    }
    let receivable=0,paidGross=cashDividends?dividendsGross:0;
    dividendsNet=uniformPaidPrincipal;
    for(const {w,i} of selected){
      const view=distributions[i];if(!view.dated)continue;
      dividendsGross+=w*initial*view.grossIncome[p];
      withheld+=w*initial*view.tax[p];reinvested+=w*initial*view.reinvested[p];
      receivable+=w*initial*view.receivables[p*(steps+1)+steps];
      if(cashDividends){paidGross+=w*initial*view.paidGross[p];dividendsNet+=w*initial*view.paidGross[p]*(1-withholding);}
    }
    receivableSum+=receivable;paidGrossSum+=paidGross;
    distributionGrossSum+=dividendsGross;
    distributionNetSum+=dividendsNet;
    reinvestedSum+=reinvested;
    withheldSum+=withheld;
    const initialCashInterest=cashIndex>=0?weights[cashIndex]*initial*(gross[cashIndex][p*(steps+1)+steps]-1):0;
    cashInterestSum+=initialCashInterest+paidCash-dividendsNet-(cashWithdrawn-nominalWithdrawn);
    const remaining = previous * fx[p * (steps + 1) + steps],
      ratio = nav;
    returns.push(ratio - 1);
    terminalWealth.push(remaining);
    drawdowns.push(worst);
    underwater.push(longest * dt);
    if (ratio < 1) losses++;
    if (ratio < alternativeGross) shortfalls++;
    if (failed) failures++;
    if (floorBroken) floorBreaches++;
    if (everUnder && run === 0) recoveries++;
    if (run > 0) unfinishedRecoveries++;
    if (remaining >= policy.terminalTarget && !failed) goalSuccess++;
    const safe = Math.max(1e-5, ratio);
    const pathUtility =
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
    utility += pathUtility;
    if (utilities) utilities[p] = pathUtility;
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
    ...(utilities ? { pathUtilities: utilities } : {}),
    certaintyEquivalent,
    dividendPolicy:policy.dividendPolicy,
    dividendWithholding:withholding,
    cashYield:policy.cashYield||0,
    expectedCashInterest:cashInterestSum/paths,
    expectedGrossDistributions:distributionGrossSum/paths,
    expectedNetDistributions:(distributionGrossSum-withheldSum)/paths,
    expectedDividendWithholding:withheldSum/paths,
    expectedNetReinvestedDividends:reinvestedSum/paths,
    expectedGrossDividendCash:paidGrossSum/paths,
    expectedDividendReceivable:receivableSum/paths,
    dividendTiming:selected.filter(({i})=>assets[i].type!=="cash").map(({i})=>({
      symbol:assets[i].symbol,mode:distributions[i].dated?"issuer-calendar":"uniform-estimate",
      source_url:distributions[i].calendar?.source_url||null,
      calendarObservedAt:distributions[i].calendar?.observed_at||null,
      events:distributions[i].calendar?.events.map(r=>({ex_date:r.ex_date,pay_date:r.pay_date,
        amount_per_share:r.amount_per_share,amount_basis:r.amount_basis}))||[],
      cappedEvents:distributions[i].capped||0,
    })),
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
    shortfallRate: alternativeRate > 0 ? alternativeRate : null,
    shortfallBasis: alternativeRate <= 0 ? null
      : billRate !== null && billRate >= cashRate ? "bill" : "cash",
    shortfallProbability: alternativeRate > 0 ? shortfalls / paths : null,
    shortfallProbabilitySE: alternativeRate > 0
      ? Math.sqrt((shortfalls / paths) * (1 - shortfalls / paths) / paths) : null,
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
