import test from 'node:test';
import assert from 'node:assert/strict';
import {currentAccount} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {referenceRequest} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {prepareContinuousAccountRequest,continuousAccountHandoff,
 ACCOUNT_RESEARCH_COHORT,FIXED_SEARCH} from '../scripts/continuous_account_origin.mjs';

const cut='2026-12-31',issued='2026-12-31T23:00:00Z';
const asset=(symbol,price)=>({symbol,currency:'USD',price_date:cut,price,
 history:[{date:cut,close:price,adj_close:price}]});
const snapshot=()=>({price_as_of:cut,requested_as_of:cut,
 generated_at:'2026-12-31T22:00:00Z',assets:[asset('SPY',100),asset('AAA',110)],macro:[]});
const book=()=>({schema:'full-engine-cash-account-research-v1',
 status:'complete',observed_through:cut,accounted_sessions:2,calendar_sessions:2,
 nav:[{date:'2026-12-30',nav:1000,identity_residual:0},
 {date:cut,nav:1050,cash:500,receivables:0,
 holdings:[{symbol:'AAA',quantity:5,raw_close:110,market_value:550}],identity_residual:0}],
 journal:[{date:'2026-12-30',type:'shadow-trade',symbol:'AAA'}],
 decisions:[{cut:'2026-12-29',execute:'2026-12-30'}],
 final_cash:500,final_units:{AAA:5},pending_receivables:[]});
const run=({market=snapshot(),ledger=book(),issue=issued}={})=>
 prepareContinuousAccountRequest({snapshot:market,ledger,
  ledgerBytes:Buffer.from(JSON.stringify(ledger)),issuedAt:issue});

test('carried shares and cash use the actual optimizer account interface',()=>{
 const input=run(),request=input.request;
 assert.equal(input.cohort_id,ACCOUNT_RESEARCH_COHORT);
 assert.equal(request.settings.account.enabled,true);
 assert.equal(request.settings.account.cash,500);
 assert.deepEqual(request.settings.account.positions,[{symbol:'AAA',quantity:5,costBasis:null}]);
 assert.equal(request.settings.capital,1050);
 const reconstructed=currentAccount(snapshot(),request.settings.account,null,1050);
 assert.equal(reconstructed.capital,1050);
 assert.equal(reconstructed.positions.find(x=>x.symbol==='AAA').weight,550/1050);
 assert.equal(reconstructed.positions.find(x=>x.symbol==='CASH').weight,500/1050);
 assert.equal(referenceRequest(snapshot()).settings.account.enabled,false);
 assert.equal(input.original_v2_cohort_reused,false);
 assert.equal(input.confirmatory_eligible,false);
});
test('research handoff forbids seed or search-budget shopping',()=>{
 const input=run(),output=continuousAccountHandoff(input);
 assert.equal(output.request.settings.seed,20261024);
 assert.deepEqual(output.search,FIXED_SEARCH);
 assert.equal(output.confirmatory_eligible,false);
 assert.throws(()=>continuousAccountHandoff({...input,
  search:{...FIXED_SEARCH,candidates:1000}}),/Invalid research cohort/);
});
test('unpaid dividend is never silently converted into investable cash',()=>{
 const a=book();a.nav.at(-1).receivables=20;a.nav.at(-1).nav=1070;
 assert.throws(()=>run({ledger:a}),/Unsettled dividends/);
 const b=book();b.pending_receivables=[{symbol:'AAA',gross:20,pay_date:'2027-01-04'}];
 assert.throws(()=>run({ledger:b}),/Unsettled dividends/);
});
test('held positions must match the original close and final share balance',()=>{
 const market=snapshot();market.assets[1].price=111;
 assert.throws(()=>run({market}),/matching unadjusted original cut close/);
 const ledger=book();ledger.final_units.AAA=6;
 assert.throws(()=>run({ledger}),/Original holdings disagree/);
});
test('later outcomes and labels cannot enter a previous decision',()=>{
 const ledger=book();ledger.journal.push({date:'2027-01-02',type:'dividend-payment'});
 assert.throws(()=>run({ledger}),/future postings/);
 const later=book();later.nav.at(-1).date='2027-01-02';
 assert.throws(()=>run({ledger:later}),/Missing complete account ledger/);
 const market=snapshot();market.assets[0].history.push({date:'2027-01-02',close:900});
 assert.throws(()=>run({market}),/Future market observations/);
});
test('account must be complete and its NAV self-financing',()=>{
 const a=book();a.status='incomplete';
 assert.throws(()=>run({ledger:a}),/Missing complete account ledger/);
 const b=book();b.final_cash=200;
 assert.throws(()=>run({ledger:b}),/final settled cash/);
 const c=book();c.nav.at(-1).nav=2000;
 assert.throws(()=>run({ledger:c}),/unrepresented assets/);
});
test('research account cannot issue after next opening',()=>{
 assert.throws(()=>run({issue:'2027-01-01T17:00:00Z'}),/after close and before next opening/);
 const market=snapshot();market.generated_at='2027-01-02T22:00:00Z';
 assert.throws(()=>run({market}),/collected after New York close/);
});
test('all-cash account does not manufacture shares or baseline assets',()=>{
 const b=book();b.nav.at(-1).holdings=[];b.nav.at(-1).nav=1050;
 b.nav.at(-1).cash=1050;b.final_cash=1050;b.final_units={};
 const output=run({ledger:b});
 assert.deepEqual(output.request.settings.account.positions,[]);
 const x=currentAccount(snapshot(),output.request.settings.account,null,1050);
 assert.deepEqual(x.positions.map(p=>p.symbol),['CASH']);
});
