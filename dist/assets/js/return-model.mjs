import { finite, valuation, scenarios } from "./analytics.mjs";

const boundedReturn = (value) => Math.min(2, Math.max(-0.8, value));

export function buildReturnAnchors(assets, settings, overrides = {}) {
  return assets.map((asset) => {
    const assumptions = overrides[asset.symbol] || {};
    const model = valuation(asset, assumptions);
    const fundamental =
      settings.driftMode === "fundamental" && finite(model?.annualReturn);
    const reserve =
      settings.driftMode === "fundamental" &&
      asset.symbol === "SHY" &&
      finite(settings.reserveReturn);
    const annual = boundedReturn(
      reserve
        ? settings.reserveReturn
        : fundamental
          ? model.annualReturn
          : settings.manualReturn,
    );
    const range =
      fundamental && settings.uncertainFundamentals !== false
        ? scenarios(asset, assumptions)
            .map((s) => s.result?.annualReturn)
            .filter(finite)
            .map(boundedReturn)
        : [annual];
    return {
      symbol: asset.symbol,
      annual,
      mu: Math.log1p(annual),
      low: Math.min(annual, ...range),
      high: Math.max(annual, ...range),
      fundamental,
      source: reserve
        ? "Treasury 3M · continuidad supuesta"
        : fundamental
          ? "Valoración propia"
          : "Supuesto manual",
    };
  });
}

export function triangularQuantile(probability, low, mode, high) {
  if (high - low < 1e-12) return mode;
  const split = (mode - low) / (high - low);
  return probability < split
    ? low + Math.sqrt(probability * (high - low) * (mode - low))
    : high - Math.sqrt((1 - probability) * (high - low) * (high - mode));
}

// A shared scenario moves all fundamental anchors together. This explicit
// comonotonic assumption avoids treating fundamental uncertainty as independent.
export function sampleDrifts(anchors, settings, random) {
  const uncertainty =
    settings.driftMode === "fundamental" &&
    settings.uncertainFundamentals !== false;
  const scenario = uncertainty ? random() : 0.5;
  return anchors.map((anchor) =>
    Math.log1p(
      uncertainty
        ? triangularQuantile(scenario, anchor.low, anchor.annual, anchor.high)
        : anchor.annual,
    ),
  );
}
