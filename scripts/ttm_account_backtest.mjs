/** Chronological economic diagnostic of reconstructed raw TTM ranks.
 * This adapter deliberately cannot claim to replay the live allocation model.
 */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {rawSignal} from './ttm_signal_replay.mjs';
import {totalReturnPrices,replayAccount,compareAccounts} from './account_replay.mjs';
import {MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..'),sha=bytes=>createHash('sha256').update(bytes).digest('hex');
export const ACCOUNT_PROTOCOL=Object.freeze({id:'reconstructed-ttm-account-v1',
 market_commit:'8dcd06cfd06b2ca34ca6fb64e31d5b6344525cd5',price_cut:'2026-10-28',
 initial_capital:100000,lead_sessions:2,positions:5,minimum_signals:30,equity_weight:.35,
 cash_yield:0,dividends:'provider-gross-total-return-reinvestment',
 costs:{commissionFixed:0,commissionBps:0,spreadBps:5,slippageBps:2,capitalGainsTax:0,minTrade:0},
 cost_multipliers:[1,3],block_months:12,bootstrap_draws:2000,seed:20261029});
export const ACCOUNT_IDS=['ttm_monthly','yield_monthly','ttm_initial_hold','index_monthly','index_initial_hold','cash'];

const alphabet=(a,b)=>a.symbol<b.symbol?-1:a.symbol>b.symbol?1:0;
function historicalAsset(a){
 // An allowlist prevents current financial quality, analyst estimates, dated
 // issuer profiles or benchmark holdings from entering this component test.
 return Object.fromEntries(['symbol','type','sector','assumptions','splits','history','distribution_index','price_adjustments','price_date']
  .filter(k=>a[k]!==undefined).map(k=>[k,a[k]]));
}

export function accountDecisions(market,facts,protocol=ACCOUNT_PROTOCOL){
 if(market.price_as_of!==facts.price_cut)throw Error('Mismatched frozen cut');
 const assets=new Map(market.assets.map(a=>[a.symbol,historicalAsset(a)])),benchmark=assets.get('SPY');
 if(!benchmark)throw Error('Missing benchmark calendar');
 const dates=benchmark.history.filter(r=>r.date<=market.price_as_of).map(r=>r.date),index=new Map(dates.map((d,i)=>[d,i]));
 if(index.size!==dates.length||dates.some((d,i)=>i&&d<=dates[i-1]))throw Error('Ambiguous benchmark calendar');
 const decisions=[],pending=[],exclusions={};let previous='';
 for(const input of facts.origins){
  if(input.origin<=previous||!index.has(input.origin))throw Error('Invalid reconstructed origin');
  previous=input.origin;
  const execute=dates[index.get(input.origin)+protocol.lead_sessions];
  if(!execute){pending.push({cut:input.origin,reason:'Second future session not observed'});continue;}
  const rows=[],seen=new Set(),reasons={};
  for(const fact of input.facts){
   if(seen.has(fact.symbol)||!assets.has(fact.symbol))throw Error('Ambiguous reconstructed constituent');seen.add(fact.symbol);
   const row=rawSignal(assets.get(fact.symbol),fact.eps,benchmark,input.origin);
   if(row.reason){reasons[row.reason]=(reasons[row.reason]||0)+1;exclusions[row.reason]=(exclusions[row.reason]||0)+1;continue;}
   rows.push({symbol:row.symbol,signal:row.signal,earnings_yield:row.earnings_yield,
    eps_filed:fact.eps.filed,eps_period_end:fact.eps.period_end});
  }
  const rank=key=>[...rows].sort((a,b)=>b[key]-a[key]||alphabet(a,b)).slice(0,protocol.positions),
   enough=rows.length>=protocol.minimum_signals&&rows.length>=protocol.positions,
   weights=selected=>Object.fromEntries([...selected.map(r=>[r.symbol,protocol.equity_weight/protocol.positions]),['CASH',1-protocol.equity_weight]]);
  decisions.push({cut:input.origin,execute,usable_signals:rows.length,excluded:reasons,
   ttm_target:enough?weights(rank('signal')):null,yield_target:enough?weights(rank('earnings_yield')):null,
   ttm_selection:enough?rank('signal'):[],yield_selection:enough?rank('earnings_yield'):[],
   scope:'Raw block valuation rank with current catalogue; no live CAPM/IC, optimizer, risk forecast or trade gate'});
 }
 if(!decisions.length)throw Error('No executable historical origins');
 return {dates:dates.filter(d=>d>=decisions[0].cut),decisions,pending,exclusions};
}

export function accountOrders(id,decisions,protocol=ACCOUNT_PROTOCOL){
 if(!ACCOUNT_IDS.includes(id))throw Error('Unknown account rule');
 let initialized=false;
 return decisions.map(d=>{
  let target=null,reason='hold-without-rebalancing';
  if(id==='cash')reason='unremunerated-cash';
  else if(id.startsWith('index')&&(!initialized||id==='index_monthly')){
   target={SPY:protocol.equity_weight,CASH:1-protocol.equity_weight};reason='predeclared-index-allocation';
  }else if(!initialized||id.endsWith('monthly')){
   target=id==='yield_monthly'?d.yield_target:d.ttm_target;
   reason=target?'predeclared-rank-allocation':'insufficient-signals-hold';
  }
  if(target)initialized=true;
  return {cut:d.cut,execute:d.execute,target,
   decision:{reason,usable_signals:d.usable_signals,
    selection:target&&!id.startsWith('index')?(id==='yield_monthly'?d.yield_selection:d.ttm_selection):[]}};
 });
}

export function runAccountBacktest(market,facts,{protocol=ACCOUNT_PROTOCOL,onProgress=()=>{}}={}){
 const schedule=accountDecisions(market,facts,protocol),prices=totalReturnPrices(market.assets),runs=[];
 for(const multiplier of protocol.cost_multipliers){
  const costs={...protocol.costs,spreadBps:protocol.costs.spreadBps*multiplier,slippageBps:protocol.costs.slippageBps*multiplier},accounts=[];
  for(const id of ACCOUNT_IDS){
   const account=replayAccount({id,dates:schedule.dates,prices,orders:accountOrders(id,schedule.decisions,protocol),
    initialCapital:protocol.initial_capital,costs});accounts.push(account);onProgress({multiplier,id,status:account.status});
  }
  const ttm=accounts.find(a=>a.id==='ttm_monthly'),comparisons=['yield_monthly','ttm_initial_hold','index_monthly']
   .map(id=>compareAccounts(ttm,accounts.find(a=>a.id===id),{block:protocol.block_months,draws:protocol.bootstrap_draws,seed:protocol.seed}));
  runs.push({cost_multiplier:multiplier,cost_assumptions:costs,accounts,comparisons});
 }
 return {schema_version:1,protocol,engine_reference_version:MODEL_VERSION,price_kernel_executed:false,
  price_cut:market.price_as_of,start:schedule.dates[0],end:schedule.dates.at(-1),
  scheduled_origins:schedule.decisions.length,pending_origins:schedule.pending,exclusions:schedule.exclusions,
  calendar:'Observed SPY sessions, not a certified original exchange calendar',large_reallocation_threshold:.1,
  upstream_ttm_exclusions:facts.exclusions,decisions:schedule.decisions,runs,
  production_eligible:false,automatic_promotion:false,prospective:false,
  historical_universe_verified:false,original_vintages_verified:false,economic_superiority:'not-established',
  full_model_replay:{status:'blocked',blockers:[
   'Historical benchmark holdings for the CAPM/IC refinement and ETF exposure',
   'Original historical bond and equity ETF valuation profiles',
   'Complete historical financial quality/confidence and macro vintages',
   'Corporate actions, execution prices and dividend pay-dates for a broker account'],
   not_executed:['Live robust optimizer and transition gate','Historical GJR reestimation','Full simulator risk distribution']},
  limitations:['Current surviving universe and catalogue selected after many outcomes',
   'Current provider-adjusted prices and reconstructed filings, not original vintages',
   'Inherited ex-post corporate-action exclusions from the TTM study',
   'Synthetic gross total-return units; not the app cash-dividend policy or broker fills',
   'Fixed 35% equity sleeve; uncalibrated absolute anchors and full mandate risk limits not tested',
   'Historical results already examined, no untouched temporal holdout or causal performance claim',
   'Pointwise exploratory intervals with few nonoverlapping annual blocks; no promotion test']};
}

export function accountBacktestSummary(report){
 const {decisions,runs,...meta}=report;
 return {...meta,runs:runs.map(run=>({...run,accounts:run.accounts.map(a=>{
  const {nav,transitions,final_units,observed_prefix,metrics,...row}=a,
   compact=m=>{if(!m)return null;const {complete_months,...rest}=m;return {...rest,complete_month_count:complete_months.length};};
  return {...row,metrics:compact(metrics),observed_prefix:row.status==='complete'?null:compact(observed_prefix),reviews:transitions.length,
   largest_transitions:transitions.filter(t=>!t.initial_allocation&&t.reallocation>1e-6).sort((a,b)=>b.reallocation-a.reallocation).slice(0,5)
    .map(({cut,execute,reallocation,entered,exited,cost})=>({cut,execute,reallocation,entered,exited,cost}))};
 })}))};
}

export function backtestSourceHashes(){
 const hashes={},visit=path=>{
  const relative=path.slice(ROOT.length+1);if(hashes[relative])return;
  const bytes=readFileSync(path);hashes[relative]=sha(bytes);
  for(const m of bytes.toString().matchAll(/\b(?:from|import)\s*['"]([^'"]+\.mjs)(?:\?[^'"]*)?['"]/g))
   if(m[1].startsWith('.'))visit(resolve(dirname(path),m[1]));
 };
 visit(fileURLToPath(import.meta.url));hashes['docs/protocolo-cuenta-historica-0.35.md']=sha(readFileSync(resolve(ROOT,'docs/protocolo-cuenta-historica-0.35.md')));
 return hashes;
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=(f,d)=>{const i=process.argv.indexOf(f);return i<0?d:process.argv[i+1];},
  marketPath=value('--market',null),marketBytes=marketPath?readFileSync(marketPath):execFileSync('git',
   ['show',ACCOUNT_PROTOCOL.market_commit+':dist/data/market.json'],{cwd:ROOT,maxBuffer:32*1024*1024}),
  factsPath=resolve(ROOT,'docs/auditorias/ttm-signal-inputs-2026-10-29.json.gz'),factsBytes=readFileSync(factsPath),
  facts=JSON.parse(gunzipSync(factsBytes));
 if(sha(marketBytes)!==facts.input_market_sha256)throw Error('Frozen market hash mismatch');
 const report=runAccountBacktest(JSON.parse(marketBytes),facts,{onProgress:p=>console.log(JSON.stringify(p))});
 report.input_hashes={market_sha256:sha(marketBytes),ttm_gzip_sha256:sha(factsBytes)};
 report.protocol_publication_commit='fb2b41405d0a9ce5a24c1fa8710507043356348a';
 report.source_hashes=backtestSourceHashes();report.runtime_node_version=process.version;
 report.result_sha256=sha(JSON.stringify({decisions:report.decisions,runs:report.runs}));
 const output=resolve(value('--output','out/ttm-account-backtest.json')),summary=resolve(value('--summary','out/ttm-account-summary.json'));
 for(const [path,data] of [[output,report],[summary,accountBacktestSummary(report)]]){
  mkdirSync(dirname(path),{recursive:true});writeFileSync(path,JSON.stringify(data,null,1)+'\n');
 }
 console.log(JSON.stringify({origins:report.scheduled_origins,result_sha256:report.result_sha256,production_eligible:false,summary}));
}
