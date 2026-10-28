import test from "node:test";
import assert from "node:assert/strict";
import { curveRecessionProbability, conditionedRegimes, effectiveRegimes, DEFAULT_REGIMES, regimes, CURVE_RECESSION_MODEL }
  from "../dist/assets/js/policy.mjs?v=0.34.0";
import { normalCDF } from "../dist/assets/js/random.mjs?v=0.34.0";

const near = (a, b, tolerance = 1e-12) => assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`);
const days = Array.from({ length: 40 }, (_, k) =>
  new Date(Date.UTC(2026, 8, 1) + k * 86400000).toISOString().slice(0, 10));
const curve = (long, short, until = days.length) => [
  { id: "DGS10", history: days.slice(0, until).map((date, k) => ({ date, value: long(k) })) },
  { id: "DGS3MO", history: days.slice(0, until).map((date, k) => ({ date, value: short(k) })) },
];

test("recession probability is the NY Fed probit of the average 10Y-3M spread known at the cut", () => {
  // Spread 1 pp in the last 21 sessions, 3 pp before: only the window counts.
  const macro = curve((k) => (k < 19 ? 7 : 5), () => 4);
  const r = curveRecessionProbability(macro, days.at(-1));
  near(r.spread, 1);
  assert.equal(r.observations, CURVE_RECESSION_MODEL.window);
  near(r.probability, normalCDF(-0.5333 - 0.633));
  // An inverted curve raises it; later data is never used.
  const inverted = curveRecessionProbability(curve(() => 3.5, () => 5), days.at(-1));
  assert.ok(inverted.probability > 0.5);
  assert.equal(curveRecessionProbability(macro, days[10]), null); // fewer than 15 sessions
  near(curveRecessionProbability(curve((k) => (k < 30 ? 5 : 9), () => 4), days[29]).spread, 1);
});

test("conditioning sets recession, keeps relative weights of the rest and is idempotent", () => {
  const rows = conditionedRegimes(DEFAULT_REGIMES, { probability: 0.13 });
  near(rows.find((r) => r.id === "recession").probability, 0.13);
  near(rows.reduce((s, r) => s + r.probability, 0), 1);
  near(rows.find((r) => r.id === "base").probability / rows.find((r) => r.id === "inflation").probability, 0.55 / 0.15);
  assert.deepEqual(conditionedRegimes(rows, { probability: 0.13 }).map((r) => r.probability), rows.map((r) => r.probability));
  assert.doesNotThrow(() => regimes(rows));
  near(conditionedRegimes(DEFAULT_REGIMES, { probability: 0.999 }).find((r) => r.id === "recession").probability, 0.9);
  // Hand-fixed probabilities and sets without a recession scenario are left alone.
  const macro = curve(() => 5, () => 4);
  assert.equal(effectiveRegimes(DEFAULT_REGIMES, "manual", macro, days.at(-1)).rows, DEFAULT_REGIMES);
  const custom = [{ ...DEFAULT_REGIMES[0], probability: 1 }];
  assert.equal(effectiveRegimes(custom, "curve", macro, days.at(-1)).rows, custom);
  assert.equal(effectiveRegimes(DEFAULT_REGIMES, "curve", [], days.at(-1)).source, "manual");
});
