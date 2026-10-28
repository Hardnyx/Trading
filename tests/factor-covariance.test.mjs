import test from "node:test";
import assert from "node:assert/strict";
import { marketFactorCovariance, conditionalFactorization, factorizeStressedCovariance } from "../dist/assets/js/factor-covariance.mjs";
import { cholesky } from "../dist/assets/js/risk-math.mjs?v=0.35.0";
import { updateEwmaVariance, conditionalRisk } from "../dist/assets/js/conditional-risk.mjs";

function histories() {
  const prices={SPY:100,AAA:100,BBB:100,CASH:1};
  const histories=Object.fromEntries(Object.keys(prices).map(k=>[k,[]]));
  for(let t=0;t<360;t++){
    const day=new Date(Date.UTC(2025,0,1)+t*86400000).toISOString().slice(0,10);
    const market=.006*Math.sin(1.13*t)+.003*Math.cos(.41*t);
    const events={SPY:market,
      AAA:1.2*market+.004*Math.sin(1.7*t),
      BBB:-.4*market+.003*Math.cos(1.93*t),CASH:0};
    for(const symbol of Object.keys(prices)){
      prices[symbol]*=Math.exp(events[symbol]);
      histories[symbol].push({date:day,close:prices[symbol],adj_close:prices[symbol]});
    }
  }
  const assets=Object.entries(histories).map(([symbol,history])=>({
    symbol,history,type:symbol==="CASH"?"cash":"etf",
    price_date:history.at(-1).date,price:history.at(-1).adj_close,
  }));
  return assets;
}
test("dated market factor plus residual covariance exactly reconstructs TOTAL risk",()=>{
  const all=histories(), asOf=all[0].price_date;
  const chosen=all.filter(a=>a.symbol!=="SPY");
  const model=marketFactorCovariance(chosen,all,asOf);
  assert.equal(model.available,true);
  assert.ok(model.observations>=126);
  assert.equal(model.inputEnd,asOf);
  cholesky(model.residualCovariance);
  for(let i=0;i<chosen.length;i++)for(let j=0;j<chosen.length;j++){
    const combined=model.residualCovariance[i][j]+model.loading[i]*model.loading[j];
    assert.ok(Math.abs(combined-model.covariance[i][j])<1e-10);
  }
  const adjusted=conditionalFactorization(model,[1.35,.8,1]);
  cholesky(adjusted.residualCovariance);
  for(let i=0;i<chosen.length;i++)for(let j=0;j<chosen.length;j++){
    const combined=adjusted.residualCovariance[i][j]+adjusted.loading[i]*adjusted.loading[j];
    assert.ok(Math.abs(combined-model.covariance[i][j]*[1.35,.8,1][i]*[1.35,.8,1][j])<1e-10);
  }
});
test("factor calculation refuses missing or future-only SPY, no fabricated beta",()=>{
  const all=histories(), asOf=all[0].price_date;
  assert.equal(marketFactorCovariance(all.slice(1),all.slice(1),asOf).available,false);
  assert.equal(marketFactorCovariance(all.slice(1),all,"2024-12-31").available,false);
});
test("unaccepted assets really use a recursive daily EWMA, asymmetric GJR is separate",()=>{
  const h=.00012,negative=-.07,lambda=.94;
  const shock=updateEwmaVariance(h,negative,lambda);
  assert.ok(shock>h);
  const calm=updateEwmaVariance(shock,0,lambda);
  assert.ok(calm<shock);
  const risk=conditionalRisk([{symbol:"AAA"},{symbol:"BBB"}],
    [[.04,.01],[.01,.06]],
    {volatilityMode:"ewma",lambda});
  assert.equal(risk.active,0);
  assert.equal(risk.dynamic,true);
  assert.equal(risk.innovationLaw,"gaussian-factor-residual");
  assert.equal(risk.studentNu,null);
  assert.equal(risk.multipliers.length,2);
});
test("factorization is unbiased to a standalone sector proxy's absence",()=>{
  const all=histories(), asOf=all[0].price_date;
  const sel=all.filter(a=>["SPY","AAA"].includes(a.symbol));
  const model=marketFactorCovariance(sel,all,asOf);
  assert.equal(model.available,true);
  const spy=sel.findIndex(a=>a.symbol==="SPY");
  assert.ok(model.residualCovariance[spy][spy]<1e-12);
  cholesky(model.residualCovariance);
});

test("correlation stress refactors the simulated SPY exposure and leaves diagonals intact",()=>{
  const assets=[{symbol:"SPY"},{symbol:"AAA"},{symbol:"BBB"}];
  const original=[[.04,.01,-.005],[.01,.09,.002],[-.005,.002,.08]];
  const stressed=original.map((row,i)=>row.map((v,j)=>
    i===j?v:.8*v+.2*Math.sqrt(original[i][i]*original[j][j])));
  const base=factorizeStressedCovariance(original,assets);
  const altered=factorizeStressedCovariance(stressed,assets);
  assert.ok(Math.abs(base.loading[1]-altered.loading[1])>0.01);
  for(let i=0;i<assets.length;i++)for(let j=0;j<assets.length;j++)
    assert.ok(Math.abs(altered.loading[i]*altered.loading[j]+
      altered.residualCovariance[i][j]-stressed[i][j])<1e-10);
  assert.equal(factorizeStressedCovariance(stressed.slice(1).map(row=>row.slice(1)),assets.slice(1)),null);
  assert.throws(()=>factorizeStressedCovariance(stressed,assets.slice(1)),/dimensiones/);
});
