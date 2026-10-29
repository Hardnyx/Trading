import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {gzipSync,gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {seededRandom,normalGenerator} from '../dist/assets/js/random.mjs?v=0.35.0';
import {prepareComposition} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {buildReturnAnchors,constituentForecasts} from '../dist/assets/js/return-model.mjs?v=0.35.0';
import {buildSignalForecast,signalEligibility,signalCohort,scoreSignalForecast,rankCorrelation,
 monthlySignalInterval,summarizeSignals,updateSignalLedger,SIGNAL_PROTOCOL} from '../scripts/signal_ledger.mjs';

const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} != ${b}`);
function sessions(start,n){const rows=[];let t=new Date(start+'T12:00:00Z');while(rows.length<n){
 if(![0,6].includes(t.getUTCDay()))rows.push(t.toISOString().slice(0,10));t.setUTCDate(t.getUTCDate()+1);
}return rows;}
function fixture(){
 const dates=sessions('2025-05-05',385),cut=dates.at(-1),stamp=cut+'T22:00:00Z',normal=normalGenerator(seededRandom(912)),
  market=dates.map(()=>normal()*.008),path=returns=>{let p=100;return dates.map((date,k)=>({date,close:p*=Math.exp(returns[k]),adj_close:p,volume:1e6}));},
  stocks=Array.from({length:30},(_,i)=>{const history=path(market.map(r=>r*(.5+i/30)+normal()*.008));
   return {symbol:'S'+i,type:'stock',name:'Stock '+i,sector:'Industrial',price:history.at(-1).close,price_date:cut,history,
    dividend_per_share:.5,assumptions:{growth:.03+i/1000,multiple:20,horizon:3,discount:.1},
    financials:{observed_at:stamp,eps:{value:3+i/10,filed:dates.at(-50),period_end:dates.at(-80),method:'TTM',components:[{filed:dates.at(-50),val:3+i/10}]}}};}),
  history=path(market),benchmark={symbol:'SPY',type:'etf',sector:'Índice amplio',price:history.at(-1).close,price_date:cut,history,
   holdings:{as_of:cut,observed_at:stamp,expense_ratio:.001,positions:stocks.map(a=>({symbol:a.symbol,weight:1/30}))}},
  snapshot={schema_version:1,price_as_of:cut,requested_as_of:cut,generated_at:stamp,
   macro:[{id:'DGS3MO',date:cut,value:4}],assets:[benchmark,...stocks]},
  volatility={schema_version:1,as_of:cut,source_market_generated_at:stamp,no_news_attribution:true,instruments:{}};
 return {snapshot,volatility,cut,issued:cut+'T23:00:00Z'};
}
function plainOrigin(){
 return {protocol:SIGNAL_PROTOCOL,cohort_id:'old',month:'2026-10',engine_version:'old-engine',price_kernel_version:'old-kernel',
  issued_at:'2026-10-23T23:00:00Z',issue_ny_date:'2026-10-23',input_price_as_of:'2026-10-23',benchmark:'SPY',risk_free:.04,
  publication:{verified:true,committed_at:'2026-10-24T00:00:00Z',first_commit:'fixture'},
  lead_sessions:2,horizons:[21,63,252],sealed_stocks:30,
  benchmark_forecast:{status:'sealed',annual_anchor:.06},
  rows:Array.from({length:30},(_,i)=>({symbol:'S'+i,status:'sealed',raw_signal:i/100,score:(i-15)/10,confidence:.6,
   earnings_yield:1/(i+10),annual_return_anchor:.05+i/1000,zero_ic_annual_anchor:.04,
   refinement:{rawBeta:1,beta:1,omega:.2,alpha:.01+i/1000,equilibrium:.04}}))};
}
function mature(origin=plainOrigin(),n=23){
 const days=sessions('2026-10-26',n),assets=[{symbol:'SPY',history:days.map((date,k)=>({date,adj_close:100*Math.exp(.0001*k)}))},
  ...origin.rows.filter(r=>r.status==='sealed').map(r=>({symbol:r.symbol,history:days.map((date,k)=>({date,
   adj_close:100*Math.exp(Math.log1p(r.annual_return_anchor)*(k-1)/252)}))}))];
 return {price_as_of:days.at(-1),assets};
}
test('the seal stores all stocks and the exact production score, confidence and bounded anchor without optimization',()=>{
 const {snapshot,volatility,issued}=fixture(),before=JSON.stringify(snapshot),f=buildSignalForecast(snapshot,volatility,issued),
  req=referenceRequest({...snapshot,volatility}),x=prepareComposition(snapshot,req.settings,{},req.rules),
  universe=x.anchorUniverse||snapshot.assets,lookup=constituentForecasts(universe,x.options,{}),
  stocks=snapshot.assets.filter(a=>a.type==='stock'),anchors=buildReturnAnchors(stocks,x.options,{},universe),
  zero=buildReturnAnchors(stocks,{...x.options,informationCoefficient:0},{},universe);
 assert.equal(f.rows.length,30);assert.equal(f.sealed_stocks,30);
 for(const r of f.rows){assert.deepEqual(r.refinement,lookup(r.symbol).refinement);near(r.confidence,lookup(r.symbol).confidence);
  near(r.raw_signal,lookup(r.symbol).model.annualReturn);near(r.annual_return_anchor,anchors.find(a=>a.symbol===r.symbol).annual);
  near(r.zero_ic_annual_anchor,zero.find(a=>a.symbol===r.symbol).annual);}
 near(f.benchmark_forecast.annual_anchor,x.anchors.find(a=>a.symbol==='SPY').annual);
 assert.equal(JSON.stringify(snapshot),before);assert.equal(f.automatic_promotion,false);
});
test('sealing rejects a future observation, pre-close capture and a stale two-session window',()=>{
 const {snapshot,issued,cut}=fixture();assert.throws(()=>signalEligibility(snapshot,cut+'T12:00:00Z'),/Ineligible/);
 assert.throws(()=>signalEligibility(snapshot,'2026-12-31T23:00:00Z'),/window/);
 snapshot.assets[1].financials.observed_at='2027-01-01T00:00:00Z';
 assert.throws(()=>signalEligibility(snapshot,issued),/observed after/);
});
test('a cohort binds code content independently of hash-map insertion order',()=>{
 assert.equal(signalCohort({a:'1',b:'2'}),signalCohort({b:'2',a:'1'}));
 assert.notEqual(signalCohort({a:'1'}),signalCohort({a:'2'}));
});
test('scores wait for the exact future interval and compare the same stocks with the simple reference',()=>{
 const origin=plainOrigin();assert.equal(scoreSignalForecast(origin,mature(origin,22),21),null);
 const s=scoreSignalForecast(origin,mature(),21);
 assert.equal(s.origin_date,'2026-10-27');assert.equal(s.maturity_date,'2026-11-25');assert.equal(s.scored_stocks,30);
 near(s.metrics.raw_rank_ic,1);near(s.metrics.yield_rank_ic,-1);near(s.metrics.paired_rank_ic_gain,2);
 for(const r of s.rows)near(r.anchor_error,0);
 assert.ok(s.metrics.paired_mae_gain_vs_equilibrium>0);
 near(s.benchmark_metrics.anchor_error,s.benchmark_metrics.realized_total_return-s.benchmark_metrics.forecast);
});
test('missing or delisted assets remain in the denominator and cannot shift the origin or maturity',()=>{
 const origin=plainOrigin(),m=mature(origin,24);m.assets=m.assets.filter(a=>a.symbol!=='S0');
 const s=scoreSignalForecast(origin,m,21);assert.equal(s.missing_outcomes,1);assert.equal(s.expected_stocks,30);
 assert.equal(s.diagnostic_status,'insufficient-cross-section');assert.deepEqual(s.metrics,{});
 assert.equal(s.rows.find(r=>r.symbol==='S0').asset_present,false);assert.equal(s.maturity_date,'2026-11-25');
});
test('an unavailable forecast is never filled after its outcome is known',()=>{
 const origin=plainOrigin();origin.rows.push({symbol:'LATE',status:'unavailable-at-issue',reason:'No EPS'});
 const m=mature();m.assets.push({symbol:'LATE',history:m.assets[1].history});
 assert.equal(scoreSignalForecast(origin,m,21).rows.find(r=>r.symbol==='LATE').status,'unavailable-at-issue');
});
test('nonfinite recorded predictors and duplicate benchmark sessions cannot become successful scores',()=>{
 const origin=plainOrigin();origin.rows[0].zero_ic_annual_anchor=null;
 assert.throws(()=>scoreSignalForecast(origin,mature(),21),/Invalid sealed predictors/);
 const m=mature();m.assets[0].history.push({...m.assets[0].history[1]});
 assert.throws(()=>scoreSignalForecast(plainOrigin(),m,21),/session index/);
});
test('a return that began before publication is excluded rather than moved to a more convenient entry',()=>{
 const origin={...plainOrigin(),issue_ny_date:'2026-10-27'};
 const s=scoreSignalForecast(origin,mature(),21);assert.equal(s.status,'nonprospective');assert.equal(s.origin_date,'2026-10-27');
 const summary=summarizeSignals([origin],[s],'old','2026-12-01T23:00:00Z');
 assert.equal(summary.cohorts.old.horizons[21].mature_origins,0);assert.equal(summary.cohorts.old.horizons[21].excluded_nonprospective,1);
});
test('a backdated claim cannot bypass a later first publication, and unverifiable history is not scored',()=>{
 const origin=plainOrigin();origin.publication={verified:true,committed_at:'2026-10-28T23:00:00Z'};
 assert.equal(scoreSignalForecast(origin,mature(),21).status,'nonprospective');
 delete origin.publication;assert.equal(scoreSignalForecast(origin,mature(),21).status,'unverified-publication');
});
test('monthly intervals need enough consecutive time blocks and rank ties are retained',()=>{
 near(rankCorrelation([1,1,2,3],[1,1,2,3]),1);assert.equal(rankCorrelation([1,1,1],[1,2,3]),null);
 assert.equal(monthlySignalInterval(Array(19).fill(.1),Array.from({length:19},(_,i)=>i),1),null);
 assert.equal(monthlySignalInterval(Array(20).fill(.1),Array.from({length:20},(_,i)=>i),12),null);
 const months=Array.from({length:48},(_,i)=>i);for(const x of monthlySignalInterval(Array(48).fill(.1),months,12,20))near(x,.1);
 months[47]++;assert.equal(monthlySignalInterval(Array(48).fill(.1),months,12),null);
});
test('different source cohorts never pool evidence and overlapping origins remain visible',()=>{
 const origin=plainOrigin(),s=scoreSignalForecast(origin,mature(),21),next={...s,origin_date:'2026-10-28',maturity_date:'2026-11-26'},
  other={...origin,cohort_id:'new'},summary=summarizeSignals([origin,other],[s,next,{...s,cohort_id:'new'}],'new','2026-12-01T23:00:00Z');
 assert.equal(summary.cohorts.old.horizons[21].mature_origins,2);assert.equal(summary.cohorts.old.horizons[21].nonoverlapping_origins,1);
 assert.equal(summary.cohorts.new.horizons[21].mature_origins,1);assert.equal(summary.predictive_validation,'not-established');
 assert.equal(summary.automatic_promotion,false);
});
function save(root,snapshot,volatility){mkdirSync(resolve(root,'dist/data'),{recursive:true});
 writeFileSync(resolve(root,'dist/data/market.json'),JSON.stringify(snapshot));writeFileSync(resolve(root,'dist/data/volatility.json'),JSON.stringify(volatility));}
test('a source revision cannot replace the first monthly seal or its archived input',()=>{
 const root=mkdtempSync(resolve(tmpdir(),'signal-month-'));try{
  const {snapshot,volatility,issued}=fixture();save(root,snapshot,volatility);updateSignalLedger({root,issuedAt:issued});
  const dir=resolve(root,'data/signal-validation/forecasts'),path=resolve(dir,readdirSync(dir)[0]),first=readFileSync(path),origin=JSON.parse(gunzipSync(first)),
   archive=readFileSync(resolve(root,'data/signal-validation',origin.input_archive));
  snapshot.assets[1].financials.eps.value=999;save(root,snapshot,volatility);updateSignalLedger({root,issuedAt:issued});
  assert.deepEqual(readFileSync(path),first);assert.deepEqual(readFileSync(resolve(root,'data/signal-validation',origin.input_archive)),archive);
  assert.equal(readdirSync(dir).length,1);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('archive corruption and scoring with a future capture fail closed',()=>{
 const root=mkdtempSync(resolve(tmpdir(),'signal-integrity-'));try{
  const {snapshot,volatility,issued}=fixture();save(root,snapshot,volatility);
  assert.throws(()=>updateSignalLedger({root,issuedAt:snapshot.price_as_of+'T20:00:00Z'}),/scoring time/);
  updateSignalLedger({root,issuedAt:issued});
  const path=resolve(root,'data/signal-validation/forecasts',readdirSync(resolve(root,'data/signal-validation/forecasts'))[0]),
   origin=JSON.parse(gunzipSync(readFileSync(path)));
  writeFileSync(resolve(root,'data/signal-validation',origin.input_archive),gzipSync('{}'));
  assert.throws(()=>updateSignalLedger({root,issuedAt:issued}),/integrity/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
test('the first mature score is frozen, and a changed sealed forecast cannot reuse that score',()=>{
 const root=mkdtempSync(resolve(tmpdir(),'signal-score-'));try{
  const {snapshot,volatility,issued}=fixture();save(root,snapshot,volatility);updateSignalLedger({root,issuedAt:issued});
  const git=args=>execFileSync('git',args,{cwd:root,stdio:['ignore','pipe','pipe'],env:{...process.env,GIT_AUTHOR_DATE:issued,GIT_COMMITTER_DATE:issued}});
  git(['init','-q']);git(['add','data/signal-validation']);
  git(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Synthetic publication fixture']);
  const dir=resolve(root,'data/signal-validation/forecasts'),file=resolve(dir,readdirSync(dir)[0]),
   origin=JSON.parse(gunzipSync(readFileSync(file))),days=sessions('2026-10-26',23);
  // Monthly fixture ends on 23-Oct. Add realized endpoints without rebuilding
  // any of the recorded predictors or their original accounting data.
  assert.equal(origin.input_price_as_of,'2026-10-23');
  for(const a of snapshot.assets){const anchor=origin.rows.find(r=>r.symbol===a.symbol)?.annual_return_anchor??.06;
   a.history.push(...days.map((date,k)=>({date,close:100*Math.exp(Math.log1p(anchor)*(k-1)/252),adj_close:100*Math.exp(Math.log1p(anchor)*(k-1)/252),volume:1e6})));
   a.price_date=days.at(-1);a.price=a.history.at(-1).close;}
  snapshot.price_as_of=snapshot.requested_as_of=days.at(-1);snapshot.generated_at=days.at(-1)+'T22:00:00Z';
  volatility.as_of=snapshot.price_as_of;volatility.source_market_generated_at=snapshot.generated_at;
  save(root,snapshot,volatility);updateSignalLedger({root,issuedAt:days.at(-1)+'T23:00:00Z'});
  const score=resolve(root,'data/signal-validation/scores/2026-10.h21.json.gz'),first=readFileSync(score);
  snapshot.assets[1].history.at(-1).adj_close*=2;save(root,snapshot,volatility);
  updateSignalLedger({root,issuedAt:days.at(-1)+'T23:10:00Z'});assert.deepEqual(readFileSync(score),first);
  origin.rows[0].annual_return_anchor=.99;writeFileSync(file,gzipSync(JSON.stringify(origin)));
  assert.throws(()=>updateSignalLedger({root,issuedAt:days.at(-1)+'T23:20:00Z'}),/changed after scoring/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
