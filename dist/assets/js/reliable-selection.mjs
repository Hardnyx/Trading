import { generatePaths, evaluatePaths } from './path-model.mjs?v=0.34.1';
import { MODEL_VARIANTS, variantInputs } from './robust-core.mjs?v=0.34.1';
import { pairedDecisionEvidence, reviewRobustDecision, tailStressInputs, DECISION_EXPERIMENT_SEEDS } from './robust-decision.mjs?v=0.34.1';
import { riskSamplingEvidence } from './simulation-evidence.mjs?v=0.34.1';
import { tradePlan } from './policy.mjs?v=0.34.1';

const overlap = (a,b) => a.reduce((s,w,i)=>s+Math.min(w,b[i]),0);
const positions = (x,w) => x.assets.flatMap((a,i)=>w[i]>1e-9?[{symbol:a.symbol,weight:w[i]}]:[]);
const keyOf = positions => positions.map(p=>[p.symbol,Math.round(p.weight*1e8)])
  .sort((a,b)=>a[0].localeCompare(b[0])).map(p=>p.join(':')).join('|');

/** A finite, auditable opportunity set; no global-optimality claim. */
export function selectReliableCandidate(inputs, candidates, { paths = 1000, validWeights, starts = 1 } = {}) {
  const x=inputs, capital=x.current.capital,
    current=x.assets.map(a=>x.current.positions.find(p=>p.symbol===a.symbol)?.weight||0),
    heldKey=keyOf(x.current.positions), seen=new Set(), rows=[];
  if(x.options.innovationLaw==='student-t-research')throw Error('El estrés Student no selecciona carteras económicas');
  if(!Number.isFinite(x.riskFree))throw Error('Falta tasa corta al corte para una selección económica completa');
  const add = p => {
    if (!p?.length || p.some(r=>!x.assets.some(a=>a.symbol===r.symbol))) return;
    const key=keyOf(p); if(seen.has(key))return;seen.add(key);
    const w=x.assets.map(a=>Math.round((p.find(r=>r.symbol===a.symbol)?.weight||0)*1e8)/1e8), hold=key===heldKey;
    if (!hold && !validWeights(w,x)) return;
    const plan=tradePlan(x.assets,positions(x,w),x.current.positions,capital,x.costs);
    const initial=x.current.source==='Capital inicial en efectivo';
    if(!hold && (!plan.complete||plan.smallTrades||(!initial&&plan.turnover>x.costs.maxTurnover+1e-8)))return;
    rows.push({key,weights:w,positions:positions(x,w),plan,hold,
      worstScore:Infinity,maximumRisk:0,screenPass:true,models:[]});
  };
  add(x.current.positions); for(const p of candidates)add(p);
  const inputsByModel=MODEL_VARIANTS.map(v=>variantInputs(x,v));
  // Every discovered candidate is screened under ALL economic models. These
  // draws are never reused for choosing finalists or confirming a transition.
  for(const altered of inputsByModel){
    const sample=generatePaths(altered,100,DECISION_EXPERIMENT_SEEDS.screen,12);
    for(const row of rows){
      const m=evaluatePaths(row.weights,sample,{capital,cost:row.plan.total});
      row.worstScore=Math.min(row.worstScore,m.score);
      row.maximumRisk=Math.max(row.maximumRisk,m.cvar95);
      // Loose screen only; sampling margins are enforced on fresh paths.
      if(m.cvar95>x.rules.cvarBudget+2*m.cvar95SE||
         m.lossProbability>x.rules.maxLossProbability+2*m.lossProbabilitySE||
         m.liquidityFailureProbability>x.policy.maxLiquidityFailure+.05)row.screenPass=false;
    }
  }
  const screened=rows.filter(r=>r.hold||r.screenPass), picked=new Set();
  const best=[...screened].sort((a,b)=>b.worstScore-a.worstScore||a.key.localeCompare(b.key));
  for(const r of best.slice(0,16))picked.add(r.key);
  for(const r of [...screened].filter(r=>!r.hold).sort((a,b)=>a.maximumRisk-b.maximumRisk||b.worstScore-a.worstScore).slice(0,6))picked.add(r.key);
  picked.add(heldKey);
  const finalists=screened.filter(r=>picked.has(r.key)).map(r=>({...r,worstScore:Infinity,
    feasible:true,maximumRisk:0,minimumLowerGain:Infinity}));
  for(let k=0;k<inputsByModel.length;k++){
    const altered=inputsByModel[k], sample=generatePaths(altered,paths,DECISION_EXPERIMENT_SEEDS.selection,52),
      held=evaluatePaths(current,sample,{capital,cost:0,pathUtilities:true});
    for(const row of finalists){
      const m=evaluatePaths(row.weights,sample,{capital,cost:row.plan.total,pathUtilities:true}),
        evidence=pairedDecisionEvidence(m.pathUtilities,held.pathUtilities,x.policy,capital),
        risk=riskSamplingEvidence(m,x.rules,x.policy),
        hurdle=Math.max(x.costs.minBenefit,row.plan.total*x.costs.benefitCostRatio);
      row.models.push({id:MODEL_VARIANTS[k].id,utilities:m.pathUtilities,evidence,risk});
      row.worstScore=Math.min(row.worstScore,m.score);
      row.minimumLowerGain=Math.min(row.minimumLowerGain,evidence.lowerGain);
      row.maximumRisk=Math.max(row.maximumRisk,risk.rows[0].upper);
      if(risk.failures.length||(!row.hold&&(evidence.meanUtilityGain<=0||evidence.lowerGain<hurdle)))row.feasible=false;
    }
  }
  const tail=tailStressInputs(x), tailSample=generatePaths(tail,paths,DECISION_EXPERIMENT_SEEDS.selection,52);
  for(const row of finalists){
    const risk=riskSamplingEvidence(evaluatePaths(row.weights,tailSample,{capital,cost:row.plan.total,riskOnly:true}),x.rules,x.policy);
    row.maximumRisk=Math.max(row.maximumRisk,risk.rows[0].upper);
    if(risk.failures.length)row.feasible=false;
  }
  const eligible=finalists.filter(r=>!r.hold&&r.feasible),
    leader=[...eligible].sort((a,b)=>b.worstScore-a.worstScore||a.key.localeCompare(b.key))[0];
  const unresolved=leader?eligible.filter(row=>row===leader||!row.models.every((m,k)=>
    pairedDecisionEvidence(leader.models[k].utilities,m.utilities,x.policy,capital,
      Math.max(5,eligible.length*5)).lowerGain>x.costs.minBenefit)):[];
  // This is an explicit conservative policy for unresolved rankings, not a
  // claim that failure to reject proves statistical equivalence.
  const chosen=[...unresolved].sort((a,b)=>{
    const d=a.plan.turnover-b.plan.turnover;
    return Math.abs(d)>1e-9?d:a.maximumRisk-b.maximumRisk||a.key.localeCompare(b.key);
  })[0]||finalists.find(r=>r.hold);
  if(!chosen)throw Error('No se pudo conservar la referencia de la cuenta');
  const peers=unresolved.filter(r=>r!==chosen), minimumOverlap=peers.length?
    Math.min(...peers.map(r=>overlap(chosen.weights,r.weights))):1;
  const ranges=x.assets.map((a,i)=>({symbol:a.symbol,
    minimum:unresolved.length?Math.min(...unresolved.map(r=>r.weights[i])):current[i],
    maximum:unresolved.length?Math.max(...unresolved.map(r=>r.weights[i])):current[i]}))
    .filter(r=>r.maximum>1e-9);
  const stability={method:'robust-finite-pool',starts,compared:finalists.length,commonPaths:paths,
    unresolved:peers.length,minimumOverlap,ranges,
    level:minimumOverlap>=.8?'high':minimumOverlap>=.6?'medium':'low',
    scope:'Unresolved modelwise rankings; sampling uncertainty is not parameter or predictive validity'};
  // Exactly ONE selected transition reaches confirmation. A rejection cannot
  // be used to try the next candidate on the same confirmation data.
  const audit=reviewRobustDecision(x,chosen.positions,{paths,validWeights});
  return {positions:chosen.positions,weights:chosen.weights,plan:chosen.plan,audit,stability,
    selection:{method:'all-models-finite-pool-with-independent-confirmation',discovered:rows.length,
      screened:screened.length,finalists:finalists.length,admissible:eligible.length,
      seeds:DECISION_EXPERIMENT_SEEDS,policy:'minimum-turnover-then-risk-among-unresolved',
      confirmationAttempts:1,globalOptimalityClaim:false,
      minimumSelectedLowerGain:chosen.minimumLowerGain,
      candidates:finalists.map(r=>({positions:r.positions,feasible:r.feasible,
        minimumLowerGain:r.minimumLowerGain,maximumRisk:r.maximumRisk,
        turnover:r.plan.turnover,selected:r===chosen}))}};
}
