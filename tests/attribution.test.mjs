import test from "node:test";
import assert from "node:assert/strict";
import { portfolioAttribution } from "../dist/assets/js/attribution.mjs?v=0.24.0";

test("additive expected return and ES reconcile with financing costs",()=>{
  const assets=[{symbol:"SHY"},{symbol:"STOCK"}];
  const paths=100, steps=1;
  const gross=[new Float64Array(paths*2),new Float64Array(paths*2)];
  for(let p=0;p<paths;p++){
    gross[0][2*p]=1; gross[0][2*p+1]=1.04;
    gross[1][2*p]=1; gross[1][2*p+1]=p<10?.65:1.2;
  }
  const sample={
    assets, gross, steps, paths,
    policy:{referenceCurrency:"USD",fxSpot:1,fxAnnualChange:0,
            fxVolatility:0,monthlyWithdrawal:0,withdrawals:[]}
  };
  const a=portfolioAttribution(assets,[.5,.5],sample,50,10000);
  assert.equal(a.available,true);
  assert.equal(a.scenarios,100);
  assert.equal(a.contributions.length,2);
  assert.ok(a.cvar95>0);
  assert.ok(Math.abs(a.rawTailLoss-a.cvar95)<1e-12);
  assert.ok(Math.abs(
    a.contributions.reduce((x,v)=>x+v.expectedReturnContribution,0)-
    a.costLoss-a.meanReturn)<1e-10);
  assert.ok(Math.abs(
    a.contributions.reduce((x,v)=>x+v.leftTailLossContribution,0)+
    a.costLoss-a.cvar95)<1e-10);
  sample.policy.fxVolatility=.1;
  assert.equal(portfolioAttribution(assets,[.5,.5],sample,50,10000).available,false);
});
