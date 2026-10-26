/** Fixed-universe, paired-model, finite-pool minimax-regret research. Not a live trading signal. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.9.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.9.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.9.0';
import {distributionAccounting,distributionTerminalValue} from '../dist/assets/js/distribution-ledger.mjs?v=0.9.0';
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.9.0';
import {seededRandom} from '../dist/assets/js/random.mjs?v=0.9.0';
import {MODEL_VARIANTS,variantInputs,minimaxRegret,pairedUtilityEvidence} from './robust_portfolio_core.mjs';

const market=JSON.parse(readFileSync('dist/data/market.json'));
const volatility=JSON.parse(readFileSync('dist/data/volatility.json'));
if(volatility.source_market_generated_at!==market.generated_at)throw Error('Inconsistent risk vintage');
const profiles=JSON.parse(readFileSync(process.argv[2]));
const config={candidateCount:1200,searchPaths:300,verificationPaths:1500,finalists:12,localRounds:3,localStarts:3,
  seed:20261026,...(process.argv[4]?JSON.parse(readFileSync(process.argv[4])):{})};
for(const key of ['candidateCount','searchPaths','verificationPaths','finalists','seed','localRounds','localStarts'])
 if(!Number.isInteger(config[key])||config[key]<1)throw Error('Invalid research configuration');
if(config.searchPaths<100||config.verificationPaths<100||config.candidateCount>10000||config.finalists>30||config.localRounds>6||config.localStarts>6)
 throw Error('Research budget outside supported bounds');
const snapshot={...market,volatility,assets:market.assets.map(a=>profiles[a.symbol]?{...a,bond_profile:profiles[a.symbol]}:a)};
const preset=referenceRequest(snapshot);
const shortRate=snapshot.macro.find(r=>r.id==='DGS3MO')?.value/100;
if(!Number.isFinite(shortRate))throw Error('Missing observed short-rate anchor');
const accountInput=JSON.parse(readFileSync(process.argv[3]));
if(!accountInput.account?.enabled)throw Error('Supply an explicit research account file');
// Explicit hypotheses for held funds. These are sensitivity inputs, not
// inferred analyst forecasts or validated asset-class expected returns.
const hypotheses={VTI:{expectedReturn:shortRate+.035,uncertainty:.15},
  GLD:{expectedReturn:0,uncertainty:.15}};
const settings={...preset.settings,seed:config.seed,assetAssumptions:hypotheses,
  account:accountInput.account};
const x=prepareComposition(snapshot,settings,{},preset.rules);
if(x.policy.objective!=='growth'||x.policy.referenceCurrency!=='USD'||
 x.policy.monthlyWithdrawal||x.policy.withdrawals.length||x.policy.capitalFloor||x.policy.terminalTarget)
 throw Error('Terminal screening only implemented for USD growth without flows/floor/target');
const ids=MODEL_VARIANTS.map(v=>v.id),inputs=MODEL_VARIANTS.map(v=>variantInputs(x,v));
const n=x.assets.length,cash=x.assets.findIndex(a=>a.symbol==='CASH');
const weights=positions=>x.assets.map(a=>positions.find(p=>p.symbol===a.symbol)?.weight||0);
const positions=w=>w.flatMap((weight,i)=>weight>1e-9?[{symbol:x.assets[i].symbol,weight}]:[]);
const current=weights(x.current.positions);
const rows=[],seen=new Set();
function add(id,w){
 if(Math.abs(w.reduce((a,b)=>a+b,0)-1)>1e-8)throw Error('Missing or unknown portfolio weights');
 const key=w.map(v=>v.toFixed(8)).join(',');if(seen.has(key))return;
 seen.add(key);const plan=tradePlan(x.assets,positions(w),x.current.positions,x.current.capital,x.costs);
 rows.push({id,weights:w,positions:positions(w),cost:plan.total,turnover:plan.turnover,
  structuralFeasible:validWeights(w,x),feasible:validWeights(w,x),utilities:{},screen:{}});
}
const allCash=Array(n).fill(0);allCash[cash]=1;
add('current-account',current);add('cash',allCash);
const omittedReferences=[];
for(const [id,p] of [
 ['previous-reference',[['SHY',.35],['CASH',.15],['CMCSA',.20],['AMZN',.15],['MU',.05],['NFLX',.05],['NVDA',.05]]],
 ['concentrated-reference',[['TLT',.05],['SHY',.35],['CASH',.10],['CMCSA',.20],['ADBE',.15],['MU',.15]]],
 ['passive-under-caps',[['VTI',.35],['SHY',.35],['IEF',.15],['GLD',.05],['CASH',.10]]],
]) {
 const missing=p.filter(([symbol])=>!x.assets.some(a=>a.symbol===symbol)).map(([symbol])=>symbol);
 if(missing.length)omittedReferences.push({id,reason:'Reference instrument outside fixed universe',missing});
 else add(id,weights(p.map(([symbol,weight])=>({symbol,weight}))));
}
const random=seededRandom(config.seed);
for(let trial=0;trial<config.candidateCount;trial++){
 const w=[...allCash];
 const order=x.assets.map((a,i)=>({i,key:random()})).filter(r=>r.i!==cash&&x.buyAllowed[r.i])
  .sort((a,b)=>a.key-b.key).slice(0,x.rules.maxPositions-1).map(r=>r.i);
 const transfers=1+Math.floor(random()*19);
 for(let unit=0;unit<transfers;unit++){
  for(let attempt=0;attempt<order.length*2;attempt++){
   const i=order[Math.floor(random()*order.length)];
   w[i]+=.05;w[cash]-=.05;
   if(validWeights(w,x))break;
   w[i]-=.05;w[cash]+=.05;
  }
 }
 add('search-'+String(trial).padStart(5,'0'),w);
}
console.log('Fixed pool',x.assets.map(a=>a.symbol).join(','),'candidate allocations',rows.length);
function terminals(sample){
 const accounting=distributionAccounting(sample);
 return sample.assets.map((_,i)=>Float64Array.from({length:sample.paths},(_,p)=>
   distributionTerminalValue(accounting[i],sample,i,p)));
}
function terminalMetrics(w,terminal,cost){
 const selected=w.map((weight,i)=>({weight,i})).filter(r=>r.weight>1e-9);
 const returns=[];let log=0,loss=0;
 for(let p=0;p<terminal[0].length;p++){
  let gross=0;for(const r of selected)gross+=r.weight*terminal[r.i][p];
  const value=gross*(1-cost/x.current.capital)-1;
  returns.push(value);log+=Math.log(Math.max(1e-5,1+value));loss+=value<0;
 }
 returns.sort((a,b)=>a-b);const k=Math.max(1,Math.ceil(returns.length*.05));
 return {utility:log/returns.length,medianReturn:returns[Math.floor(returns.length/2)],
  cvar95:Math.max(0,-returns.slice(0,k).reduce((a,b)=>a+b,0)/k),lossProbability:loss/returns.length};
}
const screeningTerminals=[];
for(let s=0;s<inputs.length;s++){
 const sample=generatePaths(inputs[s],config.searchPaths,config.seed+1,52),terminal=terminals(sample);
 screeningTerminals.push(terminal);
 for(const row of rows){
  const m=terminalMetrics(row.weights,terminal,row.cost);row.screen[ids[s]]=m;row.utilities[ids[s]]=m.utility;
  if(m.cvar95>x.rules.cvarBudget||m.lossProbability>x.rules.maxLossProbability)row.feasible=false;
 }
 console.log('Screened',ids[s]);
}
for(let round=0;round<config.localRounds;round++){
 const leaders=minimaxRegret(rows,ids).ranking.slice(0,config.localStarts);
 const start=rows.length;
 for(const leader of leaders){
  for(let from=0;from<n;from++){
   if(leader.weights[from]<.05-1e-8)continue;
   for(let to=0;to<n;to++){
    if(to===from||!x.buyAllowed[to])continue;
    const w=[...leader.weights];w[from]-=.05;w[to]+=.05;
    if(validWeights(w,x))add('local-'+round+'-'+rows.length,w);
   }
  }
 }
 for(const row of rows.slice(start))for(let s=0;s<ids.length;s++){
  const m=terminalMetrics(row.weights,screeningTerminals[s],row.cost);
  row.screen[ids[s]]=m;row.utilities[ids[s]]=m.utility;
  if(m.cvar95>x.rules.cvarBudget||m.lossProbability>x.rules.maxLossProbability)row.feasible=false;
 }
 console.log('Local exchanges',round,'added',rows.length-start);
 if(rows.length===start)break;
}
const screened=minimaxRegret(rows,ids);
if(!screened.best)throw Error('No candidate passed all terminal model screens');
// Union of robust finalists, each model's best, plus explicit references.
const picked=new Set(screened.ranking.slice(0,config.finalists).map(r=>r.id));
for(const id of ids){const winner=rows.filter(r=>r.feasible).sort((a,b)=>b.utilities[id]-a.utilities[id])[0];if(winner)picked.add(winner.id);}
for(const row of rows)if(!row.id.startsWith('search-')&&!row.id.startsWith('local-'))picked.add(row.id);
const final=rows.filter(r=>picked.has(r.id)).map(r=>({...r,feasible:r.structuralFeasible,utilities:{},verification:{}}));
for(let s=0;s<inputs.length;s++){
 const sample=generatePaths(inputs[s],config.verificationPaths,config.seed+100003,52);
 const baseline=evaluatePaths(current,sample,{capital:x.current.capital,cost:0,details:true});
 for(const row of final){
  const m=evaluatePaths(row.weights,sample,{capital:x.current.capital,cost:row.cost,details:true});
  row.pairedMonteCarlo??={};
  row.pairedMonteCarlo[ids[s]]=pairedUtilityEvidence(m.terminal,baseline.terminal,
    x.current.capital,final.length*ids.length);
  row.utilities[ids[s]]=m.expectedLogGrowth;
  row.verification[ids[s]]={medianReturn:m.medianReturn,cvar95:m.cvar95,
   lossProbability:m.lossProbability,expectedLogGrowth:m.expectedLogGrowth,
   drawdownProbability:m.drawdownProbability,liquidityFailureProbability:m.liquidityFailureProbability};
  if(m.cvar95>x.rules.cvarBudget||m.lossProbability>x.rules.maxLossProbability||
    m.drawdownProbability>x.policy.maxDrawdownProbability||m.liquidityFailureProbability>x.policy.maxLiquidityFailure)
   row.feasible=false;
 }
 console.log('Verified weekly',ids[s]);
}
const ranked=minimaxRegret(final,ids),incumbent=final.find(r=>r.id==='current-account');
const best=ranked.best;
const pairedGains=best?Object.fromEntries(ids.map(id=>[id,
 x.current.capital*(Math.exp(best.utilities[id])-Math.exp(incumbent.utilities[id]))])):null;
const threshold=best?Math.max(x.costs.minBenefit,best.cost*x.costs.benefitCostRatio):null;
const robustImprovement=best&&ids.every(id=>best.pairedMonteCarlo[id].lower_ce_gain_dollars>=threshold);
const report={method:'fixed-universe-finite-pool-minimax-regret-shadow-v1',not_promoted:true,
 generated_at:new Date().toISOString(),source_market_generated_at:market.generated_at,price_as_of:market.price_as_of,
 information_observed_through:Object.values(profiles).map(p=>p.observed_at).concat(market.generated_at).sort().at(-1),
 market_sha256:createHash('sha256').update(readFileSync('dist/data/market.json')).digest('hex'),
 config,universe:x.assets.map(a=>a.symbol),selection:x.selection,rules:x.rules,
 account:{positions:x.current.positions,capital_at_snapshot_prices:x.current.capital,
   observation_basis:accountInput.basis||'Explicit research account; valued at saved market prices, not live execution quotes'},
 explicit_etf_hypotheses:hypotheses,issuer_profiles:profiles,
 scenarios:inputs.map((v,i)=>({id:v.variant,description:MODEL_VARIANTS[i].description,
  anchors:v.anchors.map(a=>({symbol:a.symbol,annual:a.annual,low:a.low,high:a.high,source:a.source})),
  earnings_stresses:v.stressEvidence})),
 omitted_references:omittedReferences,
 candidate_count:rows.length,screen_feasible:screened.ranking.length,verified_candidates:final.length,
 verification_feasible:ranked.ranking.length,benchmarks:ranked.benchmarks,
 candidate:best?{...best,weights:undefined,screen:undefined}:null,
 current:{...incumbent,weights:undefined,screen:undefined},
 references:final.filter(r=>!r.id.startsWith('search-')&&!r.id.startsWith('local-')).map(r=>({...r,weights:undefined,screen:undefined})),
 ranking:ranked.ranking.slice(0,10).map(r=>({...r,weights:undefined,screen:undefined})),
 paired_certainty_equivalent_gain_dollars:pairedGains,required_gain_dollars:threshold,
 decision:robustImprovement?'candidate_survives_all_assumed_model_utilities':'no_robust_rebalance_evidence',
 limitations:['Finite candidate pool, local 5-percentage-point exchanges and fixed shortlist; not a global optimum.',
 'Operating-margin ratio is only an EPS stress, not accounting normalization.',
 'ETF returns, multiples and scenario set are hypotheses, not OOS-calibrated probabilities.',
 'Common random numbers pair portfolios and variants; verification seed is independent of search.',
 'Monte Carlo intervals condition on each model; no mature prospective economic validation or live order authorization.',
 'Current VTI holding can exceed the 35% construction cap; report this separately from economic superiority.',
 'Value horizon is annualized as in the live model; no demonstrated 12-month convergence to exit multiples.']};
mkdirSync('out',{recursive:true});writeFileSync('out/portfolio-robustness.json',JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({candidate:best?.positions,decision:report.decision,gains:pairedGains,threshold,
 incumbentStructuralFeasibility:incumbent.structuralFeasible,output:'out/portfolio-robustness.json'}));
