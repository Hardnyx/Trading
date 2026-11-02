import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {flatBaseline} from '../scripts/scoped_pilot_distributions.mjs';
import {generatePaths} from '../dist/assets/js/path-model.mjs';

test('zero-mean reference removes anchor uncertainty and regimes without changing origin covariance',()=>{
  const x={assets:[{symbol:'AAA',type:'stock'}],covariance:[[.04]],conditional:{dynamic:true},
    factorization:{},horizonVariance:{},regimes:[{id:'stress'}],
    options:{horizon:1,model:'merton',uncertainFundamentals:true,mandate:{cashYield:0}},
    anchors:[{symbol:'AAA',sector:'A',annual:.2,low:.1,high:.3}]};
  const baseline=flatBaseline(x);
  assert.equal(baseline.covariance,x.covariance);assert.equal(baseline.assets,x.assets);
  assert.equal(baseline.conditional.dynamic,false);assert.equal(baseline.factorization,null);
  assert.equal(baseline.options.uncertainFundamentals,false);
  assert.equal(baseline.anchors[0].annual,0);assert.equal(x.anchors[0].annual,.2);
  const sample=generatePaths(baseline,2000,20261102,252);
  const mean=sample.gross[0].filter((_,i)=>i%253===252).reduce((a,b)=>a+b,0)/2000;
  assert.ok(Math.abs(mean-1)<.02,'Flat GBM reference must preserve zero arithmetic drift');
});

test('frozen marginals preserve all original stocks, horizons and numerical probability invariants',()=>{
  const load=p=>JSON.parse(gunzipSync(readFileSync(new URL('../'+p,import.meta.url))));
  const frozen=load('data/historical/scoped-pilot-distributions-v1/forecasts.json.gz'),
    full=load('data/historical/scoped-engine-pilot-v1/results.json.gz');
  assert.equal(frozen.production_eligible,false);assert.equal(frozen.independent_holdout,false);
  assert.equal(frozen.certified_full_engine_cuts,0);
  for(let k=0;k<full.results.length;k++) {
    const r=frozen.origins[k],expected=full.results[k].prepared.symbols.filter(s=>s!=='CASH');
    assert.equal(r.cut,full.results[k].cut);
    assert.equal(r.records.length,expected.length*3*2);
    for(const symbol of expected)for(const h of [21,63,252])for(const id of frozen.protocol.models) {
      const rows=r.records.filter(r=>r.symbol===symbol&&r.horizon_sessions===h&&r.model===id);
      assert.equal(rows.length,1);
      const d=rows[0].distribution;
      assert.ok(d.loss_probability>=0&&d.loss_probability<=1);
      assert.ok(d.q05<=d.q95&&d.variance_log>0);
      assert.equal(d.quantiles.length,100);
      assert.ok(d.quantiles.every((v,i)=>Number.isFinite(v)&&(!i||v>=d.quantiles[i-1])));
    }
  }
});
