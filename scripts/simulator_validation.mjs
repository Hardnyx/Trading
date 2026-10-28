/** Prospective validation of the actual price kernel. No account data or trading. */
import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { prepareComposition, composeMultiStart } from '../dist/assets/js/composer.mjs?v=0.34.0';
import { referenceRequest } from '../dist/assets/js/reference-preset.mjs?v=0.34.0';
import { generatePaths, PRICE_KERNEL_VERSION, BASE_REGIME } from '../dist/assets/js/path-model.mjs?v=0.34.0';
import { marketFactorCovariance } from '../dist/assets/js/factor-covariance.mjs?v=0.34.0';
import { namedRandom, normalGenerator } from '../dist/assets/js/random.mjs?v=0.34.0';
import { quantile } from '../dist/assets/js/analytics.mjs?v=0.34.0';
import { MODEL_VERSION } from '../dist/assets/js/policy.mjs?v=0.34.0';
import { ewmaCovariance } from '../dist/assets/js/risk-math.mjs?v=0.34.0';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const HORIZONS=[1,5,21], LEAD=2, GRID=100;
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const nyDate=stamp=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(stamp));
const average=values=>values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
export function originBlockInterval(values,block=5,draws=1000){
  if(values.length<4*block)return null;
  const random=namedRandom(0x9173bd25,'origin-block-interval'),means=[];
  for(let d=0;d<draws;d++){
    const sample=[];
    while(sample.length<values.length){
      const start=Math.floor(random()*(values.length-block+1));
      sample.push(...values.slice(start,start+block));
    }
    means.push(average(sample.slice(0,values.length)));
  }
  means.sort((a,b)=>a-b);return [quantile(means,.025),quantile(means,.975)];
}

export function distributionSummary(values) {
  if(values.length<100||values.some(v=>!Number.isFinite(v)||v<=-1))
    throw Error('Nonfinite or bankrupt numerical price distribution');
  const sorted=[...values].sort((a,b)=>a-b), logs=values.map(Math.log1p), meanLog=average(logs),
    varianceLog=average(logs.map(v=>(v-meanLog)**2)), tail=sorted.slice(0,Math.ceil(sorted.length*.05));
  return {mean:average(values),mean_log:meanLog,variance_log:varianceLog,
    q05:quantile(sorted,.05),q95:quantile(sorted,.95),es_loss_signed:-average(tail),
    quantiles:Array.from({length:GRID},(_,i)=>quantile(sorted,(i+.5)/GRID))};
}

export function buildKernelForecast(snapshot,volatility,issuedAt,{paths=1000,referenceDecision=null}={}) {
  if(!Number.isFinite(Date.parse(issuedAt))||Date.parse(snapshot.generated_at)>Date.parse(issuedAt)||
      !snapshot.price_as_of||nyDate(issuedAt)<snapshot.price_as_of||
      nyDate(issuedAt)<(snapshot.requested_as_of||snapshot.price_as_of))
    throw Error('Forecast cannot predate the first available source information');
  if(volatility.as_of!==snapshot.price_as_of||volatility.source_market_generated_at!==snapshot.generated_at)
    throw Error('Original market and risk vintage differ');
  const request=referenceRequest({...snapshot,volatility}),x=prepareComposition(snapshot,request.settings,{},request.rules),
    sample=generatePaths(x,paths,0x5a91c237,252,{maxSteps:LEAD+Math.max(...HORIZONS)}),records=[];
  if(!Number.isFinite(x.riskFree))throw Error('Missing economic input: DGS3MO');
  for(let i=0;i<x.assets.length;i++){
    const a=x.assets[i],anchor=x.anchors[i];
    if(a.type==='cash'||(!anchor.fundamental&&!anchor.bond))continue;
    const prices=(a.history||[]).map(r=>r.adj_close).filter(v=>v>0).slice(-501),
      logReturns=prices.slice(1).map((p,k)=>Math.log(p/prices[k]));
    const dailyVariance=ewmaCovariance([logReturns],x.options.lambda)[0][0]/252,
      baselineNormal=normalGenerator(namedRandom(0x9173bd25,a.symbol));
    for(const horizon of HORIZONS){
      const values=Array.from({length:paths},(_,p)=>{
        const offset=p*(sample.steps+1);
        return sample.gross[i][offset+LEAD+horizon]/sample.gross[i][offset+LEAD]-1;
      });
      const baseline=Array.from({length:paths},()=>Math.expm1(-.5*dailyVariance*horizon+
        Math.sqrt(dailyVariance*horizon)*baselineNormal()));
      records.push({symbol:a.symbol,horizon_sessions:horizon,anchor:anchor.annual,anchor_source:anchor.source,
        kernel:distributionSummary(values),ewma_zero_mean:distributionSummary(baseline)});
    }
  }
  // Joint portfolio calibration uses the SAME price paths, including market
  // dependence. Its target is a future static total-return basket, not broker
  // fills, withdrawals or an executable strategy return.
  const baskets=[];
  if(referenceDecision?.positions?.length)baskets.push({name:'reference-decision',positions:referenceDecision.positions});
  const spy=x.assets.findIndex(a=>a.symbol==='SPY'),shy=x.assets.findIndex(a=>a.symbol==='SHY');
  if(spy>=0&&shy>=0)baskets.push({name:'risk-comparator',positions:[{symbol:'SPY',weight:.2},
    {symbol:'SHY',weight:.35},{symbol:'CASH',weight:.45}]});
  if(baskets.length){
    const factor=marketFactorCovariance(x.assets,snapshot.assets,x.asOf,x.options.lambda),
      baselineInput={...x,covariance:factor.available?factor.covariance:x.covariance,factorization:null,
        conditional:{dynamic:false},regimes:[BASE_REGIME],
        options:{...x.options,volatilityMode:'legacy',model:'gbm',uncertainFundamentals:false},
        anchors:x.assets.map(a=>({symbol:a.symbol,sector:a.sector,annual:0,low:0,high:0}))},
      baseline=generatePaths(baselineInput,paths,0x9173bd25,252,{maxSteps:LEAD+21});
    const basketReturn=(weights,sample,p,h)=>weights.reduce((total,r)=>{
      if(r.symbol==='CASH')return total+r.weight*Math.expm1(Math.log1p(x.policy.cashYield||0)*h/252);
      const i=x.assets.findIndex(a=>a.symbol===r.symbol);if(i<0)throw Error('Unknown sealed basket constituent');
      const offset=p*(sample.steps+1);
      return total+r.weight*(sample.gross[i][offset+LEAD+h]/sample.gross[i][offset+LEAD]-1);
    },0);
    for(const basket of baskets)for(const h of HORIZONS)records.push({symbol:'PORTFOLIO:'+basket.name,
      weights:basket.positions,cash_yield_assumed:x.policy.cashYield||0,horizon_sessions:h,
      kernel:distributionSummary(Array.from({length:paths},(_,p)=>basketReturn(basket.positions,sample,p,h))),
      ewma_zero_mean:distributionSummary(Array.from({length:paths},(_,p)=>basketReturn(basket.positions,baseline,p,h)))});
  }
  return {schema_version:1,protocol:'future-origin-total-return-marginals-v1',
    price_kernel_version:PRICE_KERNEL_VERSION,engine_version:MODEL_VERSION,issued_at:issuedAt,
    issue_ny_date:nyDate(issuedAt),input_price_as_of:snapshot.price_as_of,
    market_collected_at:snapshot.generated_at,lead_sessions:LEAD,paths,
    horizons:HORIZONS,records,
    scope:'Exact production price kernel; asset and joint static-basket total returns at 1/5/21 sessions after a future origin. Cash uses the declared rate. No validation of broker execution, withdrawals, portfolio superiority or 12-month profitability.',
    baseline:'Zero arithmetic mean and flat observed EWMA variance; same information cutoff',
    original_vintages_verified:false};
}

export function scoreDistribution(forecast,realized) {
  const loss=-realized,varLoss=-forecast.q05,
    crps=2*average(forecast.quantiles.map((q,i)=>
      (((i+.5)/forecast.quantiles.length)-(realized<q?1:0))*(realized-q)));
  return {realized,crps,covered90:realized>=forecast.q05&&realized<=forecast.q95,
    var95_exception:realized<forecast.q05,
    es_residual:varLoss+Math.max(0,loss-varLoss)/.05-forecast.es_loss_signed,
    mean_error:realized-forecast.mean,
    qlike:forecast.variance_log>0?Math.log(forecast.variance_log)+
      (Math.log1p(realized)-forecast.mean_log)**2/forecast.variance_log:null};
}

export function scoreKernelForecast(origin,snapshot,horizon) {
  if(!origin.horizons.includes(horizon))throw Error('Unknown sealed horizon');
  const spy=snapshot.assets.find(a=>a.symbol==='SPY'),
    future=(spy?.history||[]).filter(r=>r.date>origin.input_price_as_of&&r.date<=snapshot.price_as_of)
      .sort((a,b)=>a.date.localeCompare(b.date)),
    start=future[origin.lead_sessions-1],end=future[origin.lead_sessions+horizon-1];
  if(!end)return null;
  // An outcome is excluded if its starting close was not strictly after
  // publication. Never retroactively move the origin to find a usable return.
  if(start.date<=origin.issue_ny_date)return {schema_version:1,status:'nonprospective',
    price_kernel_version:origin.price_kernel_version,
    reason:'Realized return would start on or before publication date',horizon_sessions:horizon,
    input_price_as_of:origin.input_price_as_of,issued_at:origin.issued_at,origin_date:start.date};
  const rows=origin.records.filter(r=>r.horizon_sessions===horizon).map(row=>{
    let y=0;
    for(const position of row.weights||[{symbol:row.symbol,weight:1}]){
      if(position.symbol==='CASH'){y+=position.weight*Math.expm1(Math.log1p(row.cash_yield_assumed||0)*horizon/252);continue;}
      const a=snapshot.assets.find(a=>a.symbol===position.symbol),
        p=a?.history.find(r=>r.date===start.date)?.adj_close,
        q=a?.history.find(r=>r.date===end.date)?.adj_close;
      if(!(p>0&&q>0))return {symbol:row.symbol,status:'missing-original-outcome'};
      y+=position.weight*(q/p-1);
    }
    return {symbol:row.symbol,status:'scored',kernel:scoreDistribution(row.kernel,y),
      ewma_zero_mean:scoreDistribution(row.ewma_zero_mean,y)};
  });
  return {schema_version:1,status:'scored',price_kernel_version:origin.price_kernel_version,
    issued_at:origin.issued_at,input_price_as_of:origin.input_price_as_of,
    horizon_sessions:horizon,origin_date:start.date,maturity_date:end.date,rows};
}

export function summarizeKernelValidation(origins,scores,updatedAt) {
  const horizons={};
  for(const h of HORIZONS){
    const all=scores.filter(s=>s.status==='scored'&&s.price_kernel_version===PRICE_KERNEL_VERSION&&s.horizon_sessions===h)
      .sort((a,b)=>a.origin_date.localeCompare(b.origin_date)),independent=[];
    let previousEnd='';
    for(const origin of all)if(origin.origin_date>=previousEnd){independent.push(origin);previousEnd=origin.maturity_date;}
    const rows=all.flatMap(s=>s.rows.filter(r=>r.status==='scored')),
      assets=rows.filter(r=>!r.symbol?.startsWith('PORTFOLIO:')),
      independentAssets=independent.flatMap(s=>s.rows.filter(r=>r.status==='scored'&&!r.symbol?.startsWith('PORTFOLIO:'))),
      portfolioNames=[...new Set(rows.filter(r=>r.symbol?.startsWith('PORTFOLIO:')).map(r=>r.symbol))];
    const model=(name,observations=assets)=>Object.fromEntries(['crps','var95_exception','es_residual','mean_error','qlike']
      .map(key=>[key,average(observations.map(r=>r[name][key]).filter(v=>v!==null).map(Number))]));
    const deltas=independent.map(s=>average(s.rows.filter(r=>r.status==='scored'&&!r.symbol?.startsWith('PORTFOLIO:'))
      .map(r=>r.ewma_zero_mean.crps-r.kernel.crps))).filter(Number.isFinite);
    horizons[h]={sealed:origins.filter(s=>s.price_kernel_version===PRICE_KERNEL_VERSION).length,
      scored_origins:all.length,nonoverlapping_origins:independent.length,asset_observations:assets.length,
      nonoverlapping_asset_observations:independentAssets.length,
      missing_outcomes:all.reduce((n,s)=>n+s.rows.filter(r=>r.status!=='scored').length,0),
      kernel:model('kernel'),ewma_zero_mean:model('ewma_zero_mean'),
      portfolios:Object.fromEntries(portfolioNames.map(name=>{
        const r=rows.filter(r=>r.symbol===name);
        return [name,{observations:r.length,kernel:model('kernel',r),ewma_zero_mean:model('ewma_zero_mean',r)}];
      })),
      origin_paired_crps_gain:average(deltas),origin_block95_crps_gain:originBlockInterval(deltas),
      status:independent.length>=20&&independentAssets.length>=500?'ready-for-diagnostic-review':'accumulating'};
  }
  return {schema_version:1,price_kernel_version:PRICE_KERNEL_VERSION,updated_at:updatedAt,
    sealed:origins.filter(s=>s.price_kernel_version===PRICE_KERNEL_VERSION).length,
    historical_sealed:origins.length,
    excluded_nonprospective:scores.filter(s=>s.status==='nonprospective'&&s.price_kernel_version===PRICE_KERNEL_VERSION).length,
    horizons,predictive_validation:'not-established',automatic_promotion:false,
    criteria:'20 nonoverlapping origins and 500 asset observations only enable diagnostic review; they do not certify predictive skill or economic advantage.',
    limitations:'Quantile-grid CRPS and origin-block intervals are approximate. Confidence blocks use five nonoverlapping origins, not independent asset rows. Larger-horizon overlapping origins are descriptive only. Current-source adjusted outcomes do not certify historical price vintages.'};
}

function readGzip(p){return JSON.parse(gunzipSync(readFileSync(p)).toString());}
function writeImmutable(p,value){if(existsSync(p))return false;mkdirSync(dirname(p),{recursive:true});
  writeFileSync(p,gzipSync(JSON.stringify(value)),{flag:'wx'});return true;}

export function updateKernelLedger({root=ROOT,issuedAt=null,skipIneligible=false}={}) {
  const marketBytes=readFileSync(resolve(root,'dist/data/market.json')),
    volBytes=readFileSync(resolve(root,'dist/data/volatility.json')),snapshot=JSON.parse(marketBytes),volatility=JSON.parse(volBytes),
    base=resolve(root,'data/simulator-validation'),forecastDir=resolve(base,'forecasts'),scoreDir=resolve(base,'scores');
  mkdirSync(forecastDir,{recursive:true});mkdirSync(scoreDir,{recursive:true});
  const forecastPath=resolve(forecastDir,snapshot.price_as_of+'.json.gz');
  if(!existsSync(forecastPath)){
    try{
      const cachedPath=resolve(root,'data/forecasts',snapshot.price_as_of+'.json'),
        cached=existsSync(cachedPath)?JSON.parse(readFileSync(cachedPath)):null,
        compatible=cached?.engine_version===MODEL_VERSION&&cached.market_sha256===sha(marketBytes)&&
          cached.volatility_sha256===sha(volBytes);
      const request=referenceRequest({...snapshot,volatility}),referenceDecision=compatible?{positions:cached.positions}:
        composeMultiStart(snapshot,request.settings,request.overrides,request.rules);
      const forecast=buildKernelForecast(snapshot,volatility,issuedAt||new Date().toISOString(),{referenceDecision});
      forecast.market_sha256=sha(marketBytes);forecast.volatility_sha256=sha(volBytes);
      forecast.source_commit=process.env.GITHUB_SHA||null;
      forecast.workflow_run_id=process.env.GITHUB_RUN_ID||null;
      forecast.source_kernel_sha256=sha(['path-model','random','return-model','conditional-risk','factor-covariance']
        .map(name=>readFileSync(resolve(ROOT,'dist/assets/js',name+'.mjs'))).join(''));
      // Timestamp completion, never the beginning of a possibly long search.
      forecast.issued_at=issuedAt||new Date().toISOString();
      forecast.issue_ny_date=nyDate(forecast.issued_at);
      writeImmutable(forecastPath,forecast);
    }catch(e){if(!skipIneligible||!/predate|Missing economic input/.test(e.message))throw e;}
  }
  const origins=readdirSync(forecastDir).filter(p=>p.endsWith('.json.gz')).map(p=>readGzip(resolve(forecastDir,p)));
  for(const origin of origins)for(const h of origin.horizons){
    const p=resolve(scoreDir,origin.input_price_as_of+'.h'+h+'.json.gz');if(existsSync(p))continue;
    const score=scoreKernelForecast(origin,snapshot,h);if(!score)continue;
    writeImmutable(p,{...score,scored_at:issuedAt||new Date().toISOString(),realized_market_sha256:sha(marketBytes)});
  }
  const scores=readdirSync(scoreDir).filter(p=>p.endsWith('.json.gz')).map(p=>readGzip(resolve(scoreDir,p))),
    summary=summarizeKernelValidation(origins,scores,issuedAt||new Date().toISOString());
  writeFileSync(resolve(root,'dist/data/simulator-validation.json'),JSON.stringify(summary,null,1)+'\n');
  return summary;
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const summary=updateKernelLedger({skipIneligible:process.argv.includes('--skip-ineligible')});
  console.log(JSON.stringify({kernel:summary.price_kernel_version,sealed:summary.sealed,
    horizons:summary.horizons,predictive_validation:summary.predictive_validation}));
}
