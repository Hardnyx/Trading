import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareComposition,validWeights} from '../dist/assets/js/composer.mjs?v=0.34.1';
import {selectReliableCandidate} from '../dist/assets/js/reliable-selection.mjs?v=0.34.1';
import {reviewRobustDecision,DECISION_EXPERIMENT_SEEDS} from '../dist/assets/js/robust-decision.mjs?v=0.34.1';

function fixture(){
  const cut='2026-10-23',history=Array.from({length:300},(_,k)=>({
    date:new Date(Date.parse(cut+'T12:00:00Z')-(299-k)*86400000).toISOString().slice(0,10),close:100,adj_close:100,volume:1e6}));
  const s={price_as_of:cut,generated_at:cut+'T23:00:00Z',macro:[{id:'DGS3MO',date:cut,value:4}],assets:[
    {symbol:'AAA',type:'stock',sector:'Industria',history,price:100,price_date:cut,
      assumptions:{growth:-.05,multiple:30,horizon:3,discount:.1},dividend_per_share:0,
      financials:{eps:{value:10,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}},
    {symbol:'SHY',type:'etf',sector:'Treasuries cortos',history,price:100,price_date:cut,
      bond_profile:{date:cut,yieldToMaturity:.045,duration:1,expenseRatio:0},dividend_per_share:0}]};
  return prepareComposition(s,{seed:19,horizon:1,volatilityMode:'ewma',research:{AAA:{confidence:1}},
    account:{enabled:true,cash:100000,positions:[]},execution:{minBenefit:100,spreadBps:0,slippageBps:0},
    macroRegimes:[{id:'base',probability:1,earningsShift:0,multipleShift:0,rateShift:0,rateJumpBps:0}]},
    {AAA:{multiple:30}},{maxGlobal:1,maxPosition:.5,maxTreasury:1,maxSector:1});
}
test('all-model selection can choose a sound alternative instead of rejecting only a base winner',()=>{
  const x=fixture(),before=JSON.stringify(x),bad=[{symbol:'AAA',weight:.5},{symbol:'CASH',weight:.5}],
    good=[{symbol:'SHY',weight:.5},{symbol:'CASH',weight:.5}];
  const base=reviewRobustDecision(x,bad,{paths:1000,validWeights});
  assert.equal(base.status,'rejected');
  const r=selectReliableCandidate(x,[bad,good],{paths:1000,validWeights});
  assert.deepEqual(r.positions,good);assert.equal(r.audit.status,'passed');
  assert.equal(r.selection.confirmationAttempts,1);
  assert.equal(new Set(Object.values(r.selection.seeds)).size,3);
  assert.equal(r.audit.seed,DECISION_EXPERIMENT_SEEDS.confirmation);
  assert.equal(JSON.stringify(x),before);
});
test('changing discovery seed or candidate order cannot reroll a fixed comparison',()=>{
  const x=fixture(),p=[{symbol:'SHY',weight:.5},{symbol:'CASH',weight:.5}],
    a=reviewRobustDecision(x,p,{paths:1000,validWeights});
  x.options={...x.options,seed:999};
  const b=reviewRobustDecision(x,p,{paths:1000,validWeights});
  assert.deepEqual(a,b);
  const first=selectReliableCandidate(x,[p,[...p].reverse()],{paths:1000,validWeights}),
    second=selectReliableCandidate(x,[[...p].reverse(),p],{paths:1000,validWeights});
  assert.deepEqual(first,second);
});
test('the incumbent and its zero-cost hold remain available when evidence does not clear the hurdle',()=>{
  const x=fixture();x.costs={...x.costs,minBenefit:10000};
  const r=selectReliableCandidate(x,[[{symbol:'SHY',weight:.5},{symbol:'CASH',weight:.5}]],{paths:1000,validWeights});
  assert.deepEqual(r.positions,[{symbol:'CASH',weight:1}]);assert.equal(r.plan.total,0);
  assert.equal(r.audit.status,'rejected');
});
