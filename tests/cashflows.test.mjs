import test from "node:test";
import assert from "node:assert/strict";
import { evaluatePaths } from "../dist/assets/js/path-model.mjs?v=0.28.0";
import { portfolioAttribution } from "../dist/assets/js/attribution.mjs?v=0.28.0";
import { annualDistributionYield, dividendStep, cashGrowth, uniformCashGrowth } from "../dist/assets/js/cashflows.mjs?v=0.28.0";
import { mandate } from "../dist/assets/js/policy.mjs?v=0.28.0";

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

test('cash yield accrues only until each withdrawal, including two flows within one grid step',()=>{
 const s=fixture();s.asOf='2025-10-27';
 s.policy=mandate({cashYield:.05,withdrawals:[{date:'2026-04-27',amount:1000},{date:'2026-04-28',amount:200}]});
 for(let p=0;p<s.paths;p++)for(let t=0;t<=s.steps;t++)s.gross[1][p*(s.steps+1)+t]=cashGrowth(.05,t*s.dt);
 const r=evaluatePaths([0,1],s,{capital:10000});
 const year=day=>(Date.parse(day+'T12:00:00Z')-Date.parse(s.asOf+'T12:00:00Z'))/(365.25*86400000);
 const expected=10500-1000*cashGrowth(.05,1-year('2026-04-27'))-200*cashGrowth(.05,1-year('2026-04-28'));
 assert.ok(Math.abs(r.medianTerminalWealth-expected)<1e-8);
 assert.ok(Math.abs(r.meanReturn-.05)<1e-10);
 assert.ok(Math.abs(r.expectedCashInterest-(expected-8800))<1e-8);
 assert.equal(r.liquidityFailureProbability,0);
});

test('uniform dividend cash earns interest with the same accounting in valuation and attribution',()=>{
 const s=fixture();s.policy=mandate({cashYield:.05,dividendPolicy:'cash'});
 const r=evaluatePaths([1,0],s,{capital:10000});
 assert.ok(r.expectedCashInterest>0);
 assert.ok(r.meanReturn>evaluatePaths([1,0],fixture(),{capital:10000}).meanReturn);
 const attr=portfolioAttribution(s.assets,[1,0],s,0,10000);
 assert.ok(Math.abs(attr.meanReturn-r.meanReturn)<1e-10);
 assert.equal(uniformCashGrowth(.05,0,1),0);
});
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

function explicitPath(levels, dividendPolicy="cash", dividendWithholding=0) {
 const sample=fixture(dividendPolicy,dividendWithholding);
 sample.steps=levels.length-1;sample.dt=1/sample.steps;
 sample.gross=sample.assets.map((_,i)=>Float64Array.from(
   {length:sample.paths*levels.length},(_,k)=>i===0?levels[k%levels.length]:1));
 sample.fx=new Float64Array(sample.paths*levels.length).fill(1);
 return sample;
}
test("a single distribution conserves total return on rising and falling paths",()=>{
 for(const total of [.6,.9,1,1.3]) {
   const dist=dividendStep(1,total,.04,1,1);
   assert.ok(Math.abs(dist.priceGross+dist.grossCash-total)<1e-12);
   const r=evaluatePaths([1,0],explicitPath([1,total]),{capital:10000});
   assert.ok(Math.abs(r.meanReturn-(total-1))<1e-12);
 }
});
test("cash and taxed reinvestment reconcile with an explicit two-step share ledger",()=>{
 const levels=[1,1.25,.85],d=Math.sqrt(1.04)-1,capital=10000,tax=.3;
 for(const mode of ["cash","reinvest"]) {
   const s=explicitPath(levels,mode,tax);
   let shares=1,cash=0,grossPaid=0,netReinvested=0,withheld=0;
   for(let t=1;t<levels.length;t++) {
     const price=levels[t]/(1+d)**t;
     const gross=shares*price*d;
     grossPaid+=gross;withheld+=gross*tax;
     if(mode==="cash")cash+=gross*(1-tax);
     else {shares+=gross*(1-tax)/price;netReinvested+=gross*(1-tax);}
   }
   const wealth=shares*levels.at(-1)/(1+d)**2+cash;
   const r=evaluatePaths([1,0],s,{capital});
   assert.ok(Math.abs(r.meanReturn-(wealth-1))<1e-12);
   assert.ok(Math.abs(r.expectedGrossDistributions-capital*grossPaid)<1e-8);
   assert.ok(Math.abs(r.expectedDividendWithholding-capital*withheld)<1e-8);
   assert.ok(Math.abs(r.expectedNetReinvestedDividends-capital*netReinvested)<1e-8);
   const attribution=portfolioAttribution(s.assets,[1,0],s,0,capital);
   assert.ok(Math.abs(attribution.meanReturn-r.meanReturn)<1e-12);
   assert.ok(Math.abs(attribution.cvar95-r.cvar95)<1e-12);
 }
});
test("reinvestment deducts withholding and never supplies cash for a withdrawal",()=>{
 const free=evaluatePaths([1,0],fixture("reinvest",0),{capital:10000});
 const taxed=fixture("reinvest",.3);
 taxed.policy.withdrawals=[{date:"2027-01-23",amount:1}];
 const r=evaluatePaths([1,0],taxed,{capital:10000});
 assert.ok(r.meanReturn<free.meanReturn);
 assert.ok(r.expectedDividendWithholding>0);
 assert.equal(r.expectedNetDividendCash,0);
 assert.equal(r.liquidityFailureProbability,1);
});
