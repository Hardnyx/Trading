import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {FUND_V2,mixWeights,maxDrift,ordersFor,reviewStrategic,sessionsBetween} from '../dist/assets/js/strategic-fund.mjs';
import {validFund,personalMix} from '../dist/assets/js/ui/fund-view.mjs';
import {publicStrategicFund,emptyStrategicState,reviewV2} from '../scripts/fund_review.mjs';

const prices={VTI:400,VXUS:80,AGG:100};
const near=(a,b,e=1e-9)=>assert.ok(Math.abs(a-b)<e,`${a} != ${b}`);

test('fondo-v2 follows its registration exactly',()=>{
  const reg=JSON.parse(readFileSync(new URL('../docs/fondo-v2-registro.json',import.meta.url)));
  assert.ok(Object.isFrozen(FUND_V2));
  const w=Object.fromEntries(mixWeights(FUND_V2.mix).map(p=>[p.symbol,p.weight]));
  for(const [k,v] of Object.entries(reg.strategic_weights))near(w[k],v);
  assert.equal(FUND_V2.threshold,.05);
  assert.equal(reg.engine_tilts.status,'disabled');
  assert.equal(reg.post_hoc_changes_permitted,false);
});

test('a personal mix never produces negative or excess weights',()=>{
  for(const mix of [{equity:1,usShare:1,cash:.5},{equity:.2,usShare:0,cash:.9},{equity:-1,usShare:2,cash:NaN}]){
    const w=mixWeights(mix);
    assert.ok(w.every(p=>p.weight>=0));
    near(w.reduce((s,p)=>s+p.weight,0),1);
  }
  assert.equal(personalMix({mix:FUND_V2.mix,initial_capital:1e5},{equity:3}).equity,.7);
});

test('the fund holds inside the 5 pp band and rebalances beyond it',()=>{
  const target=mixWeights(FUND_V2.mix);
  const buy=ordersFor(prices,[],100000,target);
  near(buy.cash,5000,1e-6);
  const state={positions:buy.positions,cash:buy.cash};
  const hold=reviewStrategic({asOf:'2026-11-13',generatedOn:'2026-11-14',prices},state);
  assert.equal(hold.status,'hold');
  near(hold.drift,0,1e-9);
  const moved=reviewStrategic({asOf:'2026-11-13',generatedOn:'2026-11-14',prices:{...prices,VTI:600}},state);
  assert.equal(moved.status,'rebalance');
  assert.ok(moved.drift>.05);
  assert.ok(moved.orders.find(o=>o.symbol==='VTI').trade_shares<0);
  near(maxDrift([{symbol:'A',weight:.5},{symbol:'B',weight:.5}],[{symbol:'A',weight:.6},{symbol:'B',weight:.4}]),.1);
});

test('exception rules: no trades with missing or stale prices',()=>{
  const state={positions:[{symbol:'VTI',quantity:10}],cash:1000};
  const missing=reviewStrategic({asOf:'2026-11-13',generatedOn:'2026-11-14',prices:{VTI:400,AGG:100}},state);
  assert.equal(missing.status,'hold');
  assert.match(missing.reason,/VXUS/);
  const stale=reviewStrategic({asOf:'2026-11-06',generatedOn:'2026-11-14',prices},state);
  assert.equal(stale.status,'hold');
  assert.equal(sessionsBetween('2026-11-06','2026-11-14'),6);
});

test('whole shares never spend more than the fund holds',()=>{
  const plan=ordersFor(prices,[],12345,mixWeights(FUND_V2.mix));
  assert.ok(plan.whole_cash>=0);
  assert.ok(plan.orders.every(o=>o.target_whole_shares<=o.target_shares));
});

test('a review publishes a valid page summary and replays identically',()=>{
  const history=(price)=>[{date:'2026-11-13',close:price,adj_close:price}];
  const market={price_as_of:'2026-11-13',generated_at:'2026-11-14T00:00:00Z',assets:[
    {symbol:'VTI',type:'etf',name:'Vanguard Total Stock Market',price:400,history:history(400)},
    {symbol:'VXUS',type:'etf',name:'Vanguard Total International Stock',price:80,history:history(80)},
    {symbol:'AGG',type:'etf',name:'iShares Core U.S. Aggregate Bond',price:100,history:history(100)},
    {symbol:'SPY',type:'etf',price:500,history:history(500)},{symbol:'BIL',type:'etf',price:91,history:history(91)}]};
  const a=reviewV2(market,emptyStrategicState()),b=reviewV2(market,emptyStrategicState());
  assert.deepEqual(a.record,b.record);
  assert.equal(a.record.status,'rebalance');
  assert.equal(a.state.inception,'2026-11-13');
  const fund=publicStrategicFund(a.state,[a.record],market);
  assert.equal(validFund(fund),true);
  near(fund.equity_weight,.7,1e-6);
  const later={...market,price_as_of:'2026-11-16',generated_at:'2026-11-16T22:00:00Z',assets:market.assets.map(x=>({...x,
    history:[...x.history,{date:'2026-11-16',close:x.price*1.01,adj_close:x.price*1.01}],price:x.price*1.01}))};
  const again=reviewV2(later,a.state);
  assert.equal(again.record.status,'hold');
  assert.match(again.record.reason,/^Mantener/);
});

test('fondo-v3 uses only volatility known at the previous month end',async()=>{
  const {FUND_V3,timedEquityShare,volatilityForCut}=await import('../dist/assets/js/strategic-fund.mjs');
  assert.equal(FUND_V3.role,'shadow');
  assert.equal(timedEquityShare(.3,.15),.6);
  assert.equal(timedEquityShare(.1,.15),.9);
  near(timedEquityShare(.15,.15),.7);
  const days=[];
  for(let m=0;m<70;m++)for(let d=1;d<=20;d++){
    const y=2000+Math.floor(m/12),mm=String(m%12+1).padStart(2,'0');
    days.push({date:`${y}-${mm}-${String(d).padStart(2,'0')}`,r:(d%2?1:-1)*.01});
  }
  const cut='2005-10-15',base=volatilityForCut(days,cut);
  assert.equal(base.monthEnd,'2005-09-20');
  // A shock inside the cut's own month cannot change its target.
  const shocked=days.map(x=>x.date.startsWith('2005-10')?{...x,r:.2}:x);
  assert.deepEqual(volatilityForCut(shocked,cut),base);
  assert.equal(volatilityForCut(days.slice(0,600),'2002-06-15'),null);
});

test('fondo-v3 falls back to the static mix without enough history',async()=>{
  const {v3Mix}=await import('../scripts/fund_review.mjs');
  const r=v3Mix([{date:'2026-01-02',r:.01}],'2026-11-13');
  assert.equal(r.volatility,null);
  near(r.mix.equity,.7);
});
