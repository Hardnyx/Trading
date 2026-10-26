import test from 'node:test';
import assert from 'node:assert/strict';
import {financialFreshness} from '../dist/assets/js/financial-freshness.mjs?v=0.13.0';
import {fundamentalForecast} from '../dist/assets/js/research-model.mjs?v=0.13.0';
const stock=()=>({symbol:'AAA',type:'stock',price:100,price_date:'2026-10-26',history:[],
 assumptions:{growth:.04,multiple:15,horizon:3},
 financials:{eps:{value:5,filed:'2026-07-30',period_end:'2026-06-30',method:'TTM'}},
 filings:[{form:'10-Q',filing_date:'2026-10-23',report_date:'2026-09-30'}]});

test('newer reporting period blocks old EPS, even after a fresh download',()=>{
 const a=stock();a.financials.observed_at='2026-10-26T20:00:00Z';
 const f=financialFreshness(a,'2026-10-26');assert.equal(f.status,'newer_report');assert.equal(f.blocked,true);
 assert.equal(f.period,'2026-06-30');
 const result=fundamentalForecast(a,{}, {},{asOf:'2026-10-26'});
 assert.equal(result.valid,false);assert.match(result.error,/más reciente/);
});
test('amendments, 8-Ks, future filings and same-period filings do not imply a new EPS period',()=>{
 const a=stock();a.filings=[{form:'10-Q/A',filing_date:'2026-10-23'},
  {form:'8-K',filing_date:'2026-10-23'},
  {form:'10-Q',filing_date:'2026-10-29',report_date:'2026-09-30'},
  {form:'10-Q',filing_date:'2026-08-02',report_date:'2026-06-30'}];
 assert.equal(financialFreshness(a,'2026-10-26').blocked,false);
 assert.equal(financialFreshness(a,'2026-10-30').blocked,true);
});
test('legacy snapshots need verification when a later filing lacks a reporting period',()=>{
 const a=stock();delete a.filings[0].report_date;
 assert.equal(financialFreshness(a,'2026-10-26').blocked,true);
 a.financials.eps=null;assert.equal(financialFreshness(a,'2026-10-26').status,'missing');
});
