/** Evaluate omitted eligible instruments through shadow-only forced shortlist trials.
 * Outputs are NOT paired across universes: all re-simulation warnings remain.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.29.0";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.29.0";

const snapshot=JSON.parse(readFileSync("dist/data/market.json","utf8"));
const volatility=JSON.parse(readFileSync("dist/data/volatility.json","utf8"));
if(volatility.source_market_generated_at!==snapshot.generated_at)
  throw Error("Input provenance is inconsistent");
const preset=referenceRequest({...snapshot,volatility});
const search={candidates:100,paths:240,finalPaths:500};
const common={...preset.settings,researchShadowMode:true};
const base=composePortfolio(snapshot,common,{},preset.rules,search);
const selected=new Set(base.model_inputs?.assets?.map(a=>a.symbol)||[]);
const omitted=(base.selection.outsideWithHigherPriority||[])
  .map(x=>x.symbol).filter(x=>!selected.has(x));
const candidates=omitted.slice(0,5);
const outcomes=[];
for(const symbol of candidates){
  const challenger=composePortfolio(snapshot,
    {...common,researchForceInclude:[symbol]}, {},preset.rules,search);
  if(!challenger.selection.forcedResearchCandidates.includes(symbol))
    throw Error("Forced research candidate absent from shortlisting metadata: "+symbol);
  const selection=new Set(challenger.model_inputs?.assets?.map(a=>a.symbol)||[]);
  if(!selection.has(symbol))throw Error("Research shortlist excluded forced "+symbol);
  outcomes.push({
    admitted:symbol,
    status:challenger.status,
    new_weights:challenger.positions,
    median:challenger.metrics?.medianReturn,
    cvar:challenger.metrics?.cvar95,
    certainty_equivalent:challenger.metrics?.certaintyEquivalent,
    candidates_dropped_from_base:[...selected].filter(x=>!selection.has(x)),
    note:"Different asset universe, covariance and simulations; not a paired portfolio superiority test.",
  });
  console.log(symbol,"new SHY",challenger.positions?.find(p=>p.symbol==="SHY")?.weight,
    "CE",challenger.metrics?.certaintyEquivalent);
}
const report={
  method:"iterative-omitted-assets-admission-shadow-v1",
  as_of:snapshot.price_as_of,
  market_collected_at:snapshot.generated_at,
  not_promoted:true,
  base:{
    weights:base.positions,median:base.metrics?.medianReturn,
    cvar:base.metrics?.cvar95,
    certainty_equivalent:base.metrics?.certaintyEquivalent,
    eligible:base.selection.eligible,simulated:base.selection.simulated,
  },
  challenged:candidates,
  outcomes,
  warning:"Candidate screens and distributional assumptions are NOT validated economic forecasts. Differences do not establish global optimality.",
};
const out=resolve(process.argv[2]||"out/omitted-universe-shadow.json");
mkdirSync(dirname(out),{recursive:true});
writeFileSync(out,JSON.stringify(report,null,2)+"\n");
console.log("Excluded-instrument shadow comparisons",outcomes.length);
