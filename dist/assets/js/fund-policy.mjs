import { referenceRequest } from "./reference-preset.mjs?v=0.35.0";

/**
 * Simulated fund policy v1: US-listed ETFs, growth mandate with a 60-90%
 * equity band, every decision starting from the fund's own holdings.
 * The zero-premium low-conviction model constrains risk but never ranks or
 * authorizes a trade. Fixed here so code changes cannot silently move the
 * published fund; a new policy needs a new id and its own track record.
 */
export const FUND_POLICY = Object.freeze({
  id: "fondo-v1",
  adoptedOn: "2026-11-14",
  initialCapital: 100000,
  purchaseTypes: ["etf"],
  region: "global",
  riskOnlyModels: ["low_conviction"],
  rules: { minEquity: 0.6, maxEquity: 0.9, cvarBudget: 0.3, maxSector: 0.5 },
  execution: { minBenefit: 250, benefitCostRatio: 3 },
  // Re-entering a portfolio abandoned within this many sessions needs twice
  // the confirmed gain, so near-ties cannot alternate.
  hysteresis: { sessions: 20, overlap: 0.8, multiplier: 2 },
  search: { candidates: 120, paths: 250, finalPaths: 650 },
});

export function emptyFundState(policy = FUND_POLICY) {
  return { schema: "simulated-fund-state-v1", policy: policy.id, inception: null,
    as_of: null, cash: policy.initialCapital, positions: [], held: [] };
}

/** Engine request for one review of the fund from its current holdings. */
export function fundRequest(snapshot, state, policy = FUND_POLICY) {
  if (state.policy !== policy.id) throw Error("El estado pertenece a otra política del fondo");
  const base = referenceRequest(snapshot);
  base.settings.mandate.region = policy.region;
  base.settings.purchaseTypes = [...policy.purchaseTypes];
  base.settings.riskOnlyModels = [...policy.riskOnlyModels];
  base.settings.execution = { ...base.settings.execution, ...policy.execution };
  base.settings.capital = policy.initialCapital;
  base.settings.account = { enabled: true, cash: state.cash,
    positions: state.positions.map(({ symbol, quantity }) => ({ symbol, quantity })) };
  base.rules = { ...base.rules, ...policy.rules };
  return base;
}

/** Share of a weight vector two portfolios hold in common. */
export function overlap(a, b) {
  const symbols = new Set([...a, ...b].map(p => p.symbol));
  let total = 0;
  for (const symbol of symbols)
    total += Math.min(a.find(p => p.symbol === symbol)?.weight || 0,
      b.find(p => p.symbol === symbol)?.weight || 0);
  return total;
}

/** Whole-share and fractional orders that move the holdings to the target. */
export function rebalanceOrders(snapshot, state, target) {
  const price = symbol => snapshot.assets.find(a => a.symbol === symbol)?.price;
  const value = state.cash + state.positions.reduce((s, p) => s + p.quantity * price(p.symbol), 0);
  const rows = [], positions = [];
  let invested = 0;
  for (const { symbol, weight } of target) {
    if (symbol === "CASH") continue;
    const p = price(symbol);
    if (!(p > 0)) throw Error("Falta precio para " + symbol);
    const fractional = weight * value / p, whole = Math.floor(fractional + 1e-9);
    const held = state.positions.find(r => r.symbol === symbol)?.quantity || 0;
    positions.push({ symbol, quantity: fractional });
    invested += fractional * p;
    rows.push({ symbol, price: p, target_weight: weight, target_shares: fractional,
      target_whole_shares: whole, held_shares: held, trade_shares: fractional - held,
      trade_whole_shares: whole - Math.round(held) });
  }
  for (const p of state.positions)
    if (!target.some(t => t.symbol === p.symbol))
      rows.push({ symbol: p.symbol, price: price(p.symbol), target_weight: 0, target_shares: 0,
        target_whole_shares: 0, held_shares: p.quantity, trade_shares: -p.quantity,
        trade_whole_shares: -Math.round(p.quantity) });
  return { value, orders: rows.sort((a, b) => a.trade_shares - b.trade_shares),
    positions, cash: value - invested };
}
