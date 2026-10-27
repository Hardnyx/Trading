import test from "node:test";
import assert from "node:assert/strict";
import {projectionCalendar,distributionAccounting,reconcileDistributionReturn,yearFraction}
  from "../dist/assets/js/distribution-ledger.mjs?v=0.27.0";
import {evaluatePaths} from "../dist/assets/js/path-model.mjs?v=0.27.0";
import {portfolioAttribution} from "../dist/assets/js/attribution.mjs?v=0.27.0";
import {mandate} from "../dist/assets/js/policy.mjs?v=0.27.0";
import {journalOrigin,appendForecast,evaluateJournal,freezeMaturedOutcomes} from "../dist/assets/js/journal.mjs?v=0.27.0";
import {maturityCheck} from "../scripts/seal_forecast.mjs";

function sample(mode="cash",tax=0,level=1){
 const asOf="2026-10-23",steps=52,paths=3,dt=1/52;
 const event={ex_date:"2026-11-02",pay_date:"2026-11-05",conditional:false};
 const asset={symbol:"SHY",type:"etf",price:100,dividend_per_share:4,
   distribution_calendar:{source_layer:"issuer-planned-calendar",published_on:"2026-10-21",
     observed_at:"2026-10-22T20:00:00Z",source_url:"https://issuer.example/calendar",
     frequency:12,coverage_start:"2026-01-01",coverage_end:"2028-12-31",records:[event]},
   issuer_distributions:{source_layer:"issuer",records:[{...event,currency:"USD",
     observed_at:"2026-10-22T20:00:00Z",amount_per_share:4}]}};
 const assets=[asset,{symbol:"CASH",type:"cash",price:1}],
   gross=assets.map((_,i)=>Float64Array.from({length:paths*(steps+1)},(_,k)=>
     i===0?level**((k%(steps+1))*dt):1));
 return {assets,gross,steps,paths,dt,asOf,informationAsOf:asOf,
   policy:mandate({dividendPolicy:mode,dividendWithholding:tax}),
   fx:new Float64Array(paths*(steps+1)).fill(1)};
}

test("issuer dates require original observation and full horizon coverage",()=>{
 const s=sample();
 assert.equal(projectionCalendar(s.assets[0],s.asOf,s.informationAsOf,1).available,true);
 assert.equal(projectionCalendar(s.assets[0],s.asOf,"2026-10-21",1).available,false);
 s.assets[0].distribution_calendar.coverage_end="2027-01-01";
 assert.equal(projectionCalendar(s.assets[0],s.asOf,s.asOf,1).available,false);
});

test('dated dividend cash starts earning interest on pay-date and pending claims earn none',()=>{
 const s=sample();s.policy.cashYield=.05;
 const ledger=distributionAccounting(s)[0],pay=yearFraction(s.asOf,'2026-11-05');
 assert.equal(ledger.cashAt(0,pay-1e-5),0);
 assert.ok(Math.abs(ledger.cashAt(0,pay)-.04)<1e-10);
 const r=evaluatePaths([1,0],s,{capital:10000});
 const interest=400*((1.05)**(1-pay)-1);
 assert.ok(Math.abs(r.medianTerminalWealth-(10000+interest))<1e-8);
 assert.ok(Math.abs(r.expectedCashInterest-interest)<1e-8);
 assert.ok(Math.abs(r.expectedNetDividendCash-400)<1e-8);
 assert.ok(Math.abs(portfolioAttribution(s.assets,[1,0],s,0,10000).meanReturn-r.meanReturn)<1e-10);
});

test('declared cash interest is not scored as an observed zero or as an observed contractual return',()=>{
 const cash={symbol:'CASH',type:'cash',history:[{date:'2025-10-27',adj_close:1},{date:'2026-10-27',adj_close:1}]};
 const policy={cashYield:.05,dividendPolicy:'cash'};
 assert.equal(reconcileDistributionReturn(cash,'2025-10-27','2026-10-27',policy).code,'missing_cash_interest');
 const entry={origin:{prospective:true,price_as_of:'2025-10-27',positions:[{symbol:'CASH',weight:1}],settings:{mandate:policy}},
  target_date:'2026-10-27',prediction:{mean:.05,p05:.05,p95:.05,lossProbability:0}};
 const result=evaluateJournal([entry],{price_as_of:'2026-10-27',assets:[cash]});
 assert.equal(result.count,0);assert.equal(result.rows[0].status,'unreconciled_cash_interest');
 assert.equal(freezeMaturedOutcomes([entry],{price_as_of:'2026-10-27',assets:[cash]})[0].outcome,undefined);
});
test("a right to a dividend preserves NAV at ex-date but cannot fund a withdrawal before pay-date",()=>{
 for(const [date,failure] of [["2026-11-03",1],["2026-11-06",0]]){
   const s=sample();s.policy.withdrawals=[{date,amount:100}];
   const r=evaluatePaths([1,0],s,{capital:10000,details:true});
   assert.equal(r.liquidityFailureProbability,failure);
   assert.ok(Math.abs(r.meanReturn)<1e-10);
   assert.ok(Math.abs(r.expectedNetDividendCash-400)<1e-8);
 }
});
test("dated cash and reinvestment match an explicit share ledger with withholding and pay-date price",()=>{
 for(const mode of ["cash","reinvest"]){
   const s=sample(mode,.3,1.2),r=evaluatePaths([1,0],s,{capital:10000});
   const ex=yearFraction(s.asOf,"2026-11-02"),pay=yearFraction(s.asOf,"2026-11-05");
   const divisor=1.2**ex/(1.2**ex-.04),priceAtPay=1.2**pay/divisor;
   const net=.04*.7;
   const expected=mode==="cash"?1.2/divisor+net-1:(1+net/priceAtPay)*1.2/divisor-1;
   assert.ok(Math.abs(r.meanReturn-expected)<1e-10);
   const a=portfolioAttribution(s.assets,[1,0],s,0,10000);
   assert.ok(Math.abs(a.meanReturn-r.meanReturn)<1e-10);
   assert.ok(Math.abs(a.cvar95-r.cvar95)<1e-10);
   assert.ok(Math.abs(r.expectedDividendWithholding-120)<1e-8);
 }
});
test("unpaid distributions at maturity remain receivables instead of liquid cash",()=>{
 const s=sample();
 const row=s.assets[0].distribution_calendar.records[0];
 row.ex_date="2027-10-20";row.pay_date="2027-10-27";
 s.assets[0].issuer_distributions.records[0]={...row,currency:"USD",amount_per_share:4,
   observed_at:"2026-10-22T20:00:00Z"};
 const r=evaluatePaths([1,0],s,{capital:10000});
 assert.ok(Math.abs(r.meanReturn)<1e-10);
 assert.ok(Math.abs(r.expectedDividendReceivable-400)<1e-8);
 assert.equal(r.expectedNetDividendCash,0);
});
test("buying on the ex-date does not acquire the earlier dividend claim",()=>{
 const s=sample();s.asOf="2026-11-02";s.informationAsOf=s.asOf;
 const r=evaluatePaths([1,0],s,{capital:10000});
 assert.equal(r.expectedNetDividendCash,0);
});
test("conditional calendar rows do not manufacture an undeclared year-end distribution",()=>{
 const s=sample();s.assets[0].distribution_calendar.records[0].conditional=true;
 delete s.assets[0].issuer_distributions;
 const r=evaluatePaths([1,0],s,{capital:10000});
 assert.equal(r.expectedGrossDistributions,0);
});
test("a declared amount beyond simulated asset value cannot create money",()=>{
 const s=sample();s.assets[0].issuer_distributions.records[0].amount_per_share=200;
 const r=evaluatePaths([1,0],s,{capital:10000});
 assert.ok(r.expectedGrossDistributions<=10000);
 assert.ok(Math.abs(r.meanReturn)<1e-9);
 assert.ok(r.dividendTiming[0].cappedEvents>0);
});

function realizedAsset(){
 return {symbol:"SHY",type:"etf",currency:"USD",splits:[],history:[
   {date:"2026-10-23",close:100,adj_close:100},
   {date:"2026-11-02",close:96,adj_close:100},
   {date:"2026-11-05",close:96,adj_close:100},
   {date:"2026-12-01",close:99,adj_close:103.125}],
   distribution_index:{complete_ex_date_index:true,currency:"USD",
     coverage_start:"2026-10-23",coverage_end:"2026-12-01",
     records:[{ex_date:"2026-11-02",amount_per_share:4}]},
   issuer_distributions:{source_layer:"issuer",source_url:"https://issuer.example",
     records:[{ex_date:"2026-11-02",pay_date:"2026-11-05",amount_per_share:4,currency:"USD"}]}};
}
test("realized return uses verified payments and the original share quantity, not adjusted-close cash reinvestment",()=>{
 const a=realizedAsset();
 const cash=reconcileDistributionReturn(a,"2026-10-23","2026-12-01",
   {dividendPolicy:"cash",dividendWithholding:.3});
 const reinvest=reconcileDistributionReturn(a,"2026-10-23","2026-12-01",
   {dividendPolicy:"reinvest",dividendWithholding:.3});
 assert.equal(cash.available,true);assert.equal(reinvest.available,true);
 assert.ok(Math.abs(cash.return-.018)<1e-12);
 assert.ok(Math.abs(reinvest.return-((1+2.8/96)*99/100-1))<1e-12);
});
test("unmatched dividends, missing payment dates, incomplete windows and splits block realized scores",()=>{
 for(const mutate of [a=>delete a.issuer_distributions,
   a=>a.issuer_distributions.records[0].amount_per_share=5,
   a=>a.distribution_index.coverage_start="2026-10-24",
   a=>a.splits=[{date:"2026-11-15",ratio:2}]]){
   const a=realizedAsset();mutate(a);
   assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01",{dividendPolicy:"cash"}).available,false);
 }
});

test("a matured sealed forecast scores a reconciled distribution ledger under its saved tax convention",()=>{
 const a=realizedAsset(),origin={schema_version:2,maturity_date:"2026-12-01",
   original_price_as_of:"2026-10-23",positions:[{symbol:"SHY",weight:1}],
   model_settings:{capital:10000,initial_cost:100,mandate:mandate({dividendPolicy:"cash",dividendWithholding:.3})},
   forecast:{probability_loss:.2,p05:-.02,p95:.02}};
 const r=maturityCheck(origin,{price_as_of:"2026-12-01",assets:[a]});
 assert.equal(r.status,"eligible_outcome_approximation");
 assert.ok(Math.abs(r.realized_under_model_conventions-.018)<1e-12);
 assert.ok(Math.abs(r.realized_after_initial_cost-((1.018)*.99-1))<1e-12);
 assert.equal(r.distribution_reconciliation.available,true);
});
test("local forecast outcomes freeze the reconciled cash evidence without rewriting the original",()=>{
 const a=realizedAsset(),policy=mandate({dividendPolicy:"cash",dividendWithholding:.3});
 const start={price_as_of:"2026-10-23",generated_at:"2026-10-23T22:00:00Z",
   assets:[{...a,price:100,price_date:"2026-10-23",history:[a.history[0]],
     issuer_distributions:null,distribution_index:null}]};
 const origin=journalOrigin(start,[{symbol:"SHY",weight:1}],{mandate:policy},{},{},"2026-10-24T01:00:00Z");
 const frozen=JSON.stringify(origin);
 const journal=appendForecast([],origin,{horizonYears:.1,meanReturn:.02,medianReturn:.02,
   p05:-.1,p95:.1,lossProbability:.2,settings:{model:"gbm",seed:1},drifts:[],policy});
 const future={price_as_of:"2026-12-01",generated_at:"2026-12-01T23:00:00Z",assets:[a]};
 const r=evaluateJournal(journal,future);
 assert.equal(r.count,1);assert.ok(Math.abs(r.rows[0].realized-.018)<1e-12);
 const saved=freezeMaturedOutcomes(journal,future);
 assert.equal(saved[0].outcome.distribution_reconciliation.evidence[0].events,1);
 assert.equal(JSON.stringify(origin),frozen);
});

test("observed Yahoo rounding reconciles with the precise issuer amount and rejects unexplained differences",()=>{
 const a=realizedAsset();
 a.distribution_index.source_url="https://finance.yahoo.com/quote/SHY/history/";
 a.distribution_index.records[0].amount_per_share=.263;
 a.issuer_distributions.records[0].amount_per_share=.262737;
 const result=reconcileDistributionReturn(a,"2026-10-23","2026-12-01",{dividendPolicy:"cash"});
 assert.equal(result.available,true);
 assert.equal(result.rounded_index_matches,1);
 assert.ok(Math.abs(result.cash-.262737/100)<1e-12);
 assert.ok(Math.abs(result.return-((99+.262737)/100-1))<1e-12);
 a.issuer_distributions.records[0].amount_per_share=.2621;
 assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01",{dividendPolicy:"cash"}).available,false);
 a.issuer_distributions.records[0].amount_per_share=.262737;
 a.distribution_index.source_url="https://other.example/history/";
 assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01",{dividendPolicy:"cash"}).available,false);
 a.distribution_index.source_url="https://finance.yahoo.com/quote/SHY/history/";
 a.distribution_index.records[0].amount_per_share=.26301;
 assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01",{dividendPolicy:"cash"}).available,false);
});

test("payment reinvestment uses the earliest eligible close even with unordered imported history",()=>{
 const a=realizedAsset(),policy={dividendPolicy:"reinvest",dividendWithholding:.3};
 const expected=reconcileDistributionReturn(a,"2026-10-23","2026-12-01",policy);
 a.history.reverse();
 const actual=reconcileDistributionReturn(a,"2026-10-23","2026-12-01",policy);
 assert.equal(actual.available,true);
 assert.equal(actual.return,expected.return);
 assert.ok(Math.abs(actual.return-((1+2.8/96)*99/100-1))<1e-12);
});

test("ambiguous prices and invalid reconciliation dates cannot produce realized scores",()=>{
 for(const mutate of [
   a=>a.history.push({...a.history[2],close:110}),
   a=>a.history[2].close=Infinity,
   a=>a.history[2].close=NaN,
   a=>a.history[2].close=0,
 ]){
   const a=realizedAsset();mutate(a);
   assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01",
     {dividendPolicy:"reinvest"}).available,false);
 }
 for(const [start,end] of [["2026-12-01","2026-10-23"],["2026-02-30","2026-12-01"],
   ["2026-10-23","invalid"]]){
   assert.equal(reconcileDistributionReturn(realizedAsset(),start,end).available,false);
   assert.equal(reconcileDistributionReturn({type:"cash"},start,end).available,false);
 }
});

test("a nonfinite adjusted close cannot certify the absence of distributions",()=>{
 const a=realizedAsset();
 a.distribution_index.records=[];
 a.issuer_distributions.records=[];
 a.history[0].adj_close=Infinity;
 assert.equal(reconcileDistributionReturn(a,"2026-10-23","2026-12-01").available,false);
});
