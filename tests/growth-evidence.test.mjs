import test from 'node:test';
import assert from 'node:assert/strict';
import {growthEvidence} from '../dist/assets/js/growth-evidence.mjs?v=0.27.0';
import {assetAt, fundamentalForecast} from '../dist/assets/js/research-model.mjs?v=0.27.0';

const asset=()=>({symbol:'TEST',type:'stock',price:100,price_date:'2026-10-26',history:[],
 assumptions:{growth:.05,multiple:20,discount:.1,horizon:3},financials:{
 eps:{value:5,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'},
 earnings_history:{observed_at:'2026-10-27T18:00:00Z',through_filing_date:'2026-10-27',
 records:[{period_end:'2025-12-31'},{period_end:'2025-12-31'},{period_end:'2024-12-31'}]},
 growth_research:{outcomes:8,latest_candidate:{annual_growth:.08,training_observations:5}}}});

test('catalog growth has no predictive vintage; a manual edit stays a declared assumption',()=>{
 const a=asset(),e=growthEvidence(a,{}, {},{asOf:'2026-10-27'});
 assert.equal(e.kind,'catalog_convention');assert.equal(e.sourceVintage,null);
 assert.equal(e.annualPeriods,2);assert.equal(e.reconstructedOutcomes,8);
 assert.equal(e.originalVintagesVerified,false);assert.equal(e.productionEligible,false);
 assert.equal(growthEvidence(a,{growth:.08}).kind,'manual');
 assert.equal(growthEvidence(a,{}, {basis:'drivers'}).kind,'drivers');
});
test('a later history capture cannot leak into an earlier information cutoff',()=>{
 const a=asset();
 for(const asOf of ['2025-12-31','2026-10-26']){
  const e=growthEvidence(a,{}, {},{asOf});
  assert.equal(e.annualPeriods,0);assert.equal(e.shrinkageCandidate,null);
  const historical=assetAt(a,a.price_date,asOf);
  assert.equal(historical.financials.earnings_history,null);
  assert.equal(historical.financials.growth_research,null);
 }
 assert.equal(assetAt(a,a.price_date,'2026-10-27').financials.earnings_history,a.financials.earnings_history);
});
test('history candidates do not change production growth, bands or portfolio anchors',()=>{
 const a=asset(),before=structuredClone(a);delete before.financials.earnings_history;delete before.financials.growth_research;
 const x=fundamentalForecast(before,{}, {},{asOf:'2026-10-27'}),y=fundamentalForecast(a,{}, {},{asOf:'2026-10-27'});
 assert.equal(y.valid,true);assert.ok(Math.abs(y.assumptions.growth-.05)<1e-12);
 for(const key of ['central','low','high','equivalentGrowth','confidence'])assert.equal(y[key],x[key]);
 assert.equal(y.growthEvidence.shrinkageCandidate,.08);assert.equal(y.growthEvidence.calibrated,false);
});
test('missing consensus cannot give a fallback assumption an analyst vintage',()=>{
 const a=asset();
 const fallback=growthEvidence(a,{}, {basis:'blend'},{asOf:'2026-10-27',consensusUsed:false,consensusObservedAt:'2026-10-27T17:00:00Z'});
 assert.equal(fallback.kind,'catalog_convention');assert.equal(fallback.sourceVintage,null);
 const consensus=growthEvidence(a,{}, {basis:'blend'},{asOf:'2026-10-27',consensusUsed:true,consensusObservedAt:'2026-10-27T17:00:00Z'});
 assert.equal(consensus.kind,'blend');assert.equal(consensus.sourceVintage,'2026-10-27T17:00:00Z');
 assert.equal(consensus.calibrated,false);
});
