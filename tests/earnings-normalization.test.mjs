import test from 'node:test';
import assert from 'node:assert/strict';
import {dilutedEarningsBridge} from '../dist/assets/js/earnings-normalization.mjs?v=0.30.0';
import {fundamentalForecast,assetAt} from '../dist/assets/js/research-model.mjs?v=0.30.0';
const record=value=>({value,period_end:'2026-06-30',filed:'2026-08-01',method:'TTM',components:[
 {start:'2025-07-01',end:'2026-06-30',filed:'2026-08-01',val:value,accn:'one'}]});
const asset=()=>({symbol:'AAA',type:'stock',price:100,price_date:'2026-10-26',sector:'Industrial',
 assumptions:{growth:.05,multiple:15,discount:.1,horizon:3},history:[],splits:[],
 financials:{eps:record(10),continuing_eps:record(4),discontinued_eps:record(6)}});

test('earnings bridge reconciles published diluted figures with audit components',()=>{
 const a=asset(),b=dilutedEarningsBridge(a);
 assert.equal(b.available,true);assert.equal(b.adjustment,-6);assert.equal(b.residual,0);
 assert.equal(b.evidence.length,3);assert.equal(b.period,'2026-06-30');
 assert.deepEqual(assetAt(a,a.price_date,a.price_date).financials.continuing_eps,a.financials.continuing_eps);
});
test('missing discontinued EPS is not interpreted as zero and historical cutoffs are respected',()=>{
 const a=asset();a.financials.discontinued_eps=null;
 assert.equal(dilutedEarningsBridge(a).available,false);
 assert.equal(dilutedEarningsBridge(asset(),'2026-07-31').available,false);
});
test('mismatched periods, intervals, residuals and split vintages cannot normalize earnings',()=>{
 const changes=[a=>{a.financials.continuing_eps.period_end='2026-03-31'},
 a=>{a.financials.continuing_eps.components[0].start='2025-01-01'},
 a=>{a.financials.discontinued_eps.value=5},
 a=>{a.splits=[{date:'2026-07-01',ratio:2}];a.financials.continuing_eps.components[0].accn='other'},
 a=>{a.financials.continuing_eps.components[0].filed='2026-11-01'},
 a=>{a.financials.continuing_eps.components=[]},
 a=>{a.financials.continuing_eps.components[0].val=999}];
 for(const change of changes){const a=asset();change(a);assert.equal(dilutedEarningsBridge(a).available,false);}
});
test('reported mode stays unchanged while the accounting sensitivity widens both sides',()=>{
 const a=asset(),plain=asset();delete plain.financials.continuing_eps;delete plain.financials.discontinued_eps;
 const before=fundamentalForecast(plain),after=fundamentalForecast(a);
 assert.equal(after.valid,true);assert.equal(after.central,before.central);
 assert.ok(after.accountingSensitivity>0);
 assert.ok(after.low<=Math.max(-.85,after.central-after.accountingSensitivity)+1e-12);
 assert.ok(after.high>=Math.min(2,after.central+after.accountingSensitivity)-1e-12);
 assert.ok(after.low<=before.low);assert.ok(after.high>=before.high);
});
test('continuing basis is explicit, does not mutate facts and cannot mix with unbridged consensus or margins',()=>{
 const a=asset(),before=JSON.stringify(a);
 const own=fundamentalForecast(a,{}, {earningsBasis:'continuing'});
 assert.equal(own.valid,true);assert.equal(own.earningsBasis,'continuing');
 assert.ok(own.ownEPS<fundamentalForecast(a).ownEPS);assert.equal(JSON.stringify(a),before);
 for(const basis of ['drivers','consensus','blend'])assert.equal(fundamentalForecast(a,{}, {basis,earningsBasis:'continuing'}).valid,false);
 a.financials.discontinued_eps=null;
 assert.equal(fundamentalForecast(a,{}, {earningsBasis:'continuing'}).valid,false);
 assert.equal(fundamentalForecast(asset(),{}, {earningsBasis:'invented'}).valid,false);
});
test('normalization cannot bypass an unparsed newer financial report',()=>{
 const a=asset();a.filings=[{form:'10-Q',filing_date:'2026-10-22',report_date:'2026-09-30'}];
 assert.equal(fundamentalForecast(a,{}, {earningsBasis:'continuing'}).valid,false);
});
