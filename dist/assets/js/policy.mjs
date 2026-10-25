import { finite, normalizeWeights, sum } from "./analytics.mjs?v=0.5.0";

export const MODEL_VERSION = "0.5.1";
export function informationDate(snapshot) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(new Date(snapshot.generated_at))
      .map((r) => [r.type, r.value]),
  );
  const observed = `${parts.year}-${parts.month}-${parts.day}`;
  return snapshot.requested_as_of && snapshot.requested_as_of < observed
    ? snapshot.requested_as_of
    : observed;
}
export const DEFAULT_MANDATE = {
  objective: "growth",
  referenceCurrency: "USD",
  horizon: 1,
  maxDrawdown: 0.25,
  maxDrawdownProbability: 0.25,
  minimumCash: 0.05,
  monthlyWithdrawal: 0,
  withdrawals: [],
  terminalTarget: 0,
  capitalFloor: 0,
  maxLiquidityFailure: 0.02,
  fxSpot: 1,
  fxAnnualChange: 0,
  fxVolatility: 0,
  fxMarketCorrelation: 0,
  fxConfirmed: false,
  benchmark: "SPY",
  riskAversion: 5,
};
export const DEFAULT_EXECUTION = {
  commissionFixed: 0,
  commissionBps: 0,
  spreadBps: 5,
  slippageBps: 2,
  capitalGainsTax: 0,
  maxTurnover: 1,
  minTrade: 25,
  minBenefit: 100,
  benefitCostRatio: 2,
};
export const DEFAULT_RESEARCH = {
  basis: "own",
  confidence: 0.6,
  priorReturn: 0.06,
  revenueGrowth: null,
  targetMargin: null,
  annualDilution: 0,
  consensusComparable: false,
  marginFloor: null,
  leverageCeiling: null,
  epsFloor: null,
  cashConversionFloor: null,
  maxDilution: null,
  thesis: "",
  invalidation: "",
  catalyst: "",
  reviewDate: "",
};
export const DEFAULT_REGIMES = [
  {
    id: "base",
    label: "Continuidad",
    probability: 0.55,
    earningsShift: 0,
    multipleShift: 0,
    rateShift: 0,
    rateJumpBps: -40,
  },
  {
    id: "recession",
    label: "Recesión",
    probability: 0.2,
    earningsShift: -0.07,
    multipleShift: -0.12,
    rateShift: -0.015,
    rateJumpBps: -80,
  },
  {
    id: "inflation",
    label: "Inflación persistente",
    probability: 0.15,
    earningsShift: -0.03,
    multipleShift: -0.15,
    rateShift: 0.015,
    rateJumpBps: 60,
  },
  {
    id: "expansion",
    label: "Expansión",
    probability: 0.1,
    earningsShift: 0.03,
    multipleShift: 0.05,
    rateShift: 0.005,
    rateJumpBps: -20,
  },
];
export const SECTOR_PROXIES = {
  Tecnología: "XLK",
  Comunicación: "XLC",
  "Consumo discrecional": "XLY",
  "Consumo básico": "XLP",
  Financiero: "XLF",
  Energía: "XLE",
  Salud: "XLV",
  Industrial: "XLI",
  "Servicios públicos": "XLU",
  Inmobiliario: "XLRE",
  Materiales: "XLB",
};

function range(value, low, high, label) {
  if (!finite(value) || value < low || value > high)
    throw new Error(`Revisa ${label}.`);
}
export function mandate(input = {}) {
  const value = { ...DEFAULT_MANDATE, ...input };
  if (!["growth", "preservation", "target"].includes(value.objective))
    throw new Error("Objetivo de inversión no válido.");
  if (!/^[A-Z]{3}$/.test(value.referenceCurrency))
    throw new Error("Moneda de referencia no válida.");
  range(value.horizon, 0.25, 5, "el horizonte");
  for (const key of [
    "maxDrawdown",
    "maxDrawdownProbability",
    "minimumCash",
    "maxLiquidityFailure",
  ])
    range(value[key], 0, 1, key);
  for (const key of ["monthlyWithdrawal", "terminalTarget", "capitalFloor"])
    range(value[key], 0, 1e12, key);
  range(value.riskAversion, 1, 20, "la aversión al riesgo");
  if (value.objective === "target" && !(value.terminalTarget > 0))
    throw new Error("Define el capital objetivo al final del horizonte.");
  if (value.referenceCurrency === "USD")
    Object.assign(value, {
      fxSpot: 1,
      fxAnnualChange: 0,
      fxVolatility: 0,
      fxMarketCorrelation: 0,
    });
  else {
    if (value.fxConfirmed !== true)
      throw new Error(
        "Confirma los supuestos cambiarios para la moneda de referencia.",
      );
    range(value.fxSpot, 0.00001, 1e6, "el tipo de cambio por USD");
    range(
      value.fxAnnualChange,
      -0.8,
      1,
      "la variación anual del tipo de cambio",
    );
    range(value.fxVolatility, 0, 1, "la volatilidad cambiaria");
    range(value.fxMarketCorrelation, -1, 1, "la correlación cambiaria");
  }
  if (!Array.isArray(value.withdrawals) || value.withdrawals.length > 120)
    throw new Error("Calendario de retiros no válido.");
  value.withdrawals = value.withdrawals
    .map((row) => {
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(row.date) ||
        !Number.isFinite(Date.parse(row.date)) ||
        new Date(row.date).toISOString().slice(0, 10) !== row.date
      )
        throw new Error("Fecha de retiro no válida.");
      range(row.amount, 0, 1e12, "el retiro");
      return { date: row.date, amount: row.amount };
    })
    .sort((a, b) => a.date.localeCompare(b.date));
  return value;
}
export function execution(input = {}) {
  const value = { ...DEFAULT_EXECUTION, ...input };
  for (const key of ["commissionFixed", "minTrade", "minBenefit"])
    range(value[key], 0, 1e7, key);
  for (const key of ["commissionBps", "spreadBps", "slippageBps"])
    range(value[key], 0, 1000, key);
  range(value.capitalGainsTax, 0, 1, "el impuesto supuesto");
  range(value.maxTurnover, 0, 1, "la rotación máxima");
  range(value.benefitCostRatio, 0, 100, "la relación beneficio/costo");
  return value;
}
export function regimes(input = DEFAULT_REGIMES) {
  if (!Array.isArray(input) || !input.length || input.length > 8)
    throw new Error("Escenarios macro no válidos.");
  const result = input.map((row) => ({ ...row }));
  for (const row of result) {
    range(row.probability, 0, 1, "la probabilidad del escenario");
    range(row.earningsShift, -0.5, 0.5, "el cambio de beneficios");
    range(row.multipleShift, -0.8, 1, "el cambio de múltiplo");
    range(row.rateShift, -0.1, 0.1, "el cambio de tasa");
    range(row.rateJumpBps, -500, 500, "el shock de tasas");
  }
  if (Math.abs(sum(result.map((row) => row.probability)) - 1) > 1e-6)
    throw new Error("Las probabilidades macro deben sumar 100%.");
  return result;
}
export function withCashAsset(snapshot) {
  if (snapshot.assets.some((asset) => asset.symbol === "CASH")) return snapshot;
  const reference =
    snapshot.assets.find((asset) => asset.symbol === "SPY") ||
    snapshot.assets[0];
  return {
    ...snapshot,
    assets: [
      ...snapshot.assets,
      {
        symbol: "CASH",
        name: "Efectivo USD",
        type: "cash",
        sector: "Efectivo",
        currency: "USD",
        price: 1,
        price_date: snapshot.price_as_of,
        change: 0,
        dividend_per_share: 0,
        financials: null,
        assumptions: { expectedReturn: 0 },
        history: reference.history.map((row) => ({
          date: row.date,
          close: 1,
          adj_close: 1,
          volume: 0,
        })),
        source_url: "https://github.com/Hardnyx/Trading",
        synthetic: true,
      },
    ],
  };
}
export function withdrawalSchedule(policy, asOf) {
  const start = Date.parse(asOf + "T12:00:00Z"),
    horizon = policy.horizon;
  const rows = policy.withdrawals.map((row) => ({
    year: (Date.parse(row.date + "T12:00:00Z") - start) / (365.25 * 86400000),
    amount: row.amount,
    date: row.date,
  }));
  for (let month = 1; month <= Math.floor(horizon * 12 + 1e-8); month++)
    if (policy.monthlyWithdrawal > 0)
      rows.push({
        year: month / 12,
        amount: policy.monthlyWithdrawal,
        date: null,
      });
  return rows
    .filter((row) => row.year > 0 && row.year <= horizon + 1e-8)
    .sort((a, b) => a.year - b.year);
}
export function currentAccount(snapshot, account, baseline, capital) {
  const lookup = new Map(snapshot.assets.map((asset) => [asset.symbol, asset]));
  if (account?.enabled) {
    if (
      !Array.isArray(account.positions) ||
      account.positions.length > 200 ||
      !finite(account.cash) ||
      account.cash < 0
    )
      throw new Error("Posiciones actuales no válidas.");
    const seen = new Set();
    const rows = account.positions.map((row) => {
      const asset = lookup.get(row.symbol);
      if (
        !asset ||
        row.symbol === "CASH" ||
        seen.has(row.symbol) ||
        !finite(asset.price) ||
        asset.price <= 0 ||
        !finite(row.quantity) ||
        row.quantity < 0 ||
        (row.costBasis != null && (!finite(row.costBasis) || row.costBasis < 0))
      )
        throw new Error("Cantidad o activo de la cuenta no válido.");
      seen.add(row.symbol);
      return { ...row, value: row.quantity * asset.price, price: asset.price };
    });
    const total = sum(rows.map((row) => row.value)) + account.cash;
    if (!(total > 0)) throw new Error("La cuenta necesita capital positivo.");
    return {
      capital: total,
      positions: [
        ...rows.map((row) => ({ ...row, weight: row.value / total })),
        {
          symbol: "CASH",
          weight: account.cash / total,
          quantity: account.cash,
          costBasis: 1,
          price: 1,
        },
      ].filter((row) => row.weight > 0),
      source: "Cantidades y efectivo ingresados",
    };
  }
  if (baseline?.positions?.length) {
    const rows = baseline.positions.map((row) => {
      const asset = lookup.get(row.symbol);
      if (!asset)
        throw new Error(
          `Falta ${row.symbol} para valorar la cartera registrada.`,
        );
      return {
        ...row,
        value: (() => {
          const origin = asset.history.find((r) => r.date === baseline.as_of);
          if (!(origin?.adj_close > 0))
            throw new Error(
              `Falta el precio ajustado de origen de ${row.symbol}; importa las cantidades actuales.`,
            );
          return (
            (baseline.capital * row.weight * asset.history.at(-1).adj_close) /
            origin.adj_close
          );
        })(),
        price: asset.price,
        costBasis: finite(row.costBasis) ? row.costBasis : null,
      };
    });
    const total = sum(rows.map((row) => row.value));
    return {
      capital: total,
      positions: rows.map((row) => ({ ...row, weight: row.value / total })),
      source:
        "Referencia teórica de retorno ajustado; sin conciliación con el broker",
    };
  }
  if (!finite(capital) || capital <= 0)
    throw new Error("Capital inicial no válido.");
  return {
    capital,
    positions: [{ symbol: "CASH", weight: 1, price: 1, costBasis: 1 }],
    source: "Capital inicial en efectivo",
  };
}
export function tradePlan(assets, target, current, capital, assumptions = {}) {
  const costs = execution(assumptions),
    lookup = new Map(assets.map((asset) => [asset.symbol, asset]));
  if (!finite(capital) || capital <= 0)
    throw new Error("Capital de ejecución no válido.");
  const validate = (rows) => {
    if (
      !Array.isArray(rows) ||
      !rows.length ||
      rows.some((r) => !finite(r.weight) || r.weight < 0) ||
      new Set(rows.map((r) => r.symbol)).size !== rows.length ||
      Math.abs(sum(rows.map((r) => r.weight)) - 1) > 1e-7
    )
      throw new Error("Pesos de ejecución no válidos.");
    return new Map(rows.map((row) => [row.symbol, row]));
  };
  const before = validate(current),
    after = validate(target);
  const symbols = [...new Set([...before.keys(), ...after.keys()])];
  const quote = (reserve) => {
    const rows = [];
    let total = 0,
      turnover = 0,
      taxComplete = true;
    for (const symbol of symbols) {
      const old = before.get(symbol),
        weight = after.get(symbol)?.weight || 0;
      const dollarChange =
        weight * (capital - reserve) - (old?.weight || 0) * capital;
      turnover += Math.abs(dollarChange) / (2 * capital);
      if (symbol === "CASH" || Math.abs(dollarChange) < 1e-7) continue;
      const asset = lookup.get(symbol);
      if (!asset || !finite(asset.price) || asset.price <= 0)
        throw new Error(`Falta precio para estimar el cambio en ${symbol}.`);
      const notional = Math.abs(dollarChange),
        commission =
          costs.commissionFixed + (notional * costs.commissionBps) / 1e4;
      const spread = (notional * costs.spreadBps) / 2e4,
        slippage = (notional * costs.slippageBps) / 1e4;
      let tax = 0;
      if (dollarChange < 0 && costs.capitalGainsTax > 0) {
        if (!finite(old?.costBasis) || old.costBasis < 0) taxComplete = false;
        else
          tax =
            ((Math.max(0, asset.price - old.costBasis) * notional) /
              asset.price) *
            costs.capitalGainsTax;
      }
      const cost = commission + spread + slippage + tax;
      total += cost;
      rows.push({
        symbol,
        side: dollarChange > 0 ? "buy" : "sell",
        from: old?.weight || 0,
        to: weight,
        delta: dollarChange / capital,
        notional,
        quantity: notional / asset.price,
        commission,
        spread,
        slippage,
        tax,
        cost,
        small: notional < costs.minTrade,
      });
    }
    return { rows, total, turnover, taxComplete };
  };
  let reserve = 0,
    result = quote(0);
  for (let i = 0; i < 60 && Math.abs(result.total - reserve) > 1e-7; i++) {
    reserve = result.total;
    if (reserve >= capital) break;
    result = quote(reserve);
  }
  if (Math.abs(result.total - reserve) > 1e-6) {
    let low = 0,
      high = capital;
    for (let i = 0; i < 70; i++) {
      reserve = (low + high) / 2;
      result = quote(reserve);
      if (result.total > reserve) low = reserve;
      else high = reserve;
    }
  }
  const budgetResidual = result.total - reserve,
    investableCapital = capital - reserve;
  const ending = target.map((row) => ({
    ...row,
    value: row.weight * investableCapital,
  }));
  return {
    ...result,
    investableCapital,
    ending,
    budgetResidual,
    complete:
      result.taxComplete &&
      investableCapital > 0 &&
      Math.abs(budgetResidual) < 1e-5,
    smallTrades: result.rows.filter((row) => row.small).length,
    assumptions: costs,
  };
}
