import test from "node:test";
import assert from "node:assert/strict";
import { crossSectionalRefinement, marketExposure, ALPHA_SCORE_LIMIT, BLUME_BETA_WEIGHT }
  from "../dist/assets/js/return-model.mjs?v=0.28.0";
import { seededRandom, normalGenerator } from "../dist/assets/js/random.mjs?v=0.28.0";

const near = (a, b, tolerance = 1e-10) =>
  assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`);
const dates = Array.from({ length: 401 }, (_, k) =>
  new Date(Date.UTC(2025, 0, 1) + k * 86400000).toISOString().slice(0, 10));
const asOf = dates.at(-1);
const path = (returns) => {
  let price = 100;
  return dates.map((date, k) => ({ date, adj_close: k ? (price *= Math.exp(returns[k - 1])) : price }));
};

function universe(count = 30, seed = 7) {
  const normal = normalGenerator(seededRandom(seed));
  const market = dates.slice(1).map(() => 0.01 * normal());
  const stocks = Array.from({ length: count }, (_, i) => {
    const beta = 0.4 + 1.2 * i / (count - 1), vol = 0.008 + 0.012 * ((i * 7) % count) / count;
    return { symbol: `S${i}`, type: "stock", beta,
      history: path(market.map((m) => beta * m + vol * normal())) };
  });
  const benchmark = { symbol: "SPY", type: "etf", history: path(market),
    holdings: { as_of: asOf, observed_at: asOf + "T22:00:00Z", positions: stocks.map((s) => ({ symbol: s.symbol, weight: 1 / count })) } };
  // Building-block signals spread far wider than a modest skill supports.
  const forecasts = new Map(stocks.map((s, i) => {
    const raw = -0.1 + 0.3 * ((i * 11) % count) / count;
    return [s.symbol, { model: { annualReturn: raw }, central: 0.06 + 0.6 * (raw - 0.06),
      low: -0.2, high: 0.3, confidence: 0.6 }];
  }));
  return { assets: [benchmark, ...stocks], lookup: (symbol) => forecasts.get(symbol) ?? null };
}
const settings = { asOf, yieldCurve: { DGS3MO: 4 }, mandate: { benchmark: "SPY" } };

test("exposure recovers beta and residual volatility from dated daily returns", () => {
  const { assets } = universe();
  const market = assets[0].history.slice(1).map((row, k) => Math.log(row.adj_close / assets[0].history[k].adj_close));
  const exact = { symbol: "X", type: "stock", history: path(market.map((m) => 1.5 * m + 0.0002)) };
  const e = marketExposure(exact, assets[0], asOf);
  near(e.beta, 1.5, 1e-9);
  near(e.omega, 0, 1e-9);
  assert.equal(e.observations, 400);
  const residual = market.map((m, k) => (k % 2 ? 0.01 : -0.01));
  const noisy = marketExposure({ symbol: "Y", type: "stock", history: path(market.map((m, k) => m + residual[k])) }, assets[0], asOf);
  near(noisy.omega, 0.01 * Math.sqrt(252), 0.01);
  assert.equal(marketExposure(assets[1], assets[0], dates[200]), null); // < 250 sessions
});

test("refined anchors are CAPM equilibrium plus a benchmark-neutral Grinold-Kahn alpha", () => {
  const { assets, lookup } = universe();
  const r = crossSectionalRefinement(assets, settings, lookup);
  const rows = [...r.values()], w = 1 / rows.length;
  const market = rows.reduce((s, x) => s + w * x.buildingBlock, 0);
  // The benchmark keeps its building-block mean; only the spread changes.
  near(rows.reduce((s, x) => s + w * x.anchor, 0), market);
  near(rows.reduce((s, x) => s + w * x.alpha, 0), 0);
  near(rows.reduce((s, x) => s + w * x.beta, 0), 1);
  for (const x of rows) {
    near(x.equilibrium, 0.04 + x.beta * (market - 0.04));
    near(x.anchor, x.equilibrium + x.alpha);
    assert.ok(Math.abs(x.score) <= ALPHA_SCORE_LIMIT);
    near(x.ic, 0.05);
  }
  const spread = (values) => Math.sqrt(values.reduce((s, v) => s + (v - market) ** 2, 0) / values.length);
  assert.ok(spread(rows.map((x) => x.anchor)) < spread(rows.map((x) => x.buildingBlock)) / 2);
  // Blume adjustment pulls betas toward one before rescaling.
  const steep = rows.at(-1);
  near(steep.beta * (rows.reduce((s, x) => s + w * (BLUME_BETA_WEIGHT * x.rawBeta + 1 - BLUME_BETA_WEIGHT), 0)),
    BLUME_BETA_WEIGHT * steep.rawBeta + 1 - BLUME_BETA_WEIGHT);
});

test("zero skill leaves only the equilibrium; missing inputs disable the refinement", () => {
  const { assets, lookup } = universe();
  const flat = crossSectionalRefinement(assets, { ...settings, informationCoefficient: 0 }, lookup);
  for (const x of flat.values()) near(x.anchor, x.equilibrium);
  assert.equal(crossSectionalRefinement(assets, { ...settings, yieldCurve: {} }, lookup), null);
  assert.equal(crossSectionalRefinement(assets, { ...settings, driftMode: "manual" }, lookup), null);
  assert.equal(crossSectionalRefinement(assets.slice(1), settings, lookup), null);
  assert.equal(crossSectionalRefinement(universe(10).assets, settings, lookup), null); // < 20 stocks
});
