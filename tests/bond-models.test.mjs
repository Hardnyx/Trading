import test from "node:test";
import assert from "node:assert/strict";
import { bondAssumptions, CREDIT_CONVENTIONS } from "../dist/assets/js/research-model.mjs?v=0.34.1";
import { bondRegimeShift, bondScenarioAnnualReturn } from "../dist/assets/js/return-model.mjs?v=0.34.1";
import { regimeCondition, centeredRegimeConditions } from "../dist/assets/js/path-model.mjs?v=0.34.1";
import { regimes, DEFAULT_REGIMES } from "../dist/assets/js/policy.mjs?v=0.34.1";

const near = (a, b, tolerance = 1e-12) => assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`);
const settings = { asOf: "2026-10-27", informationAsOf: "2026-10-27", yieldCurve: { DGS3MO: 4.22, T10YIE: 2.35 } };
const fund = (symbol, profile) => ({ symbol, type: "etf", price_date: "2026-10-27",
  bond_profile: { date: "2026-10-26", source_url: "x", ...profile } });

test("high yield and EM funds net a stated credit loss and carry a larger spread beta", () => {
  const hyg = bondAssumptions(fund("HYG", { yieldToMaturity: .0791, duration: 3.14, expenseRatio: .0049 }), settings);
  near(hyg.carry, .0791 - .0049 - .02);
  assert.equal(hyg.spreadBeta, 3);
  const emb = bondAssumptions(fund("EMB", { yieldToMaturity: .0711, duration: 6.33, expenseRatio: .0039 }), settings);
  near(emb.carry, .0711 - .0039 - .0075);
  // A recession widens HYG's spread three times the IG convention.
  const recession = regimes(DEFAULT_REGIMES).find((r) => r.id === "recession");
  near(bondRegimeShift(hyg, recession), -0.015 + 3 * 0.015);
  assert.ok(bondScenarioAnnualReturn(hyg, bondRegimeShift(hyg, recession), 1) < hyg.carry - 0.08);
  // Without a dated profile, no Treasury proxy stands in for credit.
  assert.equal(bondAssumptions({ symbol: "HYG", type: "etf", price_date: "2026-10-27" }, settings), null);
  assert.ok(CREDIT_CONVENTIONS.HYG.expectedLoss > CREDIT_CONVENTIONS.EMB.expectedLoss);
});

test("TIP earns real yield plus breakeven; scenarios move the real yield and accrue inflation", () => {
  const tip = bondAssumptions(fund("TIP", { inflationLinked: true, realYield: .0266, duration: 6.2, expenseRatio: .0018 }), settings);
  assert.equal(tip.inflationLinked, true);
  near(tip.carry, .0266 + .0235 - .0018);
  assert.equal(tip.spreadBeta, 0);
  const rows = regimes(DEFAULT_REGIMES), inflation = rows.find((r) => r.id === "inflation");
  // Nominal +1.5 pp with inflation +1.5 pp: the real yield does not move,
  // and the extra inflation accrues to principal.
  near(bondRegimeShift(tip, inflation), 0);
  const asset = { symbol: "TIP", type: "etf" }, anchor = { bond: tip };
  near(regimeCondition(asset, anchor, inflation, 1), Math.log1p(.015));
  // Centered like every scenario: the probability-weighted gross mean is one.
  const c = centeredRegimeConditions(asset, anchor, rows, 2);
  near(rows.reduce((s, r, k) => s + r.probability * Math.exp(2 * c[k]), 0), 1);
  // No breakeven at the cut: no nominal anchor.
  assert.equal(bondAssumptions(fund("TIP", { inflationLinked: true, realYield: .0266, duration: 6.2, expenseRatio: .0018 }),
    { ...settings, yieldCurve: { DGS3MO: 4.22 } }), null);
  // Saved scenarios without the new field inherit its convention by id.
  near(regimes([{ ...DEFAULT_REGIMES[1], inflationShift: undefined, probability: 1 }])[0].inflationShift, -0.01);
});

test("international equity funds take an earnings-yield anchor from a dated issuer P/E", async () => {
  const { valuationAnchor, buildReturnAnchors } = await import("../dist/assets/js/return-model.mjs?v=0.34.1");
  const efa = { symbol: "EFA", type: "etf", price_date: "2026-10-27", history: [],
    equity_valuation: { priceEarnings: 20, date: "2026-10-26", observed_at: "2026-10-27T00:10:00Z", expenseRatio: .0032 } };
  const a = valuationAnchor(efa, settings);
  // 6% prior + 0.6 x (5% earnings yield + 2.35% breakeven - 6%) - 0.32% expenses.
  near(a.annual, .06 + .6 * (.05 + .0235 - .06) - .0032);
  near(a.high - a.annual, .15);
  assert.match(a.source, /P\/E 20[.,]0 al 2026-10-26/);
  const [built] = buildReturnAnchors([efa], settings, {}, [efa]);
  near(built.annual, a.annual);
  assert.equal(built.valuationDate, "2026-10-26");
  // Observed after the cut, stale, or without a breakeven: no anchor.
  const at = (v) => valuationAnchor({ ...efa, equity_valuation: { ...efa.equity_valuation, ...v } }, settings);
  assert.equal(at({ observed_at: "2026-10-28T12:00:00Z" }), null);
  // An evening capture (00:10 UTC on the 28th is 20:10 on the 27th in New
  // York) is known at the 27th's information cut.
  assert.notEqual(at({ observed_at: "2026-10-28T00:10:00Z" }), null);
  assert.equal(at({ date: "2026-08-01" }), null);
  assert.equal(valuationAnchor(efa, { ...settings, yieldCurve: {} }), null);
  // An explicit user expectation still wins.
  const [own] = buildReturnAnchors([efa], { ...settings, assetAssumptions: { EFA: { expectedReturn: .04, uncertainty: .05 } } }, {}, [efa]);
  near(own.annual, .04);
});

test("observations are dated on the New York calendar of the information cut", async () => {
  const { observationDate, observedBy } = await import("../dist/assets/js/observation.mjs?v=0.34.1");
  assert.equal(observationDate("2026-10-28T00:12:18.56+00:00"), "2026-10-27");
  assert.equal(observationDate("2026-10-27T13:00:00Z"), "2026-10-27");
  assert.equal(observationDate("2026-01-15T04:59:00Z"), "2026-01-14"); // EST, UTC-5
  assert.equal(observedBy("2026-10-28T03:59:00Z", "2026-10-27"), true);
  assert.equal(observedBy("2026-10-28T04:00:00Z", "2026-10-27"), false);
  assert.equal(observedBy("not a time", "2026-10-27"), false);
  assert.equal(observedBy(undefined, "2026-10-27"), false);
});

test("in a market jump credit spreads widen with each fund's spread beta", async () => {
  const { jumpParameters } = await import("../dist/assets/js/path-model.mjs?v=0.34.1");
  const recession = regimes(DEFAULT_REGIMES).find((r) => r.id === "recession");
  const options = { jumpMean: -0.12, jumpVol: 0.08 };
  const jump = (bond) => jumpParameters({ symbol: "B", type: "etf" }, { bond }, options, recession).mean;
  // Treasuries still gain when yields fall in the event.
  near(jump({ duration: 16, spreadBeta: 0 }), 16 * 0.008);
  // High yield: -80 bp rates + 3 x 150 bp spread = +370 bp.
  near(jump({ duration: 3.14, spreadBeta: 3 }), -3.14 * 0.037);
  near(jump({ duration: 6.33, spreadBeta: 1.5 }), -6.33 * 0.0145);
  // Inflation-linked funds take no credit spread.
  near(jump({ duration: 6.2, spreadBeta: 0, inflationLinked: true }), 6.2 * 0.008);
  near(regimes([{ ...DEFAULT_REGIMES[0], spreadJumpBps: undefined, probability: 1 }])[0].spreadJumpBps, 75);
});
