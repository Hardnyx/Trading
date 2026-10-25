/**
 * Select a transparent research subset for the Monte Carlo optimizer.
 * All instruments remain in the published universe and research screen.
 * Selection uses coverage, liquidity and sector diversification, not past winners.
 */
export const MAX_COMPOSITION_ASSETS = 40;

function dollarVolume(asset) {
  const history = asset.history || [];
  const recent = history.slice(-20).filter((row) =>
    Number.isFinite(row.volume) && row.volume > 0 &&
    Number.isFinite(row.close) && row.close > 0
  );
  if (!recent.length) return 0;
  return recent.reduce((total, row) => total + row.volume * row.close, 0) / recent.length;
}

function informationScore(asset) {
  const f = asset.financials || {};
  const hasEps = asset.type === "stock" && Number.isFinite(f.eps?.value);
  const hasSales = asset.type === "stock" && Number.isFinite(f.revenue?.value);
  return (hasEps ? 2 : 0) + (hasSales ? 1 : 0);
}

export function selectCompositionUniverse(eligible, heldSymbols = [], benchmark = "SPY", limit = MAX_COMPOSITION_ASSETS) {
  if (!Number.isInteger(limit) || limit < 4) throw new Error("Límite de activos inválido.");
  const held = new Set(heldSymbols);
  const mandatory = new Set([...held, "CASH", "SHY", "SPY", benchmark]);
  const chosen = [];
  const seen = new Set();
  const select = (asset) => {
    if (asset && !seen.has(asset.symbol)) {
      chosen.push(asset);
      seen.add(asset.symbol);
    }
  };
  for (const asset of eligible) if (mandatory.has(asset.symbol)) select(asset);
  if (chosen.length > limit) throw new Error("La cartera actual supera el límite de activos de simulación.");
  const sectors = new Map();
  const extras = eligible
    .filter((asset) => !seen.has(asset.symbol))
    .sort((a, b) =>
      informationScore(b) - informationScore(a) ||
      dollarVolume(b) - dollarVolume(a) ||
      a.symbol.localeCompare(b.symbol)
    );
  for (const asset of extras) {
    const sector = asset.sector || "Otros";
    if (!sectors.has(sector)) sectors.set(sector, []);
    sectors.get(sector).push(asset);
  }
  // One candidate per group on each pass to prevent a single sector taking all slots.
  while (chosen.length < limit && [...sectors.values()].some((rows) => rows.length)) {
    for (const rows of sectors.values()) {
      if (chosen.length >= limit) break;
      if (rows.length) select(rows.shift());
    }
  }
  return {
    assets: chosen,
    omitted: eligible.filter((asset) => !seen.has(asset.symbol)).map((asset) => asset.symbol),
  };
}
