import { generatePaths, evaluatePaths, utilityCertaintyEquivalent } from './path-model.mjs?v=0.35.0';
import { MODEL_VARIANTS, variantInputs } from './robust-core.mjs?v=0.35.0';
import { pairedDecisionEvidence, reviewRobustDecision, tailStressInputs, DECISION_EXPERIMENT_SEEDS } from './robust-decision.mjs?v=0.35.0';
import { riskSamplingEvidence } from './simulation-evidence.mjs?v=0.35.0';
import { tradePlan } from './policy.mjs?v=0.35.0';

const overlap = (a,b) => a.reduce((s,w,i)=>s+Math.min(w,b[i]),0);
const positions = (x,w) => x.assets.flatMap((a,i)=>w[i]>1e-9?[{symbol:a.symbol,weight:w[i]}]:[]);
const keyOf = positions => positions.map(p=>[p.symbol,Math.round(p.weight*1e8)])
  .sort((a,b)=>a[0].localeCompare(b[0])).map(p=>p.join(':')).join('|');

/** Approximate simultaneous MC bounds for the ACTUAL maximin objective.
 * min(a)-min(b) = max_k min_l (a_l-b_k). Pair the same simulated paths in
 * every cross-model contrast; do not confuse non-rejection with equivalence.
 */
export function robustRegretEvidence(leaderModels, alternativeModels, policy, capital, familySize=25) {
  const mean=values=>values.reduce((a,b)=>a+b,0)/values.length;
  if(!leaderModels.length||!alternativeModels.length)throw Error('Incomplete robust objective grid');
  const baseline=Math.min(...alternativeModels.map(m=>mean(m.utilities)));
  let point=-Infinity,lower=-Infinity,upper=-Infinity;
  for(const candidate of alternativeModels){
    let p=Infinity,l=Infinity,u=Infinity;
    for(const leader of leaderModels){
      const e=pairedDecisionEvidence(leader.utilities,candidate.utilities,policy,capital,familySize),
        margin=e.z*e.standardError;
      p=Math.min(p,e.meanUtilityGain);l=Math.min(l,e.meanUtilityGain-margin);
      u=Math.min(u,e.meanUtilityGain+margin);
    }
    point=Math.max(point,p);lower=Math.max(lower,l);upper=Math.max(upper,u);
  }
  const difference=v=>utilityCertaintyEquivalent(baseline+v,policy,capital)-
    utilityCertaintyEquivalent(baseline,policy,capital);
  return {gain:difference(point),lowerGain:difference(lower),upperGain:Math.max(0,difference(upper)),
    lowerUtilityGain:lower,upperUtilityGain:upper,familySize,
    scope:'Paired cross-model Monte Carlo approximation with plug-in certainty-equivalent conversion; not predictive confidence'};
}

/** Rank assessed rows against the mandate's worst-model utility, then bound
 * the opportunity loss before applying a turnover preference. */
export function rankRobustCandidates(eligible,policy,capital,indifferenceDollars) {
  const leader=[...eligible].sort((a,b)=>b.worstScore-a.worstScore||a.key.localeCompare(b.key))[0],
    familySize=Math.max(25,eligible.length**2*25);
  for(const row of eligible)row.regret=robustRegretEvidence(leader.models,row.models,policy,capital,familySize);
  const unresolved=leader?eligible.filter(row=>row===leader||row.regret.lowerGain<=indifferenceDollars):[],
    indifferent=leader?eligible.filter(row=>row===leader||row.regret.upperGain<=indifferenceDollars):[];
  const chosen=[...indifferent].sort((a,b)=>{
    const d=a.plan.turnover-b.plan.turnover;
    return Math.abs(d)>1e-9?d:b.worstScore-a.worstScore||a.maximumRisk-b.maximumRisk||a.key.localeCompare(b.key);
  })[0]||null;
  return {leader,unresolved,indifferent,chosen};
}

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
      row.models.push({id:MODEL_VARIANTS[k].id,score:m.score,utilities:m.pathUtilities,evidence,risk});
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
  const eligible=finalists.filter(r=>!r.hold&&r.feasible);
  // The point leader is adaptive: cover every possible leader/alternative
  // and cross-model pair, not just contrasts chosen after seeing the paths.
  const ranking=rankRobustCandidates(eligible,x.policy,capital,x.costs.minBenefit),
    {leader,unresolved,indifferent}=ranking;
  // Prefer lower turnover only when the estimated opportunity loss has an
  // upper bound inside the mandate's economic indifference threshold. An
  // uncertain ranking alone cannot replace growth with minimum risk.
  const chosen=ranking.chosen||finalists.find(r=>r.hold);
  if(!chosen)throw Error('No se pudo conservar la referencia de la cuenta');
  const peers=unresolved.filter(r=>r!==chosen), minimumOverlap=peers.length?
    Math.min(...peers.map(r=>overlap(chosen.weights,r.weights))):1;
  const rangeRows=[...new Set([...unresolved,chosen])];
  const ranges=x.assets.map((a,i)=>({symbol:a.symbol,
    minimum:Math.min(...rangeRows.map(r=>r.weights[i])),
    maximum:Math.max(...rangeRows.map(r=>r.weights[i]))}))
    .filter(r=>r.maximum>1e-9);
  const stability={method:'robust-finite-pool',starts,compared:finalists.length,commonPaths:paths,
    selectionRule:'bounded-regret',practicalTies:Math.max(0,indifferent.length-1),
    indifferenceDollars:x.costs.minBenefit,selectedRegretUpper:chosen.regret?.upperGain??null,
    unresolved:peers.length,minimumOverlap,ranges,
    level:minimumOverlap>=.8?'high':minimumOverlap>=.6?'medium':'low',
    scope:'Unresolved worst-objective rankings; sampling uncertainty is not parameter or predictive validity'};
  // Exactly ONE selected transition reaches confirmation. A rejection cannot
  // be used to try the next candidate on the same confirmation data.
  const audit=reviewRobustDecision(x,chosen.positions,{paths,validWeights});
  return {positions:chosen.positions,weights:chosen.weights,plan:chosen.plan,audit,stability,
    selection:{method:'all-models-finite-pool-with-independent-confirmation',discovered:rows.length,
      screened:screened.length,finalists:finalists.length,admissible:eligible.length,
      seeds:DECISION_EXPERIMENT_SEEDS,policy:'maximin-objective-with-bounded-regret-turnover-ties',
      indifferenceDollars:x.costs.minBenefit,selectedRegret:chosen.regret??null,
      pointLeader:leader?{positions:leader.positions,
        worstCertaintyEquivalent:utilityCertaintyEquivalent(leader.worstScore,x.policy,capital)}:null,
      confirmationAttempts:1,globalOptimalityClaim:false,
      minimumSelectedLowerGain:chosen.minimumLowerGain,
      candidates:finalists.map(r=>({positions:r.positions,feasible:r.feasible,
        worstCertaintyEquivalent:utilityCertaintyEquivalent(r.worstScore,x.policy,capital),regret:r.regret??null,
        minimumLowerGain:r.minimumLowerGain,maximumRisk:r.maximumRisk,
        turnover:r.plan.turnover,selected:r===chosen}))}};
}
