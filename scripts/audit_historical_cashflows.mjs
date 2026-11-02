/** Outcome-only cash-dividend reconciliation. No forecast or portfolio changes. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
import {digest} from './scoped_engine_pilot.mjs';
import {assertEquivalent} from './attribute_scoped_pilot.mjs';
import {reconcileDistributionReturn} from '../dist/assets/js/distribution-ledger.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const STOCK_SCORE_COMMIT='39ff3b2f5c992c9b441fea4c5efd3307a5eeba06';
const MARKET_COMMIT='b2d15329e2484ce103d7d729b90c65e4367b218d';
const check=(ok,message)=>{if(!ok)throw Error(message);};
export function realizeCash(asset,start,end,policy) {
  if(!asset)return {available:false,reason:'missing-stock-outcome'};
  if((asset.price_adjustments||[]).some(e=>e.date>start))
    return {available:false,reason:'unreconciled-non-split-price-adjustment'};
  return reconcileDistributionReturn(asset,start,end,policy);
}
export function auditCashflows(stockScores,market,issuerInputs,policy) {
  check(issuerInputs.outcome_only===true&&issuerInputs.forecast_input_eligible===false,'Issuer facts cannot become forecast inputs');
  check(policy.dividendPolicy==='cash'&&policy.cashYield===0&&policy.dividendWithholding===0,
    'Cash audit only implements the frozen zero-yield, zero-withholding convention');
  const assets=new Map(market.assets.map(a=>[a.symbol,a])),issuers=new Map(issuerInputs.assets.map(a=>[a.symbol,a.issuer_distributions]));
  check(assets.size===market.assets.length&&issuers.size===issuerInputs.assets.length,'Duplicate source identity');
  const queue=new Map();
  const origins=stockScores.origins.map(origin=>({cut:origin.cut,horizons:origin.horizons.map(h=>{
    const rows=h.observations.filter(r=>r.role==='stock').map(row=>{
      if(!h.maturity)return {symbol:row.symbol,status:'pending',reason:'immature'};
      const asset=assets.get(row.symbol),before=realizeCash(asset,origin.cut,h.maturity,policy),
        issuer=issuers.get(row.symbol);
      if(issuer)check(issuer.symbol===row.symbol&&issuer.source_layer==='issuer','Issuer identity mismatch');
      const after=realizeCash(issuer?{...asset,issuer_distributions:issuer}:asset,origin.cut,h.maturity,policy);
      if(!after.available&&asset) {
        const events=asset.distribution_index?.records.filter(e=>e.ex_date>origin.cut&&e.ex_date<=h.maturity&&e.amount_per_share>0)||[];
        const entry=queue.get(row.symbol)||{symbol:row.symbol,blocked_rows:0,required_events:new Map(),reasons:new Set()};
        entry.blocked_rows++;entry.reasons.add(after.reason);
        for(const event of events)entry.required_events.set(event.ex_date,{...event,
          amount_basis:'frozen-provider-index-not-issuer-confirmed',pay_date:null});
        queue.set(row.symbol,entry);
      }
      return {symbol:row.symbol,status:after.available?'reconciled':'blocked',
        before,after,issuer_source_added:!!issuer,issuer_source_representation:issuer?.source_representation??null,
        ...(after.available?{gross_adjusted_proxy:row.realized_proxy,
          cash_minus_adjusted_proxy:Number.isFinite(row.realized_proxy)?after.return-row.realized_proxy:null,
          broker_execution_verified:false,price_vintage_verified:false}:{})};
    });
    return {horizon_sessions:h.horizon_sessions,maturity:h.maturity,rows,
      before_reconciled:rows.filter(r=>r.before?.available).length,
      after_reconciled:rows.filter(r=>r.after?.available).length,
      newly_reconciled:rows.filter(r=>!r.before?.available&&r.after?.available).length};
  })}));
  const summaries=Object.fromEntries([21,63,252].map(h=>{
    const horizons=origins.map(o=>o.horizons.find(r=>r.horizon_sessions===h)),rows=horizons.flatMap(h=>h.rows);
    return [h,{mature_rows:rows.filter(r=>r.status!=='pending').length,pending_rows:rows.filter(r=>r.status==='pending').length,
      before_reconciled:horizons.reduce((n,h)=>n+h.before_reconciled,0),
      after_reconciled:horizons.reduce((n,h)=>n+h.after_reconciled,0),
      newly_reconciled:horizons.reduce((n,h)=>n+h.newly_reconciled,0),
      blocked:rows.filter(r=>r.status==='blocked').length}];
  }));
  return {method:'frozen-historical-cashflow-outcome-audit-v1',policy,
    forecast_scoring_performed:false,forecasts_changed:false,optimization_executed:false,
    production_eligible:false,prospective:false,certified_full_engine_cuts:0,predictive_validation:'not-established',
    scope:'Gross cash-dividend wealth with issuer-linked payment facts and model tax/yield conventions; not certified corporate-action completeness, broker execution or a strategy backtest',
    summaries,origins,recovery_queue:[...queue.values()].map(r=>({...r,reasons:[...r.reasons].sort(),
      required_events:[...r.required_events.values()].sort((a,b)=>a.ex_date.localeCompare(b.ex_date))}))
      .sort((a,b)=>b.blocked_rows-a.blocked_rows||a.symbol.localeCompare(b.symbol))};
}
export function main(output='data/historical/cashflow-reconciliation-v1/report.json',verify=false) {
  const show=(commit,path)=>execFileSync('git',['show',`${commit}:${path}`],{cwd:ROOT,maxBuffer:128*1024*1024}),
    marketRaw=show(MARKET_COMMIT,'dist/data/market.json'),
    scoreRaw=show(STOCK_SCORE_COMMIT,'data/historical/expanded-stock-validation-scores-v1/report.json'),
    base=resolve(ROOT,'data/historical/issuer-cashflows-v1'),manifestRaw=readFileSync(resolve(base,'manifest.json')),
    manifest=JSON.parse(manifestRaw),issuerRaw=readFileSync(resolve(base,'normalized.json')),issuer=JSON.parse(issuerRaw);
  check(digest(manifestRaw)===issuer.manifest_sha256&&
    digest(readFileSync(resolve(ROOT,'scripts/issuer_cashflow_inputs.py')))===issuer.normalizer_sha256,'Issuer normalization identity mismatch');
  for(const source of manifest.sources)check(digest(readFileSync(resolve(base,source.path)))===source.sha256,'Issuer source hash mismatch');
  const original=JSON.parse(gunzipSync(readFileSync(resolve(ROOT,'data/historical/scoped-engine-pilot-v1/results.json.gz')))),
    policy={dividendPolicy:'cash',cashYield:0,dividendWithholding:0};
  for(const row of original.results)for(const [key,value] of Object.entries(policy))
    check(row.proposal.mandate[key]===value,'Original pilot mandate differs');
  const report={...auditCashflows(JSON.parse(scoreRaw),JSON.parse(marketRaw),issuer,policy),
    evidence:{market_commit:MARKET_COMMIT,market_sha256:digest(marketRaw),
      stock_score_commit:STOCK_SCORE_COMMIT,stock_score_sha256:digest(scoreRaw),
      issuer_manifest_sha256:digest(manifestRaw),issuer_normalized_sha256:digest(issuerRaw),
      scorer_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))}};
  const target=resolve(ROOT,output);mkdirSync(dirname(target),{recursive:true});
  if(verify)assertEquivalent(report,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.summaries,null,2));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main(process.argv.slice(2).find(a=>a!=='--verify'),process.argv.includes('--verify'));
