import { readFileSync } from "node:fs";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.8.0";

// Reproducible diagnostic on the actual published cut. Not a backtest
// or a recommendation to buy the positions selected.
const snapshot = JSON.parse(readFileSync(new URL("../dist/data/market.json", import.meta.url)));
const search = { candidates: 120, paths: 250, finalPaths: 600 };
console.log(JSON.stringify({
  diagnostic: "observed-market-cut",
  generatedAt: snapshot.generated_at,
  instruments: snapshot.assets.length,
  invalidatedEps: snapshot.assets
    .filter((asset) => asset.quality_flags?.includes("eps_share_income_scale_mismatch"))
    .map((asset) => asset.symbol),
  priceCutoff: snapshot.price_as_of,
}));
for (const [scenario, rules, seed, overrides] of [
  ["default", {}, 20261025, {}],
  ["default_seed_2", {}, 20261101, {}],
  ["default_seed_3", {}, 20261215, {}],
  ["reserve_cap_50pct", { reserveCap: 0.5 }, 20261025, {}],
  ["nflx_conservative", {}, 20261025, { NFLX: { growth: 0.04, multiple: 20 } }],
]) {
  const started = Date.now();
  const result = composePortfolio(snapshot, {
    seed, model: "merton", horizon: 1,
  }, overrides, rules, search);
  console.log(JSON.stringify({
    scenario,
    seed,
    status: result.status,
    cut: result.as_of,
    selection: {
      published: result.selection?.published,
      eligible: result.selection?.eligible,
      simulated: result.selection?.simulated,
    },
    proposed: result.positions,
    signals: result.signals?.map(({symbol,anchor,adverseAnchor,favorableAnchor,confidence,source}) =>
      ({symbol,anchor,adverseAnchor,favorableAnchor,confidence,source})),
    riskLimits: result.diagnostics?.selected?.nearLimits || [],
    references: result.diagnostics?.references,
    indicators: result.metrics ? {
      meanReturn: result.metrics.meanReturn,
      certaintyEquivalent: result.metrics.certaintyEquivalent,
      cvar95: result.metrics.cvar95,
      lossProbability: result.metrics.lossProbability,
      drawdownProbability: result.metrics.drawdownProbability,
    } : null,
    search: result.search,
    runSeconds: Math.round((Date.now() - started) / 1000),
  }));
}
