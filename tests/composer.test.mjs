import test from "node:test";
import assert from "node:assert/strict";
import {
  composePortfolio,
  prepareComposition,
  terminalScenarios,
  evaluateWeights,
  DEFAULT_COMPOSITION_RULES,
} from "../dist/assets/js/composer.mjs?v=0.3.0";
import { triangularQuantile } from "../dist/assets/js/return-model.mjs?v=0.3.0";

function snapshot() {
  const asOf = "2026-10-23";
  const assets = Array.from({ length: 7 }, (_, i) => {
    const reserve = i === 6,
      symbol = reserve ? "SHY" : String.fromCharCode(65 + i).repeat(3);
    const history = Array.from({ length: 301 }, (_, t) => {
      const date = new Date(Date.UTC(2026, 9, 23) - (300 - t) * 86400000)
        .toISOString()
        .slice(0, 10);
      const close = 100 * Math.exp(0.002 * Math.sin(t / (3 + i)));
      return { date, close, adj_close: close, volume: 1000000 };
    });
    const price = history.at(-1).close;
    return {
      symbol,
      name: symbol,
      type: reserve ? "etf" : "stock",
      sector: reserve ? "Treasuries cortos" : `Sector ${Math.floor(i / 2)}`,
      price,
      price_date: asOf,
      history,
      assumptions: { growth: 0.06, multiple: 15, discount: 0.1, horizon: 3 },
      financials: reserve
        ? {}
        : {
            eps: {
              value: 9 + i * 0.3,
              filed: "2026-09-01",
              period_end: "2026-06-30",
              method: "TTM",
            },
          },
      dividend_per_share: 0,
    };
  });
  return {
    price_as_of: asOf,
    generated_at: "2026-10-24T00:00:00Z",
    assets,
    macro: [{ id: "DGS3MO", date: asOf, value: 4 }],
  };
}

test("composition is reproducible, fully invested and respects position, sector and risk limits", () => {
  const input = snapshot(),
    options = { model: "gbm", seed: 765, horizon: 1 };
  const before = JSON.stringify(input);
  const a = composePortfolio(input, options),
    b = composePortfolio(input, options);
  assert.equal(a.status, "proposed");
  assert.deepEqual(a.positions, b.positions);
  assert.deepEqual(a.metrics, b.metrics);
  assert.ok(Math.abs(a.positions.reduce((s, p) => s + p.weight, 0) - 1) < 1e-9);
  assert.ok(a.positions.length <= DEFAULT_COMPOSITION_RULES.maxPositions);
  const sectors = new Map();
  for (const p of a.positions)
    if (!["SHY","CASH"].includes(p.symbol)) {
      const sector = input.assets.find(
        (asset) => asset.symbol === p.symbol,
      ).sector;
      sectors.set(sector, (sectors.get(sector) || 0) + p.weight);
    }
  assert.ok(
    [...sectors.values()].every(
      (w) => w <= DEFAULT_COMPOSITION_RULES.maxSector + 1e-9,
    ),
  );
  for (const p of a.positions)
    assert.ok(p.weight <= (["SHY","CASH"].includes(p.symbol) ? 1 : 0.2) + 1e-9);
  assert.ok(a.metrics.cvar95 <= a.rules.cvarBudget);
  assert.ok(a.metrics.lossProbability <= a.rules.maxLossProbability);
  assert.notEqual(a.settings.seed, a.verification.seed);
  assert.ok(a.calibration_end <= input.price_as_of);
  assert.equal(a.search.method, "reserve-tilts-random-local-exchanges");
  assert.equal(a.search.exhaustive, false);
  assert.equal(a.diagnostics.references.cash.feasible, true);
  assert.ok(a.diagnostics.references.reserve);
  assert.equal(a.diagnostics.references.equity20, null);
  assert.ok(a.diagnostics.selected.largestPosition.weight > 0);
  assert.equal(JSON.stringify(input), before);
});

test("future prices and unpublished earnings never enter an ex ante composition", () => {
  const input = snapshot();
  input.assets[0].financials.eps.filed = "2026-10-24";
  for (const a of input.assets)
    a.history.push({
      date: "2026-10-24",
      close: 9000,
      adj_close: 9000,
      volume: 1,
    });
  const prepared = prepareComposition(input, { model: "gbm" });
  assert.ok(!prepared.assets.some((a) => a.symbol === "AAA"));
  assert.ok(
    prepared.assets.every((a) =>
      a.history.every((r) => r.date <= input.price_as_of),
    ),
  );
  assert.ok(prepared.anchors.every((a) => Number.isFinite(a.mu)));
  assert.ok(prepared.calibrationEnd <= input.price_as_of);
});

test("reversing past return direction does not turn a historical winner into a forecast anchor", () => {
  const original = snapshot(),
    reversed = structuredClone(original);
  for (const asset of reversed.assets) {
    const last = asset.history.at(-1).adj_close;
    for (const row of asset.history) {
      row.adj_close = (last * last) / row.adj_close;
      row.close = row.adj_close;
    }
  }
  const a = prepareComposition(original, { model: "gbm" }),
    b = prepareComposition(reversed, { model: "gbm" });
  assert.deepEqual(a.anchors, b.anchors);
  for (let i = 0; i < a.covariance.length; i++)
    for (let j = 0; j < a.covariance.length; j++)
      assert.ok(Math.abs(a.covariance[i][j] - b.covariance[i][j]) < 1e-10);
});

test("terminal scenarios preserve the configured annual anchor at zero diffusion and no jumps", () => {
  const inputs = {
    assets: [{ symbol: "AAA" }, { symbol: "SHY" }],
    covariance: [
      [0, 0],
      [0, 0],
    ],
    options: {
      model: "gbm",
      horizon: 1,
      driftMode: "manual",
      uncertainFundamentals: false,
      jumpIntensity: 0,
      jumpMean: 0,
      jumpVol: 0,
    },
    anchors: [
      { annual: 0.1, low: 0.1, high: 0.1 },
      { annual: 0.04, low: 0.04, high: 0.04 },
    ],
  };
  const metrics = evaluateWeights(
    [0.5, 0.5],
    terminalScenarios(inputs, 100, 1),
  );
  assert.ok(Math.abs(metrics.meanReturn - 0.07) < 1e-12);
  assert.equal(metrics.cvar95, 0);
  assert.equal(metrics.lossProbability, 0);
});

test("a tight risk budget keeps cash and an impossible capital floor returns no proposal", () => {
  const p = composePortfolio(
    snapshot(),
    { jumpIntensity: 3, jumpMean: -0.5, jumpVol: 0.15 },
    {},
    { cvarBudget: 0.001, maxLossProbability: 0.001 },
    { candidates: 50, paths: 500, finalPaths: 1000 },
  );
  assert.equal(p.status, "hold");
  assert.deepEqual(p.positions,[{symbol:"CASH",weight:1}]);
  assert.equal(p.metrics.cvar95,0);
  const impossible=composePortfolio(snapshot(),{mandate:{capitalFloor:200000}}, {}, {}, {candidates:30,paths:100,finalPaths:100});
  assert.equal(impossible.status,"no_feasible");
  assert.equal(impossible.positions,undefined);
  assert.throws(
    () => prepareComposition(snapshot(), {}, {}, { maxCorrelation: 1.2 }),
    /límites/,
  );
});

test("fundamental uncertainty remains bounded and degenerates to the central anchor when bounds coincide", () => {
  assert.equal(triangularQuantile(0, -0.2, 0.1, 0.4), -0.2);
  assert.equal(triangularQuantile(1, -0.2, 0.1, 0.4), 0.4);
  assert.equal(triangularQuantile(0.7, 0.1, 0.1, 0.1), 0.1);
  for (let i = 0; i <= 100; i++) {
    const r = triangularQuantile(i / 100, -0.2, 0.1, 0.4);
    assert.ok(r >= -0.2 && r <= 0.4);
  }
});
