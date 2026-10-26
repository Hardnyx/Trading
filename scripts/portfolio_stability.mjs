/**
 * Stability research: portfolio selection under seeds, search budget and
 * reduced candidate universes. Nothing is promoted into the public engine.
 * These are conditional diagnostics, NOT point-in-time historical returns.
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.12.0";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.12.0";

const market=JSON.parse(readFileSync("dist/data/market.json","utf8"));
const volatility=JSON.parse(readFileSync("dist/data/volatility.json","utf8"));
if(volatility.as_of!==market.price_as_of ||
   volatility.source_market_generated_at!==market.generated_at)
  throw Error("Risk calibration and market vintage are inconsistent");
const preset=referenceRequest({...market,volatility});
const configurations=[
  {id:"base40",seed:20261024,universe:40,budget:120},
  {id:"other_seed40",seed:20261025,universe:40,budget:120},
  {id:"smaller30",seed:20261024,universe:30,budget:120},
  {id:"larger_search40",seed:20261024,universe:40,budget:260},
];
const results=[];
for(const config of configurations){
  const start=Date.now();
  const options={...preset.settings,seed:config.seed,
                 researchUniverseLimit:config.universe};
  const result=composePortfolio(market,options,preset.overrides,preset.rules,
    {candidates:config.budget,paths:250,finalPaths:650});
  results.push({
    id:config.id,seed:config.seed,universe:config.universe,
    budget:config.budget,status:result.status,
    positions:result.positions,
    simulated:result.selection.simulated,
    outside:result.selection.outsideSample.length,
    metrics:result.metrics ? {
      certaintyEquivalent:result.metrics.certaintyEquivalent,
      cvar95:result.metrics.cvar95,
      medianReturn:result.metrics.medianReturn,
      lossProbability:result.metrics.lossProbability,
    } : null,
    elapsed_seconds:Math.round((Date.now()-start)/1000),
  });
  console.log(config.id, "status",result.status,
    "SHY",(result.positions||[]).find(p=>p.symbol==="SHY")?.weight??0,
    "CVaR",result.metrics?.cvar95);
}
const holdings=r=>new Set((r.positions||[]).filter(x=>x.symbol!=="CASH")
  .map(p=>p.symbol));
const base=results[0];
const comparisons=results.slice(1).map(r=>{
  const a=holdings(base),b=holdings(r);
  const union=new Set([...a,...b]);
  const intersect=[...a].filter(x=>b.has(x)).length;
  return {
    against:r.id,
    jaccard:union.size?intersect/union.size:1,
    shy_weight_difference:((r.positions||[]).find(p=>p.symbol==="SHY")?.weight||0)-
      ((base.positions||[]).find(p=>p.symbol==="SHY")?.weight||0),
    cvar_difference:(r.metrics?.cvar95??0)-(base.metrics?.cvar95??0),
    // Scenario sets / universes are not identical; differences are not
    // mathematically paired or comparable as utility confidence intervals.
    no_cross_universe_optimality_claim:true,
  };
});
const result={
  method:"universe-seed-budget-stability-shadow-v1",
  snapshot_cut:market.price_as_of,
  source_market_generated_at:market.generated_at,
  no_promotion:true,
  outcomes:results,comparisons,
  warning:"Different universes and paths imply nonidentical feasible models; differences do not establish OOS portfolio superiority.",
};
const out=resolve(process.argv[2]||"out/portfolio-stability.json");
mkdirSync(dirname(out),{recursive:true});
writeFileSync(out,JSON.stringify(result,null,2)+"\n");
console.log("Stability report",out);
