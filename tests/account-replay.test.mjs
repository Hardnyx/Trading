import test from 'node:test';
import assert from 'node:assert/strict';
import {replayAccount,totalReturnPrices,validateTarget,compareAccounts,accountMetrics} from '../scripts/account_replay.mjs';

const zero={spreadBps:0,slippageBps:0,commissionBps:0,commissionFixed:0};
const dates=['2024-01-02','2024-01-03','2024-01-04','2024-01-05'];
const prices=(a=[100,100,110,120])=>new Map([['A',new Map(dates.map((d,i)=>[d,a[i]]))]]);
const buy={cut:dates[0],execute:dates[1],target:{A:.5,CASH:.5}};
const run=overrides=>replayAccount({id:'test',dates,prices:prices(),orders:[buy],initialCapital:1000,costs:zero,...overrides});

test('a held account carries its original units and cash, without resetting capital each review',()=>{
 const a=run({orders:[buy,{cut:dates[2],execute:dates[3],target:null}]});
 assert.equal(a.status,'complete');assert.equal(a.final_units.A,5);assert.equal(a.final_cash,500);
 assert.equal(a.metrics.ending_nav,1100);assert.equal(a.transitions[1].before_nav,1100);
 assert.equal(a.trade_count,1);assert.equal(a.transitions[1].cost,0);
 assert.ok(Math.abs(a.final_weights.A-600/1100)<1e-12);
 assert.ok(Math.abs(a.metrics.final_noncash_exposure-600/1100)<1e-12);
});

test('costs are funded by the account, including both legs of a change and no closing liquidation',()=>{
 const a=run({costs:{...zero,spreadBps:20},orders:[buy,{cut:dates[2],execute:dates[3],target:{CASH:1}}]});
 const net=1000/(1+.5*.001),units=.5*net/100,terminal=.5*net+units*120*(1-.001);
 assert.ok(Math.abs(a.metrics.ending_nav-terminal)<1e-6);
 assert.ok(Math.abs(a.transitions[0].before_nav-a.transitions[0].cost-a.transitions[0].after_nav)<1e-6);
 assert.equal(a.trade_count,2);assert.equal(a.transitions[0].trades[0].side,'buy');
 assert.equal(a.transitions[1].trades[0].side,'sell');assert.equal(a.final_units.A,undefined);
});

test('a missing held outcome invalidates the full account, rather than filling zero or selling before disappearance',()=>{
 const p=prices();p.get('A').delete(dates[2]);const a=run({prices:p});
 assert.equal(a.status,'incomplete');assert.equal(a.metrics,null);
 assert.equal(a.observed_through,dates[1]);assert.equal(a.issues[0].date,dates[2]);
 assert.equal(a.trade_count,1);assert.equal(a.final_units.A,5);
 assert.equal(compareAccounts(a,run()).status,'incomplete-account');
});

test('a missing execution price cannot postpone the trade to a favorable later date',()=>{
 const p=prices();p.get('A').delete(dates[1]);const a=run({prices:p});
 assert.equal(a.status,'incomplete');assert.equal(a.transitions.length,0);
 assert.equal(a.final_cash,1000);assert.equal(a.observed_through,dates[0]);
});

test('orders require a past cutoff and unique ordered original execution dates',()=>{
 assert.throws(()=>run({orders:[{...buy,execute:buy.cut}]}),/Noncausal/);
 assert.throws(()=>run({orders:[buy,buy]}),/unordered/);
 assert.throws(()=>run({orders:[{...buy,execute:'2024-01-06'}]}),/Noncausal/);
 assert.throws(()=>run({dates:[dates[0],dates[0]]}),/calendar/);
});

test('total-return units do not receive a second dividend or raw-price split adjustment',()=>{
 const history=dates.map((date,i)=>({date,adj_close:[100,100,105,110][i],close:i<2?100:50,dividend:1000}));
 const a=run({prices:totalReturnPrices([{symbol:'A',history}])});
 assert.equal(a.final_cash,500);assert.equal(a.metrics.ending_nav,1050);
 assert.throws(()=>totalReturnPrices([{symbol:'A',history:[history[0],history[0]]}]),/Ambiguous/);
});

test('future outcomes cannot change already executed account history',()=>{
 const a=run(),p=prices();p.get('A').set(dates[3],1);const b=run({prices:p});
 assert.deepEqual(a.nav.slice(0,3),b.nav.slice(0,3));assert.deepEqual(a.transitions,b.transitions);
 assert.notEqual(a.metrics.ending_nav,b.metrics.ending_nav);
});

test('invalid targets and uncertified taxable accounting are rejected explicitly',()=>{
 for(const w of [{A:1,CASH:-.1},{A:NaN},{A:.2},{A:Infinity},[]])assert.throws(()=>validateTarget(w),/Invalid target/);
 assert.throws(()=>run({costs:{capitalGainsTax:.1}}),/taxable/);
});

test('drawdown includes costs and complete-month comparisons exclude partial endpoints',()=>{
 const rows=[{date:'2023-12-29',nav:1000},{date:'2024-01-02',nav:900},{date:'2024-01-31',nav:950},
  {date:'2024-02-01',nav:970},{date:'2024-02-29',nav:1000},{date:'2024-03-01',nav:1050}];
 const m=accountMetrics(rows,1000);assert.ok(Math.abs(m.max_drawdown-.1)<1e-12);
 assert.deepEqual(m.complete_months.map(r=>r.month),['2024-01','2024-02']);
 assert.ok(Math.abs(m.complete_months[1].return-(1000/950-1))<1e-12);
});

test('paired intervals count calendar months, refuse gaps, and remain descriptive on positive returns',()=>{
 const months=Array.from({length:30},(_,i)=>({month:`${2022+Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}`,log_return:.01,return:Math.expm1(.01)}));
 const a={id:'a',status:'complete',metrics:{ending_nav:1200,complete_months:months}},
  b={id:'b',status:'complete',metrics:{ending_nav:1000,complete_months:months.map(r=>({...r,log_return:0,return:0}))}};
 const c=compareAccounts(a,b);assert.equal(c.complete_months,30);assert.equal(c.nonoverlapping_annual_blocks,2);
 assert.equal(c.formal_test,false);assert.equal(c.superiority,'not-established');assert.ok(c.moving_block_95[0]>0);
 const short=structuredClone(a);short.metrics.complete_months.pop();assert.equal(compareAccounts(short,b).status,'unmatched-months');
 for(const x of [a,b])x.metrics.complete_months.splice(10,1);
 assert.equal(compareAccounts(a,b).moving_block_95,null);
});
