/** Frozen-input diagnosis. Numerical stability is not predictive validation. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {prepareComposition,composePortfolio,weightOverlap} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {reviewRobustDecision} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
import {MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';

const market=JSON.parse(readFileSync('dist/data/market.json')),volatility=JSON.parse(readFileSync('dist/data/volatility.json')),
  snapshot={...market,volatility},request=referenceRequest(snapshot),x=prepareComposition(snapshot,request.settings,{},request.rules),
  originalHash=createHash('sha256').update(JSON.stringify(snapshot)).digest('hex');
const samePortfolio={SPY:.35,SHY:.35,IEF:.25,CASH:.05};
const zero={symbol:'000_ZERO',type:'cash',sector:'unused-sector'},n=x.assets.length,
  augmented={...x,assets:[...x.assets,zero],anchors:[...x.anchors,{symbol:zero.symbol,sector:zero.sector,annual:0,low:0,high:0}],
    covariance:[...x.covariance.map(r=>[...r,0]),Array(n+1).fill(0)],
    conditional:{...x.conditional,fits:[...x.conditional.fits,null]},
    horizonVariance:{...x.horizonVariance,longRunDaily:[...x.horizonVariance.longRunDaily,0]},
    factorization:x.factorization?{...x.factorization,loading:[...x.factorization.loading,0],
      residualCovariance:[...x.factorization.residualCovariance.map(r=>[...r,0]),Array(n+1).fill(0)]}:null};
const a=generatePaths(x,1000,20261024,52),b=generatePaths(augmented,1000,20261024,52);
let differences=0;for(let i=0;i<n;i++)for(let k=0;k<a.gross[i].length;k++)if(a.gross[i][k]!==b.gross[i][k])differences++;
if(differences)throw Error('Irrelevant instrument changes the existing experiment');
const weights=t=>t.assets.map(a=>samePortfolio[a.symbol]||0),
  nullExperiment={changed_coordinates:differences,original:evaluatePaths(weights(x),a),
    augmented:evaluatePaths(weights(augmented),b),scenario_counts:a.scenarioCounts};
const full=process.argv.includes('--full'),seeds=full?[20261024,20261025,20261026]:[20261024,20261025],results=[];
mkdirSync('out',{recursive:true});
const checkpoint=()=>writeFileSync('out/reliability-audit-progress.json',JSON.stringify({
  engine:MODEL_VERSION,input_hash:originalHash,outcomes:results,complete:false},null,1)+'\n');
for(const seed of seeds){
  const settings={...request.settings,seed},start=Date.now(),p=composePortfolio(snapshot,settings,{},request.rules,
    {candidates:full?120:80,paths:full?250:150,finalPaths:1000});
  results.push({seed,status:p.status,positions:p.positions,reason:p.reason,
    robustDecision:p.diagnostics.robustDecision.status,minimumLowerGain:p.diagnostics.robustDecision.minimumLowerGain,
    stability:p.diagnostics.stability,discovered:p.diagnostics.reliableSelection?.discovered,
    seconds:(Date.now()-start)/1000});
  console.log(JSON.stringify(results.at(-1)));
  checkpoint();
}
if(full){
  const without=structuredClone(snapshot);delete without.assets.find(a=>a.symbol==='VTI').equity_valuation;
  const p=composePortfolio(without,request.settings,{},request.rules,{candidates:120,paths:250,finalPaths:1000});
  results.push({id:'VTI-eligibility-only',status:p.status,positions:p.positions,reason:p.reason,
    robustDecision:p.diagnostics.robustDecision.status,stability:p.diagnostics.stability});
  checkpoint();
  const changed=structuredClone(snapshot),fund=changed.assets.find(a=>a.symbol==='IGSB');
  fund.bond_profile.yieldToMaturity-=.03;
  const altered=composePortfolio(changed,request.settings,{},request.rules,{candidates:120,paths:250,finalPaths:1000});
  results.push({id:'declared-sensitivity-IGSB-yield-minus-300bp',status:altered.status,positions:altered.positions,
    reason:altered.reason,robustDecision:altered.diagnostics.robustDecision.status,
    scope:'Controlled assumption sensitivity, not a new observed market snapshot'});
  checkpoint();
  const accountSettings={...request.settings,account:{enabled:true,cash:5000,
    positions:Object.entries({SPY:.35,SHY:.35,IEF:.25}).map(([symbol,weight])=>{
      const price=snapshot.assets.find(a=>a.symbol===symbol).price;
      return {symbol,quantity:100000*weight/price,costBasis:price};
    })}};
  const held=composePortfolio(snapshot,accountSettings,{},request.rules,{candidates:120,paths:250,finalPaths:1000});
  results.push({id:'hypothetical-held-account',status:held.status,positions:held.positions,reason:held.reason,
    cost:held.trade_plan?.total,scope:'Hypothetical account, not the user brokerage account'});
  checkpoint();
}
const mapped=p=>x.assets.map(a=>p.find(r=>r.symbol===a.symbol)?.weight||0),
  overlaps=results.slice(1).map(r=>({seed:r.seed,id:r.id,weight_overlap:weightOverlap(mapped(results[0].positions),mapped(r.positions))}));
const confirmation=seeds.map(seed=>{
  const audit=reviewRobustDecision(x,results[0].positions,{paths:1000,seed:seed^0x613a27e9});
  return {seed:audit.seed,status:audit.status,minimumLowerGain:audit.minimumLowerGain,
    worstCvarUpper:Math.max(...audit.models.map(m=>m.riskEvidence.rows[0].upper),audit.tailStress.riskEvidence?.rows[0].upper||0)};
});
if(createHash('sha256').update(JSON.stringify(snapshot)).digest('hex')!==originalHash)throw Error('Audit mutated source inputs');
mkdirSync('out',{recursive:true});
writeFileSync('out/reliability-audit.json',JSON.stringify({method:'frozen-input-reliability-v1',engine:MODEL_VERSION,
  market_collected_at:market.generated_at,input_hash:originalHash,null_experiment:nullExperiment,
  outcomes:results,overlaps,independent_confirmation_replicates:confirmation,
  predictive_validation:'not-established',scope:'Finite discovery, conditional simulated contrasts and independent Monte Carlo replicates. No historical trading superiority claim.'},null,1)+'\n');
console.log(JSON.stringify({overlaps,confirmation}));
