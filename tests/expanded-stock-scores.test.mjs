import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {summarizeExpanded} from '../scripts/score_expanded_stock_validation.mjs';
import {assertEquivalent} from '../scripts/attribute_scoped_pilot.mjs';

test('nonoverlapping schedules retain pending cuts and never count overlapping returns as separate intervals',()=>{
  const origin=(cut,maturity)=>({cut,horizons:[{horizon_sessions:21,maturity,scored_stocks:maturity?2:0,
    exclusions:[],stock_metrics:{pilot_kernel:{crps:1,brier_loss:1,rmse:1},flat_ewma_zero_mean:{crps:2,brier_loss:.5,rmse:1}}}]});
  const report={origins:[origin('2024-01-02','2024-03-01'),origin('2024-02-01','2024-04-01'),
    origin('2024-03-01','2024-05-01'),origin('2024-06-01',null)]};
  const h=summarizeExpanded(report,[21])[21];
  assert.equal(h.mature_origins,3);assert.equal(h.stock_comparisons,6);
  assert.deepEqual(h.pending_cuts,['2024-06-01']);
  assert.deepEqual(h.nonoverlapping_cut_schedule,['2024-01-02','2024-03-01']);
  assert.equal(h.descriptive_better_crps_origins,3);assert.equal(h.descriptive_better_brier_origins,0);
  assert.equal(h.descriptive_better_rmse_origins,0,'Equal error is not a win');
});

test('expanded scores preserve the first two reports and separate additional evidence, overlap and immature outcomes',()=>{
  const load=p=>JSON.parse(readFileSync(new URL('../'+p,import.meta.url))),
    expanded=load('data/historical/expanded-stock-validation-scores-v1/report.json'),
    original=load('data/historical/scoped-pilot-distribution-scores-v1/report.json');
  assertEquivalent(expanded.origins.slice(0,2),original.origins,'original-scores');
  assert.equal(expanded.origin_count,8);assert.equal(expanded.additional_origins,6);
  assert.equal(expanded.optimization_executed,false);assert.equal(expanded.certified_full_engine_cuts,0);
  assert.equal(expanded.independent_holdout,false);assert.equal(expanded.pooled_inference,null);
  assert.deepEqual([21,63,252].map(h=>expanded.horizon_summary[h].mature_origins),[8,7,4]);
  assert.deepEqual([21,63,252].map(h=>expanded.horizon_summary[h].nonoverlapping_origins),[8,5,1]);
  assert.deepEqual([21,63,252].map(h=>expanded.horizon_summary[h].stock_comparisons),[304,266,152]);
  for(const o of expanded.origins)for(const h of o.horizons) {
    assert.equal(h.forecast_stocks,38);
    if(!h.maturity)assert.ok(h.observations.every(r=>r.reason==='immature'));
    else assert.ok(Object.values(h.stock_metrics).every(m=>m.n===h.scored_stocks));
  }
});
