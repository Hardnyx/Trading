/** Declared sensitivity models shared by the decision gate and research search. */
import { assetAt } from './research-model.mjs?v=0.33.0';
import { resolveAssumptions } from './analytics.mjs?v=0.33.0';
import { buildReturnAnchors } from './return-model.mjs?v=0.33.0';

export function operatingMarginStress(original, priceAsOf, informationAsOf) {
  const asset=assetAt(original,priceAsOf,informationAsOf),f=asset.financials||{};
  const eps=f.eps,op=f.operating_income,revenue=f.revenue;
  const observations=new Map();
  for(const row of f.history||[]){
    if(!Number.isFinite(row.operating_margin))continue;
    const previous=observations.get(row.period_end);
    if(!previous || row.filed>previous.filed)observations.set(row.period_end,row);
    else if(row.filed===previous.filed && row.operating_margin!==previous.operating_margin)
      return {available:false,reason:'Conflicting same-period margin evidence'};
  }
  const rows=[...observations.values()].sort((a,b)=>a.period_end.localeCompare(b.period_end));
  const span=rows.length?(Date.parse(rows.at(-1).period_end)-Date.parse(rows[0].period_end))/86400000:0;
  if(rows.length<8 || span<730 || ![eps?.value,op?.value,revenue?.value].every(Number.isFinite) ||
     !(eps.value>0 && op.value>0 && revenue.value>0) ||
     ![op,revenue].every(r=>r.period_end===eps.period_end&&r.method===eps.method))
    return {available:false,reason:'Insufficient comparable multi-year margin evidence',observations:rows.length,span_days:span};
  const margins=rows.map(r=>r.operating_margin).sort((a,b)=>a-b),n=margins.length;
  const median=n%2?margins[(n-1)/2]:(margins[n/2-1]+margins[n/2])/2;
  const current=op.value/revenue.value;
  if(!(median>0))return {available:false,reason:'Historical median not positive; no defensible multiplicative EPS proxy'};
  const factor=Math.min(1,median/current);
  return {available:true,factor,reported_eps:eps.value,stressed_eps:eps.value*factor,
    current_operating_margin:current,median_operating_margin:median,
    observations:n,span_days:span,history:rows.map(r=>({period_end:r.period_end,filed:r.filed,operating_margin:r.operating_margin})),
    basis:'Operating-margin ratio stress; NOT normalized accounting EPS or a calibrated forecast'};
}

export const MODEL_VARIANTS=[
  {id:'original',description:'Current priors and valuation assumptions'},
  {id:'no_rerating',noRerating:true,description:'No expansion above the observed earnings multiple'},
  {id:'margin_stress',marginStress:true,creditStress:true,description:'Operating-margin stress; doubled expected credit loss and 1.5x spread exposure'},
  {id:'combined',noRerating:true,marginStress:true,creditStress:true,description:'Margin and credit stress plus no multiple expansion'},
  {id:'low_conviction',noRerating:true,marginStress:true,creditStress:true,confidence:.3,equityPremium:0,informationCoefficient:0,
    description:'Combined stress, assigned confidence 30%, zero assumed broad-market equity premium'},
];

export function variantInputs(inputs,variant){
  const evidence=[],overrides=structuredClone(inputs.valuationOverrides||{}),research=structuredClone(inputs.options.research||{});
  const universe=(inputs.anchorUniverse||inputs.assets).map(original=>{
    if(original.type!=='stock')return original;
    const asset=assetAt(original,inputs.asOf,inputs.informationAsOf);
    const eps=asset.financials?.eps?.value;
    if(variant.noRerating && eps>0 && asset.price>0)
      overrides[asset.symbol]={...overrides[asset.symbol],multiple:Math.min(resolveAssumptions(asset,overrides[asset.symbol]||{}).multiple,asset.price/eps)};
    if(variant.confidence!==undefined)research[asset.symbol]={...research[asset.symbol],confidence:Math.min(research[asset.symbol]?.confidence??.6,variant.confidence)};
    if(!variant.marginStress)return asset;
    const stress=['consensus','blend'].includes(research[asset.symbol]?.basis)
      ? {available:false,reason:'El estrés de margen no sustituye un consenso de BPA comparable'}
      : operatingMarginStress(asset,inputs.asOf,inputs.informationAsOf);
    evidence.push({symbol:asset.symbol,...stress});
    if(!stress.available)return asset;
    return {...asset,financials:{...asset.financials,
      eps:{...asset.financials.eps,value:stress.stressed_eps}}};
  });
  const assetAssumptions=structuredClone(inputs.options.assetAssumptions||{});
  if(variant.equityPremium!==undefined){
    for(const symbol of ['VTI','SPY'])if(assetAssumptions[symbol])
      assetAssumptions[symbol].expectedReturn=Math.min(assetAssumptions[symbol].expectedReturn,inputs.riskFree+variant.equityPremium);
  }
  const bySymbol=new Map(universe.map(a=>[a.symbol,a]));
  const assets=inputs.assets.map(a=>bySymbol.get(a.symbol)||a);
  const options={...inputs.options,research,assetAssumptions,
    ...(variant.creditStress?{creditStress:{lossMultiplier:2,spreadMultiplier:1.5}}:{}),
    ...(variant.equityPremium!==undefined?{equityPremium:variant.equityPremium}:{}),
    ...(variant.informationCoefficient!==undefined?{informationCoefficient:variant.informationCoefficient}:{})};
  const anchors=buildReturnAnchors(assets,options,overrides,universe);
  if(variant.equityPremium!==undefined) for(let i=0;i<anchors.length;i++) {
    const asset=assets[i],a=anchors[i];
    if(asset.type!=='etf'||a.bond)continue;
    if(!a.holdingsCoverage&&!a.valuationDate)continue;
    const cap=inputs.riskFree+variant.equityPremium;
    if(a.annual>cap){const shift=cap-a.annual;anchors[i]={...a,annual:cap,mu:Math.log1p(cap),
      distributionMean:cap,low:a.low+shift,high:a.high+shift};}
  }
  return {...inputs,assets,options,anchors,anchorUniverse:universe,variant:variant.id,stressEvidence:evidence};
}

export function minimaxRegret(rows,scenarioIds,feasible=r=>r.feasible){
  const eligible=rows.filter(feasible);
  if(!eligible.length)return {best:null,ranking:[],benchmarks:null};
  for(const row of eligible)for(const id of scenarioIds)
    if(!Number.isFinite(row.utilities?.[id]))throw Error('Incomplete model-utility grid');
  const benchmarks=Object.fromEntries(scenarioIds.map(id=>[id,Math.max(...eligible.map(r=>r.utilities[id]))]));
  const ranking=eligible.map(row=>({...row,
    maxRegret:Math.max(...scenarioIds.map(id=>Math.max(0,benchmarks[id]-row.utilities[id]))),
    worstUtility:Math.min(...scenarioIds.map(id=>row.utilities[id])),
  })).sort((a,b)=>a.maxRegret-b.maxRegret||b.worstUtility-a.worstUtility||a.id.localeCompare(b.id));
  return {best:ranking[0],ranking,benchmarks};
}

export function pairedUtilityEvidence(candidate,baseline,capital,familySize=1){
  if(candidate.length!==baseline.length||candidate.length<2||!(capital>0)||
     !Number.isInteger(familySize)||familySize<1||
     [...candidate,...baseline].some(r=>!Number.isFinite(r)||r < -1))
    throw Error('Invalid paired return samples');
  const logs=baseline.map(r=>Math.log(Math.max(1e-5,1+r)));
  const differences=candidate.map((r,i)=>Math.log(Math.max(1e-5,1+r))-logs[i]);
  const mean=differences.reduce((a,b)=>a+b,0)/differences.length;
  const baselineUtility=logs.reduce((a,b)=>a+b,0)/logs.length;
  const variance=differences.reduce((s,d)=>s+(d-mean)**2,0)/(differences.length-1);
  const se=Math.sqrt(variance/differences.length);
  // Conservative Gaussian tail bound: P(Z >= z) <= exp(-z²/2).
  // Union bound over all verified portfolios and model variants. This controls
  // only the normal approximation to simulation noise, never model error.
  const z=Math.sqrt(2*Math.log(familySize/.05));
  return {mean_log_utility_gain:mean,standard_error:se,z,family_size:familySize,
    ce_gain_dollars:capital*Math.exp(baselineUtility)*Math.expm1(mean),
    lower_ce_gain_dollars:capital*Math.exp(baselineUtility)*Math.expm1(mean-z*se),
    basis:'Conservative Gaussian tail and union bound across the verification family; approximate Monte Carlo noise only, not model uncertainty or OOS skill'};
}
