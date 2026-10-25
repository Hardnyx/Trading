import test from "node:test";
import assert from "node:assert/strict";
import { conditionalRisk, studentScale, updateGjrVariance } from "../dist/assets/js/conditional-risk.mjs";
import { preparePaths, generatePaths } from "../dist/assets/js/path-model.mjs?v=0.6.0";
import { seededRandom, normalGenerator } from "../dist/assets/js/random.mjs?v=0.6.0";

const DATE="2026-10-23";
function accepted(symbol,variance=1.8) {
  return {
    status:"accepted",last_price_date:DATE,fitted_through:DATE,
    omega:.06,alpha:.07,gamma:.1,beta:.78,nu:8,
    variance_next_pct2:variance,symbol,
    verification: {
      observations:126,qlike_improvement:.04,
      weekly_block_confidence:{lower_95_one_sided:.008},
    },
  };
}
function sampleSource(data={AAA:accepted("AAA")}) {
  return {
    schema_version:1,as_of:DATE,
    source_market_generated_at:"2026-10-25T00:00:00Z",
    no_news_attribution:true,instruments:data,
  };
}
function etf(symbol,j=1){
  const history=Array.from({length:520},(_,t)=>{
    const price=100*Math.exp(.0004*t+j*.012*Math.sin(t/9+j));
    return {
      date:new Date(Date.UTC(2025,5,22)+t*86400000).toISOString().slice(0,10),
      close:price,adj_close:price,volume:100000,
    };
  });
  const delta=Date.parse(DATE+"T00:00:00Z")-
    Date.parse(history.at(-1).date+"T00:00:00Z");
  history.forEach(row=>{row.date=new Date(Date.parse(row.date+"T00:00:00Z")+delta)
    .toISOString().slice(0,10)});
  return {symbol,type:"etf",name:symbol,sector:"Índice amplio",
    price:history.at(-1).close,price_date:DATE,history,financials:{}};
}
test("point-in-time acceptance rescales TOTAL covariance PSD and preserves fallback",()=>{
  const a=[{symbol:"AAA"},{symbol:"BBB"},{symbol:"CASH"}];
  const cov=[[.04,.018,0],[.018,.09,0],[0,0,0]];
  const result=conditionalRisk(a,cov,{
    asOf:DATE,volatilityMode:"hybrid",volatilityData:sampleSource(),
  });
  assert.equal(result.enabled,true);
  assert.equal(result.active,1);
  assert.equal(result.fallback,2);
  assert.equal(result.fits[1],null);
  assert.ok(result.covariance[0][0]>cov[0][0]);
  assert.equal(result.covariance[1][1],cov[1][1]);
  assert.ok(result.covariance[0][1]**2<=result.covariance[0][0]*result.covariance[1][1]);
  assert.equal(result.covariance[1][2],0);
});
test("stale, unevaluated or malformed models never enter simulation",()=>{
  const cov=[[.02]];
  assert.equal(conditionalRisk([{symbol:"AAA"}],cov,{
    asOf:"2026-10-22",volatilityData:sampleSource(),
  }).enabled,false);
  assert.equal(conditionalRisk([{symbol:"AAA"}],cov,{
    asOf:DATE,volatilityData:sampleSource({AAA:{...accepted("AAA"),status:"research_only"}}),
  }).enabled,false);
  assert.equal(conditionalRisk([{symbol:"AAA"}],cov,{
    asOf:DATE,volatilityMode:"ewma",volatilityData:sampleSource(),
  }).enabled,false);
});
test("bad-news asymmetry updates variance without retrospectively excusing an error",()=>{
  const fit=accepted("AAA");
  const h=.0002;
  assert.ok(updateGjrVariance(fit,h,-.05)>updateGjrVariance(fit,h,.05));
  assert.ok(updateGjrVariance(fit,h,-.05)>0);
});
test("shared Student-t radial mixture is standardized in squared expectation",()=>{
  const rng=seededRandom(8371),normal=normalGenerator(rng);
  let second=0;
  for(let i=0;i<14000;i++){
    const r=studentScale(8,rng,normal);
    second+=r*r;
  }
  assert.ok(Math.abs(second/14000-1)<.09);
});
test("new GJR daily simulation respects reproducibility and disables generic Merton jumps",()=>{
  const assets=[etf("AAA"),etf("BBB",2)];
  const vol=sampleSource({AAA:accepted("AAA"),BBB:{...accepted("BBB"),status:"research_only"}});
  const inputs=preparePaths(assets,{
    asOf:DATE,informationAsOf:DATE,
    model:"merton",volatilityMode:"hybrid",volatilityData:vol,
    horizon:.25,paths:100,seed:20261025,
  },{},assets);
  assert.equal(inputs.conditional.active,1);
  const p=generatePaths(inputs,100,23,52);
  const q=generatePaths(inputs,100,23,52);
  assert.deepEqual(Array.from(p.gross[0]),Array.from(q.gross[0]));
  assert.ok([...p.gross[0]].every(x=>Number.isFinite(x)&&x>0));
  const alt=structuredClone(inputs);
  alt.options.jumpIntensity=4;
  alt.options.jumpMean=-.75;
  assert.deepEqual(Array.from(generatePaths(alt,100,23,52).gross[0]),
    Array.from(p.gross[0]));
  const ewma=preparePaths(assets,{
    asOf:DATE,informationAsOf:DATE,volatilityMode:"ewma",
  },{},assets);
  assert.equal(ewma.conditional.enabled,false);
});

test("hybrid without validated GJR cannot revert to generic Merton jumps",()=>{
  const assets=[etf("AAA"),etf("BBB",2)];
  const unavailable=sampleSource({
    AAA:{...accepted("AAA"),status:"research_only"},
    BBB:{...accepted("BBB"),status:"research_only"},
  });
  const base={asOf:DATE,informationAsOf:DATE,model:"merton",horizon:.25,
    seed:100,volatilityData:unavailable};
  const hybrid=preparePaths(assets,{...base,volatilityMode:"hybrid"},{},assets);
  assert.equal(hybrid.conditional.active,0);
  assert.equal(hybrid.conditional.dynamic,true);
  const a=generatePaths(hybrid,100,37,52);
  const larger=structuredClone(hybrid);
  larger.options.jumpIntensity=4;
  larger.options.jumpMean=-.7;
  assert.deepEqual(Array.from(a.gross[0]),
    Array.from(generatePaths(larger,100,37,52).gross[0]));
  const explicit=preparePaths(assets,{...base,volatilityMode:"legacy"},{},assets);
  assert.equal(explicit.conditional.dynamic,false);
  assert.equal(explicit.conditional.enabled,false);
  assert.notDeepEqual(Array.from(a.gross[0]),
    Array.from(generatePaths(explicit,100,37,52).gross[0]));
});
