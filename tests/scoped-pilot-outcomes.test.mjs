import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {endpointReturn,metrics,spearman,scorePilot} from '../scripts/score_scoped_pilot.mjs';

test('adjusted endpoints share a single scale; splits do not change the measured ratio',()=>{
  const asset={history:[{date:'2024-12-31',adj_close:50},{date:'2025-12-31',adj_close:60}]};
  const r=endpointReturn(asset,'2024-12-31','2025-12-31','2026-10-30');
  asset.history.forEach(r=>r.adj_close*=10);
  assert.ok(Math.abs(r.realized_proxy-.2)<1e-12);
  assert.equal(endpointReturn(asset,'2024-12-31','2025-12-31','2026-10-30').realized_proxy,r.realized_proxy);
});

test('missing endpoints never roll forward independently; documented corporate adjustments exclude the row',()=>{
  const asset={history:[{date:'2024-12-31',adj_close:50},{date:'2026-01-02',adj_close:60}]};
  assert.equal(endpointReturn(asset,'2024-12-31','2025-12-31','2026-10-30').reason,'missing_or_invalid_exact_endpoint');
  asset.price_adjustments=[{date:'2026-02-01'}];
  assert.equal(endpointReturn(asset,'2024-12-31','2025-12-31','2026-10-30').reason,'unreconciled_non_split_adjustment');
  assert.throws(()=>endpointReturn({history:[...asset.history,asset.history[0]]},'2024-12-31','2025-12-31','2026-10-30'),/Duplicate/);
});

test('tied ranks and constant comparators do not invent ranking skill',()=>{
  assert.equal(spearman([1,1,3],[4,4,5]),1);
  assert.equal(spearman([1,1,1],[1,2,3]),null);
  assert.equal(metrics([],'anchor').mae,null);
  const r=metrics([{anchor:.1,realized_proxy:.3},{anchor:.2,realized_proxy:.4}],'anchor');
  assert.ok(Math.abs(r.bias+.2)<1e-12);assert.ok(Math.abs(r.rmse-.2)<1e-12);
});

const unzip=path=>JSON.parse(gunzipSync(readFileSync(new URL('../'+path,import.meta.url))));
test('real immutable cohort keeps exclusions, matched samples, scope and CASH separate from stock scores',()=>{
  const bundle=unzip('data/historical/scoped-engine-pilot-v1/inputs.json.gz'),
    full=unzip('data/historical/scoped-engine-pilot-v1/results.json.gz');
  const dates=['2024-12-31','2025-04-30','2025-12-31','2026-04-30'];
  const symbols=[...new Set(full.results.flatMap(r=>r.prepared.symbols).filter(s=>s!=='CASH'))];
  const market={price_as_of:'2026-10-30',assets:symbols.map(symbol=>({symbol,
    history:dates.map((date,i)=>({date,adj_close:100+i}))}))};
  const excluded=market.assets.find(a=>a.symbol!=='SPY');excluded.history=excluded.history.filter(r=>r.date!=='2025-12-31');
  const report=scorePilot(bundle,full,market),o=report.origins[0];
  assert.equal(report.predictive_validation,'not-established');assert.equal(report.certified_full_engine_cuts,0);
  assert.equal(o.scored_stocks,37);assert.equal(o.exclusions.length,1);
  assert.equal(o.metrics.anchor.n,o.metrics.zero.n);assert.equal(o.metrics.anchor.n,o.metrics.benchmark_anchor.n);
  assert.ok(o.observations.every(r=>r.symbol!=='CASH'&&r.symbol!=='SPY'));
  assert.ok(o.observations.every(r=>!('low' in r)&&!('coverage' in r)));
  // Every cut remains represented when the annual horizon is immature.
  market.price_as_of='2025-06-01';const pending=scorePilot(bundle,full,market);
  assert.equal(pending.origin_count,2);assert.ok(pending.origins.every(o=>o.scored_stocks===0&&o.maturity===null));
  full.results[0].stored_snapshot_sha256='tampered';assert.throws(()=>scorePilot(bundle,full,market),/identity/);
});
