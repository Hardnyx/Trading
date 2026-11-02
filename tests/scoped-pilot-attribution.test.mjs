import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {riskAttribution,gainFailures,verifyCandidate,verifySources,assertEquivalent} from '../scripts/attribute_scoped_pilot.mjs';

test('cross-runtime verification tolerates roundoff but never decision, sample or material numeric changes',()=>{
  assertEquivalent({value:.1+.2,passes:false,rows:[1]}, {value:.3,passes:false,rows:[1]});
  for(const value of [{value:.300001,passes:false,rows:[1]},
      {value:.3,passes:true,rows:[1]},{value:.3,passes:false,rows:[1,2]}])
    assert.throws(()=>assertEquivalent(value,{value:.3,passes:false,rows:[1]}),/mismatch/);
});

test('risk audit distinguishes a point violation from an uncertainty-only rejection at the boundary',()=>{
  const rows=riskAttribution({rows:[
    {value:.44,upper:.49,limit:.45},
    {value:.46,upper:.51,limit:.45},
    {value:.45,upper:.45,limit:.45},
    {value:.44,upper:NaN,limit:.45}]});
  assert.deepEqual(rows.map(r=>[r.failed,r.point_exceeds_limit,r.sampling_margin_only]),
    [[true,false,true],[true,true,false],[false,false,false],[true,false,true]]);
  assert.deepEqual(gainFailures({meanUtilityGain:1,lowerGain:100},100,false),[]);
  assert.deepEqual(gainFailures({meanUtilityGain:0,lowerGain:0},100,false),
    ['nonpositive_utility_gain','gain_below_hurdle']);
  assert.deepEqual(gainFailures({meanUtilityGain:0,lowerGain:0},100,true),[]);
});

test('replaying a cohort fails closed on source drift or changed decisions, even with similar utility',()=>{
  const dir=mkdtempSync(join(tmpdir(),'pilot-source-'));
  try {
    writeFileSync(join(dir,'module.mjs'),'export const v=1;');
    const manifest=[{path:'module.mjs',sha256:createHash('sha256').update(readFileSync(join(dir,'module.mjs'))).digest('hex')}];
    verifySources(manifest,dir);
    writeFileSync(join(dir,'module.mjs'),'export const v=2;');
    assert.throws(()=>verifySources(manifest,dir),/source mismatch/);
  } finally {rmSync(dir,{recursive:true,force:true});}
  const archived={feasible:false,selected:false,worstCertaintyEquivalent:100100,
    minimumLowerGain:100,maximumRisk:.2,turnover:.5};
  verifyCandidate({...archived},archived);
  assert.throws(()=>verifyCandidate({...archived,feasible:true},archived),/feasible/);
  assert.throws(()=>verifyCandidate({...archived,minimumLowerGain:101},archived),/metric mismatch/);
});

test('published attribution covers every original finalist and preserves the no-validation boundary',()=>{
  const report=JSON.parse(readFileSync(new URL('../data/historical/scoped-pilot-attribution-v1/report.json',import.meta.url)));
  assert.equal(report.certified_full_engine_cuts,0);
  assert.equal(report.predictive_validation,'not-established');
  for(const key of ['production_eligible','prospective','new_search','new_confirmation','changed_decisions'])
    assert.equal(report[key],false);
  assert.equal(report.origins.length,2);
  for(const o of report.origins) {
    assert.equal(o.candidates.length,o.finalists);
    assert.equal(o.finalists,23);assert.equal(o.admissible_transitions,0);
    assert.equal(o.candidates.filter(c=>c.hold&&c.feasible&&c.selected).length,1);
    for(const c of o.candidates) {
      assert.equal(c.models.length,5);assert.equal(c.tail_stress.role,'risk-only');
      assert.ok(!('evidence' in c.tail_stress));
      assert.equal(c.feasible,c.models.every(m=>m.passes)&&c.tail_stress.passes);
      for(const m of [...c.models,c.tail_stress]) {
        assert.equal(m.passes,m.failures.length===0);
        for(const r of m.risk)assert.equal(r.failed,r.point_exceeds_limit||r.sampling_margin_only);
      }
      if(!c.hold)assert.ok(c.models.every(m=>m.evidence.lowerGain>=m.hurdle));
    }
  }
});
