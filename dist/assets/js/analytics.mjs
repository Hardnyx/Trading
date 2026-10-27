import { earningsShareBasis } from './financial-freshness.mjs?v=0.21.0';

export const TRADING_DAYS = 252;
export const finite = (x) => typeof x === "number" && Number.isFinite(x);
export const sum = (xs) => xs.reduce((a, b) => a + b, 0);
export const mean = (xs) => (xs.length ? sum(xs) / xs.length : null);
export const variance = (xs) =>
  xs.length > 1
    ? sum(xs.map((x) => (x - mean(xs)) ** 2)) / (xs.length - 1)
    : null;
export const stdev = (xs) => {
  const v = variance(xs);
  return finite(v) ? Math.sqrt(v) : null;
};
export function covariance(a, b) {
  if (a.length !== b.length || a.length < 2) return null;
  const ma = mean(a),
    mb = mean(b);
  return sum(a.map((x, i) => (x - ma) * (b[i] - mb))) / (a.length - 1);
}
export function correlation(a, b) {
  const sa = stdev(a),
    sb = stdev(b);
  return sa > 0 && sb > 0
    ? Math.max(-1, Math.min(1, covariance(a, b) / (sa * sb)))
    : null;
}
export function quantile(xs, p) {
  if (!xs.length || p < 0 || p > 1) return null;
  const a = [...xs].sort((a, b) => a - b),
    pos = (a.length - 1) * p,
    low = Math.floor(pos);
  return a[low] + (a[Math.ceil(pos)] - a[low]) * (pos - low);
}
export function normalizeWeights(positions) {
  const valid = positions.filter((p) => finite(p.weight) && p.weight > 0);
  const total = sum(valid.map((p) => p.weight));
  return total > 0
    ? valid.map((p) => ({ ...p, weight: p.weight / total }))
    : [];
}
export function dailyReturns(history) {
  const map = new Map();
  for (let i = 1; i < history.length; i++) {
    const current = history[i],
      previous = history[i - 1];
    if (current.adj_close > 0 && previous.adj_close > 0)
      map.set(current.date, current.adj_close / previous.adj_close - 1);
  }
  return map;
}
export function alignReturns(assets, lookback = 252) {
  if (!assets.length) return { dates: [], columns: [] };
  const maps = assets.map((a) => dailyReturns(a.history || []));
  const dates = [...maps[0].keys()]
    .filter((d) => maps.every((m) => m.has(d)))
    .sort()
    .slice(-lookback);
  return { dates, columns: maps.map((m) => dates.map((d) => m.get(d))) };
}
export function wealth(returns, initial = 100) {
  let value = initial;
  return [initial, ...returns.map((r) => (value *= 1 + r))];
}
export function drawdown(returns) {
  let value = 1,
    peak = 1,
    worst = 0;
  const series = returns.map((r) => {
    value *= 1 + r;
    peak = Math.max(peak, value);
    const d = value / peak - 1;
    worst = Math.min(worst, d);
    return d;
  });
  return { worst, series };
}
export function returnStats(returns, riskFree = 0.04, benchmark = []) {
  if (returns.length < 2) return null;
  const n = returns.length,
    total = wealth(returns, 1).at(-1) - 1;
  const annualized = (1 + total) ** (252 / n) - 1;
  const volatility = stdev(returns) * Math.sqrt(252);
  const rfDaily = (1 + riskFree) ** (1 / 252) - 1;
  const sharpe =
    volatility > 0 ? ((mean(returns) - rfDaily) * 252) / volatility : null;
  const threshold = quantile(returns, 0.05),
    tail = returns.filter((r) => r <= threshold);
  const bv = benchmark.length === n ? variance(benchmark) : null;
  return {
    n,
    total,
    annualized,
    volatility,
    sharpe,
    maxDrawdown: drawdown(returns).worst,
    var95: Math.max(0, -threshold),
    expectedShortfall: Math.max(0, -mean(tail)),
    beta: bv > 0 ? covariance(returns, benchmark) / bv : null,
  };
}
export function portfolioAnalysis(
  assets,
  positions,
  lookback = 252,
  riskFree = 0.04,
  benchmarkSymbol = "SPY",
) {
  const lookup = new Map(assets.map((a) => [a.symbol, a]));
  const weights = normalizeWeights(
    positions.filter((p) => lookup.has(p.symbol)),
  );
  if (!weights.length) return null;
  const selected = weights.map((p) => lookup.get(p.symbol));
  const benchmark = lookup.get(benchmarkSymbol);
  const alignment = alignReturns(
    benchmark ? [...selected, benchmark] : selected,
    lookback,
  );
  if (alignment.dates.length < 20) return null;
  const columns = alignment.columns.slice(0, selected.length);
  const returns = alignment.dates.map((_, t) =>
    sum(columns.map((col, i) => col[t] * weights[i].weight)),
  );
  const benchmarkReturns = benchmark ? alignment.columns.at(-1) : [];
  const cov = columns.map((a) => columns.map((b) => covariance(a, b) * 252));
  const matrix = columns.map((a) => columns.map((b) => correlation(a, b)));
  const volatility = stdev(returns) * Math.sqrt(252);
  const contributions = weights.map((p, i) => ({
    symbol: p.symbol,
    fraction:
      volatility > 0
        ? (p.weight * sum(cov[i].map((v, j) => v * weights[j].weight))) /
          volatility ** 2
        : null,
  }));
  const sectors = {};
  selected.forEach(
    (a, i) =>
      (sectors[a.sector] = (sectors[a.sector] || 0) + weights[i].weight),
  );
  const pairs = [];
  for (let i = 0; i < matrix.length; i++)
    for (let j = i + 1; j < matrix.length; j++)
      if (finite(matrix[i][j])) pairs.push(matrix[i][j]);
  return {
    ...alignment,
    columns,
    weights,
    selected,
    returns,
    benchmarkReturns,
    covariance: cov,
    matrix,
    contributions,
    sectors,
    averageCorrelation: mean(pairs),
    stats: returnStats(returns, riskFree, benchmarkReturns),
    benchmarkStats: benchmarkReturns.length
      ? returnStats(benchmarkReturns, riskFree)
      : null,
    effectivePositions: 1 / sum(weights.map((p) => p.weight ** 2)),
  };
}
export function metrics(asset) {
  const f = asset.financials || {},
    value = (key) => f[key]?.value ?? null;
  const eps = earningsShareBasis(asset).blocked ? null : value("eps"),
    shares = value("shares"),
    revenue = value("revenue"),
    op = value("operating_income");
  const cfo = value("cfo"),
    capex = value("capex");
  const sameCashPeriod =
    f.cfo?.period_end &&
    f.cfo.period_end === f.capex?.period_end &&
    f.cfo.method === f.capex.method;
  const fcf =
    sameCashPeriod && finite(cfo) && finite(capex) ? cfo - capex : null;
  const marketCap = shares > 0 ? asset.price * shares : null;
  return {
    eps,
    shares,
    revenue,
    operatingIncome: op,
    cfo,
    capex,
    fcf,
    marketCap,
    pe: eps > 0 ? asset.price / eps : null,
    fcfYield:
      marketCap > 0 && finite(fcf) && asset.sector !== "Financiero"
        ? fcf / marketCap
        : null,
    fcfPerShare:
      shares > 0 && finite(fcf) && asset.sector !== "Financiero"
        ? fcf / shares
        : null,
    operatingMargin:
      revenue > 0 &&
      finite(op) &&
      f.revenue?.period_end === f.operating_income?.period_end
        ? op / revenue
        : null,
    sbcRevenue:
      revenue > 0 &&
      finite(value("sbc")) &&
      f.sbc?.period_end === f.revenue?.period_end
        ? value("sbc") / revenue
        : null,
    dividendYield:
      asset.price > 0 && finite(asset.dividend_per_share)
        ? asset.dividend_per_share / asset.price
        : null,
    cash: value("cash"),
    equity: value("equity"),
    longDebt: value("long_debt"),
    period: f.eps?.period_end || f.revenue?.period_end || null,
    filed: f.eps?.filed || f.revenue?.filed || null,
    periodType: f.eps?.method || f.revenue?.method || null,
  };
}
// Building-block convention for EXPECTED returns: the gap between the
// observed P/E and the generic sector reference closes with a 10-year
// half-life (practitioner capital-market assumptions use slow, partial
// reversion). It is a stated convention, not a calibrated estimate; full
// convergence and no reversion bound the uncertainty band instead. Fair
// value keeps the reference multiple: valuation() stays a pure function.
export const RERATING_HALF_LIFE_YEARS = 10;
/**
 * Merge default and user assumptions. A multiple the user sets explicitly is
 * honored as given; the default sector multiple is only a reference toward
 * which the observed P/E partially reverts over the valuation horizon.
 */
export function resolveAssumptions(asset, assumptions = {}, method = "pe") {
  const a = { ...asset.assumptions, ...assumptions };
  const eps = metrics(asset).eps, reference = asset.assumptions?.multiple;
  const explicit = finite(assumptions.multiple);
  if (explicit || method !== "pe" || !(eps > 0) || !(asset.price > 0) ||
      !(reference > 0) || !(a.horizon >= 1))
    return { ...a, rerating: { explicit, applied: false } };
  const current = asset.price / eps,
    share = 1 - 0.5 ** (a.horizon / RERATING_HALF_LIFE_YEARS),
    effective = current * (reference / current) ** share;
  return {
    ...a,
    multiple: effective,
    rerating: { explicit: false, applied: true, current, reference, effective,
      share, halfLife: RERATING_HALF_LIFE_YEARS },
  };
}
/** Additive split of an annualized valuation return; the parts sum exactly. */
export function returnDecomposition(result, base, price) {
  if (!result || !(base > 0) || !(price > 0)) return null;
  const a = result.assumptions, h = a.horizon,
    growth = (result.futureBase / base) ** (1 / h) - 1,
    rerating = (a.multiple / (price / base)) ** (1 / h) - 1,
    priceOnly = (1 + growth) * (1 + rerating) - 1;
  return { growth, rerating: priceOnly - growth,
    dividends: result.annualReturn - priceOnly, total: result.annualReturn };
}
export function valuation(asset, assumptions = {}, method = "pe") {
  const m = metrics(asset),
    a = { ...asset.assumptions, ...assumptions };
  const base = method === "fcf" ? m.fcfPerShare : m.eps;
  const growth = a.growth,
    multiple = a.multiple,
    discount = a.discount,
    horizon = a.horizon;
  if (
    !(
      base > 0 &&
      finite(growth) &&
      growth > -1 &&
      multiple > 0 &&
      finite(discount) &&
      discount > -1 &&
      horizon >= 1 &&
      horizon <= 10 &&
      asset.price > 0
    )
  )
    return null;
  const futureBase = base * (1 + growth) ** horizon,
    exitPrice = futureBase * multiple;
  const dividends = asset.dividend_per_share || 0;
  // Dividend per share is held flat. Buybacks are not added to avoid double counting.
  let pvDividends = 0;
  for (let t = 1; t <= horizon; t++)
    pvDividends += dividends / (1 + discount) ** t;
  const fairValue = exitPrice / (1 + discount) ** horizon + pvDividends;
  const annualReturn =
    ((exitPrice + dividends * horizon) / asset.price) ** (1 / horizon) - 1;
  return {
    fairValue,
    upside: fairValue / asset.price - 1,
    annualReturn,
    exitPrice,
    futureBase,
    dividends: dividends * horizon,
    assumptions: a,
    method,
    base,
  };
}
export function scenarios(asset, assumptions, method = "pe") {
  const a = { ...asset.assumptions, ...assumptions };
  return [
    {
      id: "bear",
      label: "Adverso",

      result: valuation(
        asset,
        {
          ...a,
          growth: Math.max(-0.5, a.growth - 0.07),
          multiple: a.multiple * 0.8,
        },
        method,
      ),
    },
    {
      id: "base",
      label: "Base",

      result: valuation(asset, a, method),
    },
    {
      id: "bull",
      label: "Favorable",

      result: valuation(
        asset,
        { ...a, growth: a.growth + 0.05, multiple: a.multiple * 1.15 },
        method,
      ),
    },
  ];
}
export const MAX_SNAPSHOT_ASSETS = 1000;
export function validateSnapshot(data) {
  if (
    data?.schema_version !== 1 ||
    !Array.isArray(data.assets) ||
    !data.assets.length ||
    data.assets.length > MAX_SNAPSHOT_ASSETS
  )
    throw new Error("El archivo no es un corte de Trading válido.");
  const symbols = new Set();
  for (const asset of data.assets) {
    if (
      !/^[A-Z0-9.^-]{1,12}$/.test(asset.symbol) ||
      symbols.has(asset.symbol) ||
      !(asset.price > 0) ||
      !Array.isArray(asset.history) ||
      asset.history.length < 21 ||
      asset.history.length > 10000
    )
      throw new Error("Hay activos o precios inválidos.");
    symbols.add(asset.symbol);
    let previous = "";
    for (const row of asset.history) {
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(row.date) ||
        row.date <= previous ||
        !finite(row.adj_close) ||
        row.adj_close <= 0 ||
        !finite(row.close) ||
        row.close <= 0
      )
        throw new Error(
          "La historia de precios contiene fechas o valores inválidos.",
        );
      previous = row.date;
    }
  }
  if (!Array.isArray(data.macro)) data.macro = [];
  return data;
}
