/** Monthly prospective stock signals. No parameter fitting, optimizer or trading. */
import {readFileSync,writeFileSync,existsSync,mkdirSync,readdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {gzipSync,gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {referenceRequest,REFERENCE_ID} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {prepareComposition} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {constituentForecasts,buildReturnAnchors} from '../dist/assets/js/return-model.mjs?v=0.35.0';
import {fundamentalForecast,assetAt} from '../dist/assets/js/research-model.mjs?v=0.35.0';
import {MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {correlation,quantile} from '../dist/assets/js/analytics.mjs?v=0.35.0';
import {namedRandom} from '../dist/assets/js/random.mjs?v=0.35.0';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export const SIGNAL_PROTOCOL='monthly-complete-stock-signal-v1';
export const SIGNAL_HORIZONS=[21,63,252];
const LEAD=2,MIN_STOCKS=30,sha=b=>createHash('sha256').update(b).digest('hex');
const mean=a=>a.length?a.reduce((s,v)=>s+v,0)/a.length:null;
const readGzip=p=>JSON.parse(gunzipSync(readFileSync(p)).toString());
const nyDate=t=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(t));
function firstWeekday(cut){let t=new Date(cut+'T12:00:00Z');do t.setUTCDate(t.getUTCDate()+1);while([0,6].includes(t.getUTCDay()));return t.toISOString().slice(0,10);}
function assertObserved(value,issued){
 if(!value||typeof value!=='object')return;
 for(const [key,v] of Object.entries(value)){
  if(['observed_at','price_observed_at','first_seen_at'].includes(key)&&v&&Number.isFinite(Date.parse(v))&&Date.parse(v)>issued)
   throw Error('Ineligible issuance: source observed after publication');
  if(v&&typeof v==='object')assertObserved(v,issued);
 }
}
export function signalEligibility(snapshot,issuedAt){
 const issued=Date.parse(issuedAt),captured=Date.parse(snapshot.generated_at),cut=snapshot.price_as_of;
 if(!Number.isFinite(issued)||!Number.isFinite(captured)||captured>issued||!/^\d{4}-\d{2}-\d{2}$/.test(cut||''))
  throw Error('Ineligible issuance: market not captured before publication');
 const day=nyDate(issuedAt),hour=Number(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',hourCycle:'h23'}).format(new Date(issued)));
 if(day<cut||(day===cut&&hour<16)||day>firstWeekday(cut))throw Error('Ineligible issuance: outside conservative two-session window');
 assertObserved(snapshot,issued);
 return {issue_ny_date:day,month:day.slice(0,7),lead_sessions:LEAD,
  calendar:'Conservative weekday issuance window; outcome dates use observed SPY sessions, not a certified exchange calendar'};
}
export function signalSourceHashes(){
 const hashes={},visit=path=>{const relative=path.slice(ROOT.length+1);if(hashes[relative])return;
  const bytes=readFileSync(path);hashes[relative]=sha(bytes);
  for(const match of bytes.toString().matchAll(/\b(?:from|import)\s*['"]([^'"]+\.mjs)(?:\?[^'"]*)?['"]/g))
   if(match[1].startsWith('.'))visit(resolve(dirname(path),match[1]));
 };
 visit(resolve(ROOT,'scripts/signal_ledger.mjs'));return hashes;
}
export function signalCohort(sourceHashes){
 return sha(JSON.stringify({protocol:SIGNAL_PROTOCOL,engine:MODEL_VERSION,kernel:PRICE_KERNEL_VERSION,
  reference:REFERENCE_ID,source_hashes:Object.fromEntries(Object.entries(sourceHashes).sort(([a],[b])=>a.localeCompare(b)))}));
}
export function buildSignalForecast(snapshot,volatility,issuedAt,{sourceHashes=signalSourceHashes()}={}){
 const eligibility=signalEligibility(snapshot,issuedAt);
 if(volatility.as_of!==snapshot.price_as_of||volatility.source_market_generated_at!==snapshot.generated_at)
  throw Error('Market and variance vintage differ');
 const request=referenceRequest({...snapshot,volatility}),x=prepareComposition(snapshot,request.settings,request.overrides,request.rules),
  universe=x.anchorUniverse||snapshot.assets,lookup=constituentForecasts(universe,x.options,x.valuationOverrides),rows=[],
  stocks=snapshot.assets.filter(a=>a.type==='stock').sort((a,b)=>a.symbol.localeCompare(b.symbol)),
  benchmarkAsset=snapshot.assets.find(a=>a.symbol===x.policy.benchmark),
  anchors=new Map(buildReturnAnchors([...stocks,...(benchmarkAsset?[benchmarkAsset]:[])],x.options,x.valuationOverrides,universe).map(a=>[a.symbol,a])),
  zeroIC=new Map(buildReturnAnchors(stocks,{...x.options,informationCoefficient:0},x.valuationOverrides,universe).map(a=>[a.symbol,a])),
  benchmarkAnchor=anchors.get(x.policy.benchmark);
 if(!Number.isFinite(x.riskFree)||x.riskFree<=-1)throw Error('Ineligible issuance: missing short rate');
 for(const original of stocks){
  const asset=assetAt(original,x.asOf,x.informationAsOf),f=lookup(asset.symbol),r=f?.refinement,
   anchor=anchors.get(asset.symbol),
   details=f||fundamentalForecast(asset,{}, {},{asOf:x.informationAsOf,priceAsOf:x.asOf});
  if(!f||!r||!(r.omega>0)||!['rawBeta','beta','score','ic','alpha','equilibrium'].every(k=>Number.isFinite(r[k]))||!(asset.price>0)){
   rows.push({symbol:asset.symbol,status:'unavailable-at-issue',reason:details?.error||'No usable cross-sectional refinement',
    freshness:details?.freshness||null});continue;
  }
  rows.push({symbol:asset.symbol,status:'sealed',raw_signal:f.model.annualReturn,score:r.score,
   confidence:f.confidence,declared_research:f.research,refinement:r,
   annual_return_anchor:anchor.annual,anchor_low:anchor.low,anchor_high:anchor.high,
   zero_ic_annual_anchor:zeroIC.get(asset.symbol).annual,
   earnings_yield:f.effectiveBaseEPS/asset.price,price_at_input:asset.price,
   effective_eps:f.effectiveBaseEPS,eps_record:asset.financials.eps,
   catalogue_assumptions:asset.assumptions,effective_assumptions:f.assumptions,
   valuation_source:f.source,growth_evidence:f.growthEvidence,quality:f.quality});
 }
 return {schema_version:1,protocol:SIGNAL_PROTOCOL,cohort_id:signalCohort(sourceHashes),source_hashes:sourceHashes,
  engine_version:MODEL_VERSION,price_kernel_version:PRICE_KERNEL_VERSION,reference_id:REFERENCE_ID,
  runtime_node_version:process.version,
  issued_at:issuedAt,...eligibility,input_price_as_of:snapshot.price_as_of,information_as_of:x.informationAsOf,
  market_collected_at:snapshot.generated_at,horizons:[...SIGNAL_HORIZONS],benchmark:x.policy.benchmark,
  risk_free:x.riskFree,rows,sealed_stocks:rows.filter(r=>r.status==='sealed').length,
  benchmark_forecast:benchmarkAnchor?.fundamental?{status:'sealed',symbol:x.policy.benchmark,
   annual_anchor:benchmarkAnchor.annual,low:benchmarkAnchor.low,high:benchmarkAnchor.high,source:benchmarkAnchor.source}:
   {status:'unavailable-at-issue',reason:'No economic benchmark anchor; a generic comparison proxy is not accepted'},
  scope:'Canonical stock signal before optimization, including non-selected stocks. Point-anchor extrapolation and matched ranking references; not a simulated distribution, personal account, executed trade or strategy return.',
  original_vintages_verified:false,production_eligible:false,automatic_promotion:false};
}

export function rankCorrelation(a,b){
 const ranks=values=>{const ordered=values.map((value,i)=>({value,i})).sort((a,b)=>a.value-b.value),out=[];
  for(let k=0;k<ordered.length;){let end=k+1;while(end<ordered.length&&ordered[end].value===ordered[k].value)end++;
   for(let i=k;i<end;i++)out[ordered[i].i]=(k+end-1)/2+1;k=end;}return out;};
 return a.length>=3&&a.length===b.length?correlation(ranks(a),ranks(b)):null;
}
export function signalPublication(root,path,forecastSha){
 const relative=path.slice(resolve(root).length+1),git=args=>execFileSync('git',args,{cwd:root,stdio:['ignore','pipe','pipe']});
 try{
  const commit=git(['log','--reverse','--diff-filter=A','--format=%H','--',relative]).toString().trim().split('\n')[0];
  if(!commit)return {verified:false,reason:'No first-add commit found'};
  if(sha(git(['show',commit+':'+relative]))!==forecastSha)return {verified:false,reason:'First published blob differs from sealed file'};
  return {verified:true,first_commit:commit,committed_at:git(['show','-s','--format=%cI',commit]).toString().trim(),forecast_sha256:forecastSha};
 }catch{return {verified:false,reason:'Publication history unavailable; no prospective score assigned'};}
}
export function scoreSignalForecast(origin,snapshot,horizon){
 if(origin.protocol!==SIGNAL_PROTOCOL||!origin.horizons.includes(horizon))throw Error('Unsupported sealed signal protocol or horizon');
 if(!Number.isFinite(origin.risk_free)||origin.risk_free<=-1)throw Error('Invalid sealed short rate');
 for(const r of origin.rows)if(r.status==='sealed'&&
  (![r.raw_signal,r.score,r.confidence,r.earnings_yield,r.annual_return_anchor,r.zero_ic_annual_anchor,
    r.refinement?.rawBeta,r.refinement?.beta,r.refinement?.omega,r.refinement?.alpha].every(Number.isFinite)||
   r.annual_return_anchor<=-1||r.zero_ic_annual_anchor<=-1||!(r.refinement.omega>0)))throw Error('Invalid sealed predictors');
 if(origin.benchmark_forecast?.status==='sealed'&&(!Number.isFinite(origin.benchmark_forecast.annual_anchor)||origin.benchmark_forecast.annual_anchor<=-1))
  throw Error('Invalid sealed benchmark anchor');
 const benchmark=snapshot.assets.find(a=>a.symbol===origin.benchmark),future=(benchmark?.history||[])
  .filter(r=>r.date>origin.input_price_as_of&&r.date<=snapshot.price_as_of).sort((a,b)=>a.date.localeCompare(b.date)),
  start=future[origin.lead_sessions-1],end=future[origin.lead_sessions+horizon-1];
 if(new Set(future.map(r=>r.date)).size!==future.length)throw Error('Ambiguous benchmark session index');
 if(!end)return null;
 const meta={schema_version:1,protocol:origin.protocol,cohort_id:origin.cohort_id,month:origin.month,
  issued_at:origin.issued_at,input_price_as_of:origin.input_price_as_of,origin_date:start.date,
  maturity_date:end.date,horizon_sessions:horizon,benchmark_origin_adj_close:start.adj_close,
  benchmark_maturity_adj_close:end.adj_close};
 if(!origin.publication?.verified)return {...meta,status:'unverified-publication',reason:'First publication not verified'};
 meta.publication=origin.publication;
 if(start.date<=origin.issue_ny_date||start.date<=nyDate(origin.publication.committed_at))
  return {...meta,status:'nonprospective',reason:'Original return starts on or before issuance or first Git publication'};
 const bySymbol=new Map(snapshot.assets.map(a=>[a.symbol,a])),rf=Math.expm1(Math.log1p(origin.risk_free)*horizon/252),
  marketLog=Math.log(end.adj_close/start.adj_close),marketReturn=Math.expm1(marketLog),rows=origin.rows.map(r=>{
   if(r.status!=='sealed')return {symbol:r.symbol,status:r.status,reason:r.reason};
   const asset=bySymbol.get(r.symbol),p=asset?.history.find(r=>r.date===start.date)?.adj_close,
    q=asset?.history.find(r=>r.date===end.date)?.adj_close;
   if(![p,q,start.adj_close,end.adj_close].every(v=>Number.isFinite(v)&&v>0))
    return {symbol:r.symbol,status:'missing-original-outcome',asset_present:!!asset,
     origin_price_present:Number.isFinite(p)&&p>0,maturity_price_present:Number.isFinite(q)&&q>0};
   const totalLog=Math.log(q/p),realized=Math.expm1(totalLog),residual=totalLog-r.refinement.rawBeta*marketLog,
    fullActive=realized-rf-r.refinement.beta*(marketReturn-rf),
    forecast=Math.expm1(Math.log1p(r.annual_return_anchor)*horizon/252),
    equilibrium=Math.expm1(Math.log1p(r.zero_ic_annual_anchor)*horizon/252);
   return {symbol:r.symbol,status:'scored',origin_adj_close:p,maturity_adj_close:q,
    raw_signal:r.raw_signal,score:r.score,confidence:r.confidence,earnings_yield:r.earnings_yield,
    alpha:r.refinement.alpha,realized_total_return:realized,residual_log_return:residual,
    standardized_residual:residual/(r.refinement.omega*Math.sqrt(horizon/252)),full_active_return:fullActive,
    anchor_forecast:forecast,equilibrium_forecast:equilibrium,anchor_error:realized-forecast,
    equilibrium_error:realized-equilibrium,zero_error:realized};
  });
 const comparable=rows.filter(r=>r.status==='scored'),metrics={};
 if(comparable.length>=MIN_STOCKS){
  const get=k=>comparable.map(r=>r[k]);
  metrics.raw_rank_ic=rankCorrelation(get('raw_signal'),get('residual_log_return'));
  metrics.yield_rank_ic=rankCorrelation(get('earnings_yield'),get('residual_log_return'));
  metrics.paired_rank_ic_gain=metrics.raw_rank_ic===null||metrics.yield_rank_ic===null?null:metrics.raw_rank_ic-metrics.yield_rank_ic;
  metrics.score_standardized_pearson_ic=correlation(get('score'),get('standardized_residual'));
  metrics.final_alpha_rank_ic=rankCorrelation(get('alpha'),get('full_active_return'));
  for(const model of ['anchor','equilibrium','zero']){
   const errors=get(model+'_error');metrics[model+'_bias']=mean(errors);
   metrics[model+'_mae']=mean(errors.map(Math.abs));metrics[model+'_mse']=mean(errors.map(e=>e*e));
  }
  metrics.paired_mae_gain_vs_equilibrium=mean(comparable.map(r=>Math.abs(r.equilibrium_error)-Math.abs(r.anchor_error)));
  metrics.paired_mae_gain_vs_zero=mean(comparable.map(r=>Math.abs(r.zero_error)-Math.abs(r.anchor_error)));
 }
 const benchmarkMetrics={};
 if(origin.benchmark_forecast?.status==='sealed'&&[start.adj_close,end.adj_close].every(v=>Number.isFinite(v)&&v>0)){
  const forecast=Math.expm1(Math.log1p(origin.benchmark_forecast.annual_anchor)*horizon/252);
  Object.assign(benchmarkMetrics,{forecast,realized_total_return:marketReturn,anchor_error:marketReturn-forecast,
   zero_error:marketReturn,rate_error:marketReturn-rf,
   paired_absolute_error_gain_vs_zero:Math.abs(marketReturn)-Math.abs(marketReturn-forecast),
   paired_absolute_error_gain_vs_rate:Math.abs(marketReturn-rf)-Math.abs(marketReturn-forecast)});
 }
 return {...meta,status:'scored',expected_stocks:origin.sealed_stocks,scored_stocks:comparable.length,
  missing_outcomes:rows.filter(r=>r.status==='missing-original-outcome').length,
  diagnostic_status:comparable.length>=MIN_STOCKS?'measured':'insufficient-cross-section',metrics,benchmark_metrics:benchmarkMetrics,rows,
  original_outcome_vintages_verified:false};
}

export function monthlySignalInterval(values,months,block,draws=1000){
 if(values.length<Math.max(20,4*block)||values.some(v=>!Number.isFinite(v))||
  months.some((v,i)=>i>0&&v!==months[i-1]+1))return null;
 const rng=namedRandom(0x20261029,'monthly-signal-interval'),means=[];
 for(let n=0;n<draws;n++){const sample=[];while(sample.length<values.length){
  const start=Math.floor(rng()*(values.length-block+1));sample.push(...values.slice(start,start+block));
 }means.push(mean(sample.slice(0,values.length)));}
 return [quantile(means,.025),quantile(means,.975)];
}
export function summarizeSignals(origins,scores,currentCohort,updatedAt){
 const cohorts={};
 for(const id of new Set(origins.map(r=>r.cohort_id))){
  const seals=origins.filter(r=>r.cohort_id===id),horizons={};
  for(const horizon of SIGNAL_HORIZONS){
   const all=scores.filter(r=>r.cohort_id===id&&r.horizon_sessions===horizon&&r.status==='scored')
    .sort((a,b)=>a.origin_date.localeCompare(b.origin_date)),measured=all.filter(r=>r.diagnostic_status==='measured'),independent=[];
   let last='';for(const r of measured)if(r.origin_date>=last){independent.push(r);last=r.maturity_date;}
   const block=Math.ceil(horizon/21),statistics={},benchmarkStatistics={};
   const aggregate=(observations,field,target)=>{
   for(const key of new Set(observations.flatMap(r=>Object.keys(r[field]||{})))){
    const rows=observations.filter(r=>Number.isFinite(r[field]?.[key])),values=rows.map(r=>r[field][key]),
     months=rows.map(r=>Number(r.month.slice(0,4))*12+Number(r.month.slice(5,7)));
    target[key]={origin_count:rows.length,mean:mean(values),
     monthly_block95:monthlySignalInterval(values,months,block)};
   }
   };
   aggregate(measured,'metrics',statistics);aggregate(all,'benchmark_metrics',benchmarkStatistics);
   horizons[horizon]={sealed:seals.length,mature_origins:all.length,measured_origins:measured.length,
    nonoverlapping_origins:independent.length,expected_stock_outcomes:all.reduce((s,r)=>s+r.expected_stocks,0),
    missing_stock_outcomes:all.reduce((s,r)=>s+r.missing_outcomes,0),
    excluded_nonprospective:scores.filter(r=>r.cohort_id===id&&r.horizon_sessions===horizon&&r.status==='nonprospective').length,
    block_months:block,statistics,benchmark_statistics:benchmarkStatistics,status:'accumulating-unvalidated'};
  }
  cohorts[id]={engine_version:seals[0].engine_version,price_kernel_version:seals[0].price_kernel_version,
   protocol:seals[0].protocol,sealed:seals.length,publication_verified:seals.filter(r=>r.publication?.verified).length,horizons};
 }
 return {schema_version:1,protocol:SIGNAL_PROTOCOL,updated_at:updatedAt,current_cohort:currentCohort,
  sealed:origins.length,cohorts,predictive_validation:'not-established',automatic_promotion:false,
  criteria:'Monthly first eligible issuance, immutable inputs and first mature scores. At least 30 matched stocks per diagnostic. Intervals require 20 origins and four consecutive month blocks (1/3/12); pointwise descriptive intervals do not certify skill or authorize parameter changes.',
  limitations:'No pooling across source-code cohorts. Correlated stocks and overlapping monthly returns are not independent temporal evidence. Missing and delisted outcomes remain visible. Adjusted provider prices are not certified original outcome vintages or broker cash flows. A point anchor is not the simulator distribution.'};
}

function writeImmutable(path,bytes){
 mkdirSync(dirname(path),{recursive:true});try{writeFileSync(path,bytes,{flag:'wx'});return true;}
 catch(e){if(e.code==='EEXIST')return false;throw e;}
}
export function updateSignalLedger({root=ROOT,issuedAt=null}={}){
 const marketBytes=readFileSync(resolve(root,'dist/data/market.json')),volBytes=readFileSync(resolve(root,'dist/data/volatility.json')),
  snapshot=JSON.parse(marketBytes),volatility=JSON.parse(volBytes),sourceHashes=signalSourceHashes(),cohort=signalCohort(sourceHashes),
  base=resolve(root,'data/signal-validation'),forecasts=resolve(base,'forecasts'),scoresDir=resolve(base,'scores');
 mkdirSync(forecasts,{recursive:true});mkdirSync(scoresDir,{recursive:true});
 const now=issuedAt||new Date().toISOString(),month=nyDate(now).slice(0,7),path=resolve(forecasts,month+'.json.gz');
 if(!Number.isFinite(Date.parse(snapshot.generated_at))||Date.parse(snapshot.generated_at)>Date.parse(now)||snapshot.price_as_of>nyDate(now))
  throw Error('Scoring snapshot captured after scoring time');
 assertObserved(snapshot,Date.parse(now));
 let issuance='already-sealed';
 if(!existsSync(path)){
  try{
   const origin=buildSignalForecast(snapshot,volatility,now,{sourceHashes}),completed=issuedAt||new Date().toISOString();
   const eligibility=signalEligibility(snapshot,completed);
   if(eligibility.month!==origin.month)throw Error('Ineligible issuance: crossed monthly boundary during calculation');
   origin.issued_at=completed;origin.issue_ny_date=eligibility.issue_ny_date;
   origin.market_sha256=sha(marketBytes);origin.volatility_sha256=sha(volBytes);
   origin.source_commit=process.env.SIGNAL_SOURCE_COMMIT||null;origin.workflow_run_id=process.env.GITHUB_RUN_ID||null;
   origin.input_archive='inputs/'+origin.market_sha256+'.json.gz';
   origin.volatility_archive='inputs/'+origin.volatility_sha256+'.volatility.json.gz';
   const archive=resolve(base,origin.input_archive);
   writeImmutable(archive,gzipSync(marketBytes));
   if(sha(gunzipSync(readFileSync(archive)))!==origin.market_sha256)throw Error('Signal input archive integrity failure');
   const volArchive=resolve(base,origin.volatility_archive);writeImmutable(volArchive,gzipSync(volBytes));
   if(sha(gunzipSync(readFileSync(volArchive)))!==origin.volatility_sha256)throw Error('Signal variance archive integrity failure');
   writeImmutable(path,gzipSync(JSON.stringify(origin)));issuance='sealed';
  }catch(e){if(!e.message.startsWith('Ineligible issuance:'))throw e;issuance=e.message;}
 }
 const origins=readdirSync(forecasts).filter(p=>p.endsWith('.json.gz')).map(p=>{
  const path=resolve(forecasts,p),bytes=readFileSync(path),r=readGzip(path);
  if(sha(gunzipSync(readFileSync(resolve(base,r.input_archive))))!==r.market_sha256)throw Error('Signal input archive integrity failure');
  if(sha(gunzipSync(readFileSync(resolve(base,r.volatility_archive))))!==r.volatility_sha256)throw Error('Signal variance archive integrity failure');
  const forecastSha=sha(bytes);
  return {...r,forecast_sha256:forecastSha,publication:signalPublication(root,path,forecastSha)};
 });
 for(const origin of origins)for(const h of origin.horizons){
  const path=resolve(scoresDir,origin.month+'.h'+h+'.json.gz');
  if(existsSync(path)){if(readGzip(path).forecast_sha256!==origin.forecast_sha256)throw Error('Sealed signal changed after scoring');continue;}
  const result=scoreSignalForecast(origin,snapshot,h);if(!result)continue;
  if(result.status==='unverified-publication')continue;
  writeImmutable(path,gzipSync(JSON.stringify({...result,forecast_sha256:origin.forecast_sha256,
   scored_at:issuedAt||new Date().toISOString(),scoring_source_hashes:sourceHashes,realized_market_sha256:sha(marketBytes)})));
 }
 const scores=readdirSync(scoresDir).filter(p=>p.endsWith('.json.gz')).map(p=>readGzip(resolve(scoresDir,p))),
  summary=summarizeSignals(origins,scores,cohort,issuedAt||new Date().toISOString());
 summary.issuance_status=issuance;summary.current_month=month;summary.observed_price_as_of=snapshot.price_as_of;
 mkdirSync(resolve(root,'dist/data'),{recursive:true});writeFileSync(resolve(root,'dist/data/signal-validation.json'),JSON.stringify(summary,null,1)+'\n');
 return {...summary,issuance};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))console.log(JSON.stringify(updateSignalLedger()));
