/**
 * fondo-v2: evidence-gated strategic fund (registered in docs/fondo-v2-registro.json).
 * Weights come from the owner's mandate and broad-market conventions; engine
 * tilts stay disabled until a registered out-of-sample test supports them.
 * Pure arithmetic: no forecast, simulation or optimizer moves money here.
 */
export const FUND_V2 = Object.freeze({
  id: "fondo-v2",
  adoptedOn: "2026-11-14",
  initialCapital: 100000,
  mix: Object.freeze({ equity: 0.7, usShare: 0.6, cash: 0.05 }),
  instruments: Object.freeze({ us: "VTI", international: "VXUS", bonds: "AGG" }),
  threshold: 0.05,
  staleSessions: 3,
  // Registered exception rule: a drawdown beyond the worst of acceptance test
  // T3 (70/25/5, 1929-09 to 1932-06) flags a review but never forces a sale.
  worstHistoricalDrawdown: -0.671,
});

/** fondo-v3 (docs/fondo-v3-registro.json): fondo-v2 with the supported risk timing. */
export const FUND_V3 = Object.freeze({
  ...FUND_V2,
  id: "fondo-v3",
  role: "shadow",
  timing: Object.freeze({ base: 0.7, min: 0.6, max: 0.9, lambda: 0.94 }),
});

/** Equity share from month-end volatility against its own earlier average. */
export function timedEquityShare(sigma, sigmaBar, timing = FUND_V3.timing) {
  if (!(sigma > 0) || !(sigmaBar > 0)) return timing.base;
  return Math.min(timing.max, Math.max(timing.min, timing.base * sigmaBar / sigma));
}

/**
 * Month-end EWMA volatilities from daily returns [{date, r}] in date order.
 * Returns the share for a cut: sigma at the last session of the previous
 * month and the mean of all earlier month-end sigmas.
 */
export function volatilityForCut(returns, cut, lambda = FUND_V3.timing.lambda) {
  const month = cut.slice(0, 7), ends = [];
  let variance = null;
  for (let i = 0; i < returns.length && returns[i].date.slice(0, 7) < month; i++) {
    const r = returns[i].r;
    variance = variance === null ? r * r : lambda * variance + (1 - lambda) * r * r;
    const next = returns[i + 1];
    if (!next || next.date.slice(0, 7) !== returns[i].date.slice(0, 7))
      ends.push({ date: returns[i].date, sigma: Math.sqrt(252 * variance) });
  }
  if (ends.length < 61) return null;
  const last = ends.at(-1), earlier = ends.slice(0, -1);
  return { monthEnd: last.date, sigma: last.sigma,
    sigmaBar: earlier.reduce((s, e) => s + e.sigma, 0) / earlier.length, monthEnds: ends.length };
}

/** Target weights from a mix; bonds take what equity and cash leave. */
export function mixWeights(mix, policy = FUND_V2) {
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, Number.isFinite(v) ? v : lo));
  const equity = clamp(mix.equity, 0, 1), usShare = clamp(mix.usShare, 0, 1),
    cash = clamp(mix.cash, 0, 1 - equity);
  const { us, international, bonds } = policy.instruments;
  return [
    { symbol: us, weight: equity * usShare },
    { symbol: international, weight: equity * (1 - usShare) },
    { symbol: bonds, weight: Math.max(0, 1 - equity - cash) },
    { symbol: "CASH", weight: cash },
  ].filter(p => p.weight > 1e-12);
}

/** Largest absolute deviation of current weights from the targets. */
export function maxDrift(current, target) {
  const symbols = new Set([...current, ...target].map(p => p.symbol));
  let worst = 0;
  for (const symbol of symbols)
    worst = Math.max(worst, Math.abs((current.find(p => p.symbol === symbol)?.weight || 0) -
      (target.find(p => p.symbol === symbol)?.weight || 0)));
  return worst;
}

/** Weekday sessions between two ISO dates (holidays not removed: conservative). */
export function sessionsBetween(a, b) {
  let count = 0;
  for (let d = new Date(a + "T12:00:00Z"); d < new Date(b + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + 1))
    if (d.getUTCDay() % 6) count++;
  return count;
}

/** Whole and fractional share orders that move holdings to target weights. */
export function ordersFor(prices, holdings, cash, target) {
  const value = cash + holdings.reduce((s, p) => s + p.quantity * prices[p.symbol], 0);
  const rows = [], positions = [];
  let invested = 0, wholeInvested = 0;
  for (const { symbol, weight } of target) {
    if (symbol === "CASH") continue;
    const price = prices[symbol];
    if (!(price > 0)) throw Error("Falta precio para " + symbol);
    const shares = weight * value / price, whole = Math.floor(shares + 1e-9);
    const held = holdings.find(h => h.symbol === symbol)?.quantity || 0;
    positions.push({ symbol, quantity: shares });
    invested += shares * price; wholeInvested += whole * price;
    rows.push({ symbol, price, target_weight: weight, target_shares: shares, target_whole_shares: whole,
      held_shares: held, trade_shares: shares - held, trade_whole_shares: whole - Math.floor(held + 1e-9) });
  }
  for (const h of holdings)
    if (!target.some(t => t.symbol === h.symbol))
      rows.push({ symbol: h.symbol, price: prices[h.symbol], target_weight: 0, target_shares: 0, target_whole_shares: 0,
        held_shares: h.quantity, trade_shares: -h.quantity, trade_whole_shares: -Math.floor(h.quantity + 1e-9) });
  return { value, positions, cash: value - invested, whole_cash: value - wholeInvested,
    orders: rows.sort((a, b) => a.trade_shares - b.trade_shares) };
}

/** One review: hold unless a sleeve drifts beyond the threshold or data fail. */
export function reviewStrategic({ asOf, generatedOn, prices, mix = null }, state, policy = FUND_V2) {
  const target = mixWeights(mix || policy.mix, policy);
  const symbols = [...new Set([...state.positions.map(p => p.symbol), ...target.map(t => t.symbol).filter(s => s !== "CASH")])];
  const missing = symbols.filter(s => !(prices[s] > 0));
  const base = { date: asOf, policy: policy.id, target };
  if (missing.length)
    return { ...base, status: "hold", reason: `Sin operar: falta precio de ${missing.join(", ")}.`, drift: null, orders: [] };
  if (generatedOn && sessionsBetween(asOf, generatedOn) > policy.staleSessions)
    return { ...base, status: "hold", reason: `Sin operar: el corte ${asOf} tiene más de ${policy.staleSessions} sesiones.`, drift: null, orders: [] };
  const value = state.cash + state.positions.reduce((s, p) => s + p.quantity * prices[p.symbol], 0);
  const current = [...state.positions.map(p => ({ symbol: p.symbol, weight: p.quantity * prices[p.symbol] / value })),
    { symbol: "CASH", weight: state.cash / value }];
  const drift = maxDrift(current, target);
  if (drift <= policy.threshold + 1e-12)
    return { ...base, status: "hold", reason: `Mantener: desviación máxima ${(drift * 100).toFixed(1)} pp, dentro del umbral de ${(policy.threshold * 100).toFixed(0)} pp.`, drift, current, value, orders: [] };
  const plan = ordersFor(prices, state.positions, state.cash, target);
  if (!state.positions.length)
    return { ...base, status: "rebalance", reason: "Compra inicial a los pesos objetivo.", drift, current, value,
      orders: plan.orders, next: { positions: plan.positions.filter(p => p.quantity > 1e-9), cash: plan.cash } };
  return { ...base, status: "rebalance", reason: `Rebalancear: desviación máxima ${(drift * 100).toFixed(1)} pp supera el umbral de ${(policy.threshold * 100).toFixed(0)} pp.`,
    drift, current, value, orders: plan.orders, next: { positions: plan.positions.filter(p => p.quantity > 1e-9), cash: plan.cash } };
}
