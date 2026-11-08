/** Diagnose frozen 8-origin return forecasts against the protocol's expanding mean.
 * This is retrospective development evidence, not the full-engine H4 test.
 * Current back-adjusted provider data are not original historical vintages.
 */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const requireThat = (condition,message) => {if(!condition)throw Error(message)};
const avg = values => values.length ? values.reduce((a,b)=>a+b,0)/values.length : null;
const SOURCE_PROTOCOL = 'docs/protocolo-replay-integral-v1.json';
const SCORES = 'data/historical/expanded-stock-validation-scores-v1/report.json';
const MANIFEST = 'data/historical/expanded-stock-validation-v1/manifest.json';
export const MIN_TRAINING_RETURNS = 252;

// The reference compounds the arithmetic daily mean as prescribed by v1.
// Both endpoints of each observed interval must be trading-session aligned.
export function trainingMean(asset,cut,horizon,calendar,minimum=MIN_TRAINING_RETURNS) {
  requireThat(Number.isInteger(horizon)&&horizon>0,'Invalid forecast horizon');
  requireThat(calendar.includes(cut),'Origin absent from benchmark calendar');
  if(!asset || !Array.isArray(asset.history))return {reason:'missing-frozen-asset-history'};
  const historical=asset.history.filter(r=>r.date<=cut);
  const dates=historical.map(r=>r.date);
  requireThat(dates.every((day,i)=>i===0||day>dates[i-1]),
    'Duplicate or unordered frozen asset prices');
  const map=new Map(historical.map(r=>[r.date,r.adj_close]));
  if(!map.has(cut))return {reason:'missing-exact-origin-price'};
  const prior=calendar.filter(d=>d<=cut),returns=[];
  for(let i=1;i<prior.length;i++){
    const prev=map.get(prior[i-1]),next=map.get(prior[i]);
    if(prev===undefined || next===undefined)continue;
    if(!Number.isFinite(prev)||prev<=0||!Number.isFinite(next)||next<=0)
      return {reason:'invalid-adjusted-training-close'};
    const ret=next/prev-1;
    if(!Number.isFinite(ret)||ret<=-1)return {reason:'invalid-training-return'};
    returns.push(ret);
  }
  if(returns.length<minimum)return {reason:'insufficient-expanding-training-sessions',
    training_returns:returns.length,minimum_training_returns:minimum};
  const daily=avg(returns);
  requireThat(daily>-1,'Invalid expanding daily mean');
  const predicted=(1+daily)**horizon-1;
  requireThat(Number.isFinite(predicted),'Invalid expanding benchmark prediction');
  return {prediction:predicted,training_returns:returns.length,
    training_end:cut,training_start:prior[0],
    model:'training-only-expanding-arithmetic-daily-mean',
    historical_vendor_vintage_verified:false};
}

function scoreOrigin(origin,horizon,marketBySymbol,calendar,minimum) {
  const cut=origin.cut;
  const maturity=horizon.maturity;
  const h=horizon.horizon_sessions;
  const last=calendar.indexOf(cut);
  requireThat(last>=0,'Missing origin trading session');
  const expected=calendar[last+h]||null;
  requireThat(expected===maturity,'Maturity does not agree with frozen trading calendar');
  const rows=[],reasons=new Map();
  for(const obs of horizon.observations){
    if(obs.role!=='stock')continue;
    if(obs.reason){
      reasons.set(obs.reason,(reasons.get(obs.reason)||0)+1);
      rows.push({symbol:obs.symbol,status:'unscored',reason:obs.reason});
      continue;
    }
    requireThat(maturity!==null&&Number.isFinite(obs.realized_proxy)&&
      Number.isFinite(obs.models?.pilot_kernel?.forecast_mean),
      'Scored pair missing frozen mean or outcome');
    const trained=trainingMean(marketBySymbol.get(obs.symbol),cut,h,calendar,minimum);
    if(trained.reason){
      reasons.set(trained.reason,(reasons.get(trained.reason)||0)+1);
      rows.push({symbol:obs.symbol,status:'unscored',reason:trained.reason});
      continue;
    }
    const y=obs.realized_proxy,forecast=obs.models.pilot_kernel.forecast_mean,
      squared_candidate=(forecast-y)**2,squared_reference=(trained.prediction-y)**2;
    rows.push({symbol:obs.symbol,status:'paired',
      realized_proxy:y,candidate_mean:forecast,expanding_mean:trained.prediction,
      training_returns:trained.training_returns,training_end:trained.training_end,
      squared_candidate,squared_reference,reference_minus_candidate:squared_reference-squared_candidate});
  }
  const paired=rows.filter(r=>r.status==='paired');
  requireThat(paired.length<=horizon.scored_stocks,
    'More benchmark pairs than archived scored stocks');
  return {horizon_sessions:h,maturity,forecast_stocks:horizon.forecast_stocks,
    preexisting_scored_stocks:horizon.scored_stocks,paired_stocks:paired.length,
    exclusions:Object.fromEntries([...reasons].sort(([a],[b])=>a.localeCompare(b))),
    mse_candidate:avg(paired.map(r=>r.squared_candidate)),
    mse_reference:avg(paired.map(r=>r.squared_reference)),
    mse_gain_reference_minus_candidate:avg(paired.map(r=>r.reference_minus_candidate)),
    rows};
}

export function buildBenchmark(scored,market,manifest,protocol,minimum=MIN_TRAINING_RETURNS){
  requireThat(protocol.protocol==='full-engine-evaluation-v1'&&
    protocol.primary_tests.some(t=>t.id==='return_mse'&&
      t.reference.includes('minimum 252 daily return intervals')),
    'Frozen primary MSE benchmark is not registered');
  requireThat(minimum===MIN_TRAINING_RETURNS,'Primary benchmark minimum cannot be relaxed');
  requireThat(scored.method===manifest.protocol.id &&
    scored.scope===manifest.protocol.target &&
    scored.production_eligible===false &&
    scored.independent_holdout===false &&
    scored.optimization_executed===false &&
    scored.certified_full_engine_cuts===0 &&
    scored.predictive_validation==='not-established' &&
    scored.pooled_inference===null &&
    manifest.independent_holdout===false,
    'Frozen retrospective-only cohort contract changed');
  requireThat(scored.origin_count===manifest.origins.length &&
    scored.origins.length===manifest.origins.length,
    'Incomplete frozen scored cohort');
  requireThat(scored.evidence.forecast_commit && scored.evidence.market_commit===manifest.protocol.market_commit &&
    scored.evidence.protocol_sha256===manifest.evidence.protocol_sha256,
    'Frozen cohort or market lineage changed');
  const calendar=market.assets.find(a=>a.symbol==='SPY')?.history
    .filter(r=>r.date<=market.price_as_of).map(r=>r.date);
  requireThat(calendar?.length>0 &&
    calendar.every((v,i)=>!i||v>calendar[i-1]),'Invalid market trading calendar');
  const universe=new Map(market.assets.map(a=>[a.symbol,a]));
  requireThat(universe.size===market.assets.length,'Duplicate frozen market symbol');
  const horizons=protocol.horizons_sessions;
  requireThat(JSON.stringify(horizons)===JSON.stringify(manifest.protocol.horizons_sessions),
    'Benchmark horizons differ from frozen cohort');
  const origins=scored.origins.map((item,i)=>{
    requireThat(item.cut===manifest.origins[i].cut &&
      manifest.schedule.find(x=>x.cut===item.cut)?.selected===true,
      'Scored origin does not match frozen selected schedule');
    requireThat(item.horizons.length===horizons.length,
      'Missing or added scored horizon');
    const checked=item.horizons.map((row,j)=>{
      requireThat(row.horizon_sessions===horizons[j],'Horizon order changed');
      return scoreOrigin(item,row,universe,calendar,minimum);
    });
    return {cut:item.cut,horizons:checked};
  });
  const summary=Object.fromEntries(horizons.map((h,i)=>{
    const all=origins.map(o=>({cut:o.cut,...o.horizons[i]})),
      paired=all.filter(r=>r.paired_stocks>0&&r.maturity);
    const nonoverlapping=[];let prevEnd='';
    for(const row of paired){
      if(row.cut>=prevEnd){nonoverlapping.push(row.cut);prevEnd=row.maturity;}
    }
    const diffs=paired.map(r=>r.mse_gain_reference_minus_candidate);
    return [h,{forecast_origins:all.length,mature_origins:all.filter(r=>r.maturity).length,
      paired_origins:paired.length,paired_stock_rows:paired.reduce((n,r)=>n+r.paired_stocks,0),
      nonoverlapping_paired_origin_cuts:nonoverlapping,
      nonoverlapping_paired_origins:nonoverlapping.length,
      mean_origin_mse_candidate:avg(paired.map(r=>r.mse_candidate)),
      mean_origin_mse_reference:avg(paired.map(r=>r.mse_reference)),
      mean_origin_mse_gain_reference_minus_candidate:avg(diffs),
      origin_count_positive_gain:diffs.filter(x=>x>0).length,
      blocked_primary_inference:true,primary_test_p_value:null,
      interpretation:'Equal-weighted per-origin descriptive MSE on matched surviving stocks; shared origin assets are not independent observations'}];
  }));
  return {protocol:'retrospective-expanding-mean-benchmark-v1',
    registered_primary_benchmark:'return_mse',
    source_protocol:SOURCE_PROTOCOL,
    study_role:'previously-inspected-retrospective-development',
    forecast_data_source:'back-adjusted-provider-history-reconstructed-later',
    historical_vendor_vintage_verified:false,
    full_engine_executed:false,certified_full_engine_cuts:0,
    independent_confirmatory_holdout:false,predictive_validation:'not-established',
    calendar_origins:manifest.schedule.map(r=>({cut:r.cut,selected:r.selected,reason:r.reason})),
    origin_count:origins.length,origins,summary,
    inference:{primary_p_values:null,holm_adjusted_p_values:null,
      reason:'No full-engine historical cohort, independent holdout, certified vendor vintages or sufficient independent monthly observations'},
  };
}

export function main(output='out/retrospective-expanding-mean-benchmark-v1.json'){
  const manifestBytes=readFileSync(resolve(ROOT,MANIFEST)),
    scoredBytes=readFileSync(resolve(ROOT,SCORES)),
    protocolBytes=readFileSync(resolve(ROOT,SOURCE_PROTOCOL)),
    manifest=JSON.parse(manifestBytes), scored=JSON.parse(scoredBytes),protocol=JSON.parse(protocolBytes);
  requireThat(scored.evidence.forecast_manifest_sha256===digest(manifestBytes),
    'Frozen forecast manifest SHA256 mismatch');
  const show=(commit,path)=>execFileSync('git',['show',commit+':'+path],
    {cwd:ROOT,maxBuffer:128*1024*1024});
  const marketBytes=show(manifest.protocol.market_commit,manifest.protocol.market_path);
  requireThat(scored.evidence.market_sha256===digest(marketBytes),
    'Frozen outcome market SHA256 mismatch');
  const result=buildBenchmark(scored,JSON.parse(marketBytes),manifest,protocol);
  result.evidence={scored_report_sha256:digest(scoredBytes),
    frozen_manifest_sha256:digest(manifestBytes),
    source_protocol_sha256:digest(protocolBytes),
    frozen_market_sha256:digest(marketBytes),
    forecast_commit:scored.evidence.forecast_commit,
    market_commit:manifest.protocol.market_commit,
    benchmark_script_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))};
  const target=resolve(ROOT,output);
  mkdirSync(dirname(target),{recursive:true});
  writeFileSync(target,JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({origins:result.origin_count,summary:result.summary,
    certified_full_engine_cuts:0,confirmatory:false}));
  return result;
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main(process.argv.slice(2)[0]||undefined);
