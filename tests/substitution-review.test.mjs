import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareComposition,reviewSubstitutions,validWeights,SUBSTITUTION_Z,weightOverlap,reconcileStarts,startSeeds} from '../dist/assets/js/composer.mjs?v=0.32.0';
import {generatePaths,evaluatePaths,BASE_REGIME} from '../dist/assets/js/path-model.mjs?v=0.32.0';
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.32.0';

// Two stocks, at most two positions (cash + one): improving needs a full
// substitution, which reallocating cash alone cannot find.
function universe() {
 const asOf='2026-10-23';
 const history=Array.from({length:260},(_,i)=>({date:new Date(Date.parse(asOf+'T12:00:00Z')-(259-i)*86400000).toISOString().slice(0,10),close:100,adj_close:100,volume:1e6}));
 const stock=symbol=>({symbol,type:'stock',sector:'Industrial',price:100,price_date:asOf,history,dividend_per_share:0,
  assumptions:{growth:.06,multiple:20,discount:.1,horizon:3},financials:{eps:{value:5,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}});
 return {snapshot:{price_as_of:asOf,generated_at:asOf+'T23:00:00Z',assets:[stock('AAA'),stock('BBB')],macro:[]},
  settings:{horizon:1,seed:1,model:'gbm',volatilityMode:'legacy',uncertainFundamentals:false,macroRegimes:[BASE_REGIME],mandate:{minimumCash:.8},execution:{spreadBps:0,slippageBps:0}},
  rules:{maxPositions:2,maxCorrelation:1}};
}
function fixture(terminal) {
 const asOf='2026-10-23';
 const history=Array.from({length:260},(_,i)=>({date:new Date(Date.parse(asOf+'T12:00:00Z')-(259-i)*86400000).toISOString().slice(0,10),close:100,adj_close:100,volume:1e6}));
 const stock=symbol=>({symbol,type:'stock',sector:'Industrial',price:100,price_date:asOf,history,dividend_per_share:0,
  assumptions:{growth:.06,multiple:20,discount:.1,horizon:3},financials:{eps:{value:5,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}});
 const x=prepareComposition({price_as_of:asOf,generated_at:asOf+'T23:00:00Z',assets:[stock('AAA'),stock('BBB')],macro:[]},
  {horizon:1,seed:1,model:'gbm',volatilityMode:'legacy',uncertainFundamentals:false,macroRegimes:[BASE_REGIME],mandate:{minimumCash:.8},execution:{spreadBps:0,slippageBps:0}}, {}, {maxPositions:2,maxCorrelation:1});
 const sample=generatePaths(x,200,17,4),index=s=>x.assets.findIndex(a=>a.symbol===s);
 for(let i=0;i<x.assets.length;i++) for(let p=0;p<sample.paths;p++) for(let t=0;t<=sample.steps;t++)
  sample.gross[i][p*(sample.steps+1)+t]=1+(terminal(x.assets[i].symbol,p)-1)*t/sample.steps;
 const w=x.assets.map((a,i)=>i===index('CASH')?.8:i===index('AAA')?.2:0);
 const positions=[{symbol:'CASH',weight:.8},{symbol:'AAA',weight:.2}];
 const plan=tradePlan(x.assets,positions,x.current.positions,x.current.capital,x.costs);
 return {x,sample,index,initial:{weights:w,positions,plan,
  metrics:evaluatePaths(w,sample,{capital:x.current.capital,cost:plan.total}),feasible:true,kind:'active'}};
}
const noise=p=>(p%2?1:-1)*.05;

test('a significantly better instrument replaces a holding when positions are full',()=>{
 const {x,sample,index,initial}=fixture((s,p)=>s==='CASH'?1:s==='AAA'?1.02+noise(p):1.12+noise(p));
 assert.ok(validWeights(initial.weights,x));
 const r=reviewSubstitutions(initial,x,sample,sample);
 assert.ok(Math.abs(r.best.weights[index('BBB')]-.2)<1e-10);
 assert.equal(r.best.weights[index('AAA')],0);
 assert.equal(r.audit.accepted[0].from,'AAA');
 assert.equal(r.audit.accepted[0].to,'BBB');
 assert.equal(r.audit.accepted[0].full,true);
 assert.ok(r.audit.accepted[0].z>=SUBSTITUTION_Z);
 assert.ok(r.best.metrics.score>initial.metrics.score);
});

test('statistically equivalent alternatives do not add trades',()=>{
 // BBB is better on average by a hair, inside Monte Carlo noise.
 const {x,sample,index,initial}=fixture((s,p)=>s==='CASH'?1:s==='AAA'?1.05+noise(p):1.0502+noise(p+1));
 const r=reviewSubstitutions(initial,x,sample,sample);
 assert.deepEqual(r.best.weights,initial.weights);
 assert.equal(r.audit.accepted.length,0);
 assert.equal(r.audit.status,'no_significant_improvement');
 assert.equal(r.audit.closestRejected.to,'BBB');
 assert.ok(r.audit.closestRejected.z<SUBSTITUTION_Z);
 assert.equal(r.best.weights[index('BBB')],0);
});

test('shortfall counts paths that trail the bill at the cut, or a better declared cash yield',()=>{
 const {x,sample,index,initial}=fixture((s,p)=>s==='CASH'?1:s==='AAA'?1.02+noise(p):1);
 const opts={capital:x.current.capital,cost:initial.plan.total};
 // Portfolio returns +1.4% or -0.6%: half lose, all trail a 4% bill.
 const bill=evaluatePaths(initial.weights,{...sample,riskFreeRate:.04},opts);
 assert.equal(bill.lossProbability,.5);
 assert.equal(bill.shortfallProbability,1);
 assert.equal(bill.shortfallBasis,'bill');
 assert.equal(bill.shortfallRate,.04);
 // A 1% bill: only the losing half trails it.
 assert.equal(evaluatePaths(initial.weights,{...sample,riskFreeRate:.01},opts).shortfallProbability,.5);
 const declared=evaluatePaths(initial.weights,{...sample,riskFreeRate:.01,policy:{...sample.policy,cashYield:.05}},opts);
 assert.equal(declared.shortfallBasis,'cash');
 assert.equal(declared.shortfallRate,.05);
 const none=evaluatePaths(initial.weights,{...sample,riskFreeRate:null},opts);
 assert.equal(none.shortfallProbability,null);
 assert.equal(index('CASH')>=0,true);
});

test('independent searches are reconciled on common paths: equivalent winners, least turnover, overlap',()=>{
 const {snapshot,settings,rules}=universe();
 const proposal=(positions,status='proposed')=>({status,positions,diagnostics:{},search:{}});
 const aaa=proposal([{symbol:'CASH',weight:.8},{symbol:'AAA',weight:.2}]);
 const bbb=proposal([{symbol:'CASH',weight:.8},{symbol:'BBB',weight:.2}]);
 const cash=proposal([{symbol:'CASH',weight:1}]);
 // AAA and BBB share fundamentals: equivalent within noise, same turnover,
 // so the higher common utility wins. All-cash trades least but is
 // significantly worse, so it cannot win the turnover tie-break.
 const r=reconcileStarts(snapshot,settings,{},rules,[aaa,bbb,cash],400);
 const st=r.diagnostics.stability;
 const chosen=st.winners.find(w=>w.chosen);
 assert.equal(chosen.z,0);
 assert.equal(r.positions,chosen.positions);
 assert.notEqual(r.positions,cash.positions);
 assert.ok(st.winners.filter(w=>w!==chosen&&w.equivalent).every(w=>w.z<SUBSTITUTION_Z));
 assert.equal(st.starts,3);
 assert.equal(st.equivalent,1);
 assert.equal(st.worse,1);
 assert.ok(Math.abs(st.minimumOverlap-.8)<1e-12); // the all-cash winner (overlap 0.8 too) is excluded as worse
 assert.equal(st.level,'high');
 const byLast=st.winners.at(-1);
 assert.equal(byLast.equivalent,false);
 assert.ok(byLast.z>SUBSTITUTION_Z);
 assert.deepEqual(st.winners.map(w=>w.seed),startSeeds(1,3));
 assert.equal(r.search.starts,3);
 // A single usable start passes through untouched.
 assert.equal(reconcileStarts(snapshot,settings,{},rules,[aaa,{status:'infeasible'}],400),aaa);
 assert.equal(startSeeds(20261024,3)[0],20261024);
});
