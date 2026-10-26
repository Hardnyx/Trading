import {prepareComposition,validWeights} from "./composer.mjs?v=0.12.0";
import {generatePaths,evaluatePaths} from "./path-model.mjs?v=0.12.0";
import {distributionAccounting,distributionTerminalValue} from "./distribution-ledger.mjs?v=0.12.0";
import {tradePlan,MODEL_VERSION} from "./policy.mjs?v=0.12.0";
import {bondAssumptions} from "./research-model.mjs?v=0.12.0";
import {seededRandom} from "./random.mjs?v=0.12.0";
import {MODEL_VARIANTS,variantInputs,minimaxRegret,pairedUtilityEvidence} from "./robust-core.mjs?v=0.12.0";
import {robustTransition} from './robust-transition.mjs?v=0.12.0';

export function compareRobustPortfolio(snapshot,settings={},overrides={},rules={},options={}){
 const config={candidateCount:300,searchPaths:200,verificationPaths:1000,finalists:6,
   localRounds:2,localStarts:2,seed:settings.seed??20261024,...options.config};
 for(const key of ['candidateCount','searchPaths','verificationPaths','finalists','localRounds','localStarts','seed'])
   if(!Number.isInteger(config[key])||config[key]<1)throw Error('Presupuesto de robustez inválido');
 if(config.candidateCount>3000||config.searchPaths<100||config.verificationPaths<100||
    config.verificationPaths>3000||config.searchPaths>1000||config.finalists>20||config.localRounds>4||config.localStarts>4)
   throw Error('Reduce el presupuesto de cálculo de robustez');
 const x=prepareComposition(snapshot,settings,overrides,rules);
 x.valuationOverrides=overrides;
 if(x.policy.objective!=='growth'||x.policy.referenceCurrency!=='USD'||
    x.policy.monthlyWithdrawal||x.policy.withdrawals.length||x.policy.capitalFloor||x.policy.terminalTarget)
   throw Error('La comparación robusta admite crecimiento en USD sin retiros, suelo ni meta de capital. Tu mandato se conserva; ajusta esos campos solo si corresponde.');
 for(const a of x.assets){
   if(a.type!=='etf'||!x.current.positions.some(p=>p.symbol===a.symbol&&p.weight>0))continue;
   const own=x.options.assetAssumptions?.[a.symbol];
   if(!bondAssumptions(a,x.options)&&!(Number.isFinite(own?.expectedReturn)&&own?.uncertainty>0))
     throw Error('Completa retorno esperado e incertidumbre de '+a.symbol+' en Research antes de comparar robustez.');
 }
 const progress=options.onProgress||(()=>{});
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
 const hold=id==='current-account',initial=x.current.source==='Capital inicial en efectivo';
 const structuralFeasible=validWeights(w,x);
 const executionFeasible=plan.complete&&(hold||plan.smallTrades===0)&&
   (hold||initial||plan.turnover<=x.costs.maxTurnover+1e-8);
 rows.push({id,weights:w,positions:positions(w),cost:plan.total,turnover:plan.turnover,
  structuralFeasible,executionFeasible,feasible:structuralFeasible&&executionFeasible,utilities:{},screen:{}});
}
const allCash=Array(n).fill(0);allCash[cash]=1;
add('current-account',current);add('cash',allCash);
if(options.proposal?.positions?.length){
 const p=options.proposal.positions;
 if(p.every(row=>x.assets.some(a=>a.symbol===row.symbol)))add('session-proposal',weights(p));
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
progress('Candidatas iniciales',rows.length);
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
 progress('Escenario de búsqueda',ids[s]);
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
 progress('Intercambios locales',round+1);
 if(rows.length===start)break;
}
const screened=minimaxRegret(rows,ids);
if(!screened.best)throw Error('Ninguna candidata cumplió los límites en los cinco modelos de búsqueda');
// Union of robust finalists, each model's best, plus explicit references.
const picked=new Set(screened.ranking.slice(0,config.finalists).map(r=>r.id));
for(const id of ids){const winner=rows.filter(r=>r.feasible).sort((a,b)=>b.utilities[id]-a.utilities[id])[0];if(winner)picked.add(winner.id);}
for(const row of rows)if(!row.id.startsWith('search-')&&!row.id.startsWith('local-'))picked.add(row.id);
const final=rows.filter(r=>picked.has(r.id)).map(r=>({...r,feasible:r.structuralFeasible&&r.executionFeasible,utilities:{},verification:{}}));
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
 progress('Verificación semanal',ids[s]);
}
const ranked=minimaxRegret(final,ids),incumbent=final.find(r=>r.id==='current-account');
const best=ranked.best;
const pairedGains=best?Object.fromEntries(ids.map(id=>[id,
 x.current.capital*(Math.exp(best.utilities[id])-Math.exp(incumbent.utilities[id]))])):null;
const threshold=best?Math.max(x.costs.minBenefit,best.cost*x.costs.benefitCostRatio):null;
const robustImprovement=best&&ids.every(id=>best.pairedMonteCarlo[id].lower_ce_gain_dollars>=threshold);

 return {schema_version:1,model_version:MODEL_VERSION,method:'fixed-universe-minimax-regret',experimental:true,
   as_of:x.asOf,information_as_of:x.informationAsOf,snapshot_generated_at:snapshot.generated_at,
   horizon:x.options.horizon,capital:x.current.capital,config,universe:x.assets.map(a=>a.symbol),account_source:options.comparisonLabel||x.current.source,
   candidate_count:rows.length,screen_feasible:screened.ranking.length,verified_candidates:final.length,
   verification_feasible:ranked.ranking.length,rules:x.rules,
   candidate:best?{...best,weights:undefined,screen:undefined,
    transition:robustTransition(x.assets,x.current.positions,best.positions,x.current.capital,x.costs)}:null,
   current:{...incumbent,weights:undefined,screen:undefined},
   scenarios:inputs.map((v,i)=>({id:ids[i],description:MODEL_VARIANTS[i].description,
     earnings_stresses:v.stressEvidence,anchors:v.anchors.map(a=>({symbol:a.symbol,annual:a.annual,low:a.low,high:a.high}))})),
   paired_certainty_equivalent_gain_dollars:pairedGains,required_gain_dollars:threshold,
   decision:robustImprovement?'candidate_survives_assumed_models':'no_robust_rebalance_evidence',
   no_candidate_reason:best?null:'Ninguna candidata superó todos los límites en los cinco modelos.',
   limitations:'Búsqueda finita y supuestos sin calibración predictiva. Los intervalos cubren error de simulación, no error del modelo. El estrés de margen no es BPA contable normalizado.'};
}
