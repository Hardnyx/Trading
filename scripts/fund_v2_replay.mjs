/** Registered acceptance test T5: replay fondo-v2 over the last 30 published cuts, twice. */
import { readFileSync, writeFileSync } from "node:fs";
import { emptyStrategicState, reviewV2 } from "./fund_review.mjs";

export function replay(market, cuts = 30) {
  const symbols = ["VTI", "VXUS", "AGG", "SPY", "BIL"];
  const assets = market.assets.filter(a => symbols.includes(a.symbol));
  const dates = assets.find(a => a.symbol === "VTI").history.map(r => r.date).slice(-(cuts + 1));
  let state = emptyStrategicState();
  const records = [];
  for (const date of dates) {
    const cut = { price_as_of: date, generated_at: date + "T22:00:00Z", assets: assets.map(a => {
      const history = a.history.filter(r => r.date <= date);
      return { ...a, history, price: history.at(-1).close };
    }) };
    const step = reviewV2(cut, state);
    state = step.state;
    records.push(step.record);
  }
  return records;
}

if (process.argv[1]?.endsWith("fund_v2_replay.mjs")) {
  const market = JSON.parse(readFileSync("dist/data/market.json", "utf8"));
  const first = replay(market), second = replay(market);
  const later = first.slice(1);
  const result = {
    schema: "fondo-v2-replay-v1", cuts: later.length, period: `${later[0].date} to ${later.at(-1).date}`,
    statuses: Object.fromEntries(["hold", "rebalance"].map(s => [s, later.filter(r => r.status === s).length])),
    max_drift: Math.max(...later.map(r => r.drift ?? 0)),
    acceptance: {
      "no order on a day without a deviation above 5 pp": later.every(r => (r.drift > 0.05) === (r.orders.length > 0)),
      "identical output on a second run": JSON.stringify(first) === JSON.stringify(second),
      "whole-share orders leave cash >= 0": first.every(r => r.orders.reduce((s, o) => s + o.target_whole_shares * o.price, 0) <= (r.value ?? Infinity) + 1e-6),
    },
  };
  writeFileSync("docs/auditorias/fondo-v2-ensayo.json", JSON.stringify(result, null, 1) + "\n");
  console.log(JSON.stringify(result, null, 1));
}
