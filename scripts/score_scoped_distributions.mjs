/** Score previously archived model-implied distributions; never rerun their forecasts. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest} from './scoped_engine_pilot.mjs';
import {endpointReturn,metrics} from './score_scoped_pilot.mjs';
import {scoreDistribution} from './simulator_validation.mjs';
import {assertEquivalent} from './attribute_scoped_pilot.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
export const FREEZE_COMMIT='d79d3e4d4d6eb10a4e8a502a4676bd7210602a32';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const average=xs=>xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:null;

export function probabilityScore(distribution,realized) {
  const p=distribution.loss_probability;
  check(Number.isFinite(p)&&p>=0&&p<=1,'Invalid frozen loss probability');
  return {...scoreDistribution(distribution,realized),
    forecast_mean:distribution.mean,loss_probability:p,brier_loss:(p-Number(realized<0))**2,
    q05:distribution.q05,q95:distribution.q95,es_loss_signed:distribution.es_loss_signed};
}
function summarize(rows,id) {
  const points=rows.map(r=>({prediction:r.models[id].forecast_mean,realized_proxy:r.realized_proxy}));
  const scores=rows.map(r=>r.models[id]);
  return {...metrics(points,'prediction'),crps:average(scores.map(s=>s.crps)),
    brier_loss:average(scores.map(s=>s.brier_loss)),coverage90:average(scores.map(s=>Number(s.covered90))),
    loss_frequency:average(rows.map(r=>Number(r.realized_proxy<0))),
    forecast_loss_probability:average(scores.map(s=>s.loss_probability)),
    var95_exception_rate:average(scores.map(s=>Number(s.var95_exception))),
    signed_es_residual:average(scores.map(s=>s.es_residual))};
}
export function scoreFrozenDistributions(frozen,market) {
  const protocol=frozen.protocol,assets=new Map(market.assets.map(a=>[a.symbol,a]));
  check(assets.size===market.assets.length,'Duplicate market symbol');
  const calendar=assets.get('SPY')?.history.filter(r=>r.date<=market.price_as_of).map(r=>r.date);
  check(calendar?.length&&calendar.every((d,i)=>!i||d>calendar[i-1]),'Invalid benchmark calendar');
  check(frozen.production_eligible===false&&frozen.certified_full_engine_cuts===0,'Unexpected forecast scope');
  const origins=frozen.origins.map(origin=>{
    check(calendar.includes(origin.cut),'Missing exact origin session');
    const future=calendar.filter(d=>d>origin.cut);
    return {cut:origin.cut,horizons:protocol.horizons_sessions.map(horizon=>{
      const maturity=future[horizon-1]||null,records=origin.records.filter(r=>r.horizon_sessions===horizon),
        symbols=[...new Set(records.map(r=>r.symbol))];
      const observations=symbols.map(symbol=>{
        const forecasts=records.filter(r=>r.symbol===symbol),models={};
        check(forecasts.length===protocol.models.length&&
          protocol.models.every(id=>forecasts.filter(r=>r.model===id).length===1),'Unmatched frozen model sample');
        check(forecasts.every(r=>r.role===forecasts[0].role),'Inconsistent instrument role');
        const outcome=maturity?endpointReturn(assets.get(symbol),origin.cut,maturity,market.price_as_of):{reason:'immature'};
        if(!outcome.reason)for(const forecast of forecasts)
          models[forecast.model]=probabilityScore(forecast.distribution,outcome.realized_proxy);
        return {symbol,role:forecasts[0].role,...outcome,...(!outcome.reason?{models}:{})};
      });
      const stocks=observations.filter(r=>r.role==='stock'&&!r.reason);
      return {horizon_sessions:horizon,maturity,forecast_stocks:observations.filter(r=>r.role==='stock').length,
        scored_stocks:stocks.length,exclusions:observations.filter(r=>r.reason),observations,
        stock_metrics:Object.fromEntries(protocol.models.map(id=>[id,summarize(stocks,id)])),
        benchmark:observations.find(r=>r.role==='benchmark')||null};
    })};
  });
  return {method:protocol.id,scope:protocol.target,prospective:false,independent_holdout:false,
    production_eligible:false,certified_full_engine_cuts:0,predictive_validation:'not-established',
    pooled_inference:null,origin_count:origins.length,origins};
}
export function main(output='data/historical/scoped-pilot-distribution-scores-v1/report.json',verify=false) {
  const show=path=>execFileSync('git',['show',`${FREEZE_COMMIT}:${path}`],{cwd:ROOT,maxBuffer:128*1024*1024}),
    protocolRaw=show('docs/protocolo-distribuciones-piloto-v1.json'),protocol=JSON.parse(protocolRaw),
    forecastRaw=show(protocol.forecast_directory+'/forecasts.json.gz'),frozen=JSON.parse(gunzipSync(forecastRaw));
  check(digest(protocolRaw)===frozen.evidence.protocol_sha256,'Frozen protocol hash mismatch');
  assertEquivalent(protocol,frozen.protocol,'protocol');
  const marketRaw=execFileSync('git',['show',`${protocol.market_commit}:${protocol.market_path}`],{cwd:ROOT,maxBuffer:128*1024*1024});
  const report={...scoreFrozenDistributions(frozen,JSON.parse(marketRaw)),protocol,
    evidence:{forecast_commit:FREEZE_COMMIT,forecast_sha256:digest(forecastRaw),protocol_sha256:digest(protocolRaw),
      market_commit:protocol.market_commit,market_sha256:digest(marketRaw),
      scorer_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))}};
  const target=resolve(ROOT,output);mkdirSync(dirname(target),{recursive:true});
  if(verify)assertEquivalent(report,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.origins.map(o=>({cut:o.cut,horizons:o.horizons.map(h=>({
    horizon:h.horizon_sessions,maturity:h.maturity,scored:h.scored_stocks,metrics:h.stock_metrics}))})),null,2));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main(process.argv.slice(2).find(a=>a!=='--verify'),process.argv.includes('--verify'));
