/** Shadow-only finite-pool opportunity audit. Never authorizes trades. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {robustRegretEvidence} from '../dist/assets/js/reliable-selection.mjs?v=0.35.0';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths,utilityCertaintyEquivalent} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {MODEL_VARIANTS,variantInputs} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {riskSamplingEvidence} from '../dist/assets/js/simulation-evidence.mjs?v=0.35.0';
import {tailStressInputs} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
import {tradePlan,MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';

export function poolOpportunityEvidence(rows,policy,capital,threshold,{experiments=1}={}){
  if(!rows.length||!Number.isInteger(experiments)||experiments<1||!Number.isFinite(threshold)||threshold<0||!(capital>0))throw Error('Invalid pool protocol');
  const ids=rows[0].models.map(m=>m.id),keys=rows.map(r=>r.key);
  if(new Set(keys).size!==keys.length||!ids.length||new Set(ids).size!==ids.length)throw Error('Duplicate or empty pool/model identifiers');
  for(const row of rows)if(JSON.stringify(row.models.map(m=>m.id))!==JSON.stringify(ids))throw Error('Inconsistent model grid');
  const n=rows[0].models[0].utilities.length;
  for(const row of rows)for(const m of row.models)if(n<2||m.utilities.length!==n||!m.utilities.every(Number.isFinite))throw Error('Incomplete paired utility outcomes');
  const familySize=Math.max(25,rows.length**2*ids.length**2*experiments),mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
  const scored=rows.map(row=>({...row,worstScore:Math.min(...row.models.map(m=>mean(m.utilities)))}));
  const leader=[...scored].sort((a,b)=>b.worstScore-a.worstScore||a.key.localeCompare(b.key))[0];
  return {familySize,pointLeader:leader.key,threshold,rows:scored.map(row=>{
    // max_j min_m E[U(j,m)] - min_m E[U(row,m)], including self=0.
    // Simultaneous cross-model bounds cover every possible empirical leader.
    const comparisons=scored.filter(other=>other.key!==row.key).map(other=>({key:other.key,
      ...robustRegretEvidence(other.models,row.models,policy,capital,familySize)}));
    const point=Math.max(0,...comparisons.map(e=>e.gain)),lower=Math.max(0,...comparisons.map(e=>e.lowerGain)),
      upper=Math.max(0,...comparisons.map(e=>e.upperGain));
    return {key:row.key,worstCertaintyEquivalent:utilityCertaintyEquivalent(row.worstScore,policy,capital),
      estimatedOpportunityLoss:point,lowerOpportunityLoss:lower,upperOpportunityLoss:upper,
      resolvedWithinThreshold:upper<=threshold,comparisons};
  }),scope:'Approximate simultaneous Monte Carlo bounds within this finite pool and these declared models. Plug-in monetary conversion; no parameter, predictive or global-optimality guarantee.'};
}

const key=p=>p.map(r=>[r.symbol,r.weight]).sort((a,b)=>a[0].localeCompare(b[0])).map(r=>r.join(':')).join('|');
export function runPoolAudit(market,volatility,pool,{paths=2000,seeds=[0x48a17c29,0x5b97d031],onProgress=()=>{}}={}){
  if(!market.assets.every(a=>Array.isArray(a.history)))throw Error('Full published price histories required');
  if(market.generated_at!==volatility.source_market_generated_at||market.price_as_of!==volatility.as_of)throw Error('Market/volatility vintage mismatch');
  if(!Number.isInteger(paths)||paths<100||!seeds.length||new Set(seeds).size!==seeds.length)throw Error('Invalid simulation protocol');
  const r=referenceRequest({...market,volatility}),x=prepareComposition(market,r.settings,{},r.rules),seen=new Set(),excluded=[],rows=[];
  for(const p of pool){
    const k=key(p);if(seen.has(k))continue;seen.add(k);
    const missing=p.filter(r=>!x.assets.some(a=>a.symbol===r.symbol)).map(r=>r.symbol),w=x.assets.map(a=>p.find(r=>r.symbol===a.symbol)?.weight||0);
    if(missing.length||!validWeights(w,x)){excluded.push({key:k,missing,reason:'Absent from current production universe or violates composition constraints'});continue;}
    const plan=tradePlan(x.assets,p,x.current.positions,x.current.capital,x.costs);
    if(!plan.complete){excluded.push({key:k,reason:'Incomplete execution inputs'});continue;}
    rows.push({key:k,positions:p,weights:w,cost:plan.total});
  }
  if(!rows.length)throw Error('Empty assessable pool');
  const runs=[];
  for(const seed of seeds){
    const assessed=rows.map(row=>({...row,models:[],riskFailures:[]}));
    for(const v of MODEL_VARIANTS){
      const altered=variantInputs(x,v),sample=generatePaths(altered,paths,seed,52);
      for(const row of assessed){
        const m=evaluatePaths(row.weights,sample,{capital:x.current.capital,cost:row.cost,pathUtilities:true}),risk=riskSamplingEvidence(m,x.rules,x.policy);
        row.models.push({id:v.id,utilities:m.pathUtilities});
        row.riskFailures.push(...risk.failures.map(reason=>({model:v.id,reason})));
      }
      onProgress({seed,model:v.id});
    }
    const tailSample=generatePaths(tailStressInputs(x),paths,seed,52);
    for(const row of assessed){const risk=riskSamplingEvidence(evaluatePaths(row.weights,tailSample,{capital:x.current.capital,cost:row.cost,riskOnly:true}),x.rules,x.policy);
      row.riskFailures.push(...risk.failures.map(reason=>({model:'tail_student',reason})));}
    // Keep every assessable competitor: excluding borderline risk failures can
    // hide opportunity uncertainty. Admissibility is reported separately.
    const evidence=poolOpportunityEvidence(assessed,x.policy,x.current.capital,x.costs.minBenefit,{experiments:seeds.length});
    runs.push({seed,paths,...evidence,rows:evidence.rows.map(e=>({...e,positions:assessed.find(r=>r.key===e.key).positions,
      riskFailures:assessed.find(r=>r.key===e.key).riskFailures}))});
  }
  return {method:'finite-pool-opportunity-v1',engine:MODEL_VERSION,price_cut:market.price_as_of,capital:x.current.capital,
    pool_size:rows.length,excluded,runs,prospective:false,production_eligible:false,automatic_promotion:false,
    scope:'Frozen exposure pool chosen ex post; no discovery rerun. All assessable alternatives enter the conservative opportunity envelope, including any risk failures shown separately. No proof of constrained optimality, predictive skill or economic performance. Seeds compare MC sensitivity on identical data; they are not independent market observations.'};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const read=p=>JSON.parse(readFileSync(p)),value=(f,d)=>{const i=process.argv.indexOf(f);return i<0?d:process.argv[i+1];},
    marketFile=value('--market','dist/data/market.json'),volFile=value('--volatility','dist/data/volatility.json'),
    poolFile=value('--pool','docs/auditorias/policy-pool-0.34.1.json'),market=read(marketFile),vol=read(volFile),
    old=read(poolFile).diagnostics.reliableSelection.candidates.filter(r=>r.feasible).map(r=>r.positions),
    cuts=read('docs/auditorias/allocation-cuts-0.35.0.json').targets,
    pool=[...old,cuts.earlier,cuts.later],report=runPoolAudit(market,vol,pool,{paths:Number(value('--paths','2000')),onProgress:p=>console.log(JSON.stringify(p))}),
    hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
  report.inputs={market_sha256:hash(marketFile),volatility_sha256:hash(volFile),pool_sha256:hash(poolFile),
    allocations_sha256:hash('docs/auditorias/allocation-cuts-0.35.0.json'),source_sha256:hash(fileURLToPath(import.meta.url))};
  mkdirSync('out',{recursive:true});writeFileSync(value('--output','out/pool-opportunity-audit.json'),JSON.stringify(report,null,1)+'\n');
  console.log(JSON.stringify({leaders:report.runs.map(r=>({seed:r.seed,leader:r.pointLeader,withinThreshold:r.rows.filter(x=>x.resolvedWithinThreshold).length}))}));
}
