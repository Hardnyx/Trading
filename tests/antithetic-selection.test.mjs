import test from 'node:test';
import assert from 'node:assert/strict';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {pairUtilityMeans} from '../scripts/antithetic_selection_research.mjs';
import {pairedDecisionEvidence} from '../dist/assets/js/robust-decision.mjs?v=0.35.0';
const fixture=()=>({assets:[{symbol:'A',type:'stock',sector:'A'}],anchors:[{symbol:'A',sector:'A',annual:.06,low:.06,high:.06}],
 covariance:[[.04]],conditional:{dynamic:false,fits:[null]},regimes:[{id:'base',probability:1,earningsShift:0,multipleShift:0,rateShift:0,rateJumpBps:0}],
 options:{model:'gbm',horizon:1,uncertainFundamentals:false,researchShadowMode:true,mandate:{dividendPolicy:'reinvest'}}});
test('reflection preserves the exact flat Gaussian log-price symmetry and cancels log-utility noise',()=>{
 const x=fixture(),a=generatePaths(x,200,41),b=generatePaths(x,200,41,52,{researchMirror:true}),expected=Math.log1p(.06)-.04/2;
 const u=evaluatePaths([1],a,{pathUtilities:true}).pathUtilities,v=evaluatePaths([1],b,{pathUtilities:true}).pathUtilities,
  means=pairUtilityMeans(u,v),e=pairedDecisionEvidence(means,new Float64Array(200),a.policy,100000);
 for(let i=0;i<200;i++)assert.ok(Math.abs(means[i]-expected)<1e-12);
 assert.ok(e.standardError<1e-13);assert.ok(pairedDecisionEvidence(u,new Float64Array(200),a.policy,100000).standardError>.001);
});
test('ordinary paths are unchanged by the explicit false option; reflection requires shadow mode',()=>{
 const x=fixture();assert.deepEqual(generatePaths(x,100,7),generatePaths(x,100,7,52,{researchMirror:false}));
 x.options.researchShadowMode=false;assert.throws(()=>generatePaths(x,100,7,52,{researchMirror:true}),/investigación/);
});
test('pair averaging never counts dependent arms as independent outcomes and rejects missing data',()=>{
 assert.deepEqual([...pairUtilityMeans([1,3],[3,1])],[2,2]);
 assert.throws(()=>pairUtilityMeans([1,2],[1]));assert.throws(()=>pairUtilityMeans([NaN,1],[1,2]));
});
