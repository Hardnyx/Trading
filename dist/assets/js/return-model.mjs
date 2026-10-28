import { finite } from "./analytics.mjs?v=0.28.0";
import { fundamentalForecast, bondAssumptions, assetAt } from "./research-model.mjs?v=0.28.0";
import { DEFAULT_RESEARCH } from "./policy.mjs?v=0.28.0";
import { normalCDF, normalGenerator } from "./random.mjs?v=0.28.0";
import { actualHoldings } from "./economic-exposure.mjs?v=0.28.0";

/**
 * Annualized scenario return for a bond ETF under a parallel yield change.
 * First-order duration + a transparent zero-coupon convexity proxy.
 * This is an approximate TOTAL return, not a guaranteed carry or full curve
 * / reinvestment model. Rate shift is added ONCE in the stochastic paths.
 */
export function bondScenarioAnnualReturn(bond, yieldShift = 0, horizon = 1) {
  if (!bond || !(horizon > 0) || !finite(yieldShift))
    throw new Error("Escenario de bono inválido");
  const d = bond.duration;
  const carry = finite(bond.carry) ? bond.carry : 0;
  const convexityProxy = d * (d + 1);
  const priceMultiplier = Math.max(0.01,
    1 - d * yieldShift + 0.5 * convexityProxy * yieldShift ** 2);
  return Math.expm1(Math.log1p(carry) +
    Math.log(priceMultiplier) / horizon);
}

/** Yield change a bond fund faces in a scenario: rates plus its spread share. */
export function bondRegimeShift(bond, regime) {
  return (regime?.rateShift || 0) + (bond?.spreadBeta || 0) * (regime?.spreadShift || 0);
}
const bounded = (x) => Math.max(-0.85, Math.min(2, x));
// Operational thresholds for building an equity ETF anchor from its dated
// holdings. They are stated rules, not estimates: below them the fund stays
// under observation.
export const HOLDINGS_ANCHOR_MIN_COVERAGE = 0.70;
export const HOLDINGS_UNCOVERED_BAND = 0.15;

// Cross-sectional refinement of stock anchors (Grinold-Kahn): a building-block
// return is a signal, not an expected return. Its cross-section is rescaled to
// alpha = IC x residual volatility x score around a CAPM equilibrium, so the
// spread between stocks is the one a stated skill level can support. IC is a
// declared convention (0.05 is what a good active manager attains), not an
// estimate: there is no out-of-sample forecast error yet.
export const ALPHA_INFORMATION_COEFFICIENT = 0.05;
export const BLUME_BETA_WEIGHT = 2 / 3;
export const ALPHA_WINDOW = 500;
export const ALPHA_MIN_OBSERVATIONS = 250;
export const ALPHA_SCORE_LIMIT = 3;
const ALPHA_MIN_STOCKS = 20;
const contexts = new WeakMap();

function returnsByDate(asset, asOf, window) {
  const rows = (asset.history || []).filter((row) => row.date <= asOf && row.adj_close > 0)
    .slice(-(window + 1));
  return new Map(rows.slice(1).map((row, i) => [row.date, Math.log(row.adj_close / rows[i].adj_close)]));
}

/** Beta to the benchmark and annualized residual volatility from daily returns. */
export function marketExposure(asset, benchmark, asOf, window = ALPHA_WINDOW) {
  const own = returnsByDate(asset, asOf, window);
  const pairs = [...returnsByDate(benchmark, asOf, window)]
    .filter(([date]) => own.has(date)).map(([date, m]) => [own.get(date), m]);
  if (pairs.length < ALPHA_MIN_OBSERVATIONS) return null;
  const n = pairs.length,
    mx = pairs.reduce((s, [x]) => s + x, 0) / n,
    mm = pairs.reduce((s, [, m]) => s + m, 0) / n,
    vm = pairs.reduce((s, [, m]) => s + (m - mm) ** 2, 0) / n;
  if (!(vm > 0)) return null;
  const beta = pairs.reduce((s, [x, m]) => s + (x - mx) * (m - mm), 0) / n / vm;
  const residual = pairs.reduce((s, [x, m]) => s + (x - mx - beta * (m - mm)) ** 2, 0) / n;
  return { beta, omega: Math.sqrt(residual * 252), observations: n };
}

/**
 * Equilibrium plus benchmark-neutral alpha for every stock with a valid
 * forecast. The covered benchmark weight keeps its building-block mean, so
 * index composites do not move; only the spread between stocks shrinks or
 * widens. Null when the benchmark, its holdings or the short rate are missing.
 */
export function crossSectionalRefinement(universe, settings, lookup) {
  if (settings.driftMode === "manual") return null;
  const benchmark = universe.find((a) => a.symbol === (settings.mandate?.benchmark || "SPY"));
  const rate = settings.yieldCurve?.DGS3MO, asOf = settings.asOf;
  if (!benchmark || !finite(rate) || !asOf) return null;
  const supplied = settings.informationCoefficient;
  const ic = finite(supplied) && supplied >= 0 && supplied <= 0.2 ? supplied : ALPHA_INFORMATION_COEFFICIENT;
  const rows = [];
  for (const asset of universe) {
    if (asset.type !== "stock") continue;
    const forecast = lookup(asset.symbol);
    const exposure = forecast && marketExposure(asset, benchmark, asOf);
    if (exposure && finite(forecast.model?.annualReturn))
      rows.push({ symbol: asset.symbol, forecast, ...exposure });
  }
  if (rows.length < ALPHA_MIN_STOCKS) return null;
  const signal = rows.map((r) => r.forecast.model.annualReturn),
    centre = signal.reduce((s, v) => s + v, 0) / rows.length,
    spread = Math.sqrt(signal.reduce((s, v) => s + (v - centre) ** 2, 0) / rows.length);
  if (!(spread > 0)) return null;
  for (const [k, r] of rows.entries()) {
    r.score = Math.max(-ALPHA_SCORE_LIMIT, Math.min(ALPHA_SCORE_LIMIT, (signal[k] - centre) / spread));
    // Lower assigned confidence (data quality, user research) lowers skill.
    r.ic = ic * r.forecast.confidence / DEFAULT_RESEARCH.confidence;
    r.alpha = r.ic * r.omega * r.score;
    r.adjustedBeta = BLUME_BETA_WEIGHT * r.beta + (1 - BLUME_BETA_WEIGHT);
  }
  const bySymbol = new Map(rows.map((r) => [r.symbol, r]));
  let weight = 0, alpha = 0, beta = 0, market = 0;
  const holdings = actualHoldings(benchmark, settings.informationAsOf || asOf, settings.informationAsOf || asOf);
  for (const position of holdings?.positions || []) {
    const r = bySymbol.get(position.symbol), w = position.weight;
    if (!r || !(w > 0)) continue;
    weight += w; alpha += w * r.alpha; beta += w * r.adjustedBeta; market += w * r.forecast.central;
  }
  if (!(weight > 0) || !(beta > 0)) return null;
  const riskFree = rate / 100, marketReturn = market / weight,
    benchmarkAlpha = alpha / weight, benchmarkBeta = beta / weight;
  const result = new Map();
  for (const r of rows) {
    const scaledBeta = r.adjustedBeta / benchmarkBeta,
      neutralAlpha = r.alpha - scaledBeta * benchmarkAlpha,
      equilibrium = riskFree + scaledBeta * (marketReturn - riskFree),
      anchor = equilibrium + neutralAlpha;
    result.set(r.symbol, {
      method: "capm-equilibrium-plus-grinold-kahn-alpha",
      benchmark: benchmark.symbol, riskFree, marketReturn, coveredWeight: weight,
      beta: scaledBeta, rawBeta: r.beta, omega: r.omega, observations: r.observations,
      score: r.score, ic: r.ic, alpha: neutralAlpha, equilibrium, anchor,
      buildingBlock: r.forecast.central, shift: anchor - r.forecast.central,
    });
  }
  return result;
}

function forecastContext(universe, settings, overrides) {
  const key = JSON.stringify([settings.asOf, settings.informationAsOf, settings.research || {},
    overrides, settings.yieldCurve?.DGS3MO ?? null, settings.informationCoefficient ?? null,
    settings.mandate?.benchmark ?? null, settings.driftMode ?? null]);
  let byKey = contexts.get(universe);
  if (!byKey) contexts.set(universe, byKey = new Map());
  if (!byKey.has(key)) {
    if (byKey.size >= 8) byKey.delete(byKey.keys().next().value);
    byKey.set(key, { forecasts: new Map(), refinement: undefined });
  }
  return byKey.get(key);
}

/**
 * Memoized fundamental anchors of the universe's stocks for one context,
 * after the cross-sectional refinement when it is available.
 */
export function constituentForecasts(universe = [], settings = {}, overrides = {}) {
  const bySymbol = new Map(universe.map((asset) => [asset.symbol, asset]));
  const context = forecastContext(universe, settings, overrides);
  const memo = context.forecasts;
  const priceAsOf = settings.asOf, info = settings.informationAsOf || settings.asOf;
  const raw = (symbol) => {
    if (!memo.has(symbol)) {
      const original = bySymbol.get(symbol);
      let forecast = null;
      if (original?.type === "stock" && priceAsOf) {
        const asset = assetAt(original, priceAsOf, info);
        const f = asset.price_date === priceAsOf
          ? fundamentalForecast(asset, overrides[symbol] || {},
              settings.research?.[symbol] || {}, { asOf: info, priceAsOf })
          : null;
        forecast = f?.valid && f.thesis?.status !== "contradicted" ? f : null;
      }
      memo.set(symbol, forecast);
    }
    return memo.get(symbol);
  };
  if (context.refinement === undefined)
    context.refinement = crossSectionalRefinement(universe, settings, raw);
  const refinement = context.refinement;
  const lookup = (symbol) => {
    const f = raw(symbol), r = refinement?.get(symbol);
    return f && r ? { ...f, central: f.central + r.shift, low: f.low + r.shift,
      high: f.high + r.shift, refinement: r } : f;
  };
  lookup.refinement = refinement;
  return lookup;
}

/**
 * Building-block anchor for an equity ETF from dated holdings: covered weight
 * takes the constituents' own anchors (same assumptions, overrides and
 * partial re-rating); the uncovered remainder takes the common prior with a
 * wide band. Bounds weight the constituents' extremes (perfectly correlated
 * errors: conservative). Expense ratios are not in the snapshot and are not
 * deducted.
 */
export function holdingsAnchor(asset, lookup, settings = {}) {
  const info = settings.informationAsOf || settings.asOf;
  // Same temporal and structural validation as the exposure report: dated,
  // first observed by the information cut, no duplicates, bounded weights.
  const h = asset.type === "etf" && info ? actualHoldings(asset, info, info) : null;
  if (!h) return null;
  let covered = 0, mode = 0, low = 0, high = 0, count = 0;
  for (const position of h.positions) {
    const w = position.weight;
    if (!(w > 0) || position.symbol === asset.symbol) continue;
    const f = lookup(position.symbol);
    if (!f) continue;
    covered += w; mode += w * f.central; low += w * f.low; high += w * f.high; count++;
  }
  if (!(covered >= HOLDINGS_ANCHOR_MIN_COVERAGE) || covered > 1.05) return null;
  const share = Math.min(1, covered), rest = 1 - share,
    prior = settings.research?.[asset.symbol]?.priorReturn ?? DEFAULT_RESEARCH.priorReturn;
  return {
    annual: (mode / covered) * share + prior * rest,
    low: (low / covered) * share + (prior - HOLDINGS_UNCOVERED_BAND) * rest,
    high: (high / covered) * share + (prior + HOLDINGS_UNCOVERED_BAND) * rest,
    coverage: share, constituents: count, holdingsAsOf: h.asOf,
    source: `Holdings al ${h.asOf}: ${Math.round(share * 100)}% del peso con ancla propia de ${count} acciones; resto con prior ${(prior * 100).toFixed(0)}% ±${HOLDINGS_UNCOVERED_BAND * 100} pp; gastos del fondo no descontados`,
  };
}

export function buildReturnAnchors(assets, settings = {}, overrides = {}, universe = assets) {
  const lookup = constituentForecasts(universe, settings, overrides);
  return assets.map((asset) => {
    const research = settings.research?.[asset.symbol] || {},
      bond = bondAssumptions(asset, settings);
    const forecast =
      asset.type === "stock"
        ? fundamentalForecast(asset, overrides[asset.symbol] || {}, research, {
            asOf: settings.informationAsOf || settings.asOf || asset.price_date,
            priceAsOf: settings.asOf || asset.price_date,
          })
        : null;
    let holdings = null,
      refinement = null,
      annual,
      low,
      high,
      source,
      fundamental = false;
    if (asset.type === "cash") {
      // Declared account yield, net of fees: a contractual rate, not a forecast.
      const declared = settings.mandate?.cashYield ?? 0;
      annual = declared;
      low = declared;
      high = declared;
      source = declared > 0
        ? `Efectivo USD remunerado al ${(declared * 100).toFixed(2)}% neto declarado en el mandato; sin riesgo de tasa modelado`
        : "Efectivo USD sin remuneración (0% declarado en el mandato)";
    } else if (bond) {
      annual = bond.carry;
      low = annual;
      high = annual;
      source = bond.source;
    } else if (asset.type === "etf" &&
               asset.symbol === settings.mandate?.benchmark &&
               settings.assetAssumptions?.[asset.symbol]?.benchmarkOnlyProxy) {
      const proxy = settings.assetAssumptions[asset.symbol];
      annual = proxy.expectedReturn;
      low = annual - proxy.uncertainty;
      high = annual + proxy.uncertainty;
      source = "Índice comparador exclusivamente: prima supuesta 3,5 pp sobre tasa corta; sin calibrar ni habilitar compras";
    } else if (settings.driftMode !== "manual" && forecast?.valid) {
      refinement = forecast.thesis?.status !== "contradicted"
        ? lookup.refinement?.get(asset.symbol) ?? null : null;
      const shift = refinement?.shift ?? 0;
      annual = forecast.central + shift;
      low = forecast.low + shift;
      high = forecast.high + shift;
      source = forecast.source + (refinement
        ? ` · ancla transversal: equilibrio CAPM ${(refinement.equilibrium * 100).toFixed(1)}% + alfa ${(refinement.alpha * 100).toFixed(1)} pp (IC ${refinement.ic.toFixed(3)})`
        : "");
      fundamental = true;
    } else if (settings.driftMode !== "manual" && asset.type === "etf" &&
               !finite(settings.assetAssumptions?.[asset.symbol]?.expectedReturn) &&
               (holdings = holdingsAnchor(asset, lookup, settings))) {
      ({ annual, low, high, source } = holdings);
      fundamental = true;
    } else {
      const own = settings.assetAssumptions?.[asset.symbol] || {};
      annual = finite(own.expectedReturn)
        ? own.expectedReturn
        : (settings.manualReturn ?? 0.06);
      const dispersion = finite(own.uncertainty)
        ? own.uncertainty
        : settings.driftMode === "manual"
          ? 0
          : 0.06;
      low = annual - dispersion;
      high = annual + dispersion;
      source =
        asset.type === "stock"
          ? "Supuesto manual; sin previsión fundamental válida"
          : "Retorno y rango asumidos del ETF";
    }
    if (![annual, low, high].every(finite))
      throw new Error(`Ancla inválida para ${asset.symbol}.`);
    annual = bounded(annual);
    low = Math.min(annual, bounded(low));
    high = Math.max(annual, bounded(high));
    return {
      symbol: asset.symbol,
      sector: asset.sector,
      kind: asset.type,
      bond,
      annual,
      mu: Math.log1p(annual),
      low,
      high,
      // Drifts are sampled with this mean (centered triangular law).
      distributionMean: annual,
      fundamental,
      source,
      forecast,
      holdingsCoverage: holdings?.coverage ?? null,
      refinement,
      confidence: forecast?.confidence ?? null,
    };
  });
}
export function triangularQuantile(p, low, mode, high) {
  if (
    ![p, low, mode, high].every(finite) ||
    p < 0 ||
    p > 1 ||
    low > mode ||
    mode > high
  )
    throw new Error("Distribución triangular no válida.");
  if (high - low < 1e-12) return mode;
  const split = (mode - low) / (high - low);
  return p < split
    ? low + Math.sqrt(p * (high - low) * (mode - low))
    : high - Math.sqrt((1 - p) * (high - low) * (high - mode));
}
/**
 * Quantile of a triangular law on [low, high] whose MEAN is the anchor (the
 * stated expectation, §3 of the technical document). A mode equal to the
 * anchor shifted the mean toward the longer tail: about -2 pp for equities.
 */
export function centeredTriangularQuantile(p, low, anchor, high) {
  if (high - low < 1e-12) return anchor;
  const mode = Math.max(low, Math.min(high, 3 * anchor - low - high));
  return triangularQuantile(p, low, mode, high) + (anchor - (low + mode + high) / 3);
}
export function sampleDrifts(
  anchors,
  settings,
  random,
  normal = normalGenerator(random),
) {
  const uncertain = settings.uncertainFundamentals !== false,
    marketShare = settings.fundamentalMarketShare ?? 0.35,
    sectorShare = settings.fundamentalSectorShare ?? 0.3;
  if (
    !finite(marketShare) ||
    !finite(sectorShare) ||
    marketShare < 0 ||
    sectorShare < 0 ||
    marketShare + sectorShare > 1
  )
    throw new Error(
      "Las participaciones de incertidumbre de mercado y sector deben sumar hasta 100%.",
    );
  const market = normal(),
    sectors = new Map();
  return anchors.map((anchor) => {
    if (!sectors.has(anchor.sector)) sectors.set(anchor.sector, normal());
    const z =
      Math.sqrt(marketShare) * market +
      Math.sqrt(sectorShare) * sectors.get(anchor.sector) +
      Math.sqrt(1 - marketShare - sectorShare) * normal();
    return Math.log1p(
      uncertain
        ? centeredTriangularQuantile(
            Math.max(0, Math.min(1, normalCDF(z))),
            anchor.low,
            anchor.annual,
            anchor.high,
          )
        : anchor.annual,
    );
  });
}
