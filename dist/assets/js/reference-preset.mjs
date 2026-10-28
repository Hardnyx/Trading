import { DEFAULT_MANDATE, DEFAULT_EXECUTION, DEFAULT_REGIMES,
  informationDate } from "./policy.mjs?v=0.33.0";
import { DEFAULT_COMPOSITION_RULES } from "./composer.mjs?v=0.33.0";

// Canonical comparison: no account, holdings, localStorage or user overrides.
// Used by the actual web worker AND continuous integration.
export const REFERENCE_ID = "default-20261024-4-regimes-v2";
export function referenceRequest(snapshot) {
  return {
    settings: {
      model: "merton", horizon: 1, paths: 3000, seed: 20261024,
      driftMode: "fundamental", manualReturn: 0.06, lambda: 0.94,
      jumpIntensity: 0.35, jumpMean: -0.12, jumpVol: 0.08,
      uncertainFundamentals: true, volatilityMode: "hybrid",
      asOf: snapshot.price_as_of,
      informationAsOf: informationDate(snapshot),
      mandate: structuredClone(DEFAULT_MANDATE),
      execution: structuredClone(DEFAULT_EXECUTION),
      macroRegimes: structuredClone(DEFAULT_REGIMES),
      capital: 100000, research: {}, assetAssumptions: {},
      account: { enabled: false, cash: 0, positions: [] },
      baseline: null, volatilityData: snapshot.volatility || null,
      yieldCurve: Object.fromEntries(
        (snapshot.macro || []).map(r => [r.id, r.value])),
    },
    overrides: {},
    rules: structuredClone(DEFAULT_COMPOSITION_RULES),
  };
}

export function resultFingerprint(proposal) {
  if (!proposal) return null;
  return JSON.stringify({
    version: proposal.model_version,
    cut: proposal.as_of,
    snapshot: proposal.snapshot_generated_at,
    seed: proposal.settings?.seed,
    regimes: (proposal.settings?.macroRegimes || [])
      .map(r => [r.id, r.probability]),
    source: proposal.account_source,
    positions: (proposal.positions || [])
      .map(p => [p.symbol, Number(p.weight.toFixed(6))])
      .sort((a,b)=>a[0].localeCompare(b[0])),
    median: proposal.metrics?.medianReturn,
    cvar95: proposal.metrics?.cvar95,
  });
}
