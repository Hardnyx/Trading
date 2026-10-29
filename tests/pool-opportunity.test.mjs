import test from 'node:test';
import assert from 'node:assert/strict';
import {poolOpportunityEvidence} from '../scripts/pool_opportunity_audit.mjs';
import {DEFAULT_MANDATE} from '../dist/assets/js/policy.mjs?v=0.35.0';
const row=(key,returns,noise=0)=>({key,models:returns.map((r,m)=>({id:String(m),utilities:Array.from({length:100},(_,i)=>Math.log1p(r)+(i%2?noise:-noise))}))});
test('the empirical leader has nonzero opportunity uncertainty when another candidate can be better',()=>{
 const a=row('a',[.04]),b=row('b',[.039],.08),r=poolOpportunityEvidence([a,b],DEFAULT_MANDATE,100000,100);
 const e=r.rows.find(r=>r.key==='a');assert.equal(r.pointLeader,'a');assert.equal(e.estimatedOpportunityLoss,0);
 assert.ok(e.upperOpportunityLoss>100);assert.equal(e.resolvedWithinThreshold,false);
});
test('constant models recover exact finite-pool maximin losses despite conflicting base rankings',()=>{
 const r=poolOpportunityEvidence([row('a',[.05,.04]),row('b',[.08,.02])],DEFAULT_MANDATE,100000,100);
 assert.equal(r.pointLeader,'a');assert.equal(r.rows[0].upperOpportunityLoss,0);assert.equal(r.rows[0].resolvedWithinThreshold,true);
 assert.ok(Math.abs(r.rows[1].lowerOpportunityLoss-2000)<1e-7);
});
test('candidate permutation does not change bounds and multiple experiments widen the envelope',()=>{
 const a=row('a',[.04]),b=row('b',[.039],.08),f=(rows,n)=>poolOpportunityEvidence(rows,DEFAULT_MANDATE,100000,100,{experiments:n});
 const x=f([a,b],1),y=f([b,a],1);assert.equal(x.pointLeader,y.pointLeader);
 assert.deepEqual(x.rows,y.rows.reverse());assert.ok(f([a,b],10).rows[0].upperOpportunityLoss>x.rows[0].upperOpportunityLoss);
});
test('invalid model grids and nonfinite paired utilities fail instead of dropping comparisons',()=>{
 assert.throws(()=>poolOpportunityEvidence([],DEFAULT_MANDATE,100000,100));
 assert.throws(()=>poolOpportunityEvidence([row('a',[.04]),row('a',[.03])],DEFAULT_MANDATE,100000,100));
 assert.throws(()=>poolOpportunityEvidence([row('a',[.04]),row('b',[.03,.02])],DEFAULT_MANDATE,100000,100));
 const a=row('a',[.04]),b=row('b',[.03]);b.models[0].utilities[0]=NaN;
 assert.throws(()=>poolOpportunityEvidence([a,b],DEFAULT_MANDATE,100000,100));
 assert.throws(()=>poolOpportunityEvidence([b],DEFAULT_MANDATE,100000,100));
});
