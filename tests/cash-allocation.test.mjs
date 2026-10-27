import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareComposition,reviewCashAllocation,validWeights} from '../dist/assets/js/composer.mjs?v=0.21.0';
import {generatePaths,evaluatePaths,BASE_REGIME} from '../dist/assets/js/path-model.mjs?v=0.21.0';
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.21.0';

function fixture(minimumCash=.05) {
 const asOf='2026-10-23';
 const history=Array.from({length:260},(_,i)=>({date:new Date(Date.parse(asOf+'T12:00:00Z')-(259-i)*86400000).toISOString().slice(0,10),close:100,adj_close:100,volume:1e6}));
 const stock={symbol:'AAA',type:'stock',sector:'Industrial',price:100,price_date:asOf,history,dividend_per_share:0,
  assumptions:{growth:.06,multiple:20,discount:.1,horizon:3},financials:{eps:{value:5,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}};
 const x=prepareComposition({price_as_of:asOf,generated_at:asOf+'T23:00:00Z',assets:[stock],macro:[]},
  {horizon:1,seed:1,model:'gbm',volatilityMode:'legacy',uncertainFundamentals:false,macroRegimes:[BASE_REGIME],mandate:{minimumCash},execution:{spreadBps:0,slippageBps:0}}, {}, {maxPositions:2});
 const sample=generatePaths(x,100,17,4),cash=x.assets.findIndex(a=>a.symbol==='CASH');
 for(let i=0;i<x.assets.length;i++) for(let p=0;p<sample.paths;p++) for(let t=0;t<=sample.steps;t++)
  sample.gross[i][p*(sample.steps+1)+t]=i===cash?1:1+.12*t/sample.steps;
 const w=x.assets.map((a,i)=>i===cash?1:0);
 const plan=tradePlan(x.assets,[{symbol:'CASH',weight:1}],x.current.positions,x.current.capital,x.costs);
 return {x,sample,cash,initial:{weights:w,positions:[{symbol:'CASH',weight:1}],plan,
  metrics:evaluatePaths(w,sample,{capital:x.current.capital,cost:plan.total}),feasible:true,kind:'active'}};
}

test('cash review finds omitted local gains and respects the original issuer and equity caps',()=>{
 const {x,sample,cash,initial}=fixture();
 const original=initial.weights.slice();
 const result=reviewCashAllocation(initial,x,sample);
 assert.ok(result.best.metrics.score>initial.metrics.score);
 assert.ok(validWeights(result.best.weights,x));
 assert.ok(Math.abs(result.best.weights[1-cash]-.2)<1e-10);
 assert.equal(result.audit.status,'structural_limits');
 assert.ok(result.audit.improvements.length>0);assert.ok(result.audit.structurallyBlocked>0);
 assert.deepEqual(initial.weights,original);
});
test('an explicit cash reserve remains binding even when the risky alternative earns more',()=>{
 const {x,sample,cash,initial}=fixture(.9),result=reviewCashAllocation(initial,x,sample);
 assert.ok(Math.abs(result.best.weights[cash]-.9)<1e-10);
 assert.equal(result.audit.status,'required_reserve');
 assert.equal(result.audit.requiredCash,.9);
});
test('cash is not forced into investments that fail risk constraints or have equal objective',()=>{
 for(const multiple of [.8,1]){
  const {x,sample,cash,initial}=fixture();
  for(let i=0;i<x.assets.length;i++)if(i!==cash)
   for(let p=0;p<sample.paths;p++)for(let t=0;t<=sample.steps;t++)
    sample.gross[i][p*(sample.steps+1)+t]=1+(multiple-1)*t/sample.steps;
  const result=reviewCashAllocation(initial,x,sample);
  assert.equal(result.best.weights[cash],1);
  assert.equal(result.audit.improvements.length,0);
  assert.equal(result.audit.status,multiple<1?'risk_or_execution_limits':'no_local_improvement');
 }
});
