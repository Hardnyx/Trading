/** Read-only attribution of two published allocations under two frozen cuts. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {factorizeStressedCovariance} from '../dist/assets/js/factor-covariance.mjs?v=0.35.0';
import {MODEL_VARIANTS,variantInputs} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {pairedDecisionEvidence,reviewRobustDecision} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
import {robustRegretEvidence} from '../dist/assets/js/reliable-selection.mjs?v=0.35.0';
import {tradePlan,MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';
const arg=name=>{const i=process.argv.indexOf(name);if(i<0||!process.argv[i+1])throw Error('Missing '+name);return process.argv[i+1];},
  read=path=>JSON.parse(readFileSync(path)),hash=path=>createHash('sha256').update(readFileSync(path)).digest('hex'),
  oldProposal=read(arg('--earlier-proposal')),newProposal=read(arg('--later-proposal')),
  positions=p=>p.positions||Object.entries(p.expected).map(([symbol,w])=>({symbol,weight:w/100})),
  targets={earlier:positions(oldProposal),later:positions(newProposal)},
  symbols=[...new Set(Object.values(targets).flatMap(p=>p.map(r=>r.symbol)))].sort(),
  paths=3000,seed=0x28cfe391,cases=[];
for(const [label,marketFile,volFile] of [
  ['earlier',arg('--earlier-market'),arg('--earlier-volatility')],
  ['later',arg('--later-market'),arg('--later-volatility')]]){
  const rawMarket=read(marketFile),market={...rawMarket,generated_at:rawMarket.generated_at??rawMarket.collected_at},
    volatility=read(volFile),proposal=label==='earlier'?oldProposal:newProposal,
    cut=proposal.price_cut||proposal.original_price_as_of;
  if(cut!==market.price_as_of||volatility.as_of!==cut||volatility.source_market_generated_at!==market.generated_at)
    throw Error('Mismatched proposal/market/variance vintage');
  if(market.assets.some(a=>!Array.isArray(a.history)))
    throw Error('Archived metadata omits price histories; use the original published market file');
  if(proposal.market_sha256&&proposal.market_sha256!==hash(marketFile))throw Error('Market bytes differ from the sealed proposal');
  const r=referenceRequest({...market,volatility}),full=prepareComposition(market,r.settings,{},r.rules),
    indices=symbols.map(s=>full.assets.findIndex(a=>a.symbol===s)),matrix=m=>indices.map(i=>indices.map(j=>m[i][j]));
  if(indices.some(i=>i<0))throw Error('Published allocation is absent from the fixed comparison universe');
  const reduce=world=>{
    const assets=indices.map(i=>world.assets[i]),covariance=matrix(world.covariance);
    return {...world,assets,covariance,anchors:indices.map(i=>world.anchors[i]),
      buyAllowed:indices.map(i=>world.buyAllowed[i]),innovationCovariance:matrix(world.innovationCovariance),
      conditional:{...world.conditional,fits:indices.map(i=>world.conditional.fits[i])},
      horizonVariance:{...world.horizonVariance,longRunDaily:indices.map(i=>world.horizonVariance.longRunDaily[i])},
      factorization:factorizeStressedCovariance(covariance,assets)};
  },x=reduce(full),assets=x.assets,
    models={earlier:[],later:[]},plans=Object.fromEntries(Object.entries(targets).map(([k,p])=>
      [k,tradePlan(assets,p,x.current.positions,x.current.capital,x.costs)]));
  for(const variant of MODEL_VARIANTS){
    const altered=reduce(variantInputs(full,variant)),sample=generatePaths(altered,paths,seed,52);
    for(const [key,target] of Object.entries(targets)){
      const weights=assets.map(a=>target.find(p=>p.symbol===a.symbol)?.weight||0),
        m=evaluatePaths(weights,sample,{capital:x.current.capital,cost:plans[key].total,pathUtilities:true});
      models[key].push({id:variant.id,utilities:m.pathUtilities,certaintyEquivalent:m.certaintyEquivalent});
    }
  }
  const gain=robustRegretEvidence(models.later,models.earlier,x.policy,x.current.capital,50),
    perModel=models.later.map((m,i)=>({id:m.id,earlier:models.earlier[i].certaintyEquivalent,later:m.certaintyEquivalent,
      evidence:pairedDecisionEvidence(m.utilities,models.earlier[i].utilities,x.policy,x.current.capital,50)}));
  let holding=null;
  if(label==='later'){
    const current={...full.current,source:'Hypothetical account holding the earlier allocation',
      positions:targets.earlier.map(p=>{
        const a=assets.find(a=>a.symbol===p.symbol),price=a.price||1;
        return {...p,price,value:p.weight*x.current.capital,quantity:p.weight*x.current.capital/price,costBasis:price};
      })},held={...full,current};
    const a=reviewRobustDecision(held,targets.later,{paths:1000,validWeights});
    holding={status:a.status,hurdle:a.hurdle,minimumLowerGain:a.minimumLowerGain,maximumTurnover:x.costs.maxTurnover,
      plan:tradePlan(assets,targets.later,current.positions,current.capital,x.costs),
      allModelsBeatHolding:a.models.every(m=>m.evidence.meanUtilityGain>0&&m.evidence.lowerGain>=a.hurdle),
      currentViolatesRisk:a.currentViolatesRisk,tailStress:a.tailStress,
      models:a.models.map(m=>({id:m.id,gain:m.evidence.gain,lowerGain:m.evidence.lowerGain,
        economicPass:m.evidence.meanUtilityGain>0&&m.evidence.lowerGain>=a.hurdle,
        failures:m.failures,holdFailures:m.holdFailures,passes:m.passes})),
      scope:'Hypothetical holdings, not user brokerage positions; purchase basis is assumed at the current close.'};
  }
  cases.push({label,price_cut:cut,market_collected_at:market.generated_at,market_sha256:hash(marketFile),volatility_sha256:hash(volFile),
    anchors:x.anchors.map(a=>({symbol:a.symbol,annual:a.annual,source:a.source})),
    risk_free:x.riskFree,comparison:gain,perModel,hypotheticalHold:holding});
}
const overlap=targets.earlier.reduce((s,p)=>s+Math.min(p.weight,targets.later.find(q=>q.symbol===p.symbol)?.weight||0),0),
  report={engine:MODEL_VERSION,method:'two-cut-fixed-allocation-paired-attribution-v1',paths,seed,symbols,targets,
    capital_reallocated:1-overlap,cases,prospective:false,production_eligible:false,
    scope:'Fixed portfolios, original full-universe anchors, same relevant covariance submatrix and named random streams across cuts. Hypothetical hold uses the full production universe. No reoptimization or strategy backtest; conditional MC evidence is not market forecasting skill.'};
const outputIndex=process.argv.indexOf('--output'),output=outputIndex<0?'out/allocation-cut-attribution.json':process.argv[outputIndex+1];
mkdirSync('out',{recursive:true});writeFileSync(output,JSON.stringify(report,null,1)+'\n');
console.log(JSON.stringify({reallocated:report.capital_reallocated,cases:cases.map(c=>({cut:c.price_cut,gain:c.comparison,hold:c.hypotheticalHold?.status}))}));
