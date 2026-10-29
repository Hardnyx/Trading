/** Equal-cost variance-reduction experiment; never a production selector. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {MODEL_VARIANTS,variantInputs} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {poolOpportunityEvidence} from './pool_opportunity_audit.mjs';
export function pairUtilityMeans(a,b){
 if(a.length!==b.length||a.length<2)throw Error('Incomplete independent pairs');
 return Float64Array.from(a,(v,i)=>{if(!Number.isFinite(v)||!Number.isFinite(b[i]))throw Error('Nonfinite utility');return (v+b[i])/2;});
}
export function runAntitheticResearch(market,vol,pool,{pairs=1000,onProgress=()=>{}}={}){
 if(market.generated_at!==vol.source_market_generated_at||market.price_as_of!==vol.as_of)throw Error('Mismatched market/variance');
 const r=referenceRequest({...market,volatility:vol}),x=prepareComposition(market,r.settings,{},r.rules),seen=new Set(),rows=[],excluded=[];
 for(const positions of pool){
  const key=positions.map(p=>p.symbol+':'+p.weight).sort().join('|');if(seen.has(key))continue;seen.add(key);
  const weights=x.assets.map(a=>positions.find(p=>p.symbol===a.symbol)?.weight||0);
  if(positions.some(p=>!x.assets.some(a=>a.symbol===p.symbol))||!validWeights(weights,x)){excluded.push(key);continue;}
  const plan=tradePlan(x.assets,positions,x.current.positions,x.current.capital,x.costs);if(!plan.complete)throw Error('Incomplete plan');
  rows.push({key,positions,weights,cost:plan.total});
 }
 const runs=[],seeds=[[0x48a17c29,0x19ac3d57],[0x5b97d031,0x2de963a7]];
 for(const [seed,independentSeed] of seeds){
  const plain=rows.map(r=>({...r,models:[]})),antithetic=rows.map(r=>({...r,models:[]}));
  for(const v of MODEL_VARIANTS){
   const altered=variantInputs(x,v),shadow={...altered,options:{...altered.options,researchShadowMode:true}},
     a=generatePaths(shadow,pairs,seed,52),b=generatePaths(shadow,pairs,independentSeed,52),
     mirror=generatePaths(shadow,pairs,seed,52,{researchMirror:true});
   for(let i=0;i<rows.length;i++){
    const row=rows[i],opts={capital:x.current.capital,cost:row.cost,pathUtilities:true},
      u=evaluatePaths(row.weights,a,opts).pathUtilities,w=evaluatePaths(row.weights,b,opts).pathUtilities,
      z=evaluatePaths(row.weights,mirror,opts).pathUtilities;
    plain[i].models.push({id:v.id,utilities:Float64Array.from([...u,...w])});
    antithetic[i].models.push({id:v.id,utilities:pairUtilityMeans(u,z)});
   }
   onProgress({seed,model:v.id});
  }
  const summarize=r=>({...r,rows:r.rows.map(({comparisons,...row})=>({...row,positions:rows.find(a=>a.key===row.key).positions}))});
  runs.push({seed,independentSeed,trajectoryEvaluationsPerMethod:2*pairs,independentPairs:pairs,
   plain:summarize(poolOpportunityEvidence(plain,x.policy,x.current.capital,x.costs.minBenefit,{experiments:4})),
   antithetic:summarize(poolOpportunityEvidence(antithetic,x.policy,x.current.capital,x.costs.minBenefit,{experiments:4}))});
 }
 return {method:'antithetic-equal-cost-selection-v1',pairs,price_cut:market.price_as_of,poolSize:rows.length,excluded,runs,
  production_eligible:false,prospective:false,automatic_promotion:false,
  scope:'Same marginal law: reflect independent Gaussian primitives and uniform regime/jump draws; update each variance path separately. Error uses independent pair means, not 2n independent paths. Fixed ex-post pool, same marginal payoff-evaluation budget. Plain and antithetic estimates share one arm. No risk probabilities or CVaR are estimated from pair means. No evidence of parameter calibration, predictive skill, constrained/global optimum, or net market performance.'};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const read=p=>JSON.parse(readFileSync(p)),market=read('dist/data/market.json'),vol=read('dist/data/volatility.json'),
  old=read('docs/auditorias/policy-pool-0.34.1.json').diagnostics.reliableSelection.candidates.filter(r=>r.feasible).map(r=>r.positions),cuts=read('docs/auditorias/allocation-cuts-0.35.0.json').targets,
  report=runAntitheticResearch(market,vol,[...old,cuts.earlier,cuts.later],{onProgress:p=>console.log(JSON.stringify(p))}),
  files=['dist/data/market.json','dist/data/volatility.json','dist/assets/js/path-model.mjs','scripts/antithetic_selection_research.mjs','scripts/pool_opportunity_audit.mjs','docs/auditorias/policy-pool-0.34.1.json','docs/auditorias/allocation-cuts-0.35.0.json'];
 report.hashes=Object.fromEntries(files.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]));
 mkdirSync('out',{recursive:true});writeFileSync('out/antithetic-selection.json',JSON.stringify(report,null,1)+'\n');
 console.log(JSON.stringify(report.runs.map(r=>({seed:r.seed,plain:r.plain.pointLeader,antithetic:r.antithetic.pointLeader,
  plainMinimumUpper:Math.min(...r.plain.rows.map(x=>x.upperOpportunityLoss)),antitheticMinimumUpper:Math.min(...r.antithetic.rows.map(x=>x.upperOpportunityLoss))}))));
}
