import { finite } from "./analytics.mjs?v=0.24.0";
import { fundamentalForecast, bondAssumptions, assetAt } from "./research-model.mjs?v=0.24.0";
import { DEFAULT_RESEARCH } from "./policy.mjs?v=0.24.0";
import { normalCDF, normalGenerator } from "./random.mjs?v=0.24.0";

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
export const HOLDINGS_MAX_AGE_DAYS = 120;
export const HOLDINGS_UNCOVERED_BAND = 0.15;

/** Memoized fundamental anchors of the universe's stocks for one context. */
export function constituentForecasts(universe = [], settings = {}, overrides = {}) {
  const bySymbol = new Map(universe.map((asset) => [asset.symbol, asset]));
  const memo = new Map();
  const priceAsOf = settings.asOf, info = settings.informationAsOf || settings.asOf;
  return (symbol) => {
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
  const h = asset.holdings, info = settings.informationAsOf || settings.asOf;
  if (asset.type !== "etf" || !h?.as_of || !Array.isArray(h.positions) || !info ||
      h.as_of > info) return null;
  const age = (Date.parse(info + "T12:00:00Z") - Date.parse(h.as_of + "T12:00:00Z")) / 86400000;
  if (!(age <= HOLDINGS_MAX_AGE_DAYS)) return null;
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
    coverage: share, constituents: count, holdingsAsOf: h.as_of,
    source: `Holdings al ${h.as_of}: ${Math.round(share * 100)}% del peso con ancla propia de ${count} acciones; resto con prior ${(prior * 100).toFixed(0)}% ±${HOLDINGS_UNCOVERED_BAND * 100} pp; gastos del fondo no descontados`,
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
      annual = forecast.central;
      low = forecast.low;
      high = forecast.high;
      source = forecast.source;
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
