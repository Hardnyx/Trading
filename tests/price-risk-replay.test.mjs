import test from 'node:test';
import assert from 'node:assert/strict';
import {replayInputs,runPriceRiskReplay} from '../scripts/price_risk_replay.mjs';
const protocol={id:'test',symbols:['SPY','AAA'],minimumTraining:20,lookback:500,paths:100,
  seed:17,lead:2,horizons:[1,5],models:['targeted_ewma','dynamic_ewma','flat_ewma'],
  baskets:{current_exposure:{AAA:.5,CASH:.5}}};
function fixture(){
  const history=Array.from({length:100},(_,i)=>({date:new Date(Date.UTC(2026,0,i+1)).toISOString().slice(0,10),
    close:100*Math.exp(.001*i+.01*Math.sin(i)),adj_close:100*Math.exp(.001*i+.01*Math.sin(i)),volume:1e6}));
  return {price_as_of:history.at(-1).date,assets:['SPY','AAA'].map(symbol=>({symbol,type:'etf',sector:'Index',history}))};
}
test('past risk inputs are invariant to future prices, contemporary accounting facts and fit labels',()=>{
  const m=fixture(),cut='2026-02-28',before=JSON.stringify(m),a=replayInputs(m.assets,cut,protocol),future=structuredClone(m);
  for(const asset of future.assets){
    for(const row of asset.history)if(row.date>cut){row.adj_close*=1000;row.close*=1000;}
    asset.price=1e9;asset.bond_profile={yieldToMaturity:100};
    asset.financials={eps:{value:1e8,filed:'2026-01-01'}};
    asset.volatility={status:'accepted',variance:1e6};
  }
  assert.deepEqual(replayInputs(future.assets,cut,protocol),a);
  assert.ok(a.conditional.fits.every(f=>f===null));assert.equal(JSON.stringify(m),before);
});
test('reconstruction scores the original future dates and keeps targets and baseline pairs intact',()=>{
  const m=fixture(),r=runPriceRiskReplay(m,{protocol});
  assert.ok(r.records.length>0);assert.equal(r.prospective,false);assert.equal(r.production_eligible,false);
  for(const row of r.records){
    const dates=m.assets[0].history.map(p=>p.date),i=dates.indexOf(row.cut);
    assert.equal(row.origin_date,dates[i+2]);assert.equal(row.maturity_date,dates[i+2+row.horizon]);
    const p=m.assets[0].history.find(p=>p.date===row.origin_date).adj_close,
      q=m.assets[0].history.find(p=>p.date===row.maturity_date).adj_close;
    assert.ok(Math.abs(row.realized-(q/p-1)*(row.target.startsWith('PORTFOLIO:')?.5:1))<1e-12);
    assert.equal(r.records.filter(a=>a.cut===row.cut&&a.horizon===row.horizon&&a.target===row.target).length,3);
  }
});
test('a missing original outcome stops the reconstruction instead of shifting its maturity',()=>{
  const m=fixture();m.assets[1]={...m.assets[1],history:m.assets[1].history.filter(p=>p.date!=='2026-02-03')};
  assert.throws(()=>runPriceRiskReplay(m,{protocol}),/Missing original outcome/);
});
