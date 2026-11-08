import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {trainingMean,buildBenchmark,MIN_TRAINING_RETURNS}
  from '../scripts/benchmark_expanding_mean.mjs';

const cut='2024-12-31';
const calendar=Array.from({length:257},(_,i)=>{
  const dt=new Date(Date.UTC(2024,0,1+i));
  return dt.toISOString().slice(0,10);
});
const origin=calendar[255], maturity=calendar[256];
const data=(symbol='AAA')=>({symbol,history:calendar.map((date,i)=>({
  date,adj_close:100*(1.001**i),close:100*(1.001**i)}))});
const fake={
  protocol:'full-engine-evaluation-v1',
  primary_tests:[{id:'return_mse',reference:'training-only expanding mean of daily arithmetic total returns compounded as (1+mean_daily_return)**h-1; minimum 252 daily return intervals ending by origin, otherwise unscored'}],
  horizons_sessions:[1],
};
const manifest={independent_holdout:false,protocol:{id:'test-research',target:'gross',
  horizons_sessions:[1],market_commit:'test'},origins:[{cut:origin}],
  schedule:[{cut:origin,selected:true,reason:'selected-before-model-results'}],
  evidence:{protocol_sha256:'protocol-sha'}};
const scored={method:'test-research',scope:'gross',
  production_eligible:false,independent_holdout:false,optimization_executed:false,
  certified_full_engine_cuts:0,predictive_validation:'not-established',pooled_inference:null,
  origin_count:1,evidence:{forecast_commit:'frozen-commit',market_commit:'test',
    protocol_sha256:'protocol-sha'},origins:[{
    cut:origin,horizons:[{
      horizon_sessions:1,maturity,forecast_stocks:1,scored_stocks:1,
      observations:[{symbol:'AAA',role:'stock',realized_proxy:.005,
        models:{pilot_kernel:{forecast_mean:.002}}}],
    }],
  }]};
const market={price_as_of:maturity,assets:[data(),data('SPY')]};

test('the expanding arithmetic baseline uses only prior aligned observations',()=>{
  const result=trainingMean(data(),origin,1,calendar);
  assert.equal(result.training_returns,255);
  assert.ok(Math.abs(result.prediction-.001)<1e-12);
  assert.equal(result.training_end,origin);
  const transformed=data();transformed.history[256].adj_close=1e30;
  assert.deepEqual(trainingMean(transformed,origin,1,calendar),result,
    'Changing the future realization must not modify the trained baseline');
});
test('no endpoint or fewer than 252 aligned sessions fails closed',()=>{
  const missing=data();missing.history=missing.history.filter(r=>r.date!==origin);
  assert.equal(trainingMean(missing,origin,1,calendar).reason,'missing-exact-origin-price');
  assert.equal(trainingMean(data(),calendar[250],1,calendar).reason,
    'insufficient-expanding-training-sessions');
  assert.throws(()=>trainingMean(data(),origin,0,calendar),/horizon/);
});
test('compares identical realized targets and keeps primary inference disabled',()=>{
  const report=buildBenchmark(scored,market,manifest,fake);
  assert.equal(report.origins.length,1);
  const row=report.origins[0].horizons[0].rows[0];
  assert.equal(row.status,'paired');
  assert.ok(Math.abs(row.squared_candidate-(.002-.005)**2)<1e-14);
  assert.ok(row.reference_minus_candidate>0);
  assert.equal(report.summary[1].paired_stock_rows,1);
  assert.equal(report.summary[1].nonoverlapping_paired_origins,1);
  assert.equal(report.summary[1].primary_test_p_value,null);
  assert.equal(report.independent_confirmatory_holdout,false);
  assert.equal(report.certified_full_engine_cuts,0);
});
test('missing training does not erase the outcome or silently count as zero error',()=>{
  const small={...market,assets:[{symbol:'AAA',history:data().history.slice(-5)},data('SPY')]};
  const result=buildBenchmark(scored,small,manifest,fake);
  const r=result.origins[0].horizons[0];
  assert.equal(r.paired_stocks,0);
  assert.equal(r.mse_candidate,null);
  assert.equal(r.rows[0].reason,'insufficient-expanding-training-sessions');
});
test('rejects shifted maturities, invented confirmation and origin/sample tampering',()=>{
  const changed=structuredClone(scored);
  changed.origins[0].horizons[0].maturity=origin;
  assert.throws(()=>buildBenchmark(changed,market,manifest,fake),/Maturity/);
  changed.origins[0].horizons[0].maturity=maturity;
  changed.independent_holdout=true;
  assert.throws(()=>buildBenchmark(changed,market,manifest,fake),/retrospective-only/);
  const bad=structuredClone(scored);bad.origins[0].cut='2024-01-31';
  assert.throws(()=>buildBenchmark(bad,market,manifest,fake),/origin does not match/);
});
test('primary sample size cannot be reduced without an explicit new protocol',()=>{
  assert.equal(MIN_TRAINING_RETURNS,252);
  assert.throws(()=>buildBenchmark(scored,market,manifest,fake,251),/minimum cannot be relaxed/);
});
