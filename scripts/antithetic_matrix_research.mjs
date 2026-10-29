/** Predeclared numerical precision matrix. Read-only, no trading or promotion. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {MODEL_VARIANTS,variantInputs} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {tradePlan,mandate} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {pairUtilityMeans} from './antithetic_selection_research.mjs';
import {poolOpportunityEvidence} from './pool_opportunity_audit.mjs';
export const MATRIX_PROTOCOL=Object.freeze({budgets:[1000,4000],seed:0x6ca317d5,independentSeed:0x37bd921f,
 experiments:24,target:105000,capital:100000,scope:'Two frozen cuts, three objectives, two budgets, two methods. One new predeclared seed pair. No optional stopping.'});
export function objectivePolicies(base){
 return ['growth','preservation','target'].map(objective=>mandate({...base,objective,
  terminalTarget:objective==='target'?MATRIX_PROTOCOL.target:0}));
}
export function budgetUtilities(a,b,c,n){
 if(!Number.isInteger(n)||n<2||a.length<n||a.length!==b.length||a.length!==c.length)throw Error('Incomplete budget arms');
 const u=a.slice(0,n),v=b.slice(0,n),w=c.slice(0,n);
 if(![u,v,w].every(x=>x.every(Number.isFinite)))throw Error('Nonfinite budget utility');
 return {plain:Float64Array.from([...u,...v]),antithetic:pairUtilityMeans(u,w)};
}
export function runPrecisionMatrix(market,vol,pool,{protocol=MATRIX_PROTOCOL,onProgress=()=>{}}={}){
 if(market.generated_at!==vol.source_market_generated_at||market.price_as_of!==vol.as_of)throw Error('Mismatched vintage');
 const budgets=protocol.budgets;
 if(!budgets.length||new Set(budgets).size!==budgets.length||budgets.some(n=>!Number.isInteger(n)||n<100||n>15000)||protocol.seed===protocol.independentSeed||!Number.isInteger(protocol.experiments)||protocol.experiments<budgets.length*6)throw Error('Invalid fixed protocol');
 const request=referenceRequest({...market,volatility:vol}),x=prepareComposition(market,request.settings,{},request.rules),
  policies=objectivePolicies(x.policy),seen=new Set(),excluded=[],rows=[];
 for(const positions of pool){
  const key=positions.map(p=>p.symbol+':'+p.weight).sort().join('|');if(seen.has(key))continue;seen.add(key);
  const weights=x.assets.map(a=>positions.find(p=>p.symbol===a.symbol)?.weight||0);
  if(positions.some(p=>!x.assets.some(a=>a.symbol===p.symbol))||!validWeights(weights,x)){excluded.push(key);continue;}
  const plan=tradePlan(x.assets,positions,x.current.positions,x.current.capital,x.costs);if(!plan.complete)throw Error('Incomplete execution inputs');
  rows.push({key,positions,weights,cost:plan.total});
 }
 const assessed=policies.map(policy=>({policy,rows:rows.map(row=>({...row,arms:[]}))})),maximum=Math.max(...budgets),started=Date.now();
 for(const variant of MODEL_VARIANTS){
  const altered=variantInputs(x,variant),shadow={...altered,options:{...altered.options,researchShadowMode:true}},
   a=generatePaths(shadow,maximum,protocol.seed,52),b=generatePaths(shadow,maximum,protocol.independentSeed,52),
   c=generatePaths(shadow,maximum,protocol.seed,52,{researchMirror:true});
  for(const group of assessed){
   const views=[a,b,c].map(sample=>({...sample,policy:group.policy}));
   for(const row of group.rows){
   const opts={capital:x.current.capital,cost:row.cost,pathUtilities:true},evalArm=sample=>evaluatePaths(row.weights,sample,opts).pathUtilities;
   row.arms.push({id:variant.id,a:evalArm(views[0]),b:evalArm(views[1]),c:evalArm(views[2])});
   }
  }
  onProgress({cut:market.price_as_of,model:variant.id,maximumPairs:maximum});
 }
 const cases=[];
 for(const group of assessed)for(const pairs of budgets)for(const method of ['plain','antithetic']){
  const data=group.rows.map(row=>({key:row.key,models:row.arms.map(arm=>({id:arm.id,
   utilities:budgetUtilities(arm.a,arm.b,arm.c,pairs)[method]}))})),
   r=poolOpportunityEvidence(data,group.policy,x.current.capital,x.costs.minBenefit,{experiments:protocol.experiments});
  cases.push({objective:group.policy.objective,policy:group.policy,pairs,method,payoffEvaluations:2*pairs,
   ...r,rows:r.rows.map(({comparisons,...r})=>({...r,positions:rows.find(row=>row.key===r.key).positions}))});
 }
 return {method:'antithetic-precision-matrix-v1',protocol,price_cut:market.price_as_of,market_generated_at:market.generated_at,poolSize:rows.length,excluded,cases,
  elapsedSeconds:(Date.now()-started)/1000,prospective:false,production_eligible:false,automatic_promotion:false,
  scope:'Fixed ex-post opportunity pool; current adjusted histories and originally published variance files. Common price paths across objectives share the identical horizon, cash/dividend/FX assumptions; only utility/target changes. Prefixes couple budgets; methods share an arm. Neither cases nor paths within a pair are independent market observations. No risk limit certification, strategy backtest, parameter validation or global optimum claim.'};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=(f,d)=>{const i=process.argv.indexOf(f);return i<0?d:process.argv[i+1];},read=p=>JSON.parse(readFileSync(p)),
  marketFile=value('--market','dist/data/market.json'),volFile=value('--volatility','dist/data/volatility.json'),
  poolFile='docs/auditorias/policy-pool-0.34.1.json',allocFile='docs/auditorias/allocation-cuts-0.35.0.json',cuts=read(allocFile).targets,
  pool=[...read(poolFile).diagnostics.reliableSelection.candidates.filter(r=>r.feasible).map(r=>r.positions),cuts.earlier,cuts.later],
  quick=process.argv.includes('--quick'),protocol=quick?{...MATRIX_PROTOCOL,budgets:[100,200]}:MATRIX_PROTOCOL,
  r=runPrecisionMatrix(read(marketFile),read(volFile),pool,{protocol,onProgress:p=>console.log(JSON.stringify(p))}),
  files=[marketFile,volFile,poolFile,allocFile,'dist/assets/js/path-model.mjs','scripts/antithetic_matrix_research.mjs','scripts/antithetic_selection_research.mjs','scripts/pool_opportunity_audit.mjs'];
 r.quick=quick;r.hashes=Object.fromEntries(files.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]));
 mkdirSync('out',{recursive:true});writeFileSync(value('--output','out/antithetic-matrix.json'),JSON.stringify(r,null,1)+'\n');
 console.log(JSON.stringify(r.cases.map(c=>({objective:c.objective,pairs:c.pairs,method:c.method,leader:c.pointLeader,
  minimumUpper:Math.min(...c.rows.map(r=>r.upperOpportunityLoss)),withinThreshold:c.rows.filter(r=>r.resolvedWithinThreshold).length}))));
}
