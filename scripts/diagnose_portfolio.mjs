import { readFileSync } from "node:fs";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.20.0";
import { actualHoldings } from "../dist/assets/js/economic-exposure.mjs?v=0.20.0";
import { informationDate } from "../dist/assets/js/policy.mjs?v=0.20.0";

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
const informationAsOf=informationDate(snapshot);
const fundCoverage=snapshot.assets.filter(asset=>asset.type==="etf"&&asset.holdings)
  .map(asset=>{
    const original=actualHoldings(asset,snapshot.price_as_of,informationAsOf);
    return {
      symbol:asset.symbol,
      holdingsAsOf:asset.holdings.as_of,
      firstObservedAt:asset.holdings.observed_at,
      eligibleForInformationDate:!!original,
      coverage:asset.holdings.covered_weight,
      positionsReported:asset.holdings.positions_reported,
      sourceLayer:asset.holdings.source_layer,
      originalHash:asset.holdings.source_sha256||null,
    };
  });
console.log(JSON.stringify({
  diagnostic:"etf-issuer-holdings",
  asOf:snapshot.price_as_of,
  informationAsOf,
  downloaded:fundCoverage.length,
  usable:fundCoverage.filter(f=>f.eligibleForInformationDate).length,
  minimumCoverage:fundCoverage.length?Math.min(...fundCoverage.map(f=>f.coverage)):null,
  incomplete:fundCoverage.filter(f=>f.coverage<.95).map(f=>f.symbol),
  funds:fundCoverage,
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
