/**
 * Daily review of the simulated fund.
 *
 * The published fund follows fondo-v2 (docs/fondo-v2-registro.json): fixed
 * strategic weights, rebalanced only when a sleeve drifts beyond 5 pp. The
 * archived fondo-v1 engine review (reviewFund) is kept for its record and
 * tests. Holdings roll forward with adjusted closes, so distributions stay
 * invested. Research simulation only: no broker orders.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { composeMultiStart } from "../dist/assets/js/composer.mjs?v=0.35.0";
import { economicClass } from "../dist/assets/js/economic-exposure.mjs?v=0.35.0";
import { FUND_POLICY, emptyFundState, fundRequest, overlap, rebalanceOrders } from "../dist/assets/js/fund-policy.mjs";
import { FUND_V2, FUND_V3, mixWeights, reviewStrategic, timedEquityShare, volatilityForCut } from "../dist/assets/js/strategic-fund.mjs";

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

const EQUITY = new Set(["us-equity", "international-equity", "global-equity", "direct-equity"]);

/**
 * Passive comparators from the fund's inception, total return (adjusted
 * closes): 60/40 SPY/AGG rebalanced at each month end, SPY and Treasury bills.
 */
export function benchmarkReturns(snapshot, inception, asOf) {
  const series = symbol => {
    const rows = snapshot.assets.find(a => a.symbol === symbol)?.history || [];
    return new Map(rows.filter(r => r.date >= inception && r.date <= asOf && r.adj_close > 0).map(r => [r.date, r.adj_close]));
  };
  const spy = series("SPY"), agg = series("AGG"), bil = series("BIL");
  const dates = [...spy.keys()].filter(d => agg.has(d)).sort();
  if (!dates.length || dates[0] !== inception || dates.at(-1) !== asOf) return null;
  let equity = 0.6, bonds = 0.4;
  for (let i = 1; i < dates.length; i++) {
    equity *= spy.get(dates[i]) / spy.get(dates[i - 1]);
    bonds *= agg.get(dates[i]) / agg.get(dates[i - 1]);
    if (i < dates.length - 1 && dates[i].slice(0, 7) !== dates[i + 1].slice(0, 7)) {
      const total = equity + bonds; equity = 0.6 * total; bonds = 0.4 * total;
    }
  }
  const total = (map) => map.has(inception) && map.has(asOf) ? round(map.get(asOf) / map.get(inception) - 1) : null;
  return { method: "total-return-adjusted-closes", balanced_60_40: round(equity + bonds - 1), spy: total(spy), tbills: total(bil) };
}

/** Public summary for the web page: holdings at the latest reviewed cut. */
export function publicFund(state, reviews, snapshot, policy = FUND_POLICY) {
  const asset = s => snapshot.assets.find(a => a.symbol === s);
  const value = holdingsValue(state, snapshot);
  const holdings = state.positions.map(p => {
    const a = asset(p.symbol), amount = p.quantity * a.price;
    return { symbol: p.symbol, name: a.name || p.symbol, class: economicClass(a),
      shares: round(p.quantity, 4), whole_shares: Math.floor(p.quantity + 1e-9), price: a.price,
      value: round(amount, 2), weight: round(amount / value) };
  }).sort((a, b) => b.weight - a.weight);
  const last = reviews.at(-1) || null;
  return {
    schema_version: 1, policy: policy.id, adopted_on: policy.adoptedOn, as_of: state.as_of,
    inception: state.inception, initial_capital: policy.initialCapital, value: round(value, 2),
    return_since_inception: round(value / policy.initialCapital - 1),
    cash: round(state.cash, 2), cash_weight: round(state.cash / value),
    equity_weight: round(holdings.filter(h => EQUITY.has(h.class)).reduce((s, h) => s + h.weight, 0)),
    holdings,
    last_review: last && { date: last.date, status: last.status, reason: last.reason,
      evidence: last.evidence, risk_only: last.risk_only, hurdle: last.hurdle,
      hysteresis: last.hysteresis, metrics: last.metrics, orders: last.orders },
    benchmarks: state.inception ? benchmarkReturns(snapshot, state.inception, state.as_of) : null,
    rebalances: reviews.filter(r => r.status === "rebalance").map(r => r.date),
    history: reviews.map(r => ({ date: r.date, status: r.status, value: r.value })),
    mandate: { equity: [policy.rules.minEquity, policy.rules.maxEquity], cvar95: policy.rules.cvarBudget,
      purchase: policy.purchaseTypes, risk_only_models: policy.riskOnlyModels,
      min_benefit: policy.execution.minBenefit, benefit_cost_ratio: policy.execution.benefitCostRatio,
      hysteresis: policy.hysteresis },
    research_only: true, predictive_validation: "not-established",
  };
}

const V2_DIR = "data/fund/fondo-v2", V1_DIR = "data/fund/fondo-v1", V3_DIR = "data/fund/fondo-v3";

/** Daily market returns: French Mkt-RF + RF, then VTI adjusted closes after its last day. */
export function marketReturns(market, folder = "data/history/factors/ff5-daily") {
  const rows = [];
  for (const file of readdirSync(folder).filter(f => f.endsWith(".csv.gz")).sort()) {
    const lines = gunzipSync(readFileSync(`${folder}/${file}`)).toString("utf8").trim().split("\n");
    const head = lines[0].split(","), m = head.indexOf("Mkt-RF"), f = head.indexOf("RF");
    for (const line of lines.slice(1)) {
      const c = line.split(",");
      rows.push({ date: c[0], r: (Number(c[m]) + Number(c[f])) / 100 });
    }
  }
  const last = rows.at(-1)?.date || "";
  const vti = market.assets.find(a => a.symbol === "VTI")?.history || [];
  for (let i = 1; i < vti.length; i++)
    if (vti[i].date > last && vti[i].date <= market.price_as_of && vti[i - 1].adj_close > 0)
      rows.push({ date: vti[i].date, r: vti[i].adj_close / vti[i - 1].adj_close - 1 });
  return rows;
}

/** fondo-v3 mix for a cut; falls back to the static mix when volatility is unavailable. */
export function v3Mix(returns, cut, policy = FUND_V3) {
  const v = volatilityForCut(returns, cut, policy.timing.lambda);
  const equity = v ? timedEquityShare(v.sigma, v.sigmaBar, policy.timing) : policy.timing.base;
  return { mix: { equity, usShare: policy.mix.usShare, cash: policy.mix.cash }, volatility: v };
}

function readReviews(dir) {
  return existsSync(dir + "/reviews") ? readdirSync(dir + "/reviews").filter(f => f.endsWith(".json")).sort()
    .map(f => JSON.parse(readFileSync(`${dir}/reviews/${f}`, "utf8"))) : [];
}

export function emptyStrategicState(policy = FUND_V2) {
  return { schema: "simulated-fund-state-v2", policy: policy.id, inception: null, as_of: null,
    cash: policy.initialCapital, positions: [], peak: null };
}

/** Public summary of fondo-v2 for the web page, with fondo-v1 archived. */
export function publicStrategicFund(state, reviews, snapshot, archived = null, policy = FUND_V2) {
  const asset = s => snapshot.assets.find(a => a.symbol === s);
  const value = holdingsValue(state, snapshot),
    target = reviews.at(-1)?.target ?? mixWeights(policy.mix, policy);
  const holdings = state.positions.map(p => {
    const a = asset(p.symbol), amount = p.quantity * a.price;
    return { symbol: p.symbol, name: a.name || p.symbol, class: economicClass(a),
      shares: round(p.quantity, 4), whole_shares: Math.floor(p.quantity + 1e-9), price: a.price,
      value: round(amount, 2), weight: round(amount / value),
      target_weight: round(target.find(t => t.symbol === p.symbol)?.weight || 0) };
  }).sort((a, b) => b.weight - a.weight);
  const last = reviews.at(-1) || null;
  const prices = Object.fromEntries(Object.values(policy.instruments).map(s => [s, asset(s)?.price ?? null]));
  const names = Object.fromEntries(Object.values(policy.instruments).map(s => [s, asset(s)?.name ?? s]));
  return {
    schema_version: 2, policy: policy.id, adopted_on: policy.adoptedOn, as_of: state.as_of,
    inception: state.inception, initial_capital: policy.initialCapital, value: round(value, 2),
    return_since_inception: round(value / policy.initialCapital - 1),
    drawdown: state.peak ? round(value / state.peak - 1) : 0,
    review_flag: state.peak && value / state.peak - 1 < policy.worstHistoricalDrawdown
      ? "Caída mayor que la peor histórica de la mezcla: la regla sigue, sin ventas discrecionales; revisar el mandato." : null,
    cash: round(state.cash, 2), cash_weight: round(state.cash / value),
    equity_weight: round(holdings.filter(h => EQUITY.has(h.class)).reduce((s, h) => s + h.weight, 0)),
    holdings, target: target.map(t => ({ ...t, weight: round(t.weight) })),
    mix: policy.mix, equity_target: reviews.at(-1)?.equity_target ?? policy.mix.equity,
    volatility: reviews.at(-1)?.volatility ?? null, instruments: policy.instruments, threshold: policy.threshold, prices, names,
    last_review: last && { date: last.date, status: last.status, reason: last.reason,
      drift: last.drift, orders: last.orders },
    benchmarks: state.inception ? benchmarkReturns(snapshot, state.inception, state.as_of) : null,
    rebalances: reviews.filter(r => r.status === "rebalance").map(r => r.date),
    history: reviews.map(r => ({ date: r.date, status: r.status, value: r.value })),
    evidence: {
      moves_money: ["mandate weights", "broad market diversification", "drift rebalancing"],
      supported_not_yet_used: ["bond carry anchor (docs/registro-anclas-valoracion.md)"],
      disabled: ["equity valuation tilts (not supported)", "bond duration timing", "risk timing", "stock selection"],
    },
    archived, research_only: true,
  };
}

function writePublic(snapshot) {
  const state = JSON.parse(readFileSync(V2_DIR + "/state.json", "utf8"));
  const v1 = existsSync(V1_DIR + "/state.json") ? JSON.parse(readFileSync(V1_DIR + "/state.json", "utf8")) : null;
  const archived = v1 && [{ policy: v1.policy, from: v1.inception, until: "2026-11-14",
    reason: "Reemplazado: sus apuestas regionales se basaban en un ancla de acciones no respaldada.",
    reviews: readReviews(V1_DIR).length }];
  const fund = publicStrategicFund(state, readReviews(V2_DIR), snapshot, archived);
  if (existsSync(V3_DIR + "/state.json")) {
    const shadow = publicStrategicFund(JSON.parse(readFileSync(V3_DIR + "/state.json", "utf8")), readReviews(V3_DIR), snapshot, null, FUND_V3);
    const { archived: _a, evidence: _e, prices: _p, names: _n, ...rest } = shadow;
    fund.shadow = { ...rest, role: "shadow", registration: "docs/fondo-v3-registro.json",
      promotion_rule: "only by a new registration after at least 12 monthly targets" };
  }
  writeFileSync("dist/data/fund.json", JSON.stringify(fund, null, 1) + "\n");
}

/** One fondo-v2 review on a market snapshot; returns the next state and its record. */
export function reviewV2(market, previous, policy = FUND_V2, mix = null) {
  let state;
  try { state = rollForward(previous, market); }
  catch (error) { state = structuredClone(previous); state.rollError = error.message; }
  const prices = Object.fromEntries(market.assets.map(a => [a.symbol, a.price]));
  const result = state.rollError
    ? { date: market.price_as_of, policy: policy.id, target: mixWeights(mix || policy.mix, policy), status: "hold",
        reason: "Sin operar: " + state.rollError, drift: null, orders: [] }
    : reviewStrategic({ asOf: market.price_as_of, generatedOn: (market.generated_at || "").slice(0, 10), prices, mix }, state, policy);
  const next = structuredClone(state);
  delete next.rollError;
  if (result.status === "rebalance") { next.positions = result.next.positions; next.cash = result.next.cash; }
  next.as_of = market.price_as_of;
  next.inception ??= market.price_as_of;
  const value = state.rollError ? null : holdingsValue(next, market);
  if (value !== null) next.peak = Math.max(next.peak || 0, value);
  const { next: _drop, current, ...rest } = result;
  const record = { schema: "simulated-fund-review-v2", ...rest,
    value: value === null ? null : round(value, 2),
    current: current?.map(p => ({ ...p, weight: round(p.weight) })) ?? null,
    drift: result.drift === null ? null : round(result.drift),
    orders: result.orders.map(o => ({ ...o, trade_shares: round(o.trade_shares, 4), target_shares: round(o.target_shares, 4) })),
    engine_tilts: "disabled", research_only: true };
  return { state: next, record };
}

function reviewShadow(market, marketBytes) {
  const statePath = V3_DIR + "/state.json";
  const previous = existsSync(statePath) ? JSON.parse(readFileSync(statePath, "utf8")) : { ...emptyStrategicState(FUND_V3) };
  if (previous.as_of && previous.as_of >= market.price_as_of) return;
  const { mix, volatility } = v3Mix(marketReturns(market), market.price_as_of);
  const { state, record } = reviewV2(market, previous, FUND_V3, mix);
  record.equity_target = round(mix.equity);
  record.volatility = volatility && { month_end: volatility.monthEnd, sigma: round(volatility.sigma),
    sigma_bar: round(volatility.sigmaBar), month_ends: volatility.monthEnds };
  record.market_sha256 = sha(marketBytes);
  mkdirSync(V3_DIR + "/reviews", { recursive: true });
  writeFileSync(`${V3_DIR}/reviews/${record.date}.json`, JSON.stringify(record, null, 1) + "\n");
  writeFileSync(statePath, JSON.stringify(state, null, 1) + "\n");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const marketBytes = readFileSync("dist/data/market.json"), market = JSON.parse(marketBytes);
  if (!process.argv.includes("--publish-only")) reviewShadow(market, marketBytes);
  const statePath = V2_DIR + "/state.json";
  const previous = existsSync(statePath) ? JSON.parse(readFileSync(statePath, "utf8")) : emptyStrategicState();
  if (process.argv.includes("--publish-only") || (previous.as_of && previous.as_of >= market.price_as_of)) {
    if (previous.as_of === market.price_as_of) writePublic(market);
    console.log(JSON.stringify({ skipped: true, reason: "cut already reviewed", as_of: previous.as_of }));
    process.exit(0);
  }
  const { state, record } = reviewV2(market, previous);
  record.market_sha256 = sha(marketBytes);
  mkdirSync(V2_DIR + "/reviews", { recursive: true });
  writeFileSync(`${V2_DIR}/reviews/${record.date}.json`, JSON.stringify(record, null, 1) + "\n");
  writeFileSync(statePath, JSON.stringify(state, null, 1) + "\n");
  writePublic(market);
  console.log(JSON.stringify({ date: record.date, status: record.status, reason: record.reason, drift: record.drift }));
}
