import test from "node:test";
import assert from "node:assert/strict";
import { evaluatePaths } from "../dist/assets/js/path-model.mjs?v=0.8.2";
import { portfolioAttribution } from "../dist/assets/js/attribution.mjs?v=0.8.2";
import { annualDistributionYield, dividendStep } from "../dist/assets/js/cashflows.mjs?v=0.8.2";
import { mandate } from "../dist/assets/js/policy.mjs?v=0.8.2";

function fixture(dividendPolicy="cash",dividendWithholding=0){
 const steps=12,paths=100,dt=1/12;
 const stock={symbol:"AAA",type:"stock",price:100,dividend_per_share:4};
 const cash={symbol:"CASH",type:"cash",price:1,dividend_per_share:0};
 const assets=[stock,cash],gross=[new Float64Array(paths*(steps+1)),new Float64Array(paths*(steps+1))];
 for(let p=0;p<paths;p++)for(let t=0;t<=steps;t++){
   // Total return of 4% with no ex-dividend price change.
   gross[0][p*(steps+1)+t]=Math.pow(1.04,t/steps);
   gross[1][p*(steps+1)+t]=1;
 }
 return {assets,gross,dt,paths,steps,fx:new Float64Array(paths*(steps+1)).fill(1),
   policy:mandate({dividendPolicy,dividendWithholding}),
   asOf:"2026-10-23"};
}
test("Paid dividends are moved from total-return-adjusted shares to cash, never added twice",()=>{
 const cash=fixture("cash"),reinvest=fixture("reinvest");
 const w=[.5,.5];
 const a=evaluatePaths(w,cash,{capital:10000});
 const b=evaluatePaths(w,reinvest,{capital:10000});
 assert.equal(annualDistributionYield(cash.assets[0]),.04);
 assert.equal(dividendStep(1,1.04,.04,1,1).priceGross,1);
 assert.ok(a.expectedGrossDividendCash>195 && a.expectedGrossDividendCash<205);
 assert.equal(a.expectedGrossDividendCash,a.expectedNetDividendCash);
 assert.ok(a.meanReturn<=b.meanReturn+1e-8);
 assert.ok(b.meanReturn<.021);
 const attr=portfolioAttribution(cash.assets,w,cash,0,10000);
 assert.ok(Math.abs(attr.meanReturn-a.meanReturn)<1e-8);
 assert.ok(Math.abs(attr.cvar95-a.cvar95)<1e-8);
});
test("Assumed withholding reduces cash dividends and scenario total return",()=>{
 const free=evaluatePaths([.5,.5],fixture("cash",0),{capital:10000});
 const taxed=evaluatePaths([.5,.5],fixture("cash",.3),{capital:10000});
 assert.ok(taxed.expectedNetDividendCash<free.expectedNetDividendCash);
 assert.ok(taxed.meanReturn<free.meanReturn);
 assert.ok(taxed.expectedGrossDividendCash===free.expectedGrossDividendCash);
 const paid=fixture("cash",.3);
 assert.ok(Math.abs(portfolioAttribution(paid.assets,[.5,.5],paid,0,10000).meanReturn-taxed.meanReturn)<1e-8);
});
