import test from "node:test";
import assert from "node:assert/strict";
import { economicClass, exposureReport, actualHoldings, rawCorrelation, qualifiedOpportunity } from "../dist/assets/js/economic-exposure.mjs?v=0.8.1";
import { validWeights, DEFAULT_COMPOSITION_RULES } from "../dist/assets/js/composer.mjs?v=0.8.1";

test("Treasury funds aggregate despite having different tickers",()=>{
 const assets=[
  {symbol:"SHY",type:"etf",sector:"Treasuries cortos"},
  {symbol:"IEF",type:"etf",sector:"Treasuries intermedios"},
  {symbol:"TLT",type:"etf",sector:"Treasuries largos"},
  {symbol:"CASH",type:"cash",sector:"Efectivo"}];
 const result=exposureReport(assets,[.25,.20,.15,.40],"2026-10-23");
 assert.ok(Math.abs(result.sleeves.treasury-.60)<1e-8);
 assert.equal(economicClass(assets[0]),"treasury");
 const x={
  assets,asOf:"2026-10-23",
  rules:{...DEFAULT_COMPOSITION_RULES,maxTreasury:.5},
  buyAllowed:[true,true,true,true],
  covariance:assets.map((_,i)=>assets.map((_,j)=>i===j?.04:.001)),
  requiredCash:.05
 };
 assert.equal(validWeights([.25,.20,.15,.40],x),false);
 x.rules.maxTreasury=.65;
 assert.equal(validWeights([.25,.20,.15,.40],x),true);
});

test("Global cap never treats SHY differently without independent OOS evidence",()=>{
 const assets=[{symbol:"SHY",type:"etf",sector:"Treasuries cortos"},{symbol:"CASH",type:"cash",sector:"Efectivo"}];
 const x={assets,asOf:"2026-10-23",buyAllowed:[true,true],
  covariance:[[.002,0],[0,0]],requiredCash:.05,
  opportunityEvidence:{},
  rules:{...DEFAULT_COMPOSITION_RULES,reserveCap:1,maxFund:1,maxGlobal:.35,maxOpportunity:.5}};
 assert.equal(validWeights([.50,.50],x),false);
 assert.equal(validWeights([.35,.65],x),true);
 x.opportunityEvidence.SHY={source:"prospective-journal",validation:"self-reported",symbol:"SHY",
  as_of:"2026-10-23",oosMatured:200,netAlphaLower95:.03,costAdjustedExpectedAlpha:.04,
  factorOverlapReviewed:true,liquidityReviewed:true,parameterUncertaintyReviewed:true};
 assert.equal(qualifiedOpportunity(assets[0],x.opportunityEvidence.SHY,x.asOf),false);
 assert.equal(validWeights([.5,.5],x),false);
 x.opportunityEvidence.SHY.validation="independently-reviewed";
 assert.equal(validWeights([.5,.5],x),true);
});

test("Only dated issuer holdings count as issuer overlap, unknown is never silently diversified",()=>{
 const assets=[
 {symbol:"AAPL",type:"stock",sector:"Tecnología"},
 {symbol:"SPY",type:"etf",sector:"Índice amplio",
  holdings:{as_of:"2026-10-22",observed_at:"2026-10-22T20:00:00Z",source_url:"https://issuer.example",
            positions:[{symbol:"AAPL",weight:.3},{symbol:"MSFT",weight:.2}]}},
 {symbol:"CASH",type:"cash"}];
 let exp=exposureReport(assets,[.2,.3,.5],"2026-10-23");
 assert.ok(Math.abs(exp.issuers.AAPL-.29)<1e-8);
 assert.ok(exp.unknownHoldings.length>0);
 exp=exposureReport(assets,[.2,.3,.5],"2026-10-20");
 assert.equal(exp.issuers.AAPL,.2);
 assert.equal(actualHoldings(assets[1],"2026-10-20"),null);
 assert.ok(Math.abs(rawCorrelation([[.04,.018],[.018,.09]],0,1)-.3)<1e-8);
});

test("ETF holdings first observed Monday may inform Monday analysis with Friday price cut, not prior Friday forecasts",()=>{
 const fund={symbol:"SPY",type:"etf",sector:"Índice amplio",holdings:{
  as_of:"2026-10-22",observed_at:"2026-10-26T11:00:00Z",
  positions:[{symbol:"AAPL",weight:.08},{symbol:"MSFT",weight:.06}]}};
 assert.equal(actualHoldings(fund,"2026-10-23"),null);
 assert.ok(actualHoldings(fund,"2026-10-23","2026-10-26"));
 const previous=exposureReport([fund],[.35],"2026-10-23");
 const later=exposureReport([fund],[.35],"2026-10-23","2026-10-26",{"AAPL":"Tecnología","MSFT":"Tecnología"});
 assert.equal(previous.issuers.AAPL,undefined);
 assert.ok(Math.abs(later.issuers.AAPL-.028)<1e-10);
 assert.ok(Math.abs(later.sectors.Tecnología-.049)<1e-10);
});

test("fund overlap is a dated lower bound, with share classes consolidated",()=>{
 const a={symbol:"SPY",type:"etf",holdings:{
  as_of:"2026-10-22",observed_at:"2026-10-23T01:00:00Z",
  positions:[{symbol:"GOOG",weight:.10},{symbol:"AAPL",weight:.15}]}};
 const b={symbol:"VTI",type:"etf",holdings:{
  as_of:"2026-10-21",observed_at:"2026-10-22T01:00:00Z",
  positions:[{symbol:"GOOGL",weight:.08},{symbol:"AAPL",weight:.12}]}};
 const {knownFundOverlap}=await import("../dist/assets/js/economic-exposure.mjs?v=0.8.1");
 const f=knownFundOverlap(a,b,"2026-10-23");
 assert.equal(f.available,true);
 assert.ok(Math.abs(f.lowerBound-.20)<1e-10);
 const exp=exposureReport([a,b],[.35,.35],"2026-10-23");
 assert.ok(Math.abs(exp.issuers.GOOGL-.063)<1e-10);
 assert.equal(knownFundOverlap(a,b,"2026-10-21").available,false);
});

test("sector ETFs always use their advertised economic sector, even with known issuer holdings",()=>{
 const assets=[
  {symbol:"AAPL",type:"stock",sector:"Tecnología"},
  {symbol:"XLK",type:"etf",sector:"Tecnología",holdings:{
     as_of:"2026-10-20",observed_at:"2026-10-20T12:00:00Z",
     positions:[{symbol:"AAPL",weight:.15},{symbol:"MSFT",weight:.15}]}},
  {symbol:"CASH",type:"cash"}
 ];
 const result=exposureReport(assets,[.20,.25,.55],"2026-10-23");
 assert.ok(Math.abs(result.sectors.Tecnología-.45)<1e-8);
 assert.ok(Math.abs(result.issuers.AAPL-.2375)<1e-8);
});

test("aggregate equity cap prevents SHY reduction from forcing 60% risky stocks",()=>{
 const assets=[
  {symbol:"AAA",type:"stock",sector:"Tecnología"},
  {symbol:"BBB",type:"stock",sector:"Salud"},
  {symbol:"CCC",type:"stock",sector:"Industrial"},
  {symbol:"SHY",type:"etf",sector:"Treasuries cortos"},
  {symbol:"CASH",type:"cash",sector:"Efectivo"}
 ];
 const context={
  assets,asOf:"2026-10-23",buyAllowed:assets.map(()=>true),
  covariance:assets.map((_,i)=>assets.map((_,j)=>i===j?.04:0)),
  requiredCash:.05,rules:{...DEFAULT_COMPOSITION_RULES}
 };
 assert.equal(validWeights([.20,.20,.20,.35,.05],context),false);
 assert.equal(validWeights([.20,.15,.15,.35,.15],context),true);
 assert.ok(Math.abs(exposureReport(assets,[.20,.20,.20,.35,.05],"2026-10-23").sleeves.usEquity-.60)<1e-10);
});
