/**
 * Select a transparent research subset for the Monte Carlo optimizer.
 * All instruments remain in the published universe and research screen.
 * Selection uses coverage, liquidity and sector diversification, not past winners.
 */
export const MAX_COMPOSITION_ASSETS = 40;
export const MAX_SUPPORTED_COMPOSITION_ASSETS = 80;

function shareVolume(asset) {
  const history = asset.history || [];
  const recent = history.slice(-20).filter((row) =>
    Number.isFinite(row.volume) && row.volume > 0
  );
  if (!recent.length) return 0;
  return recent.reduce((total, row) => total + row.volume, 0) / recent.length;
}

function informationScore(asset) {
  const f = asset.financials || {};
  const hasEps = asset.type === "stock" && Number.isFinite(f.eps?.value);
  const hasSales = asset.type === "stock" && Number.isFinite(f.revenue?.value);
  return (hasEps ? 2 : 0) + (hasSales ? 1 : 0);
}

export function selectCompositionUniverse(eligible, heldSymbols = [], benchmark = "SPY", limit = MAX_COMPOSITION_ASSETS, priorities = null) {
  if (!Number.isInteger(limit) || limit < 4 || limit>MAX_SUPPORTED_COMPOSITION_ASSETS) throw new Error("Límite de activos inválido.");
  const unique = eligible.filter((asset, i) => eligible.findIndex((row) => row.symbol === asset.symbol) === i);
  if (unique.length <= limit) return { assets: unique, omitted: [], method: "all-eligible" };
  const held = new Set(heldSymbols);
  // Fixed, auditable comparators across equities, Treasuries and credit.
  // These are comparison instruments, not buy recommendations.
  const core = ["CASH", "SHY", "SPY", "SGOV", "IEF", "TLT", "AGG", "LQD",
    "HYG", "GLD", "QQQ", "VTI", "VXUS"];
  const mandatory = new Set([...held, ...core, benchmark]);
  const chosen = [];
  const seen = new Set();
  const select = (asset) => {
    if (asset && !seen.has(asset.symbol)) {
      chosen.push(asset);
      seen.add(asset.symbol);
    }
  };
  for (const asset of unique) if (mandatory.has(asset.symbol)) select(asset);
  if (chosen.length > limit) throw new Error("La cartera actual supera el límite de activos de simulación.");
  const sectors = new Map();
  const score = (asset) => priorities && Number.isFinite(priorities[asset.symbol])
    ? priorities[asset.symbol] : -Infinity;
  const extras = unique
    .filter((asset) => !seen.has(asset.symbol))
    .sort((a, b) =>
      (priorities ? score(b) - score(a) : 0) ||
      informationScore(b) - informationScore(a) ||
      shareVolume(b) - shareVolume(a) ||
      a.symbol.localeCompare(b.symbol)
    );
  // Allocate roughly half the remaining slots to economically ranked
  // candidates; keep the other half for sector breadth. The signal uses
  // forward valuation and uncertainty, NEVER a past-return ranking.
  const availableSlots = Math.max(0, limit - chosen.length);
  if (priorities) {
    const qualitySlots = Math.floor(availableSlots / 2);
    let used = 0;
    for (const asset of extras) {
      if (used >= qualitySlots) break;
      if (!Number.isFinite(priorities[asset.symbol])) continue;
      select(asset);
      used++;
    }
  }
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
    omitted: unique.filter((asset) => !seen.has(asset.symbol)).map((asset) => asset.symbol),
    method: priorities
      ? "auditable-forward-risk-adjusted-signal-and-sector-breadth"
      : "coverage-liquidity-sector-breadth",
  };
}
