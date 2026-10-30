import test from 'node:test';
import assert from 'node:assert/strict';
import {accountDecisions,accountOrders,runAccountBacktest,ACCOUNT_PROTOCOL} from '../scripts/ttm_account_backtest.mjs';

function fixture(){
 const history=Array.from({length:460},(_,i)=>({date:new Date(Date.UTC(2023,0,1+i)).toISOString().slice(0,10),
  close:100*Math.exp(.0001*i+.01*Math.sin(i+1)),adj_close:100*Math.exp(.0001*i+.01*Math.sin(i+1))})),
  cut=history.at(-1).date,origin=history[420].date,second=history[449].date,
  distribution_index={complete_ex_date_index:true,currency:'USD',coverage_start:history[0].date,coverage_end:cut,records:[]},
  benchmark={symbol:'SPY',type:'etf',history},assets=[benchmark],facts=[];
 for(let i=0;i<35;i++){
  const symbol='A'+String(i).padStart(2,'0');
  assets.push({symbol,type:'stock',sector:'Technology',history:history.map((r,k)=>({...r,
   adj_close:r.adj_close*Math.exp(.001*Math.sin(k+i)),close:r.close*Math.exp(.001*Math.sin(k+i))})),
   price_date:cut,splits:[],distribution_index,
   assumptions:{growth:.04+i*.001,multiple:20,horizon:3,discount:.1}});
  facts.push({symbol,eps:{value:4+i*.05,period_end:'2023-09-30',filed:'2023-11-01',method:'TTM'}});
 }
 return {market:{price_as_of:cut,assets},facts:{price_cut:cut,exclusions:{},origins:[
  {origin,facts,outcomes:{'21':second}},{origin:second,facts,outcomes:{}}]}};
}

test('historical decisions isolate future prices, outcomes, dividends and current financial metadata',()=>{
 const {market,facts}=fixture(),before=accountDecisions(market,facts),m=structuredClone(market),f=structuredClone(facts),cut=f.origins[0].origin;
 for(const asset of m.assets){
  asset.financials={eps:{value:100000,filed:'2024-05-01'}};asset.analyst_estimates={eps:99999};
  for(const row of asset.history)if(row.date>cut)row.close=row.adj_close=999999;
  if(asset.distribution_index)asset.distribution_index.records.push({ex_date:m.price_as_of,amount_per_share:9999});
 }
 f.origins[0].outcomes={'21':'2099-01-01'};
 assert.deepEqual(accountDecisions(m,f).decisions[0],before.decisions[0]);
 assert.equal(before.decisions[0].execute,market.assets[0].history[422].date);
 assert.equal(before.decisions[0].usable_signals,35);
});

test('paired ranking references use the same sample and deterministic tie ordering',()=>{
 const {market,facts}=fixture(),a=accountDecisions(market,facts),m=structuredClone(market),f=structuredClone(facts);
 m.assets.reverse();for(const x of f.origins)x.facts.reverse();
 assert.deepEqual(accountDecisions(m,f).decisions,a.decisions);
 for(const d of a.decisions){assert.equal(d.ttm_selection.length,5);assert.equal(d.yield_selection.length,5);
  assert.equal(d.ttm_target.CASH,.65);assert.ok(d.ttm_selection.every(r=>r.eps_filed<d.cut));}
});

test('insufficient original signals mean hold, and an unobserved fill stays pending',()=>{
 const {market,facts}=fixture();for(const origin of facts.origins)origin.facts=origin.facts.slice(0,4);
 facts.origins.push({origin:market.price_as_of,facts:[]});
 const s=accountDecisions(market,facts);assert.equal(s.decisions[0].ttm_target,null);assert.equal(s.pending.length,1);
 const orders=accountOrders('ttm_monthly',s.decisions);assert.equal(orders[0].target,null);
 assert.equal(orders[0].decision.reason,'insufficient-signals-hold');
});

test('initial-hold and monthly rules diverge only after a first actual allocation',()=>{
 const {market,facts}=fixture(),s=accountDecisions(market,facts),hold=accountOrders('ttm_initial_hold',s.decisions),
  monthly=accountOrders('ttm_monthly',s.decisions);
 assert.deepEqual(hold[0].target,monthly[0].target);assert.equal(hold[1].target,null);assert.ok(monthly[1].target);
});

test('the full run preserves inputs, reports all predeclared accounts and never promotes the component result',()=>{
 const {market,facts}=fixture(),before=JSON.stringify({market,facts}),r=runAccountBacktest(market,facts,
  {protocol:{...ACCOUNT_PROTOCOL,bootstrap_draws:50}});
 assert.equal(JSON.stringify({market,facts}),before);assert.equal(r.runs.length,2);
 for(const run of r.runs){assert.equal(run.accounts.length,6);assert.ok(run.accounts.every(a=>a.status==='complete'));
  assert.equal(run.comparisons.length,3);assert.ok(run.comparisons.every(c=>c.superiority==='not-established'));}
 assert.equal(r.production_eligible,false);assert.equal(r.prospective,false);
 assert.equal(r.full_model_replay.status,'blocked');assert.equal(r.economic_superiority,'not-established');
 const base=r.runs[0].accounts.find(a=>a.id==='ttm_monthly'),stress=r.runs[1].accounts.find(a=>a.id==='ttm_monthly');
 assert.ok(base.metrics.ending_nav>stress.metrics.ending_nav);
});
