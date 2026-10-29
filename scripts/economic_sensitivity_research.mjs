/** Declared economic assumption sensitivity; fixed data/pool, no trading. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {buildReturnAnchors} from '../dist/assets/js/return-model.mjs?v=0.35.0';
import {resolveAssumptions} from '../dist/assets/js/analytics.mjs?v=0.35.0';
import {variantInputs,MODEL_VARIANTS} from '../dist/assets/js/robust-core.mjs?v=0.35.0';
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {utilityCertaintyEquivalent} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {riskSamplingEvidence} from '../dist/assets/js/simulation-evidence.mjs?v=0.35.0';
import {pairedDecisionEvidence} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
import {pairUtilityMeans} from './antithetic_selection_research.mjs';
export const ECONOMIC_CASES=Object.freeze([
 {id:'base',axis:'reference'},
 {id:'no_rerating',axis:'rerating',variant:MODEL_VARIANTS.find(v=>v.id==='no_rerating')},
 {id:'declared_low_conviction',axis:'existing-joint-stress',variant:MODEL_VARIANTS.find(v=>v.id==='low_conviction')},
 ...[0,.02,.04].map(equityPremium=>({id:'equity_premium_'+Math.round(equityPremium*100),axis:'equity-premium',equityPremium})),
 ...[0,.1].map(informationCoefficient=>({id:'ic_'+informationCoefficient,axis:'information-coefficient',informationCoefficient})),
 ...[.5,1.5].map(growthScale=>({id:'growth_'+growthScale,axis:'catalog-growth',growthScale})),
 ...[2,3].map(lossMultiplier=>({id:'credit_loss_'+lossMultiplier,axis:'credit-loss',lossMultiplier})),
 ...[1.5,3].map(spreadMultiplier=>({id:'credit_spread_'+spreadMultiplier,axis:'credit-spread',spreadMultiplier})),
 ...[0,2].map(rateScale=>({id:'rate_scenarios_'+rateScale,axis:'rate-scenarios',rateScale})),
 {id:'joint_stress',axis:'exploratory-joint-stress',equityPremium:0,informationCoefficient:0,
  lossMultiplier:3,spreadMultiplier:3,rateScale:2,variant:MODEL_VARIANTS.find(v=>v.id==='no_rerating')}
]);
export function economicInputs(inputs,c){
 const base=variantInputs(inputs,{...(c.variant||{}),id:c.id,
  ...(c.equityPremium!==undefined?{equityPremium:c.equityPremium}:{}),
  ...(c.informationCoefficient!==undefined?{informationCoefficient:c.informationCoefficient}:{})}),
  overrides=structuredClone(base.valuationOverrides||{}),options={...base.options},universe=base.anchorUniverse||base.assets;
 if(c.lossMultiplier!==undefined||c.spreadMultiplier!==undefined)options.creditStress={
  lossMultiplier:c.lossMultiplier??options.creditStress?.lossMultiplier??1,
  spreadMultiplier:c.spreadMultiplier??options.creditStress?.spreadMultiplier??1};
 if(c.variant?.noRerating)for(const a of universe)if(a.type==='stock'&&a.financials?.eps?.value>0&&a.price>0){
  overrides[a.symbol]={...overrides[a.symbol],multiple:Math.min(resolveAssumptions(a,overrides[a.symbol]||{}).multiple,a.price/a.financials.eps.value)};
 }
 if(c.growthScale!==undefined)for(const a of universe)if(a.type==='stock'){
  const current=resolveAssumptions(a,overrides[a.symbol]||{});overrides[a.symbol]={...overrides[a.symbol],growth:current.growth*c.growthScale};
 }
 // Rebuilding for credit/growth must retain the ETF premium caps imposed by
 // variantInputs. Use its anchors unchanged when neither block changed.
 const anchors=c.lossMultiplier!==undefined||c.spreadMultiplier!==undefined||c.growthScale!==undefined
  ?buildReturnAnchors(base.assets,options,overrides,universe):base.anchors;
 if(c.equityPremium!==undefined)for(let i=0;i<anchors.length;i++){
  const a=anchors[i],asset=base.assets[i],cap=base.riskFree+c.equityPremium;
  if(asset.type==='etf'&&!a.bond&&(a.holdingsCoverage||a.valuationDate)&&a.annual>cap){
   const shift=cap-a.annual;anchors[i]={...a,annual:cap,mu:Math.log1p(cap),distributionMean:cap,low:a.low+shift,high:a.high+shift};
  }
 }
 return {...base,anchors,options,valuationOverrides:overrides,
  regimes:base.regimes.map(r=>({...r,rateShift:(r.rateShift||0)*(c.rateScale??1),rateJumpBps:(r.rateJumpBps||0)*(c.rateScale??1)}))};
}
export function sensitivityEvidence(a,b,policy,capital,familySize){
 const e=pairedDecisionEvidence(a,b,policy,capital,familySize),base=b.reduce((s,v)=>s+v,0)/b.length;
 return {...e,upperGain:utilityCertaintyEquivalent(base+e.meanUtilityGain+e.z*e.standardError,policy,capital)-utilityCertaintyEquivalent(base,policy,capital),scope:'Signed paired Monte Carlo approximation; not a parameter confidence interval or predictive evidence'};
}
const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
const key=p=>p.map(r=>r.symbol+':'+r.weight).sort().join('|');
export function runEconomicSensitivity(market,vol,pool,published,{pairs=1500,onProgress=()=>{}}={}){
 if(market.generated_at!==vol.source_market_generated_at||market.price_as_of!==vol.as_of)throw Error('Mismatched market/variance vintage');
 const req=referenceRequest({...market,volatility:vol}),x=prepareComposition(market,req.settings,{},req.rules),rows=[],excluded=[],seen=new Set(),selectedKey=key(published),
  seed=0x71e4a9c3,familySize=ECONOMIC_CASES.length*(pool.length+1)**2;
 for(const positions of [...pool,published]){
  const k=key(positions);if(seen.has(k))continue;seen.add(k);const weights=x.assets.map(a=>positions.find(p=>p.symbol===a.symbol)?.weight||0);
  if(positions.some(p=>!x.assets.some(a=>a.symbol===p.symbol))||!validWeights(weights,x)){excluded.push(k);continue;}
  const plan=tradePlan(x.assets,positions,x.current.positions,x.current.capital,x.costs);if(!plan.complete)throw Error('Incomplete plan');
  rows.push({key:k,positions,weights,cost:plan.total});
 }
 const selected=rows.find(r=>r.key===selectedKey);if(!selected)throw Error('Published allocation absent from the comparison universe');
 const cases=[],basis=new Map();
 for(const definition of ECONOMIC_CASES){
  const world=economicInputs(x,definition),shadow={...world,options:{...world.options,researchShadowMode:true}},
   a=generatePaths(shadow,pairs,seed,52),b=generatePaths(shadow,pairs,seed,52,{researchMirror:true}),evaluated=[];
  for(const row of rows){
   const opts={capital:x.current.capital,cost:row.cost,pathUtilities:true},u=evaluatePaths(row.weights,a,opts),v=evaluatePaths(row.weights,b,opts),
    utilities=pairUtilityMeans(u.pathUtilities,v.pathUtilities),risk=riskSamplingEvidence(u,x.rules,x.policy);
   evaluated.push({...row,utilities,certaintyEquivalent:utilityCertaintyEquivalent(mean(utilities),x.policy,x.current.capital),
    riskFailures:risk.failures,cvar95:u.cvar95,lossProbability:u.lossProbability});
   if(definition.id==='base')basis.set(row.key,utilities);
  }
  const best=[...evaluated].sort((a,b)=>b.certaintyEquivalent-a.certaintyEquivalent||a.key.localeCompare(b.key))[0],current=evaluated.find(r=>r.key===selectedKey),
   evidence=(a,b)=>sensitivityEvidence(a,b,x.policy,x.current.capital,familySize),
   strip=row=>({key:row.key,positions:row.positions,certaintyEquivalent:row.certaintyEquivalent,
    riskFailures:row.riskFailures,cvar95:row.cvar95,lossProbability:row.lossProbability});
  cases.push({definition,leader:strip(best),published:strip(current),capitalReallocatedFromPublished:1-best.positions.reduce((s,p)=>s+Math.min(p.weight,published.find(q=>q.symbol===p.symbol)?.weight||0),0),
   publishedDeltaVsBase:evidence(current.utilities,basis.get(selectedKey)),opportunityVsPublished:evidence(best.utilities,current.utilities),
   anchors:world.anchors.filter(a=>published.some(p=>p.symbol===a.symbol)).map(a=>({symbol:a.symbol,annual:a.annual,source:a.source,bond:a.bond||null})),
   candidates:evaluated.map(strip),regimes:world.regimes});
  onProgress({case:definition.id,leader:best.key,publishedCE:current.certaintyEquivalent});
 }
 return {method:'economic-sensitivity-fixed-pool-v1',price_cut:market.price_as_of,market_generated_at:market.generated_at,pairs,seed,familySize,
  capital:x.current.capital,policy:x.policy,poolSize:rows.length,excluded,published,cases,
  profiles:market.assets.filter(a=>published.some(p=>p.symbol===a.symbol)).map(a=>({symbol:a.symbol,bond_profile:a.bond_profile||null})),
  prospective:false,production_eligible:false,automatic_promotion:false,
  scope:'Declared exploratory assumption grid, not estimated parameter intervals or scenario probabilities. Fixed ex-post candidate pool and common random streams with pair-mean MC errors. Single-model point leaders, not five-model trade approvals; risk diagnostic uses the independent positive arm only, with no complete Student/all-model screening. Reported monetary changes are conditional model sensitivity, not realized gains or predictive confidence.'};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const read=p=>JSON.parse(readFileSync(p)),value=(f,d)=>{const i=process.argv.indexOf(f);return i<0?d:process.argv[i+1];},
  marketFile=value('--market','dist/data/market.json'),volFile=value('--volatility','dist/data/volatility.json'),poolFile='docs/auditorias/policy-pool-0.34.1.json',allocFile='docs/auditorias/allocation-cuts-0.35.0.json',
  cuts=read(allocFile).targets,pool=[...read(poolFile).diagnostics.reliableSelection.candidates.filter(r=>r.feasible).map(r=>r.positions),cuts.earlier],
  quick=process.argv.includes('--quick'),report=runEconomicSensitivity(read(marketFile),read(volFile),pool,cuts.later,{pairs:quick?100:1500,onProgress:p=>console.log(JSON.stringify(p))}),
  files=[marketFile,volFile,poolFile,allocFile,'scripts/economic_sensitivity_research.mjs','dist/assets/js/robust-core.mjs','dist/assets/js/return-model.mjs','dist/assets/js/research-model.mjs','dist/assets/js/path-model.mjs'];
 report.quick=quick;report.hashes=Object.fromEntries(files.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]));
 mkdirSync('out',{recursive:true});writeFileSync(value('--output','out/economic-sensitivity.json'),JSON.stringify(report,null,1)+'\n');
}
