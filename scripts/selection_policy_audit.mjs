/** Attribute a frozen choice to economic assumptions and its tie-break policy. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {prepareComposition} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {MODEL_VARIANTS,variantInputs} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {pairedDecisionEvidence} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
import {tradePlan,MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';

const value=(flag,fallback)=>{const i=process.argv.indexOf(flag);return i<0?fallback:process.argv[i+1];};
const marketPath=value('--market','dist/data/market.json'),volPath=value('--volatility','dist/data/volatility.json'),
  poolPath=value('--pool','out/reliability-canonical.json'),out=value('--output','out/selection-policy-audit.json'),
  bytes=readFileSync(marketPath),market=JSON.parse(bytes),volatility=JSON.parse(readFileSync(volPath)),
  proposal=JSON.parse(readFileSync(poolPath)),request=referenceRequest({...market,volatility}),
  x=prepareComposition(market,request.settings,{},request.rules),paths=Number(value('--paths','3000')),
  seed=0x28ac1379,hash=buffer=>createHash('sha256').update(buffer).digest('hex');
if(market.generated_at!==proposal.snapshot_generated_at||volatility.source_market_generated_at!==market.generated_at)
  throw Error('Frozen proposal, market and variance vintages differ');
const candidates=proposal.diagnostics.reliableSelection.candidates.filter(r=>r.feasible&&!r.positions.every(p=>p.symbol==='CASH')),
  rows=candidates.map(c=>{
    if(c.positions.some(p=>!x.assets.some(a=>a.symbol===p.symbol)))throw Error('Candidate universe differs');
    const plan=tradePlan(x.assets,c.positions,x.current.positions,x.current.capital,x.costs);
    return {...c,plan,weights:x.assets.map(a=>c.positions.find(p=>p.symbol===a.symbol)?.weight||0),models:[]};
  });
for(const model of MODEL_VARIANTS){
  const altered=variantInputs(x,model),sample=generatePaths(altered,paths,seed,52);
  for(const row of rows){
    const m=evaluatePaths(row.weights,sample,{capital:x.current.capital,cost:row.plan.total,pathUtilities:true});
    row.models.push({id:model.id,score:m.score,certaintyEquivalent:m.certaintyEquivalent,
      cvar95:m.cvar95,utilities:m.pathUtilities});
  }
}
for(const row of rows)row.worstCertaintyEquivalent=Math.min(...row.models.map(m=>m.certaintyEquivalent));
const selected=rows.find(r=>r.selected),leader=[...rows].sort((a,b)=>b.worstCertaintyEquivalent-a.worstCertaintyEquivalent)[0];
if(!selected)throw Error('Selected candidate is absent from the frozen admissible pool');
const cross=leader.models.map(l=>selected.models.map(c=>{
  const e=pairedDecisionEvidence(l.utilities,c.utilities,x.policy,x.current.capital,rows.length*25);
  return {leaderModel:l.id,selectedModel:c.id,lowerUtilityGain:e.meanUtilityGain-e.z*e.standardError,...e};
}));
const worstObjectiveLowerGain=Math.max(...selected.models.map((_,k)=>Math.min(...cross.map(r=>r[k].lowerUtilityGain))));
const strip=r=>({positions:r.positions,selected:r.selected,worstCertaintyEquivalent:r.worstCertaintyEquivalent,
  maximumRiskInSelection:r.maximumRisk,turnover:r.plan.turnover,
  models:r.models.map(({utilities,...m})=>m)});
const leaderFor=ids=>{
  const ranked=rows.map(row=>({positions:row.positions,
    worstCertaintyEquivalent:Math.min(...row.models.filter(m=>ids.includes(m.id)).map(m=>m.certaintyEquivalent))}))
    .sort((a,b)=>b.worstCertaintyEquivalent-a.worstCertaintyEquivalent);
  return ranked[0];
};
const report={engine:MODEL_VERSION,method:'frozen-candidate-policy-attribution-v1',paths,seed,
  source_market_sha256:hash(bytes),source_pool_sha256:hash(readFileSync(poolPath)),
  market_collected_at:market.generated_at,price_cut:market.price_as_of,
  assessed_pool_sha256:hash(JSON.stringify(candidates.map(r=>({positions:r.positions,selected:r.selected})))),
  sensitivityLeaders:{base:leaderFor(['original']),withoutLowConviction:leaderFor(MODEL_VARIANTS.filter(m=>m.id!=='low_conviction').map(m=>m.id)),
    allFive:leaderFor(MODEL_VARIANTS.map(m=>m.id))},
  selected:strip(selected),worstObjectiveLeader:strip(leader),
  worstObjectiveCertaintyEquivalentGap:leader.worstCertaintyEquivalent-selected.worstCertaintyEquivalent,
  worstObjectiveLowerUtilityGain:worstObjectiveLowerGain,crossModelPairedComparisons:cross,
  candidates:rows.map(strip),
  scope:'Independent Monte Carlo attribution of the frozen admissible candidate pool, not a rerun of discovery, global optimization, out-of-sample market validation or a new recommendation.'};
mkdirSync('out',{recursive:true});writeFileSync(out,JSON.stringify(report,null,1)+'\n');
console.log(JSON.stringify({selected:report.selected,leader:report.worstObjectiveLeader,
  robustGap:report.worstObjectiveCertaintyEquivalentGap,robustLowerUtility:worstObjectiveLowerGain}));
