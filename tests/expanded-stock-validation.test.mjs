import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {gunzipSync} from 'node:zlib';
import {selectedCuts,immutable} from '../scripts/expanded_stock_forecasts.mjs';
import {assertEquivalent} from '../scripts/attribute_scoped_pilot.mjs';
import {digest} from '../scripts/scoped_engine_pilot.mjs';

test('immutable replay compares JSON semantics while rejecting material changes and preserving bytes',()=>{
  const dir=mkdtempSync(join(tmpdir(),'expanded-forecast-')),path=join(dir,'forecast.json.gz');
  try {
    const original={prepared:{evidence:{missing:undefined,known:null}},records:[{mean:.1}]};
    immutable(path,original);const before=readFileSync(path);
    immutable(path,original);immutable(path,JSON.parse(JSON.stringify(original)));
    assert.deepEqual(readFileSync(path),before);
    assert.throws(()=>immutable(path,{...original,records:[{mean:.1001}]}),/mismatch/);
    assert.throws(()=>immutable(path,{...original,prepared:{evidence:{known:undefined}}}),/mismatch/);
    assert.deepEqual(readFileSync(path),before);
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('expanded sample uses the unchanged coverage boundary and ignores outcome availability',()=>{
  const bundle={protocol:{selection:{minimum_weight:.7,maximum_origins:48}},
    schedule:[{cut:'2026-09-30',research_history_weight:.7,selected:true},
      {cut:'2024-12-31',research_history_weight:.71,selected:true},
      {cut:'2023-06-30',research_history_weight:.699999,selected:false}],
    origins:[{cut:'2024-12-31'},{cut:'2026-09-30',outcomes_available:false}]};
  assert.deepEqual(selectedCuts(bundle),['2024-12-31','2026-09-30']);
  bundle.origins.pop();assert.throws(()=>selectedCuts(bundle),/selection/);
});

test('all selected origins stay archived; the original two distributions are preserved as repetitions',()=>{
  const base=new URL('../data/historical/expanded-stock-validation-v1/',import.meta.url),
    manifest=JSON.parse(readFileSync(new URL('manifest.json',base))),
    original=JSON.parse(gunzipSync(readFileSync(new URL('../data/historical/scoped-pilot-distributions-v1/forecasts.json.gz',import.meta.url))));
  assert.equal(manifest.origins.length,8);assert.equal(manifest.schedule.length,48);
  assert.equal(manifest.schedule.filter(r=>r.selected).length,8);
  assert.equal(manifest.optimization_executed,false);assert.equal(manifest.certified_full_engine_cuts,0);
  assert.equal(manifest.independent_holdout,false);assert.equal(manifest.predictive_validation,'not-established');
  for(const entry of manifest.origins) {
    const raw=readFileSync(new URL(entry.file,base)),origin=JSON.parse(gunzipSync(raw));
    assert.equal(digest(raw),entry.sha256);assert.equal(origin.cut,entry.cut);
    assert.ok(origin.prepared.calibration_end<=origin.cut);
    assert.equal(origin.records.length,entry.records);
    const symbols=new Set(origin.records.filter(r=>r.role==='stock').map(r=>r.symbol));
    assert.equal(symbols.size,entry.forecast_stocks);
    for(const symbol of symbols)for(const h of manifest.protocol.horizons_sessions)
      for(const id of manifest.protocol.models)
        assert.equal(origin.records.filter(r=>r.symbol===symbol&&r.horizon_sessions===h&&r.model===id).length,1);
    const prior=original.origins.find(r=>r.cut===origin.cut);
    if(prior)assertEquivalent(origin.records,prior.records,'repeated-original-distributions');
  }
});
