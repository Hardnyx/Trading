/**
 * Daily review of the simulated fund under its frozen policy.
 *
 * Holdings roll forward with adjusted closes, so distributions stay invested
 * in the fund that paid them. The engine starts from those holdings and only a
 * transition that beats holding in every decision model, after costs and a
 * Monte Carlo lower bound, becomes a rebalance. Re-entering a recently
 * abandoned portfolio needs a larger confirmed gain. Research simulation only:
 * no broker orders and no claim of predictive validity.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { composeMultiStart } from "../dist/assets/js/composer.mjs?v=0.35.0";
import { FUND_POLICY, emptyFundState, fundRequest, overlap, rebalanceOrders } from "../dist/assets/js/fund-policy.mjs";

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const round = (value, digits = 6) => Math.round(value * 10 ** digits) / 10 ** digits;

function adjustedOn(asset, date) {
  const rows = asset.history.filter(r => r.date <= date);
  return rows.at(-1) || null;
}

/** Reinvest distributions between two cuts by scaling share counts. */
export function rollForward(state, snapshot) {
  if (!state.as_of || state.as_of === snapshot.price_as_of) return structuredClone(state);
  const positions = state.positions.map(p => {
    const asset = snapshot.assets.find(a => a.symbol === p.symbol);
    const start = asset && adjustedOn(asset, state.as_of), end = asset && adjustedOn(asset, snapshot.price_as_of);
    if (!start || !end || !(start.close > 0 && start.adj_close > 0))
      throw Error("Falta historia para revalorizar " + p.symbol);
    const reinvest = (end.adj_close / start.adj_close) / (end.close / start.close);
    return { ...p, quantity: p.quantity * reinvest };
  });
  return { ...structuredClone(state), positions };
}

export function holdingsValue(state, snapshot) {
  const price = s => snapshot.assets.find(a => a.symbol === s)?.price;
  return state.cash + state.positions.reduce((total, p) => total + p.quantity * price(p.symbol), 0);
}

const weightsOf = (state, snapshot) => {
  const value = holdingsValue(state, snapshot),
    price = s => snapshot.assets.find(a => a.symbol === s)?.price;
  return [...state.positions.map(p => ({ symbol: p.symbol, weight: p.quantity * price(p.symbol) / value })),
    { symbol: "CASH", weight: state.cash / value }].filter(p => p.weight > 1e-9);
};

/** Hysteresis: returning to a portfolio left recently needs a larger gain. */
export function hysteresisHurdle(state, target, current, date, hurdle, policy = FUND_POLICY) {
  const recent = (state.held || []).filter(h => h.until && sessionsBetween(h.until, date) <= policy.hysteresis.sessions);
  const revisit = recent.find(h => overlap(h.positions, target) >= policy.hysteresis.overlap &&
    overlap(h.positions, current) < policy.hysteresis.overlap);
  return revisit ? { hurdle: hurdle * policy.hysteresis.multiplier, revisits: revisit.from } : { hurdle, revisits: null };
}

function sessionsBetween(a, b) {
  let count = 0;
  for (let d = new Date(a + "T12:00:00Z"); d < new Date(b + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + 1))
    if (d.getUTCDay() % 6) count++;
  return count;
}

/** One review: returns the next state and an auditable record. */
export function reviewFund(snapshot, previous, { policy = FUND_POLICY, compose = composeMultiStart } = {}) {
  const state = rollForward(previous, snapshot), date = snapshot.price_as_of;
  const current = weightsOf(state, snapshot), value = holdingsValue(state, snapshot);
  const request = fundRequest(snapshot, state, policy);
  const model = compose(snapshot, request.settings, request.overrides, request.rules, policy.search);
  const audit = model.diagnostics?.robustDecision;
  const decision = audit?.models?.filter(m => m.role !== "risk-only") || [];
  const baseHurdle = audit?.hurdle ?? null;
  let status = "hold", reason = model.reason || null, target = current, gate = null;
  if (model.status === "proposed" && overlap(model.positions, current) < 0.999) {
    gate = hysteresisHurdle(state, model.positions, current, date, baseHurdle, policy);
    const lower = Math.min(...decision.map(m => m.evidence.lowerGain));
    if (lower >= gate.hurdle) { status = "rebalance"; target = model.positions; reason = null; }
    else reason = `Mantener: la ganancia confirmada USD ${Math.round(lower)} no alcanza el umbral ` +
      `USD ${Math.round(gate.hurdle)} por volver a una cartera abandonada el ${gate.revisits}.`;
  } else if (model.status === "proposed") reason = "La cartera vigente ya es la propuesta.";
  const orders = status === "rebalance" ? rebalanceOrders(snapshot, state, target) : null;
  const next = structuredClone(state);
  next.as_of = date;
  next.inception ??= date;
  if (orders) {
    next.positions = orders.positions.filter(p => p.quantity > 1e-9);
    next.cash = orders.cash;
    const leaving = next.held.find(h => !h.until);
    if (leaving) leaving.until = date;
    next.held.push({ from: date, until: null, positions: target.map(p => ({ symbol: p.symbol, weight: round(p.weight) })) });
  }
  const record = {
    schema: "simulated-fund-review-v1", policy: policy.id, date,
    engine_version: model.model_version, status, reason,
    value: round(value, 2), current: current.map(p => ({ ...p, weight: round(p.weight) })),
    target: target.map(p => ({ symbol: p.symbol, weight: round(p.weight) })),
    proposal: model.status === "proposed" ? model.positions.map(p => ({ symbol: p.symbol, weight: round(p.weight) })) : null,
    engine_status: model.status,
    evidence: decision.map(m => ({ model: m.id, gain: round(m.evidence.gain, 2), lower_gain: round(m.evidence.lowerGain, 2),
      failures: m.failures })),
    risk_only: (audit?.models || []).filter(m => m.role === "risk-only").map(m => ({ model: m.id, failures: m.failures })),
    hurdle: baseHurdle, hysteresis: gate,
    metrics: model.metrics ? { median_return: model.metrics.medianReturn, cvar95: model.metrics.cvar95,
      loss_probability: model.metrics.lossProbability } : null,
    orders: orders?.orders.map(o => ({ ...o, trade_shares: round(o.trade_shares, 4), target_shares: round(o.target_shares, 4) })) ?? [],
    search: policy.search, research_only: true, predictive_validation: "not-established",
  };
  return { state: next, record };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const marketBytes = readFileSync("dist/data/market.json"), volatilityBytes = readFileSync("dist/data/volatility.json");
  const market = JSON.parse(marketBytes), volatility = JSON.parse(volatilityBytes);
  if (volatility.as_of !== market.price_as_of || volatility.source_market_generated_at !== market.generated_at)
    throw Error("Market snapshot and risk calibration are not the same cut");
  const snapshot = { ...market, volatility }, statePath = "data/fund/state.json";
  const previous = existsSync(statePath) ? JSON.parse(readFileSync(statePath, "utf8")) : emptyFundState();
  if (previous.as_of && previous.as_of >= market.price_as_of) {
    console.log(JSON.stringify({ skipped: true, reason: "cut already reviewed", as_of: previous.as_of }));
    process.exit(0);
  }
  const { state, record } = reviewFund(snapshot, previous);
  record.market_sha256 = sha(marketBytes);
  record.volatility_sha256 = sha(volatilityBytes);
  mkdirSync("data/fund/reviews", { recursive: true });
  writeFileSync(`data/fund/reviews/${record.date}.json`, JSON.stringify(record, null, 1) + "\n");
  writeFileSync(statePath, JSON.stringify(state, null, 1) + "\n");
  console.log(JSON.stringify({ date: record.date, status: record.status, reason: record.reason, target: record.target }));
}
