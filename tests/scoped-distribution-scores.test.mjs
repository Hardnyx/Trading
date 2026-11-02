import test from 'node:test';
import assert from 'node:assert/strict';
import {probabilityScore,scoreFrozenDistributions} from '../scripts/score_scoped_distributions.mjs';

const distribution={mean:0,mean_log:0,variance_log:.01,q05:0,q95:0,es_loss_signed:0,
  quantiles:Array(100).fill(0),loss_probability:.25};
test('Brier and CRPS obey known deterministic cases; zero return is not a loss',()=>{
  const loss=probabilityScore(distribution,-.1),gain=probabilityScore(distribution,.1),zero=probabilityScore(distribution,0);
  assert.ok(Math.abs(loss.crps-.1)<1e-12);assert.ok(Math.abs(gain.crps-.1)<1e-12);
  assert.equal(loss.brier_loss,.75**2);assert.equal(gain.brier_loss,.25**2);
  assert.equal(zero.brier_loss,.25**2);assert.equal(zero.crps,0);assert.equal(zero.covered90,true);
  assert.throws(()=>probabilityScore({...distribution,loss_probability:1.1},0),/probability/);
});

function fixture() {
  const models=['pilot_kernel','flat_ewma_zero_mean'],dates=['2024-12-31','2025-01-02','2025-01-03'];
  return {frozen:{production_eligible:false,certified_full_engine_cuts:0,protocol:{models,horizons_sessions:[1,2]},
    origins:[{cut:dates[0],records:['AAA','BBB','SPY'].flatMap(symbol=>[1,2].flatMap(horizon_sessions=>models.map(model=>({
      symbol,model,horizon_sessions,role:symbol==='SPY'?'benchmark':'stock',distribution}))))}]},
    market:{price_as_of:dates.at(-1),assets:['AAA','BBB','SPY'].map(symbol=>({symbol,
      history:dates.map((date,i)=>({date,adj_close:100+i}))}))}};
}
test('missing exact outcomes exclude matched models; benchmark and immature horizons remain separate',()=>{
  const {frozen,market}=fixture();market.assets[1].history.splice(1,1);
  const scored=scoreFrozenDistributions(frozen,market),first=scored.origins[0].horizons[0];
  assert.equal(first.scored_stocks,1);assert.equal(first.forecast_stocks,2);
  assert.equal(first.exclusions[0].symbol,'BBB');assert.equal(first.benchmark.symbol,'SPY');
  assert.equal(first.stock_metrics.pilot_kernel.n,1);assert.equal(first.stock_metrics.flat_ewma_zero_mean.n,1);
  assert.equal(scored.origins[0].horizons[1].scored_stocks,2,'Missing interior day must not exclude valid endpoints');
  market.price_as_of='2024-12-31';
  const pending=scoreFrozenDistributions(frozen,market);
  assert.ok(pending.origins[0].horizons.every(h=>h.maturity===null&&h.scored_stocks===0&&h.stock_metrics.pilot_kernel.mae===null));
  assert.equal(pending.certified_full_engine_cuts,0);assert.equal(pending.pooled_inference,null);
});
test('a duplicated model or a later corporate adjustment cannot silently change the comparison sample',()=>{
  const {frozen,market}=fixture();
  frozen.origins[0].records.push(frozen.origins[0].records[0]);
  assert.throws(()=>scoreFrozenDistributions(frozen,market),/Unmatched/);
  frozen.origins[0].records.pop();market.assets[0].price_adjustments=[{date:'2025-01-02'}];
  const scored=scoreFrozenDistributions(frozen,market);
  assert.ok(scored.origins[0].horizons.every(h=>h.exclusions.some(r=>r.symbol==='AAA'&&r.reason==='unreconciled_non_split_adjustment')));
});
