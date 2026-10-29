import test from 'node:test';
import assert from 'node:assert/strict';
import {rawSignal,trailingDividends,replay} from '../scripts/ttm_signal_replay.mjs';
import {fundamentalForecast} from '../dist/assets/js/research-model.mjs?v=0.35.0';

function fixture(){
 const origin='2024-12-31',history=Array.from({length:800},(_,i)=>({date:new Date(Date.UTC(2022,10,1+i)).toISOString().slice(0,10),
  close:100*Math.exp(.0002*i+.03*Math.sin(i)),adj_close:100*Math.exp(.0002*i+.03*Math.sin(i))})),
  benchmark={symbol:'SPY',history:history.map((r,i)=>({...r,adj_close:100*Math.exp(.0001*i+.01*Math.sin(i+1))}))},
  asset={symbol:'AAA',type:'stock',assumptions:{growth:.06,multiple:20,horizon:3,discount:.1},history,splits:[],
   distribution_index:{complete_ex_date_index:true,currency:'USD',coverage_start:'2022-11-01',coverage_end:'2025-01-08',records:[
    {ex_date:'2024-03-01',amount_per_share:.5},{ex_date:'2024-11-01',amount_per_share:.5},{ex_date:'2025-01-02',amount_per_share:100}]}},
  eps={value:5,period_end:'2024-09-30',filed:'2024-11-01',method:'TTM',components:[{filed:'2024-11-01',val:5}]};
 return {origin,benchmark,asset,eps};
}
test('the reconstructed signal equals the current fundamental model valuation on those inputs',()=>{
 const {asset,eps,origin,benchmark}=fixture(),result=rawSignal(asset,eps,benchmark,origin),
  at={...asset,price_date:origin,price:asset.history.find(r=>r.date===origin).close,dividend_per_share:1,financials:{eps}},
  actual=fundamentalForecast(at,{}, {},{asOf:origin,priceAsOf:origin});
 assert.ok(actual.valid);assert.equal(result.signal,actual.model.annualReturn);assert.equal(result.trailing_dividends,1);
});
test('future prices and dividends cannot change the signal or exposure at an old origin',()=>{
 const {asset,eps,origin,benchmark}=fixture(),before=rawSignal(asset,eps,benchmark,origin),changed=structuredClone(asset);
 for(const r of changed.history)if(r.date>origin)r.adj_close=r.close=99999;
 changed.distribution_index.records.at(-1).amount_per_share=99999;
 assert.deepEqual(rawSignal(changed,eps,benchmark,origin),before);
 assert.equal(rawSignal(asset,{...eps,filed:origin},benchmark,origin).reason,'unavailable_ttm');
});
test('missing dividend history stays unavailable, while a covered empty index means zero',()=>{
 const {asset,origin}=fixture();delete asset.distribution_index;assert.equal(trailingDividends(asset,origin),null);
 asset.distribution_index={complete_ex_date_index:true,currency:'USD',coverage_start:'2023-01-01',coverage_end:origin,records:[]};
 assert.equal(trailingDividends(asset,origin),0);asset.distribution_index.coverage_start='2024-02-01';assert.equal(trailingDividends(asset,origin),null);
});
test('a future non-share price adjustment cannot be treated as an ordinary split',()=>{
 const {asset,eps,origin,benchmark}=fixture();asset.price_adjustments=[{date:'2025-01-02',ratio:1.2}];
 assert.equal(rawSignal(asset,eps,benchmark,origin).reason,'unreconciled_future_price_adjustment');
});
test('outcomes are separate from signal construction and require the frozen price cut',()=>{
 const {asset,benchmark,eps,origin}=fixture(),market={price_as_of:'2025-01-08',assets:[asset,benchmark]},
  facts={price_cut:'2025-01-08',origins:[{origin,outcomes:{'21':'2025-01-07'},facts:[{symbol:'AAA',eps}]}],exclusions:{},input_market_sha256:'x'};
 assert.throws(()=>replay({...market,price_as_of:'2025-01-09'},facts),/cut/);
 // One signal is insufficient for a transversal score, never an IC sample.
 assert.equal(replay(market,facts).origins.length,0);
});
