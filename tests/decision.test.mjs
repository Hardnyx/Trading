import test from "node:test";
import assert from "node:assert/strict";
import {
  mandate,
  currentAccount,
  tradePlan,
  withCashAsset,
  regimes,
  DEFAULT_REGIMES,
} from "../dist/assets/js/policy.mjs?v=0.27.0";
import {
  fundamentalForecast,
  consensusAt,
  evaluateThesis,
  bondAssumptions,
  CREDIT_CONVENTIONS,
} from "../dist/assets/js/research-model.mjs?v=0.27.0";
import {
  valuation,
  correlation,
  mean,
  resolveAssumptions,
  returnDecomposition,
  RERATING_HALF_LIFE_YEARS,
} from "../dist/assets/js/analytics.mjs?v=0.27.0";
import { sampleDrifts, bondScenarioAnnualReturn, buildReturnAnchors, holdingsAnchor, constituentForecasts, HOLDINGS_ANCHOR_MIN_COVERAGE, centeredTriangularQuantile, bondRegimeShift } from "../dist/assets/js/return-model.mjs?v=0.27.0";
import {
  seededRandom,
  normalGenerator,
} from "../dist/assets/js/random.mjs?v=0.27.0";
import {
  generatePaths,
  evaluatePaths,
  BASE_REGIME,
  jumpParameters,
  regimeCondition,
  centeredRegimeConditions,
} from "../dist/assets/js/path-model.mjs?v=0.27.0";
import {
  journalOrigin,
  appendForecast,
  evaluateJournal,
  freezeMaturedOutcomes,
} from "../dist/assets/js/journal.mjs?v=0.27.0";
import {
  reviewPortfolio,
  registerPortfolio,
} from "../dist/assets/js/monitor.mjs?v=0.27.0";

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
test("bond rates change total return through duration and convexity, not fixed yield",()=>{
  const shy={carry:.045,duration:1.8};
  near(bondScenarioAnnualReturn(shy,0,1),.045);
  assert.ok(bondScenarioAnnualReturn(shy,.015,1)<shy.carry);
  assert.ok(bondScenarioAnnualReturn(shy,-.015,1)>shy.carry);
  near(1+bondScenarioAnnualReturn(shy,.015,1),
    (1+shy.carry)*(1-1.8*.015+.5*1.8*2.8*.015**2));
  assert.throws(()=>bondScenarioAnnualReturn(shy,NaN,1),/inválido/);
});

test("bond rate scenarios use duration instead of the equity jump", () => {
  const assets = [{ symbol: "SHY", type: "etf" }],
    a = { ...anchor(0.04), bond: { duration: 2 } },
    x = inputs(assets, [a]);
  // Two equally likely rate scenarios: each path gets the duration/convexity
  // effect of its scenario, centered so the anchor stays the expected return.
  const up = { ...BASE_REGIME, id: "up", probability: .5, rateShift: 0.01, rateJumpBps: 100 },
    down = { ...BASE_REGIME, id: "down", probability: .5, rateShift: -0.01, rateJumpBps: -100 };
  x.regimes = [up, down];
  const cUp = Math.log(1 - 2 * .01 + .5 * 2 * 3 * .01**2),
    cDown = Math.log(1 + 2 * .01 + .5 * 2 * 3 * .01**2),
    centre = Math.log(.5 * Math.exp(cUp) + .5 * Math.exp(cDown));
  near(regimeCondition(assets[0], a, up, 1), cUp);
  const sample = generatePaths(x, 400, 4, 12);
  const terminal = Array.from({ length: sample.paths }, (_, p) =>
    sample.gross[0][p * (sample.steps + 1) + sample.steps]);
  for (const value of terminal)
    assert.ok(Math.abs(value - 1.04 * Math.exp(cUp - centre)) < 1e-9 ||
      Math.abs(value - 1.04 * Math.exp(cDown - centre)) < 1e-9);
  near(terminal.reduce((s, v) => s + v, 0) / terminal.length, 1.04, 0.002);
  // Two years: each scenario compounds its condition, the mean stays 1.04².
  const x2 = inputs(assets, [a], { horizon: 2 });
  x2.regimes = [up, down];
  const long = generatePaths(x2, 400, 4, 12);
  const terminal2 = Array.from({ length: long.paths }, (_, p) =>
    long.gross[0][p * (long.steps + 1) + long.steps]);
  near(terminal2.reduce((s, v) => s + v, 0) / terminal2.length, 1.04 ** 2, 0.003);
  const j = jumpParameters(assets[0], a, x.options, up);
  near(j.mean, -0.02);
});
test("centered scenario conditions match the simulation and keep the gross mean", () => {
  const asset = { symbol: "TLT", type: "etf" },
    a = { ...anchor(0.045), bond: { carry: .045, duration: 16 } },
    macro = [
      { ...BASE_REGIME, id: "up", probability: .3, rateShift: 0.01 },
      { ...BASE_REGIME, id: "down", probability: .7, rateShift: -0.005 },
    ];
  // The terminal mean is preserved at every horizon, not only at one year:
  // bonds and equities (EPS growth 12%) under the default scenarios.
  const defaults = regimes(DEFAULT_REGIMES),
    equity = [{ symbol: "EQ", type: "stock" }, { ...anchor(.08), forecast: { equivalentGrowth: .12 } }];
  for (const H of [0.25, 0.5, 1, 2, 3, 5])
    for (const [who, law, rows] of [[asset, a, macro], [asset, a, defaults], [...equity, defaults]]) {
      const c = centeredRegimeConditions(who, law, rows, H);
      near(rows.reduce((s, r, k) => s + r.probability * Math.exp(H * c[k]), 0), 1, 1e-12);
    }
  const centered = centeredRegimeConditions(asset, a, macro, 5);
  for (const [k, r] of macro.entries())
    near(centered[k] - centered[0],
      regimeCondition(asset, a, r, 5) - regimeCondition(asset, a, macro[0], 5));
  // Uncentered regime returns would put both bounds of TLT on one side of carry.
  const bounds = centered.map((c) => Math.expm1(Math.log1p(.045) + c));
  assert.ok(Math.min(...bounds) < .045 && Math.max(...bounds) > .045);
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
test("local journal keeps the simulated dividend policy and refuses mismatched total-return scores",()=>{
 for(const policy of [{dividendPolicy:"cash",dividendWithholding:0},
   {dividendPolicy:"reinvest",dividendWithholding:.3}]) {
   const s=snapshot(),origin=journalOrigin(s,[{symbol:"AAA",weight:1}],{},{},{},
     "2026-10-24T01:00:00Z");
   const prediction={horizonYears:.001,meanReturn:0,medianReturn:0,
     p05:-.1,p95:.1,lossProbability:.5,settings:{model:"gbm",seed:1},
     drifts:[],policy};
   const journal=appendForecast([],origin,prediction);
   assert.deepEqual(journal[0].cashflow_policy,policy);
   s.price_as_of="2026-11-01";
   const result=evaluateJournal(journal,s);
   assert.equal(result.count,0);
   assert.equal(result.rows[0].status,"unreconciled_distributions");
 }
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

test("expected returns close only part of the gap to the sector multiple", () => {
  const a = stock(); // P/E 10, sector reference 15, three-year horizon
  const resolved = resolveAssumptions(a);
  const share = 1 - 0.5 ** (3 / RERATING_HALF_LIFE_YEARS);
  assert.ok(Math.abs(resolved.rerating.share - share) < 1e-12);
  assert.ok(Math.abs(resolved.multiple - 10 * 1.5 ** share) < 1e-12);
  assert.ok(resolved.multiple > 10 && resolved.multiple < 15);
  // An explicit multiple is the user's view and is honored as given.
  assert.equal(resolveAssumptions(a, { multiple: 15 }).multiple, 15);
  assert.equal(resolveAssumptions(a, { multiple: 15 }).rerating.explicit, true);
  // FCF multiples are not compared with a P/E reference.
  assert.equal(resolveAssumptions(a, {}, "fcf").multiple, 15);
  // Fair value keeps the reference multiple.
  assert.equal(valuation(a).assumptions.multiple, 15);

  const p = fundamentalForecast(a, {}, { confidence: 1, priorReturn: 0 });
  const full = valuation(a, { multiple: 15 }).annualReturn;
  const none = valuation(a, { multiple: 10 }).annualReturn;
  assert.ok(p.model.annualReturn > none && p.model.annualReturn < full);
  assert.ok(p.low <= none + 1e-12 && p.high >= full - 1e-12,
    "no reversion and full convergence must bound the band");
  const d = p.decomposition;
  assert.ok(Math.abs(d.growth + d.rerating + d.dividends - p.model.annualReturn) < 1e-12);
  assert.ok(Math.abs(d.growth - 0.07) < 1e-12);
  assert.ok(d.rerating > 0 && d.rerating < (1.5 ** (1 / 3) - 1) * 1.07);
  // The price-implied growth still inverts the fair-value equation.
  const fair = { ...a, price: valuation(a).fairValue };
  assert.ok(Math.abs(fundamentalForecast(fair).impliedGrowth - 0.07) < 1e-9);
  // An expensive stock gets partial, not full, multiple contraction.
  const rich = { ...a, price: 250 };
  const contraction = fundamentalForecast(rich, {}, { confidence: 1, priorReturn: 0 });
  assert.ok(contraction.decomposition.rerating < 0);
  assert.ok(contraction.model.annualReturn > valuation(rich).annualReturn);
});

test("return decomposition rejects missing inputs", () => {
  assert.equal(returnDecomposition(null, 10, 100), null);
  assert.equal(returnDecomposition(valuation(stock()), 0, 100), null);
});

test("equity ETFs take a building-block anchor from dated holdings", () => {
  const a = stock(); // AAA, valid own-forecast anchor
  const b = { ...stock(), symbol: "BBB", price: 80 };
  const etf = (positions, as_of = "2026-10-20", observed_at = "2026-10-21T02:00:00Z") => ({
    symbol: "FFF", type: "etf", sector: "Índice amplio", price: 50, price_date: "2026-10-23",
    history: [], holdings: { as_of, observed_at, positions },
  });
  const settings = { asOf: "2026-10-23", informationAsOf: "2026-10-23" };
  const universe = [a, b];
  const lookup = constituentForecasts(universe, settings, {});
  const fa = lookup("AAA"), fb = lookup("BBB");
  assert.ok(fa && fb);
  // 50% AAA + 30% BBB covered; 20% outside the universe takes the 6% prior.
  const anchor = holdingsAnchor(etf([{ symbol: "AAA", weight: .5 }, { symbol: "BBB", weight: .3 }, { symbol: "ZZZ", weight: .2 }]), lookup, settings);
  const covered = (.5 * fa.central + .3 * fb.central) / .8;
  assert.ok(Math.abs(anchor.annual - (.8 * covered + .2 * .06)) < 1e-12);
  assert.ok(Math.abs(anchor.low - (.8 * (.5 * fa.low + .3 * fb.low) / .8 + .2 * (.06 - .15))) < 1e-12);
  assert.equal(anchor.coverage, .8);
  assert.match(anchor.source, /80% del peso con ancla propia de 2 acciones/);
  // Below the coverage rule, stale or future holdings: no anchor.
  assert.ok(HOLDINGS_ANCHOR_MIN_COVERAGE >= .7);
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .6 }, { symbol: "ZZZ", weight: .4 }]), lookup, settings), null);
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .9 }], "2026-05-01"), lookup, settings), null);
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .9 }], "2026-10-24"), lookup, settings), null);
  // Dated before the cut but first observed after it, unobserved, or with
  // duplicated constituents: the same rejection as the exposure report.
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .9 }], "2026-10-20", "2026-10-28T02:00:00Z"), lookup, settings), null);
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .9 }], "2026-10-20", null), lookup, settings), null);
  assert.equal(holdingsAnchor(etf([{ symbol: "AAA", weight: .45 }, { symbol: "AAA", weight: .45 }]), lookup, settings), null);
  // The anchor builder uses it, and an explicit user expectation still wins.
  const fund = etf([{ symbol: "AAA", weight: .9 }, { symbol: "ZZZ", weight: .1 }]);
  const [built] = buildReturnAnchors([fund], settings, {}, universe);
  assert.ok(Math.abs(built.annual - (.9 * fa.central + .1 * .06)) < 1e-12);
  assert.equal(built.holdingsCoverage, .9);
  const [own] = buildReturnAnchors([fund], { ...settings, assetAssumptions: { FFF: { expectedReturn: .03, uncertainty: .05 } } }, {}, universe);
  assert.equal(own.annual, .03);
  assert.equal(own.holdingsCoverage, null);
});

test("drift uncertainty keeps the anchor as its mean, also when the band is skewed", () => {
  const mean = (low, anchor, high) => {
    let total = 0; const n = 20000;
    for (let k = 0; k < n; k++) total += centeredTriangularQuantile((k + .5) / n, low, anchor, high);
    return total / n;
  };
  near(mean(-.148, .062, .216), .062, 1e-6);
  near(mean(-.30, .10, .12), .10, 1e-6); // mode clipped at the top: shifted, still centered
  near(centeredTriangularQuantile(.3, .04, .04, .04), .04);
});

test("macro scenarios add dispersion without moving the expected equity return", () => {
  const assets = [{ symbol: "AAA", type: "stock", sector: "Tecnología" }],
    x = inputs(assets, [anchor(0.08)]);
  x.regimes = regimes(DEFAULT_REGIMES);
  x.options = { ...x.options, uncertainFundamentals: false };
  const sample = generatePaths(x, 6000, 9, 12);
  let total = 0;
  for (let p = 0; p < sample.paths; p++) total += sample.gross[0][p * (sample.steps + 1) + sample.steps];
  near(total / sample.paths, 1.08, 0.003);
});

test("investment-grade credit nets expected loss and widens with the scenario spread", () => {
  const lqd = { symbol: "LQD", type: "etf", price_date: "2026-10-26",
    bond_profile: { yieldToMaturity: .0598, duration: 7.63, expenseRatio: .0014, date: "2026-10-23" } };
  const b = bondAssumptions(lqd, { asOf: "2026-10-26", yieldCurve: { DGS30: 5.3 } });
  near(b.carry, .0598 - .0014 - CREDIT_CONVENTIONS.LQD.expectedLoss);
  assert.equal(b.spreadBeta, 1);
  assert.match(b.source, /pérdida esperada de crédito/);
  // A stale credit profile never borrows the Treasury curve.
  assert.equal(bondAssumptions(lqd, { asOf: "2027-03-01", yieldCurve: { DGS30: 5.3 } }), null);
  near(bondRegimeShift(b, { rateShift: -.015, spreadShift: .015 }), 0);
  near(bondRegimeShift({ spreadBeta: 0 }, { rateShift: -.015, spreadShift: .015 }), -.015);
  // Saved scenarios without the field inherit the default convention by id.
  const legacy = regimes([{ id: "recession", probability: 1, earningsShift: 0, multipleShift: 0, rateShift: 0, rateJumpBps: 0 }]);
  assert.equal(legacy[0].spreadShift, DEFAULT_REGIMES.find(r => r.id === "recession").spreadShift);
});
