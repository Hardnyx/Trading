import { finite, metrics, valuation, scenarios, resolveAssumptions, returnDecomposition } from "./analytics.mjs?v=0.18.0";
import { DEFAULT_RESEARCH } from "./policy.mjs?v=0.18.0";
import { dilutedEarningsBridge } from './earnings-normalization.mjs?v=0.18.0';
import { financialFreshness } from './financial-freshness.mjs?v=0.18.0';

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const years = (a, b) =>
  (Date.parse(b + "T12:00:00Z") - Date.parse(a + "T12:00:00Z")) /
  (365.25 * 86400000);
const samePeriod = (...rows) =>
  rows.every(
    (r) =>
      r?.period_end &&
      r.period_end === rows[0].period_end &&
      r.method === rows[0].method,
  );

// A price cutoff and an information cutoff can differ (e.g. a weekend release).
// Callers must record both. Records with an unknown publication date are not PIT evidence.
export function assetAt(
  asset,
  priceAsOf = asset.price_date,
  informationAsOf = priceAsOf,
) {
  const financials = {};
  for (const [key, row] of Object.entries(asset.financials || {})) {
    if (key === "history")
      financials.history = (row || []).filter(
        (r) =>
          r.filed &&
          r.filed <= informationAsOf &&
          r.period_end <= informationAsOf,
      );
    else if (!row || typeof row !== "object") financials[key] = row;
    else
      financials[key] =
        row.filed &&
        row.filed <= informationAsOf &&
        row.period_end <= informationAsOf
          ? row
          : null;
  }
  const history = (asset.history || []).filter((row) => row.date <= priceAsOf);
  const latest = history.at(-1);
  return {
    ...asset,
    financials,
    history,
    price:
      asset.price_date === priceAsOf
        ? asset.price
        : latest?.close || asset.price,
    price_date: latest?.date || asset.price_date,
    // Historical chart adjustments do not prove an original dividend vintage.
    dividend_per_share: asset.price_date<=informationAsOf
      ? asset.dividend_per_share : null,
    analyst_estimates:
      asset.analyst_estimates?.observed_at?.slice(0, 10) <= informationAsOf
        ? asset.analyst_estimates
        : null,
  };
}
export function validateResearch(input = {}) {
  const r = { ...DEFAULT_RESEARCH, ...input };
  if (!["own", "drivers", "consensus", "blend"].includes(r.basis))
    throw new Error("Base de previsión no válida.");
  if (!["reported", "continuing"].includes(r.earningsBasis))
    throw new Error("Base de beneficios no válida.");
  for (const [key, low, high] of [
    ["confidence", 0, 1],
    ["priorReturn", -0.8, 2],
    ["annualDilution", -0.5, 1],
    ["revenueGrowth", -0.8, 2],
    ["targetMargin", 0.0001, 1],
    ["marginFloor", -1, 1],
    ["leverageCeiling", -100, 100],
    ["epsFloor", -1000, 10000],
    ["cashConversionFloor", -100, 100],
    ["maxDilution", -1, 10],
    ["comparableEPS", 0.00001, 10000],
  ])
    if (r[key] != null && (!finite(r[key]) || r[key] < low || r[key] > high))
      throw new Error(`Revisa ${key} en la previsión.`);
  for (const key of ["thesis", "invalidation", "catalyst"])
    if (typeof r[key] !== "string" || r[key].length > 4000)
      throw new Error("Texto de tesis no válido.");
  if (
    r.reviewDate &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(r.reviewDate) ||
      !Number.isFinite(Date.parse(r.reviewDate)) ||
      new Date(r.reviewDate).toISOString().slice(0, 10) !== r.reviewDate)
  )
    throw new Error("Fecha de revisión no válida.");
  return r;
}
export function businessQuality(original, asOf = original.price_date) {
  const asset = assetAt(original, original.price_date, asOf),
    f = asset.financials || {},
    m = metrics(asset),
    ni = f.net_income?.value;
  const netMargin =
    samePeriod(f.net_income, f.revenue) && m.revenue > 0
      ? ni / m.revenue
      : null;
  const conversion =
    samePeriod(f.cfo, f.net_income) && ni > 0 ? m.cfo / ni : null;
  const reinvestment =
    samePeriod(f.capex, f.cfo) && m.cfo > 0 ? m.capex / m.cfo : null;
  const debtRows = [f.long_debt, f.current_debt];
  const debt =
    debtRows.every((r) => finite(r?.value)) &&
    debtRows[0].period_end === debtRows[1].period_end
      ? debtRows[0].value + debtRows[1].value
      : null;
  const netDebt =
    finite(debt) &&
    finite(m.cash) &&
    f.cash.period_end === debtRows[0].period_end
      ? debt - m.cash
      : null;
  const leverage =
    asset.sector !== "Financiero" && finite(netDebt) && m.fcf > 0
      ? netDebt / m.fcf
      : null;
  const marginHistory = (f.history || [])
    .filter((r) => finite(r.operating_margin))
    .map((r) => r.operating_margin)
    .sort((a, b) => a - b);
  const normalizedOperatingMargin = marginHistory.length
    ? marginHistory[Math.floor(marginHistory.length / 2)]
    : null;
  const history = (f.history || [])
    .filter((r) => r.shares > 0 && r.shares_split_adjusted === true)
    .sort((a, b) => a.period_end.localeCompare(b.period_end));
  const latest = history.at(-1),
    prior =
      latest &&
      history
        .filter(
          (r) =>
            years(r.period_end, latest.period_end) >= 0.85 &&
            years(r.period_end, latest.period_end) <= 1.15,
        )
        .at(-1);
  const dilution = prior ? latest.shares / prior.shares - 1 : null;
  const age = m.filed ? years(m.filed, asOf) * 365.25 : null;
  const coverage =
    [
      m.eps,
      m.revenue,
      m.operatingMargin,
      conversion,
      reinvestment,
      leverage,
      dilution,
    ].filter(finite).length / 7;
  const reliability =
    (m.eps > 0 ? 0.5 + 0.5 * coverage : 0) *
    (age === null ? 0.25 : Math.exp(-Math.max(0, age - 135) / 365));
  return {
    netMargin,
    normalizedOperatingMargin,
    operatingMargin: m.operatingMargin,
    cashConversion: conversion,
    reinvestment,
    netDebt,
    netDebtToFCF: leverage,
    dilution,
    sbcRevenue: m.sbcRevenue,
    coverage,
    reliability,
    ageDays: age,
    period: m.period,
    filed: m.filed,
    evidence: {
      operatingMargin: f.operating_income,
      netDebtToFCF: f.long_debt,
      eps: f.eps,
      cashConversion: f.cfo,
      dilution: latest,
    },
  };
}
export function evaluateThesis(
  original,
  research = {},
  asOf = original.price_date,
) {
  const r = validateResearch(research),
    asset = assetAt(original, original.price_date, asOf),
    quality = businessQuality(asset, asOf),
    m = metrics(asset);
  const observations = [
    [
      "marginFloor",
      "Margen operativo mínimo",
      quality.operatingMargin,
      "gte",
      "operatingMargin",
    ],
    [
      "leverageCeiling",
      "Deuda neta / FCF máxima",
      quality.netDebtToFCF,
      "lte",
      "netDebtToFCF",
    ],
    ["epsFloor", "BPA mínimo", m.eps, "gte", "eps"],
    [
      "cashConversionFloor",
      "Conversión CFO / beneficio mínima",
      quality.cashConversion,
      "gte",
      "cashConversion",
    ],
    [
      "maxDilution",
      "Dilución anual máxima",
      quality.dilution,
      "lte",
      "dilution",
    ],
  ]
    .filter(([key]) => finite(r[key]))
    .map(([key, label, value, comparison, evidence]) => ({
      key,
      label,
      value,
      threshold: r[key],
      comparison,
      status: !finite(value)
        ? "missing"
        : (comparison === "gte" ? value >= r[key] : value <= r[key])
          ? "supported"
          : "contradicted",
      period: quality.evidence[evidence]?.period_end || null,
      filed: quality.evidence[evidence]?.filed || null,
    }));
  return {
    quality,
    observations,
    status: observations.some((r) => r.status === "contradicted")
      ? "contradicted"
      : observations.some((r) => r.status === "missing")
        ? "insufficient"
        : observations.length
          ? "supported"
          : "unconfigured",
    overdue: !!r.reviewDate && r.reviewDate <= asOf,
    thesis: r.thesis,
    invalidation: r.invalidation,
    catalyst: r.catalyst,
    reviewDate: r.reviewDate,
  };
}
export function consensusAt(asset, targetDate, asOf, research) {
  const raw = asset.analyst_estimates;
  if (!raw?.observed_at || raw.observed_at.slice(0, 10) > asOf)
    return { error: "Sin consenso observado al corte" };
  if (!research.consensusComparable || !(research.comparableEPS > 0))
    return {
      error:
        "Confirma comparabilidad e ingresa un BPA actual de la misma base contable",
    };
  const rows = (raw.periods || [])
    .filter((r) => r.frequency === "annual" && r.eps_mean > 0)
    .sort((a, b) => a.period_end.localeCompare(b.period_end));
  const left = rows.filter((r) => r.period_end <= targetDate).at(-1),
    right = rows.find((r) => r.period_end >= targetDate);
  const basis = (row) =>
    ["gaap", "non_gaap"].includes(row?.eps_basis)
      ? row.eps_basis
      : research.consensusBasis;
  const compatible = (row) =>
    row &&
    (row.currency || research.consensusCurrency) === "USD" &&
    ["gaap", "non_gaap"].includes(basis(row)) &&
    (!research.consensusBasis || basis(row) === research.consensusBasis);
  if (
    !compatible(left || right) ||
    (left && right && (!compatible(right) || basis(left) !== basis(right)))
  )
    return {
      error:
        "Moneda o base contable del consenso sin confirmar o incompatibles",
    };
  let chosen = left || right;
  if (left && right && left !== right) {
    const fraction =
      years(left.period_end, targetDate) /
      years(left.period_end, right.period_end);
    const interpolate = (key) =>
      left[key] > 0 && right[key] > 0
        ? Math.exp(
            Math.log(left[key]) * (1 - fraction) +
              Math.log(right[key]) * fraction,
          )
        : null;
    chosen = {
      ...left,
      period_end: targetDate,
      eps_mean: interpolate("eps_mean"),
      eps_low: interpolate("eps_low"),
      eps_high: interpolate("eps_high"),
      interpolated: true,
    };
  } else if (!chosen || Math.abs(years(targetDate, chosen.period_end)) > 0.35)
    return { error: "Sin consenso anual próximo al horizonte de valoración" };
  return {
    ...chosen,
    observed_at: raw.observed_at,
    source: raw.provider || "Consenso",
    basis: basis(chosen),
  };
}
export function fundamentalForecast(
  original,
  assumptions = {},
  research = {},
  context = {},
) {
  let r;
  try {
    r = validateResearch(research);
  } catch (error) {
    return { valid: false, error: error.message };
  }
  const asOf = context.asOf || original.price_date,
    asset = assetAt(original, context.priceAsOf || original.price_date, asOf),
    a = { ...asset.assumptions, ...assumptions };
  const quality = businessQuality(asset, asOf),
    thesis = evaluateThesis(asset, r, asOf),
    horizon = a.horizon,
    base = metrics(asset).eps,
    warnings = [];
  const earningsBridge = dilutedEarningsBridge(asset, asOf);
  const freshness=financialFreshness(original,asOf);
  if(['newer_report','split_basis_unverified'].includes(freshness.status))return {valid:false,error:freshness.reason,quality,thesis,freshness};
  if (!finite(horizon) || horizon < 1 || horizon > 10)
    return {
      valid: false,
      error: "El horizonte de valoración debe estar entre 1 y 10 años",
      quality,
      thesis,
    };
  let adjustedAsset = asset,
    growth = a.growth;
  if (r.earningsBasis === 'continuing') {
    if (r.basis !== 'own') return {valid:false,error:'El BPA continuado requiere previsión propia; ventas/márgenes y consenso necesitan otra conciliación contable',quality,thesis,earningsBridge};
    if (!earningsBridge.available || !(earningsBridge.continuing>0))
      return {valid:false,error:'BPA continuado positivo sin conciliar: '+earningsBridge.reason,quality,thesis,earningsBridge};
    adjustedAsset={...asset,financials:{...asset.financials,eps:{...asset.financials.eps,value:earningsBridge.continuing}}};
    warnings.push('BPA de operaciones continuadas: no acredita beneficios recurrentes ni normalización del ciclo');
  }
  if (
    ["blend", "consensus"].includes(r.basis) &&
    r.consensusComparable &&
    r.comparableEPS > 0
  )
    adjustedAsset = {
      ...asset,
      financials: {
        ...asset.financials,
        eps: { ...asset.financials?.eps, value: r.comparableEPS },
      },
    };
  if (r.basis === "drivers") {
    if (
      !finite(r.revenueGrowth) ||
      !(quality.netMargin > 0) ||
      !(r.targetMargin > 0)
    )
      return {
        valid: false,
        error: "Faltan crecimiento de ventas y márgenes netos comparables",
        quality,
        thesis,
      };
    growth =
      ((1 + r.revenueGrowth) *
        (r.targetMargin / quality.netMargin) ** (1 / horizon)) /
        (1 + r.annualDilution) -
      1;
  }
  // The default sector multiple is a reference reached only partially; an
  // explicit user multiple is honored as given.
  const exit = resolveAssumptions(adjustedAsset, assumptions),
    referenceMultiple = a.multiple;
  a.multiple = exit.multiple;
  const own = valuation(adjustedAsset, { ...a, growth });
  if (!own)
    return {
      valid: false,
      error: "Sin BPA publicado positivo y supuestos comparables al corte",
      quality,
      thesis,
    };
  const targetDate = new Date(
    Date.parse(asOf + "T12:00:00Z") + horizon * 365.25 * 86400000,
  )
    .toISOString()
    .slice(0, 10);
  const consensus = consensusAt(asset, targetDate, asOf, r);
  let forecastEPS = own.futureBase,
    source =
      r.basis === "drivers"
        ? "Ventas, margen neto y dilución propios"
        : r.earningsBasis === "continuing" ? "BPA continuado conciliado y múltiplo propios" : "BPA y múltiplo propios";
  if (["consensus", "blend"].includes(r.basis)) {
    if (consensus.error && r.basis === "consensus")
      return {
        valid: false,
        error: consensus.error,
        quality,
        thesis,
        consensus,
      };
    if (consensus.error)
      warnings.push(consensus.error + "; se usa la previsión propia");
    else {
      forecastEPS =
        r.basis === "consensus"
          ? consensus.eps_mean
          : (own.futureBase + consensus.eps_mean) / 2;
      source =
        r.basis === "consensus"
          ? "Consenso comparable / múltiplo propio"
          : "50% propia / 50% consenso comparable";
    }
  }
  const comparableBase = adjustedAsset.financials?.eps?.value || base,
    equivalentGrowth = (forecastEPS / comparableBase) ** (1 / horizon) - 1;
  const model = valuation(adjustedAsset, { ...a, growth: equivalentGrowth });
  if (!model || !finite(model.annualReturn))
    return {
      valid: false,
      error: "La previsión produce valores no válidos",
      quality,
      thesis,
    };
  const confidence =
      r.confidence *
      quality.reliability *
      (thesis.status === "contradicted" ? 0.25 : 1),
    prior = r.priorReturn;
  const central = clamp(
      thesis.status === "contradicted"
        ? Math.min(
            prior,
            model.annualReturn,
            prior + confidence * (model.annualReturn - prior),
          )
        : prior + confidence * (model.annualReturn - prior),
      -0.85,
      2,
    ),
    cases = scenarios(adjustedAsset, { ...a, growth: equivalentGrowth }),
    dispersion = 2 - confidence;
  // Symmetric accounting sensitivity avoids moving the mode by treating a
  // favorable normalization as certain. This is not a calibrated error band.
  let accountingSensitivity = 0;
  if (r.basis === 'own' && earningsBridge.available && earningsBridge.reported>0 && earningsBridge.continuing>0) {
    const alternativeEPS=r.earningsBasis==='continuing'?earningsBridge.reported:earningsBridge.continuing;
    const alternative=valuation({...asset,financials:{...asset.financials,eps:{...asset.financials.eps,value:alternativeEPS}}},{...a,growth});
    if (alternative && finite(alternative.annualReturn)) accountingSensitivity=Math.abs(alternative.annualReturn-model.annualReturn);
  }
  // Re-rating is uncertainty, not expectation: no reversion and full
  // convergence to the sector reference bound the band.
  let reratingLow = 0, reratingHigh = 0;
  if (exit.rerating.applied) {
    const bounds = [exit.rerating.current, exit.rerating.reference].map((multiple) =>
      valuation(adjustedAsset, { ...a, growth: equivalentGrowth, multiple })?.annualReturn);
    if (bounds.every(finite)) {
      reratingLow = Math.min(0, Math.min(...bounds) - model.annualReturn) * dispersion;
      reratingHigh = Math.max(0, Math.max(...bounds) - model.annualReturn) * dispersion;
    }
  }
  const low = clamp(
    Math.min(
      central - accountingSensitivity,
      central + reratingLow,
      central +
        (cases[0].result.annualReturn - model.annualReturn) * dispersion,
    ),
    -0.85,
    2,
  );
  const high = clamp(
    Math.max(
      central + accountingSensitivity,
      central + reratingHigh,
      central +
        (cases[2].result.annualReturn - model.annualReturn) * dispersion,
    ),
    -0.85,
    2,
  );
  let pvDividends = 0;
  for (let t = 1; t <= horizon; t++)
    pvDividends += (asset.dividend_per_share || 0) / (1 + a.discount) ** t;
  const neededEPS =
    ((asset.price - pvDividends) * (1 + a.discount) ** horizon) / referenceMultiple;
  const impliedGrowth =
    neededEPS > 0 ? (neededEPS / comparableBase) ** (1 / horizon) - 1 : null;
  if (quality.ageDays > 180)
    warnings.push("Fundamentos con más de 180 días desde su presentación");
  return {
    valid: true,
    model,
    quality,
    thesis,
    source,
    warnings,
    consensus,
    forecastEPS,
    targetDate,
    earningsBridge,
    earningsBasis: r.earningsBasis,
    accountingSensitivity,
    effectiveBaseEPS: comparableBase,
    ownEPS: own.futureBase,
    ownAnnualReturn: own.annualReturn,
    confidence,
    prior,
    central,
    low,
    high,
    impliedGrowth,
    equivalentGrowth,
    assumptions: { ...a, growth: equivalentGrowth },
    rerating: exit.rerating,
    decomposition: returnDecomposition(model, comparableBase, asset.price),
    research: r,
  };
}
export const INITIAL_BOND_PROFILES = {
  SHY: {
    duration: 1.78871,
    yieldToMaturity: 0.0464,
    expenseRatio: 0.0015,
    date: "2026-10-22",
    source_url:
      "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf",
  },
  TLT: {
    duration: 14.96103,
    yieldToMaturity: 0.0535,
    expenseRatio: 0.0015,
    date: "2026-10-22",
    source_url:
      "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
  },
};
export function bondAssumptions(asset, settings = {}) {
  const supplied = settings.assetAssumptions?.[asset.symbol] || {},
    profile = asset.bond_profile || INITIAL_BOND_PROFILES[asset.symbol],
    asOf = settings.informationAsOf || settings.asOf || asset.price_date;
  const usable = profile && profile.date <= asOf ? profile : null,
    curve = settings.yieldCurve || {},
    proxy = asset.symbol === "SHY" ? curve.DGS2 : curve.DGS30;
  const stale = usable && years(usable.date, asOf) * 365.25 > 45;
  const yieldRate = finite(supplied.yieldToMaturity)
    ? supplied.yieldToMaturity
    : finite(proxy) && (!usable || stale)
      ? proxy / 100
      : usable?.yieldToMaturity;
  const duration = finite(supplied.duration)
      ? supplied.duration
      : usable?.duration,
    expense = finite(supplied.expenseRatio)
      ? supplied.expenseRatio
      : usable?.expenseRatio;
  if (
    !finite(yieldRate) ||
    yieldRate < -0.05 ||
    yieldRate > 1 ||
    !finite(duration) ||
    duration < 0 ||
    duration > 40 ||
    !finite(expense) ||
    expense < 0 ||
    expense > 0.1
  )
    return null;
  return {
    yieldToMaturity: yieldRate,
    duration,
    expenseRatio: expense,
    carry: yieldRate - expense,
    date: usable?.date || null,
    source: finite(supplied.yieldToMaturity)
      ? "TIR y duración ingresadas"
      : finite(proxy) && (!usable || stale)
        ? "Curva Treasury próxima / duración del perfil"
        : "iShares: TIR bruta menos gastos",
    stale: !!stale,
    source_url: usable?.source_url || null,
  };
}
