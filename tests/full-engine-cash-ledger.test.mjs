import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyAccountInputs,replayCashAccount} from '../scripts/full_engine_cash_ledger.mjs';

const days=['2026-11-30','2026-12-01','2026-12-02','2026-12-03','2026-12-04','2026-12-07'];
const stamp='2026-11-30T23:00:00Z',published='2026-12-01T00:00:00Z';
const first={cut:days[0],execute:days[1],issued_at:stamp,
  publication:{verified:true,first_commit:'a'.repeat(40),committed_at:published},
  forecast_sha256:'b'.repeat(64),model_status:'proposed',
  positions:[{symbol:'AAA',weight:.5},{symbol:'CASH',weight:.5}]};
const index=(events=[],end=days.at(-1))=>({
  complete:true,currency:'USD',coverage_start:days[0],coverage_end:end,events});
const assets=(aaa=[100,100,99,49.5,50,51])=>[
 {symbol:'SPY',currency:'USD',history:days.map((date,i)=>({date,close:100+i})),
  distributions:index()},
 {symbol:'AAA',currency:'USD',history:days.map((date,i)=>({date,close:aaa[i]})),
  distributions:index([{kind:'dividend',ex_date:days[2],pay_date:days[4],amount_per_share:2}]),
  splits:[{date:days[3],ratio:2}]},
];
const zero={commissionFixed:0,commissionBps:0,spreadBps:0,
  slippageBps:0,capitalGainsTax:0,maxTurnover:1,minTrade:0};
const run=opts=>replayCashAccount({
  calendar:days,assets:assets(),decisions:[first],initialCapital:1000,
  costs:zero,mandate:{referenceCurrency:'USD',cashYield:0,
    dividendPolicy:'cash',dividendWithholding:0},...opts});

test('cash book acquires at first next close, not same-cut closing price',()=>{
 const r=run();
 assert.equal(r.status,'complete');
 assert.equal(r.decisions.length,1);
 assert.equal(r.decisions[0].cut,'2026-11-30');
 assert.equal(r.decisions[0].execute,'2026-12-01');
 assert.equal(r.nav[0].nav,1000);
 assert.equal(r.nav[1].holdings[0].quantity,5);
 assert.equal(r.nav[1].cash,500);
 assert.equal(r.nav[1].receivables,0);
 assert.equal(r.decisions[0].shadow_trade_count,1);
});
test('dividend entitlement, payment date and split preserve double-entry NAV',()=>{
 const r=run();
 assert.equal(r.status,'complete',JSON.stringify(r.issues));
 assert.equal(r.nav[2].receivables,10);
 assert.equal(r.nav[2].cash,500);
 assert.equal(r.nav[2].nav,1005);
 assert.equal(r.nav[3].holdings[0].quantity,10);
 assert.equal(r.nav[3].receivables,10);
 assert.equal(r.nav[3].nav,1005);
 assert.equal(r.nav[4].receivables,0);
 assert.equal(r.nav[4].cash,510);
 assert.equal(r.nav[4].holdings[0].quantity,10);
 assert.equal(r.nav[4].nav,1010);
 assert.equal(r.nav[5].nav,1020);
 assert.ok(r.nav.every(row=>Math.abs(row.identity_residual)<1e-6));
 assert.equal(r.journal.filter(e=>e.type==='dividend-receivable').length,1);
 assert.equal(r.journal.filter(e=>e.type==='dividend-payment').length,1);
});
test('withholding reduces NAV at pay date, not ex date',()=>{
 const r=run({mandate:{referenceCurrency:'USD',cashYield:0,
   dividendPolicy:'cash',dividendWithholding:.3}});
 assert.equal(r.status,'complete');
 assert.equal(r.nav[2].nav,1005);
 assert.equal(r.nav[4].cash,507);
 assert.equal(r.nav[4].withheld_taxes,3);
 assert.equal(r.nav[4].nav,1007);
});
test('execution spread and slippage debit settled account, without negative cash',()=>{
 const r=run({costs:{...zero,spreadBps:20,slippageBps:10}});
 assert.equal(r.status,'complete',JSON.stringify(r.issues));
 const d=r.decisions[0];
 assert.ok(d.trading_cost>0);
 assert.ok(d.after_nav<d.before_nav);
 assert.ok(Math.abs(d.after_nav-(d.before_nav-d.trading_cost))<1e-6);
 assert.ok(r.nav.every(x=>x.cash>=0&&Math.abs(x.identity_residual)<1e-6));
});
test('future outcomes cannot change the earlier journal or executed quantities',()=>{
 const a=run(),altered=assets();
 altered[1].history.at(-1).close=500;
 const b=run({assets:altered});
 assert.equal(b.status,'complete');
 assert.deepEqual(a.nav.slice(0,-1),b.nav.slice(0,-1));
 assert.deepEqual(a.decisions,b.decisions);
 assert.notEqual(a.nav.at(-1).nav,b.nav.at(-1).nav);
});
test('missing raw close leaves incomplete ledger without forward-filling',()=>{
 const changed=assets();
 changed[1].history=changed[1].history.filter(p=>p.date!==days[3]);
 const result=run({assets:changed});
 assert.equal(result.status,'incomplete');
 assert.equal(result.observed_through,days[2]);
 assert.equal(result.blocked_on,days[3]);
 assert.match(result.issues[0].reason,/Missing observed raw close/);
});
test('missing dividend source coverage leaves incomplete ledger and no fabricated zero income',()=>{
 const changed=assets();
 changed[1].distributions=index([],days[2]);
 const r=run({assets:changed});
 assert.equal(r.status,'incomplete');
 assert.equal(r.blocked_on,days[3]);
 assert.match(r.issues[0].reason,/dividend coverage/);
});
test('the next execution cannot move forward to fix absent price or late publication',()=>{
 assert.throws(()=>run({decisions:[{...first,execute:days[2]}]}),/FIRST observed session/);
 assert.throws(()=>run({decisions:[{...first,publication:{...first.publication,
  committed_at:'2026-12-01T15:00:00Z'}}]}),/after next-session opening/);
});
test('no synthetic interest, unfiled withdrawal, FX or futures in a cash-only cohort',()=>{
 for(const mandate of [
  {cashYield:.01},{monthlyWithdrawal:10},{referenceCurrency:'PEN'},
  {dividendPolicy:'reinvest'}
 ])assert.throws(()=>run({mandate}),/inferred|requires|scheduled|conversion|Reinvestment/i);
 const base=run({decisions:[{...first,positions:[{symbol:'CASH',weight:1}]}]});
 assert.equal(base.status,'complete');
 assert.ok(base.nav.every(x=>x.nav===1000));
 assert.equal(base.account_outcome_validated,false);
});
test('deposits and withdrawals are recorded externally with exact source references',()=>{
 const flows=[
  {date:days[2],kind:'deposit',amount:100,source_sha256:'f'.repeat(64)},
  {date:days[4],kind:'withdrawal',amount:40,source_sha256:'e'.repeat(64)},
  {date:days[4],kind:'interest',amount:1,source_sha256:'c'.repeat(64)},
 ];
 const r=run({flows});
 assert.equal(r.status,'complete');
 assert.equal(r.nav[2].external_cash_flow,100);
 assert.equal(r.nav[4].external_cash_flow,-40);
 assert.equal(r.nav[4].realized_cash_interest,1);
 assert.ok(r.nav.every(row=>Math.abs(row.identity_residual)<1e-6));
 assert.equal(r.nav.at(-1).nav,1081);
 assert.throws(()=>run({flows:[{date:days[2],kind:'interest',amount:1}]}),/unsourced/);
});
test('sells, exits and later decisions use actual held units rather than resetting capital',()=>{
 const second={...first,cut:days[3],execute:days[4],
  forecast_sha256:'c'.repeat(64),issued_at:'2026-12-03T22:00:00Z',
  publication:{verified:true,first_commit:'d'.repeat(40),committed_at:'2026-12-03T23:00:00Z'},
  positions:[{symbol:'CASH',weight:1}]};
 const r=run({decisions:[first,second]});
 assert.equal(r.status,'complete',JSON.stringify(r.issues));
 assert.equal(r.decisions.length,2);
 assert.deepEqual(r.final_units,{});
 assert.equal(r.nav[4].cash,r.nav[4].nav);
 assert.ok(r.nav[5].cash===r.nav[5].nav);
 assert.equal(r.decisions[1].shadow_trade_count,1);
});
