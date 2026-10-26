import { finite } from "./analytics.mjs?v=0.8.3";
import { fundamentalForecast, bondAssumptions } from "./research-model.mjs?v=0.8.3";
import { normalCDF, normalGenerator } from "./random.mjs?v=0.8.3";

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

const bounded = (x) => Math.max(-0.85, Math.min(2, x));
export function buildReturnAnchors(assets, settings = {}, overrides = {}) {
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
    let annual,
      low,
      high,
      source,
      fundamental = false;
    if (asset.type === "cash") {
      annual = 0;
      low = 0;
      high = 0;
      source = "Efectivo USD sin remuneración supuesta";
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
      distributionMean: (low + annual + high) / 3,
      fundamental,
      source,
      forecast,
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
        ? triangularQuantile(
            Math.max(0, Math.min(1, normalCDF(z))),
            anchor.low,
            anchor.annual,
            anchor.high,
          )
        : anchor.annual,
    );
  });
}
