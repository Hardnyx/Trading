/** Descriptive scoring of immutable pilot anchors; never production validation. */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const check=(condition,message)=>{if(!condition)throw Error(message);};
const mean=xs=>xs.reduce((s,x)=>s+x,0)/xs.length;

function ranks(xs) {
  const sorted=xs.map((v,i)=>({v,i})).sort((a,b)=>a.v-b.v),out=[];
  for(let i=0;i<sorted.length;){let j=i+1;while(j<sorted.length&&sorted[j].v===sorted[i].v)j++;
    for(let k=i;k<j;k++)out[sorted[k].i]=(i+j-1)/2;i=j;}
  return out;
}
export function spearman(xs,ys) {
  if(xs.length<3)return null;
  const a=ranks(xs),b=ranks(ys),ma=mean(a),mb=mean(b);
  const va=a.reduce((s,x)=>s+(x-ma)**2,0),vb=b.reduce((s,x)=>s+(x-mb)**2,0);
  return va>0&&vb>0?a.reduce((s,x,i)=>s+(x-ma)*(b[i]-mb),0)/Math.sqrt(va*vb):null;
}
export function metrics(rows,key) {
  if(!rows.length)return {n:0,bias:null,mae:null,rmse:null,spearman:null};
  const errors=rows.map(r=>r[key]-r.realized_proxy);
  return {n:rows.length,bias:mean(errors),mae:mean(errors.map(Math.abs)),
    rmse:Math.sqrt(mean(errors.map(x=>x*x))),
    spearman:spearman(rows.map(r=>r[key]),rows.map(r=>r.realized_proxy))};
}
export function endpointReturn(asset,cut,maturity,marketCut) {
  if(!asset)return {reason:'missing_asset'};
  check(new Set(asset.history.map(r=>r.date)).size===asset.history.length,'Duplicate price date');
  if((asset.price_adjustments||[]).some(r=>cut<r.date&&r.date<=marketCut))
    return {reason:'unreconciled_non_split_adjustment'};
  const p=asset.history.find(r=>r.date===cut)?.adj_close,
    q=asset.history.find(r=>r.date===maturity)?.adj_close;
  if(![p,q].every(v=>Number.isFinite(v)&&v>0))return {reason:'missing_or_invalid_exact_endpoint'};
  return {realized_proxy:q/p-1,origin_adjusted_close:p,maturity_adjusted_close:q};
}

export function scorePilot(bundle,full,market) {
  check(full.production_eligible===false&&full.certified_full_engine_cuts===0,'Unexpected pilot scope');
  check(JSON.stringify(bundle.protocol)===JSON.stringify(full.protocol),'Pilot protocol mismatch');
  check(bundle.origins.length===full.results.length,'Origin count mismatch');
  const assets=new Map(market.assets.map(a=>[a.symbol,a]));
  check(assets.size===market.assets.length,'Duplicate market symbol');
  const calendar=assets.get('SPY')?.history.map(r=>r.date);
  check(calendar?.length&&calendar.every((d,i)=>!i||d>calendar[i-1]),'Invalid benchmark calendar');
  const origins=full.results.map((result,i)=>{
    const input=bundle.origins[i],cut=result.cut;
    check(input.cut===cut&&result.stored_snapshot_sha256===input.snapshot_sha256,'Origin identity mismatch');
    const date=new Date(cut+'T12:00:00Z');date.setUTCFullYear(date.getUTCFullYear()+1);
    const anniversary=date.toISOString().slice(0,10),maturity=calendar.find(d=>d>=anniversary&&d<=market.price_as_of)||null;
    const seen=new Set(),stockSymbols=new Set(input.snapshot.assets.filter(a=>a.type==='stock').map(a=>a.symbol));
    const benchmark=result.prepared.anchors.find(a=>a.symbol==='SPY');
    check(Number.isFinite(benchmark?.annual),'Missing archived benchmark anchor');
    const observations=result.prepared.anchors.filter(a=>stockSymbols.has(a.symbol)).map(a=>{
      check(!seen.has(a.symbol)&&Number.isFinite(a.annual),'Invalid or duplicate anchor');seen.add(a.symbol);
      return {symbol:a.symbol,anchor:a.annual,zero:0,benchmark_anchor:benchmark.annual,
        ...(maturity?endpointReturn(assets.get(a.symbol),cut,maturity,market.price_as_of):{reason:'immature'})};
    });
    const rows=observations.filter(r=>!r.reason),selection=result.proposal.diagnostics.reliableSelection;
    const confirmation=result.proposal.diagnostics.robustDecision;
    const spy=maturity?endpointReturn(assets.get('SPY'),cut,maturity,market.price_as_of):{reason:'immature'};
    const cash=result.proposal.positions.length===1&&result.proposal.positions[0].symbol==='CASH'&&
      result.proposal.positions[0].weight===1&&result.proposal.mandate.cashYield===0;
    check(cash,'Portfolio context only defined for archived zero-yield cash decisions');
    return {cut,anniversary,maturity,forecast_stocks:observations.length,scored_stocks:rows.length,
      exclusions:observations.filter(r=>r.reason),observations,
      metrics:{anchor:metrics(rows,'anchor'),zero:metrics(rows,'zero'),benchmark_anchor:metrics(rows,'benchmark_anchor')},
      gate:{screened:selection.screened,finalists:selection.finalists,admissible_transitions:selection.admissible,
        archived_feasible_finalists:selection.candidates.filter(c=>c.feasible).length,
        positive_lower_gain_finalists:selection.candidates.filter(c=>c.minimumLowerGain>confirmation.hurdle).length,
        per_model_rejection_attribution:'unavailable-in-archived-selection',
        confirmation_scope:'cash-versus-cash fallback; not a confirmation of rejected investments',
        benchmark_buy_allowed:result.prepared.buy_allowed[result.prepared.symbols.indexOf('SPY')]},
      portfolio_context:{cash_declared_return:0,benchmark:spy,
        hypothetical_35pct_spy_gross_return:spy.reason?null:0.35*spy.realized_proxy,
        costs_and_cashflows_reconciled:false,risk_matched:false}};
  });
  return {method:'scoped-pilot-anchor-outcomes-v1',production_eligible:false,prospective:false,
    certified_full_engine_cuts:0,predictive_validation:'not-established',
    independent_holdout:false,origin_count:origins.length,pooled_inference:null,origins};
}

export function main(output='data/historical/scoped-pilot-outcomes-v1/report.json') {
  const protocolPath='docs/protocolo-puntuacion-piloto-v1.json',protocolRaw=readFileSync(resolve(ROOT,protocolPath)),
    protocol=JSON.parse(protocolRaw),base=resolve(ROOT,protocol.pilot_directory),
    inputRaw=readFileSync(resolve(base,'inputs.json.gz')),resultRaw=readFileSync(resolve(base,'results.json.gz')),
    bundle=JSON.parse(gunzipSync(inputRaw)),full=JSON.parse(gunzipSync(resultRaw));
  check(full.input_file_sha256===sha(inputRaw),'Archived input hash mismatch');
  const pilotReport=JSON.parse(readFileSync(resolve(base,'report.json')));
  check(pilotReport.input_file_sha256===sha(inputRaw)&&pilotReport.full_results_sha256===sha(resultRaw),'Published cohort hash mismatch');
  const marketRaw=execFileSync('git',['show',`${protocol.market_commit}:${protocol.market_path}`],{cwd:ROOT,maxBuffer:128*1024*1024});
  const report={...scorePilot(bundle,full,JSON.parse(marketRaw)),protocol,
    evidence:{protocol_sha256:sha(protocolRaw),pilot_inputs_sha256:sha(inputRaw),pilot_results_sha256:sha(resultRaw),
      market_sha256:sha(marketRaw),market_commit:protocol.market_commit,scorer_sha256:sha(readFileSync(fileURLToPath(import.meta.url)))}};
  const path=resolve(ROOT,output);mkdirSync(dirname(path),{recursive:true});
  writeFileSync(path,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.origins.map(o=>({cut:o.cut,maturity:o.maturity,scored:o.scored_stocks,metrics:o.metrics,gate:o.gate,portfolio_context:o.portfolio_context})),null,2));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main(...process.argv.slice(2));
