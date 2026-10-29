import test from 'node:test';
import assert from 'node:assert/strict';
import {budgetUtilities,objectivePolicies,runPrecisionMatrix,MATRIX_PROTOCOL} from '../scripts/antithetic_matrix_research.mjs';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {DEFAULT_MANDATE} from '../dist/assets/js/policy.mjs?v=0.35.0';
test('budget prefixes preserve both independent ordinary arms and count antithetic pairs once',()=>{
 const r=budgetUtilities(Float64Array.of(1,2,9),Float64Array.of(3,4,8),Float64Array.of(-1,-2,-9),2);
 assert.deepEqual([...r.plain],[1,2,3,4]);assert.deepEqual([...r.antithetic],[0,0]);
 assert.throws(()=>budgetUtilities([1,2],[3],[4,5],2));assert.throws(()=>budgetUtilities([1,NaN],[1,2],[1,2],2));
});
test('objectives retain horizon, cash, FX, dividends and withdrawals without mutating the base',()=>{
 const b={...DEFAULT_MANDATE,horizon:1,cashYield:.03,monthlyWithdrawal:50},before=structuredClone(b),p=objectivePolicies(b);
 assert.deepEqual(b,before);assert.deepEqual(p.map(p=>p.objective),['growth','preservation','target']);
 for(const x of p)for(const k of Object.keys(b))if(!['objective','terminalTarget'].includes(k))assert.deepEqual(x[k],b[k]);
 assert.equal(p[2].terminalTarget,MATRIX_PROTOCOL.target);
});
test('reusing paths across utility-only objectives equals generating each objective separately',()=>{
 const x={assets:[{symbol:'A',type:'stock',sector:'A'}],anchors:[{symbol:'A',sector:'A',annual:.06,low:.06,high:.06}],covariance:[[.04]],
  conditional:{dynamic:false,fits:[null]},options:{model:'gbm',horizon:1,uncertainFundamentals:false},
  regimes:[{id:'base',probability:1,earningsShift:0,multipleShift:0,rateShift:0,rateJumpBps:0}]},sample=generatePaths(x,100,41);
 for(const policy of objectivePolicies(sample.policy)){
  const direct=generatePaths({...x,options:{...x.options,mandate:policy}},100,41),shared={...sample,policy};
  assert.deepEqual(direct.gross,shared.gross);assert.deepEqual(direct.fx,shared.fx);
  assert.deepEqual(evaluatePaths([1],direct,{pathUtilities:true}),evaluatePaths([1],shared,{pathUtilities:true}));
 }
});
test('the matrix rejects unmatched vintages before simulation',()=>{
 assert.throws(()=>runPrecisionMatrix({generated_at:'a',price_as_of:'b'},{source_market_generated_at:'c',as_of:'b'},[]),/vintage/);
});
test('a resolved target opportunity does not certify achievement of the financial target',async()=>{
 const {poolOpportunityEvidence}=await import('../scripts/pool_opportunity_audit.mjs'),p=objectivePolicies(DEFAULT_MANDATE)[2],
  row=(key,u)=>({key,models:[{id:'one',utilities:Array(100).fill(u)}]}),
  r=poolOpportunityEvidence([row('best',-.0004),row('other',-.0009)],p,100000,100);
 assert.equal(r.rows[0].upperOpportunityLoss,0);assert.equal(r.rows[0].worstCertaintyEquivalent,103000);
 assert.ok(r.rows[0].worstCertaintyEquivalent<p.terminalTarget);
 assert.ok(Math.abs(r.rows[1].upperOpportunityLoss-1000)<1e-7);
});
test('preservation opportunity is converted using its CRRA utility rather than growth utility',async()=>{
 const {poolOpportunityEvidence}=await import('../scripts/pool_opportunity_audit.mjs'),p=objectivePolicies(DEFAULT_MANDATE)[1],g=p.riskAversion,
  row=(key,r)=>({key,models:[{id:'one',utilities:Array(100).fill(((1+r)**(1-g)-1)/(1-g))}]}),
  r=poolOpportunityEvidence([row('a',.04),row('b',.03)],p,100000,100);
 assert.ok(Math.abs(r.rows[1].upperOpportunityLoss-1000)<1e-7);
});
