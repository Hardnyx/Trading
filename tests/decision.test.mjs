import test from "node:test";
import assert from "node:assert/strict";
import {
  mandate,
  currentAccount,
  tradePlan,
  withCashAsset,
} from "../dist/assets/js/policy.mjs?v=0.5.3";
import {
  fundamentalForecast,
  consensusAt,
  evaluateThesis,
} from "../dist/assets/js/research-model.mjs?v=0.5.3";
import {
  valuation,
  correlation,
  mean,
} from "../dist/assets/js/analytics.mjs?v=0.5.3";
import { sampleDrifts } from "../dist/assets/js/return-model.mjs?v=0.5.3";
import {
  seededRandom,
  normalGenerator,
} from "../dist/assets/js/random.mjs?v=0.5.3";
import {
  generatePaths,
  evaluatePaths,
  BASE_REGIME,
  jumpParameters,
} from "../dist/assets/js/path-model.mjs?v=0.5.3";
import {
  journalOrigin,
  appendForecast,
  evaluateJournal,
  freezeMaturedOutcomes,
} from "../dist/assets/js/journal.mjs?v=0.5.3";
import {
  reviewPortfolio,
  registerPortfolio,
} from "../dist/assets/js/monitor.mjs?v=0.5.3";

const near = (a, b, tol = 1e-8) =>
  assert.ok(Math.abs(a - b) < tol, `${a} != ${b}`);
function stock() {
  const f = (value) => ({
    value,
    period_end: "2026-06-30",
    filed: "2026-08-01",
    method: "TTM",
  });
  return {
    symbol: "AAA",
    name: "AAA",
    type: "stock",
    sector: "Tecnología",
    price: 100,
    price_date: "2026-10-23",
    dividend_per_share: 2,
    assumptions: { growth: 0.07, multiple: 15, discount: 0.1, horizon: 3 },
    financials: {
      eps: f(10),
      revenue: f(1000),
      net_income: f(100),
      operating_income: f(150),
      cfo: f(120),
      capex: f(20),
      long_debt: f(200),
      current_debt: f(10),
      cash: f(50),
    },
    history: Array.from({ length: 301 }, (_, i) => ({
      date: new Date(Date.UTC(2026, 9, 23) - (300 - i) * 86400000)
        .toISOString()
        .slice(0, 10),
      close: 100,
      adj_close: 100,
    })),
  };
}
function snapshot() {
  return withCashAsset({
    price_as_of: "2026-10-23",
    generated_at: "2026-10-24T00:00:00Z",
    assets: [stock()],
    macro: [],
  });
}
function inputs(assets, anchors, options = {}) {
  return {
    assets,
    anchors,
    covariance: assets.map(() => assets.map(() => 0)),
    regimes: [BASE_REGIME],
    options: {
      model: "gbm",
      horizon: 1,
      seed: 1,
      driftMode: "manual",
      uncertainFundamentals: false,
      manualReturn: 0,
      jumpIntensity: 0,
      jumpMean: -0.2,
      jumpVol: 0.1,
      asOf: "2026-10-23",
      ...options,
    },
  };
}
const anchor = (annual) => ({ annual, low: annual, high: annual });

test("a forecast rejects future filings and nonfinite subjective inputs", () => {
  const a = stock();
  assert.equal(
    fundamentalForecast(a, {}, {}, { asOf: "2026-01-01" }).valid,
    false,
  );
  assert.equal(fundamentalForecast(a, {}, { confidence: NaN }).valid, false);
  assert.equal(fundamentalForecast(a, {}, { priorReturn: 3 }).valid, false);
  const p = fundamentalForecast(a, {}, { confidence: 0, priorReturn: 2 });
  assert.equal(p.valid, true);
  assert.ok(p.low <= p.central && p.central <= p.high);
});
test("price-implied growth inverts the same dividend PV equation as valuation", () => {
  const a = stock();
  a.price = valuation(a).fairValue;
  const p = fundamentalForecast(a);
  near(p.impliedGrowth, a.assumptions.growth);
});
test("consensus keeps row currency and basis during interpolation and rejects incompatible data", () => {
  const a = stock();
  a.analyst_estimates = {
    observed_at: "2026-10-23T19:00:00Z",
    periods: [
      {
        period_end: "2028-12-31",
        frequency: "annual",
        eps_mean: 12,
        eps_basis: "non_gaap",
        currency: "USD",
      },
      {
        period_end: "2029-12-31",
        frequency: "annual",
        eps_mean: 14,
        eps_basis: "non_gaap",
        currency: "USD",
      },
    ],
  };
  const r = {
    consensusComparable: true,
    comparableEPS: 10,
    consensusBasis: "non_gaap",
  };
  const result = consensusAt(a, "2029-06-30", "2026-10-23", r);
  assert.equal(result.basis, "non_gaap");
  assert.ok(result.eps_mean > 12 && result.eps_mean < 14);
  a.analyst_estimates.periods[1].eps_basis = "gaap";
  assert.ok(consensusAt(a, "2029-06-30", "2026-10-23", r).error);
});
test("thesis thresholds distinguish contradictory evidence from missing evidence", () => {
  assert.equal(
    evaluateThesis(stock(), { marginFloor: 0.2 }).status,
    "contradicted",
  );
  const a = stock();
  delete a.financials.operating_income;
  assert.equal(evaluateThesis(a, { marginFloor: 0.2 }).status, "insufficient");
});
test("mandate rejects invalid calendar dates and unconfirmed foreign exchange assumptions", () => {
  assert.throws(() =>
    mandate({ withdrawals: [{ date: "2026-02-31", amount: 100 }] }),
  );
  assert.throws(() => mandate({ referenceCurrency: "PEN" }));
  assert.equal(
    mandate({ referenceCurrency: "PEN", fxConfirmed: true, fxSpot: 3.8 })
      .fxSpot,
    3.8,
  );
});
test("account rejects nonfinite cash, duplicates and a duplicated cash position", () => {
  const s = snapshot();
  assert.throws(() =>
    currentAccount(
      s,
      { enabled: true, cash: Infinity, positions: [] },
      null,
      100,
    ),
  );
  assert.throws(() =>
    currentAccount(
      s,
      {
        enabled: true,
        cash: 100,
        positions: [{ symbol: "CASH", quantity: 1 }],
      },
      null,
      100,
    ),
  );
});
test("costs fund themselves and HOLD incurs no phantom commission", () => {
  const assets = snapshot().assets,
    current = [{ symbol: "CASH", weight: 1 }],
    target = [
      { symbol: "AAA", weight: 0.6 },
      { symbol: "CASH", weight: 0.4 },
    ];
  const plan = tradePlan(assets, target, current, 100000, {
    commissionFixed: 1,
  });
  assert.equal(plan.complete, true);
  near(plan.total, 27.99244204, 1e-6);
  near(plan.ending.reduce((s, r) => s + r.value, 0) + plan.total, 100000, 1e-5);
  const hold = tradePlan(assets, target, target, 100000, {
    commissionFixed: 10,
  });
  assert.equal(hold.total, 0);
  assert.equal(hold.rows.length, 0);
});
test("a taxed sale requires cost basis and charges realized gains exactly once", () => {
  const assets = snapshot().assets,
    target = [{ symbol: "CASH", weight: 1 }];
  const unknown = tradePlan(
    assets,
    target,
    [{ symbol: "AAA", weight: 1 }],
    1000,
    { capitalGainsTax: 0.3 },
  );
  assert.equal(unknown.complete, false);
  const known = tradePlan(
    assets,
    target,
    [{ symbol: "AAA", weight: 1, costBasis: 20 }],
    1000,
    { capitalGainsTax: 0.3, commissionFixed: 1 },
  );
  near(known.rows[0].tax, 240);
  near(known.total, 241.45);
  near(known.ending[0].value + known.total, 1000);
});
test("fundamental uncertainty has market, sector and independent company components", () => {
  const anchors = [
    { sector: "A", low: -0.1, annual: 0, high: 0.1 },
    { sector: "A", low: -0.1, annual: 0, high: 0.1 },
    { sector: "B", low: -0.1, annual: 0, high: 0.1 },
  ];
  const random = seededRandom(4),
    normal = normalGenerator(random),
    columns = [[], [], []];
  for (let p = 0; p < 6000; p++) {
    const draws = sampleDrifts(anchors, {}, random, normal);
    draws.forEach((x, i) => columns[i].push(x));
  }
  assert.ok(
    correlation(columns[0], columns[1]) >
      correlation(columns[0], columns[2]) + 0.2,
  );
  assert.ok(correlation(columns[0], columns[1]) < 0.9);
  assert.throws(() =>
    sampleDrifts(
      anchors,
      { fundamentalMarketShare: 0.9, fundamentalSectorShare: 0.9 },
      random,
    ),
  );
});
test("asset-specific jump compensation preserves each conditional mean and cash never jumps", () => {
  const assets = [
      { symbol: "A", type: "stock" },
      { symbol: "B", type: "stock" },
      { symbol: "CASH", type: "cash" },
    ],
    x = inputs(assets, [anchor(0.1), anchor(0.1), anchor(0)], {
      model: "merton",
      jumpIntensity: 0.8,
      assetAssumptions: { A: { jumpLoading: 0.5 }, B: { jumpLoading: 2 } },
    });
  const sample = generatePaths(x, 10000, 112, 12);
  for (let i = 0; i < 2; i++) {
    const terminal = Array.from(
      { length: sample.paths },
      (_, p) => sample.gross[i][p * (sample.steps + 1) + sample.steps] - 1,
    );
    near(mean(terminal), 0.1, 0.02);
  }
  assert.ok(sample.gross[2].every((v) => v === 1));
  assert.equal(
    jumpParameters(assets[2], anchor(0), x.options, BASE_REGIME).compensator,
    0,
  );
});
test("bond rate scenarios use duration instead of the equity jump", () => {
  const assets = [{ symbol: "SHY", type: "etf" }],
    a = { ...anchor(0.04), bond: { duration: 2 } },
    x = inputs(assets, [a]);
  x.regimes = [{ ...BASE_REGIME, rateShift: 0.01, rateJumpBps: 100 }];
  const sample = generatePaths(x, 100, 4, 12);
  near(sample.gross[0][sample.steps], 1.04 * Math.exp(-0.02));
  const j = jumpParameters(assets[0], a, x.options, x.regimes[0]);
  near(j.mean, -0.02);
});
test("withdrawals change funding wealth without creating investment drawdown", () => {
  const assets = [{ symbol: "CASH", type: "cash", price_date: "2026-10-23" }],
    x = inputs(assets, [anchor(0)], {
      horizon: 0.25,
      mandate: { monthlyWithdrawal: 10 },
    }),
    sample = generatePaths(x, 100, 2, 52),
    result = evaluatePaths([1], sample, { capital: 100 });
  near(result.meanReturn, 0);
  near(result.medianTerminalWealth, 70);
  near(result.worstDrawdownP05, 0);
  assert.equal(result.liquidityFailureProbability, 0);
  const insufficient = evaluatePaths(
    [1],
    generatePaths(
      { ...x, options: { ...x.options, mandate: { monthlyWithdrawal: 40 } } },
      100,
      2,
      52,
    ),
    { capital: 100 },
  );
  assert.equal(insufficient.liquidityFailureProbability, 1);
});
test("foreign exchange compounds multiplicatively into the reference-currency return", () => {
  const x = inputs([{ symbol: "CASH", type: "cash" }], [anchor(0)], {
      mandate: {
        referenceCurrency: "PEN",
        fxSpot: 4,
        fxAnnualChange: 0.1,
        fxConfirmed: true,
      },
    }),
    r = evaluatePaths([1], generatePaths(x, 100, 4, 12), { capital: 100 });
  near(r.meanReturn, 0.1);
  near(r.medianTerminalWealth, 440);
});
test("journal origins remain immutable and score only matured prospective forecasts", () => {
  const s = snapshot(),
    settings = { horizon: 0.01, model: "gbm", capital: 100000 },
    origin = journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      settings,
      {},
      {},
      "2026-10-24T01:00:00Z",
    ),
    prediction = {
      horizonYears: 0.01,
      meanReturn: 0.05,
      medianReturn: 0.04,
      p05: -0.1,
      p95: 0.2,
      lossProbability: 0.2,
      settings: { model: "gbm", seed: 1 },
      drifts: [],
    };
  const journal = appendForecast([], origin, prediction);
  origin.positions[0].weight = 0;
  assert.equal(journal[0].origin.positions[0].weight, 1);
  assert.equal(evaluateJournal(journal, s).count, 0);
  const future = structuredClone(s);
  future.price_as_of = "2026-10-30";
  future.assets[0].history.push({
    date: "2026-10-28",
    close: 110,
    adj_close: 110,
  });
  const result = evaluateJournal(journal, future);
  assert.equal(result.count, 1);
  near(result.rows[0].realized, 0.1);
  near(result.brier, 0.04);
  const historical = journalOrigin(
    s,
    [{ symbol: "AAA", weight: 1 }],
    settings,
    {},
    {},
    "2026-12-24T01:00:00Z",
  );
  assert.equal(
    evaluateJournal(appendForecast([], historical, prediction), future).count,
    0,
  );
});
test("a split does not become a fictitious monitored loss", () => {
  const s = snapshot(),
    baseline = registerPortfolio(
      s,
      [{ symbol: "AAA", weight: 1 }],
      10000,
      {},
      "2026-10-24T00:00:00Z",
    ),
    next = structuredClone(s);
  next.price_as_of = "2026-10-26";
  next.assets[0].history.at(-1).adj_close = 50;
  next.assets[0].history.push({ date: "2026-10-26", close: 50, adj_close: 50 });
  next.assets[0].price = 50;
  next.assets[0].price_date = "2026-10-26";
  near(reviewPortfolio(next, baseline).totalReturn, 0);
});

test("capital floors also apply immediately after planned withdrawals", () => {
  const x = inputs([{ symbol: "CASH", type: "cash" }], [anchor(0)], {
    horizon: 0.25,
    mandate: { monthlyWithdrawal: 10, capitalFloor: 80 },
  });
  const result = evaluatePaths([1], generatePaths(x, 100, 1, 52), {
    capital: 100,
  });
  assert.equal(result.capitalFloorBreachProbability, 1);
});
test("opposite systemic loadings preserve the sign of their shared jump innovation", () => {
  const x = inputs(
    [
      { symbol: "A", type: "stock" },
      { symbol: "B", type: "stock" },
    ],
    [anchor(0), anchor(0)],
    {
      model: "merton",
      jumpIntensity: 1,
      jumpMean: 0,
      jumpVol: 0.2,
      assetAssumptions: { A: { jumpLoading: 1 }, B: { jumpLoading: -1 } },
    },
  );
  const sample = generatePaths(x, 3000, 91, 12),
    logs = sample.gross.map((c) =>
      Array.from({ length: sample.paths }, (_, p) =>
        Math.log(c[p * (sample.steps + 1) + sample.steps]),
      ),
    );
  near(correlation(logs[0], logs[1]), -1, 1e-8);
});

test("stale closing prices after intervening sessions are excluded from prospective scoring", () => {
  const s = snapshot();
  assert.equal(
    journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      {},
      {},
      {},
      "2026-10-28T00:00:00Z",
    ).prospective,
    false,
  );
  assert.equal(
    journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      {},
      {},
      {},
      "2026-10-26T12:00:00Z",
    ).prospective,
    true,
  );
  assert.equal(
    journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      {},
      {},
      {},
      "2026-10-26T14:00:00Z",
    ).prospective,
    false,
  );
});
test("mature forecasts with unverified withdrawal realizations are not assigned a false score", () => {
  const s = snapshot(),
    origin = journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      { mandate: { monthlyWithdrawal: 10 } },
      {},
      {},
      "2026-10-24T01:00:00Z",
    ),
    prediction = {
      horizonYears: 0.001,
      meanReturn: 0,
      medianReturn: 0,
      p05: -0.1,
      p95: 0.1,
      lossProbability: 0.5,
      settings: { model: "gbm", seed: 1 },
      drifts: [],
    };
  const journal = appendForecast([], origin, prediction);
  s.price_as_of = "2026-11-01";
  const result = evaluateJournal(journal, s);
  assert.equal(result.count, 0);
  assert.equal(result.rows[0].status, "unreconciled_flows");
});
test("a nonzero FX-market correlation requires an observed market factor", () => {
  const x = inputs([{ symbol: "AAA", type: "stock" }], [anchor(0)], {
    mandate: {
      referenceCurrency: "PEN",
      fxConfirmed: true,
      fxSpot: 4,
      fxVolatility: 0.2,
      fxMarketCorrelation: 0.5,
    },
  });
  assert.throws(() => generatePaths(x, 100, 1, 12), /SPY/);
});
test("execution costs cannot conceal a capital-floor violation at inception", () => {
  const x = inputs([{ symbol: "AAA", type: "stock" }], [anchor(0.5)], {
    mandate: { capitalFloor: 100 },
  });
  const result = evaluatePaths([1], generatePaths(x, 100, 2, 12), {
    capital: 100,
    cost: 1,
  });
  assert.equal(result.capitalFloorBreachProbability, 1);
});

test("new forecasts do not discard old origins before a long horizon matures", () => {
  const s = snapshot(),
    origin = journalOrigin(
      s,
      [{ symbol: "AAA", weight: 1 }],
      {},
      {},
      {},
      "2026-10-24T01:00:00Z",
    );
  const prediction = {
    horizonYears: 3,
    meanReturn: 0.1,
    medianReturn: 0.1,
    p05: -0.2,
    p95: 0.3,
    lossProbability: 0.2,
    settings: { model: "gbm", seed: 1 },
    drifts: [],
  };
  const older = Array.from({ length: 130 }, (_, i) => ({ id: "older-" + i }));
  const result = appendForecast(older, origin, prediction);
  assert.equal(result.length, 131);
  assert.equal(result[0].id, "older-0");
});
