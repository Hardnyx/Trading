import test from 'node:test';
import assert from 'node:assert/strict';
import {FUND_POLICY,emptyFundState,fundRequest,overlap,rebalanceOrders} from '../dist/assets/js/fund-policy.mjs';
import {DEFAULT_COMPOSITION_RULES,validWeights} from '../dist/assets/js/composer.mjs';
import {riskOnlyModels} from '../dist/assets/js/robust-decision.mjs';
import {reviewFund,rollForward,hysteresisHurdle} from '../scripts/fund_review.mjs';

const history=(close,adj)=>[{date:'2026-11-12',close:close[0],adj_close:adj[0]},{date:'2026-11-13',close:close[1],adj_close:adj[1]}];
const snapshot=()=>({price_as_of:'2026-11-13',generated_at:'2026-11-13T22:00:00Z',macro:[],assets:[
  {symbol:'SPY',type:'etf',price:500,history:history([500,500],[490,500])},
  {symbol:'AGG',type:'etf',price:100,history:history([100,100],[100,100])}]});

test('fund policy is frozen, ETF-only and keeps the reference mandate untouched',()=>{
  assert.ok(Object.isFrozen(FUND_POLICY));
  assert.equal('minEquity' in DEFAULT_COMPOSITION_RULES,false);
  const state=emptyFundState(),request=fundRequest({price_as_of:'2026-11-13',generated_at:'2026-11-13T22:00:00Z',assets:[],macro:[]},state);
  assert.deepEqual(request.settings.purchaseTypes,['etf']);
  assert.deepEqual(request.settings.riskOnlyModels,['low_conviction']);
  assert.equal(request.rules.minEquity,.6);
  assert.equal(request.settings.account.enabled,true);
  assert.equal(request.settings.account.cash,FUND_POLICY.initialCapital);
  assert.throws(()=>fundRequest({assets:[]},{...state,policy:'otra'}),/otra política/);
});

test('the base model can never be demoted to a risk-only stress',()=>{
  assert.deepEqual([...riskOnlyModels({options:{}})],[]);
  assert.throws(()=>riskOnlyModels({options:{riskOnlyModels:['original']}}));
  assert.throws(()=>riskOnlyModels({options:{riskOnlyModels:['invented']}}));
});

test('the equity floor binds complete portfolios but not partial constructions',()=>{
  const x={rules:{...DEFAULT_COMPOSITION_RULES,minEquity:.6,maxEquity:.9,maxSector:1,maxGlobal:1,maxFund:1},
    assets:[{symbol:'CASH',type:'cash'}],buyAllowed:[true],requiredCash:0,covariance:[[0]],asOf:'2026-11-13'};
  assert.equal(validWeights([1],x),false);
  assert.equal(validWeights([1],{...x,partialConstruction:true}),true);
  assert.equal(validWeights([1],{...x,rules:{...x.rules,minEquity:0}}),true);
});

test('orders reach target weights from current holdings and report whole shares',()=>{
  const state={...emptyFundState(),cash:100000};
  const result=rebalanceOrders(snapshot(),state,[{symbol:'SPY',weight:.62},{symbol:'AGG',weight:.33},{symbol:'CASH',weight:.05}]);
  assert.equal(result.value,100000);
  assert.ok(Math.abs(result.positions.find(p=>p.symbol==='SPY').quantity-124)<1e-9);
  assert.equal(result.orders.find(o=>o.symbol==='AGG').target_whole_shares,330);
  assert.ok(Math.abs(result.cash-5000)<1e-6);
  const sold=rebalanceOrders(snapshot(),{...state,cash:0,positions:[{symbol:'AGG',quantity:1000}]},[{symbol:'SPY',weight:1}]);
  assert.equal(sold.orders.find(o=>o.symbol==='AGG').trade_shares,-1000);
});

test('distributions stay invested when holdings roll to the next cut',()=>{
  const state={...emptyFundState(),as_of:'2026-11-12',cash:0,positions:[{symbol:'SPY',quantity:10}]};
  const rolled=rollForward(state,snapshot());
  assert.ok(Math.abs(rolled.positions[0].quantity-10*(500/490))<1e-12);
  assert.equal(state.positions[0].quantity,10);
});

test('returning to a recently abandoned portfolio needs a doubled gain',()=>{
  const old=[{symbol:'SPY',weight:.6},{symbol:'AGG',weight:.4}],now=[{symbol:'QQQ',weight:.6},{symbol:'AGG',weight:.4}];
  const state={held:[{from:'2026-11-02',until:'2026-11-09',positions:old},{from:'2026-11-09',until:null,positions:now}]};
  assert.equal(overlap(old,now),.4);
  assert.deepEqual(hysteresisHurdle(state,old,now,'2026-11-13',300),{hurdle:600,revisits:'2026-11-02'});
  assert.deepEqual(hysteresisHurdle(state,old,now,'2026-12-31',300),{hurdle:300,revisits:null});
});

test('a review holds unless every decision model clears the hurdle',()=>{
  const proposal=(lower)=>()=>({status:'proposed',model_version:'test',positions:[{symbol:'SPY',weight:.95},{symbol:'CASH',weight:.05}],
    diagnostics:{robustDecision:{hurdle:250,models:[
      {id:'original',role:'decision',evidence:{gain:900,lowerGain:lower},failures:[]},
      {id:'low_conviction',role:'risk-only',evidence:{gain:-800,lowerGain:-900},failures:[]}]}}});
  const start=emptyFundState();
  const bought=reviewFund(snapshot(),start,{compose:proposal(400)});
  assert.equal(bought.record.status,'rebalance');
  assert.equal(bought.state.held.length,1);
  assert.equal(bought.state.inception,'2026-11-13');
  const kept=reviewFund(snapshot(),start,{compose:proposal(100)});
  assert.equal(kept.record.status,'hold');
  assert.equal(kept.state.cash,start.cash);
  assert.equal(kept.record.risk_only[0].model,'low_conviction');
});

test('the public fund summary reports holdings, equity share and the last decision',async()=>{
  const {publicFund}=await import('../scripts/fund_review.mjs');
  const {fundPanel,validFund}=await import('../dist/assets/js/ui/fund-view.mjs');
  const snap={price_as_of:'2026-11-13',assets:[{symbol:'SPY',type:'etf',name:'SPDR S&P 500',price:500},{symbol:'AGG',type:'etf',name:'iShares Core US Aggregate Bond',price:100}]};
  const state={...emptyFundState(),as_of:'2026-11-13',inception:'2026-11-13',cash:5000,positions:[{symbol:'SPY',quantity:130},{symbol:'AGG',quantity:300}]};
  const fund=publicFund(state,[{date:'2026-11-13',status:'rebalance',value:100000,reason:null,evidence:[],risk_only:[],orders:[]}],snap);
  assert.equal(fund.value,100000);
  assert.equal(fund.equity_weight,.65);
  assert.deepEqual(fund.rebalances,['2026-11-13']);
  assert.equal(fund.holdings[0].symbol,'SPY');
  assert.equal(validFund(fund),true);
  assert.equal(validFund({...fund,holdings:null}),false);
  assert.equal(fundPanel(null,snap),'');
});
