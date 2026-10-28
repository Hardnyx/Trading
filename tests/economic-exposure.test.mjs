import test from "node:test";
import assert from "node:assert/strict";
import { economicClass, exposureReport, actualHoldings, rawCorrelation, qualifiedOpportunity, holdingsOverlap, knownFundOverlap } from "../dist/assets/js/economic-exposure.mjs?v=0.30.0";
import { readFileSync } from "node:fs";
import { validWeights, DEFAULT_COMPOSITION_RULES } from "../dist/assets/js/composer.mjs?v=0.30.0";

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

function constraintContext(assets,rules={}) {
 return {assets,asOf:"2026-10-23",informationAsOf:"2026-10-26",
   buyAllowed:assets.map(()=>true),requiredCash:0,
   covariance:assets.map((_,i)=>assets.map((_,j)=>i===j?.04:0)),
   rules:{...DEFAULT_COMPOSITION_RULES,...rules}};
}
const holdings=positions=>({as_of:"2026-10-22",observed_at:"2026-10-23T01:00:00Z",positions});
test("every published ETF has an economic group, including the expanded catalog",()=>{
 const snapshot=JSON.parse(readFileSync(new URL("../dist/data/market.json",import.meta.url)));
 assert.deepEqual(snapshot.assets.filter(a=>a.type==="etf" &&
   economicClass(a)==="unclassified-etf").map(a=>a.symbol),[]);
 const assets=[{symbol:"VGSH",type:"etf"},{symbol:"VGIT",type:"etf"},
   {symbol:"CASH",type:"cash"}];
 assert.equal(validWeights([.35,.35,.3],constraintContext(assets)),false);
 const equity=[{symbol:"VUG",type:"etf"},{symbol:"SCHD",type:"etf"},
   {symbol:"CASH",type:"cash"}];
 assert.equal(validWeights([.3,.3,.4],constraintContext(equity)),false);
});

test('world ETFs include US markets without pretending to know geographical or issuer weights',()=>{
 for(const symbol of ['VT','ACWI','URTH'])assert.equal(economicClass({symbol,type:'etf'}),'global-equity');
 for(const symbol of ['ACWX','SPDW','SPEM'])assert.equal(economicClass({symbol,type:'etf'}),'international-equity');
 for(const symbol of ['SCHB','ITOT','SCHX','VV','VO','VB','IJR','IJH','IWB','IWF','IWD','VBR','VOE','VOT','VBK','SPSM','SPTM'])
  assert.equal(economicClass({symbol,type:'etf'}),'us-equity');
 const report=exposureReport([{symbol:'VT',type:'etf'}],[1],'2026-10-26');
 assert.equal(report.sleeves.globalEquity,1);
 assert.equal(report.unclassifiedIssuerWeight,1);
 assert.deepEqual(report.issuers,{});
});
test("direct and ETF share classes share the same issuer limit",()=>{
 const assets=[{symbol:"GOOGL",type:"stock",sector:"Comunicación"},
   {symbol:"QQQ",type:"etf",holdings:holdings([{symbol:"GOOG",weight:.15},
     {symbol:"GOOGL",weight:.15},{symbol:"OTHER",weight:.7}])},
   {symbol:"CASH",type:"cash"}];
 const context=constraintContext(assets,{maxSector:1,maxPosition:.2});
 const e=exposureReport(assets,[.15,.2,.65],context.asOf,context.informationAsOf);
 assert.ok(Math.abs(e.issuers.GOOGL-.21)<1e-12);
 assert.equal(validWeights([.15,.2,.65],context),false);
 assert.equal(validWeights([.10,.1,.8],context),true);
});
test("unidentified ETF tails consume concentration capacity instead of becoming free diversification",()=>{
 const assets=[{symbol:"AAA",type:"stock",sector:"Tecnología"},
   {symbol:"SPY",type:"etf"},{symbol:"CASH",type:"cash"}];
 const x=constraintContext(assets,{maxSector:1});
 assert.equal(validWeights([.15,.1,.75],x),false);
 assert.equal(validWeights([.10,.1,.8],x),true);
 const e=exposureReport(assets,[.15,.1,.75],x.asOf,x.informationAsOf);
 assert.ok(Math.abs(e.issuerUpperBounds.AAA-.25)<1e-12);
 assert.equal(e.issuers.AAA,.15);
 assert.equal(e.unclassifiedIssuerWeight,.1);
});
test("unknown sector classifications and stale holdings cannot bypass a sector budget",()=>{
 const assets=[{symbol:"AAA",type:"stock",sector:"Tecnología"},
   {symbol:"SPY",type:"etf",holdings:holdings([
     {symbol:"BBB",weight:.5},{symbol:"CCC",weight:.5}])},
   {symbol:"CASH",type:"cash"}];
 const x=constraintContext(assets,{maxSector:.25,maxPosition:.4});
 assert.equal(validWeights([.15,.2,.65],x),false);
 x.securitySectors={BBB:"Salud",CCC:"Industrial"};
 assert.equal(validWeights([.15,.2,.65],x),true);
 assets[1].holdings.as_of="2026-01-01";
 assert.equal(actualHoldings(assets[1],x.asOf,x.informationAsOf),null);
 assert.equal(validWeights([.15,.2,.65],x),false);
 assets[1].holdings.as_of="2026-02-31";
 assert.equal(actualHoldings(assets[1],x.asOf,x.informationAsOf),null);
});
test("holdings overlap is observed shared issuer weight, distinct from correlation",()=>{
 const a={symbol:"SPY",type:"etf",holdings:holdings([
   {symbol:"AAPL",weight:.1},{symbol:"GOOG",weight:.1},{symbol:"AAA",weight:.8}])};
 const b={symbol:"QQQ",type:"etf",holdings:holdings([
   {symbol:"AAPL",weight:.2},{symbol:"GOOGL",weight:.2},{symbol:"BBB",weight:.6}])};
 const r=holdingsOverlap(a,b,"2026-10-23");
 assert.ok(Math.abs(r.knownOverlap-.2)<1e-12);
 assert.equal(r.shared.length,2);
 delete b.holdings;
 assert.equal(holdingsOverlap(a,b,"2026-10-23"),null);
});

test("high-yield and EM debt form a capped sub-sleeve of credit", async () => {
  const { exposureReport, RISKY_CREDIT } = await import("../dist/assets/js/economic-exposure.mjs?v=0.30.0");
  const { DEFAULT_COMPOSITION_RULES } = await import("../dist/assets/js/composer.mjs?v=0.30.0");
  const fund = (symbol) => ({ symbol, type: "etf" });
  const report = exposureReport([fund("EMB"), fund("HYG"), fund("LQD")], [.15, .1, .2], "2026-10-27");
  assert.ok(Math.abs(report.sleeves.riskyCredit - .25) < 1e-12);
  assert.ok(Math.abs(report.sleeves.credit - .45) < 1e-12);
  assert.ok(RISKY_CREDIT.has("JNK") && RISKY_CREDIT.has("BKLN") && !RISKY_CREDIT.has("LQD"));
  assert.equal(DEFAULT_COMPOSITION_RULES.maxRiskyCredit, .2);
});
