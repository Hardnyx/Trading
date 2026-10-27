import test from "node:test";
import assert from "node:assert/strict";
import { conditionalRisk, studentScale, updateGjrVariance, studentMarginal, studentUpperTail, normalUpperTail, updateTargetedVariance, updateEwmaVariance } from "../dist/assets/js/conditional-risk.mjs";
import { preparePaths, generatePaths } from "../dist/assets/js/path-model.mjs?v=0.27.0";
import { seededRandom, normalGenerator } from "../dist/assets/js/random.mjs?v=0.27.0";

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

test("Student-t marginal map matches reference quantiles and keeps unit variance",()=>{
  // Reference values: scipy t.ppf(norm.cdf(z), nu) * sqrt((nu-2)/nu).
  const reference={
    4.5:[[1,.8378958392],[2.326347874,2.6289085171],[3,4.4482219568],[5,30.6066561698]],
    8:[[1,.9236407074],[3,3.7036724252],[5,12.3404294918]],
  };
  for(const [nu,rows] of Object.entries(reference)){
    const law=studentMarginal(Number(nu));
    for(const [z,x] of rows){
      assert.ok(Math.abs(law(z)-x)<5e-6*Math.max(1,x),`nu=${nu} z=${z}: ${law(z)} vs ${x}`);
      assert.equal(law(-z),-law(z));
    }
    // E[T(Z)^2] by quadrature over the normal density.
    let second=0;
    for(let z=-8.5;z<=8.5;z+=.001)
      second+=law(z)**2*Math.exp(-z*z/2)/Math.sqrt(2*Math.PI)*.001;
    assert.ok(Math.abs(second-1)<2e-3,`variance ${second}`);
  }
  assert.ok(Math.abs(studentUpperTail(0,6)-.5)<1e-12);
  assert.ok(Math.abs(normalUpperTail(5)/2.866515718791939e-7-1)<2e-7);
  assert.throws(()=>studentMarginal(2),/Student-t/);
});

test("accepted GJR instruments get fat-tailed daily innovations; fallback stays Gaussian",()=>{
  const assets=[etf("AAA"),etf("BBB",2)];
  const fat={...accepted("AAA"),nu:4.5,alpha:0,gamma:0,beta:0,omega:1.8};
  const vol=sampleSource({AAA:fat,BBB:{...accepted("BBB"),status:"research_only"}});
  const inputs=preparePaths(assets,{
    asOf:DATE,informationAsOf:DATE,volatilityMode:"hybrid",volatilityData:vol,
    horizon:1,seed:20261025,
  },{},assets);
  assert.equal(inputs.conditional.active,1);
  assert.equal(inputs.conditional.innovationLaw,"student-t-marginals-gaussian-copula");
  const sample=generatePaths(inputs,400,91,252);
  const kurtosis=(i)=>{
    const r=[];
    for(let p=0;p<sample.paths;p++)for(let t=1;t<=sample.steps;t++){
      const o=p*(sample.steps+1)+t;
      r.push(Math.log(sample.gross[i][o]/sample.gross[i][o-1]));
    }
    const m=r.reduce((a,b)=>a+b,0)/r.length;
    const v=r.reduce((a,b)=>a+(b-m)**2,0)/r.length;
    return r.reduce((a,b)=>a+(b-m)**4,0)/r.length/v/v;
  };
  // Constant GJR variance isolates the innovation law: t(4.5) has theoretical
  // kurtosis 15. The EWMA fallback is Gaussian but its variance
  // clusters, so its kurtosis exceeds 3 for a different reason.
  const fat4=kurtosis(0), fallback4=kurtosis(1);
  assert.ok(fat4>7,`accepted kurtosis ${fat4}`);
  assert.ok(fat4>fallback4+2,`accepted ${fat4} vs fallback ${fallback4}`);
});

test("fallback variance reverts to its long-run level instead of carrying a spike",()=>{
  const longRun=.0001, spike=.0009;
  let targeted=spike, flat=spike;
  for(let day=0;day<1000;day++){
    // Feed each recursion its own expected squared innovation (e^2 = h).
    targeted=updateTargetedVariance(targeted,Math.sqrt(targeted),longRun,.94,.99);
    flat=updateEwmaVariance(flat,Math.sqrt(flat),.94);
  }
  // In expectation the flat EWMA keeps the spike; the targeted one returns to the long run.
  assert.ok(Math.abs(flat-spike)<1e-12,`flat ${flat}`);
  assert.ok(Math.abs(targeted-longRun)<1e-6,`targeted ${targeted}`);
  // Expected next variance equals the GARCH(1,1) mean: (1-phi)*LR + phi*h.
  const h=.0004, e=Math.sqrt(h);
  assert.ok(Math.abs(updateTargetedVariance(h,e,longRun,.94,.99)-(.01*longRun+.99*h))<1e-15);
  assert.throws(()=>updateTargetedVariance(h,e,longRun,.5,.3),/reversión/);
});

test("simulated fallback volatility moves toward the 500-session level",()=>{
  // Calm long history, then a violent last month: EWMA alone would carry it all year.
  const base=etf("AAA");
  base.history=base.history.map((row,t,all)=>({...row}));
  let close=100;
  base.history.forEach((row,t)=>{
    const sigma=t>=base.history.length-21?.04:.008;
    close*=Math.exp(sigma*Math.sin(t*12.9898)*1.4);
    row.close=row.adj_close=close;
  });
  base.price=close;
  const vol=sampleSource({AAA:{...accepted("AAA"),status:"research_only"}});
  const inputs=preparePaths([base],{asOf:DATE,informationAsOf:DATE,volatilityMode:"hybrid",
    volatilityData:vol,horizon:1,model:"gbm",macroRegimes:[{id:"base",label:"b",probability:1,earningsShift:0,multipleShift:0,rateShift:0,rateJumpBps:0}]},{},[base]);
  const lr=inputs.horizonVariance.longRunDaily[0];
  assert.ok(lr>0 && lr<inputs.covariance[0][0]/252,"spot EWMA must exceed the long-run level here");
  const terminalVol=(sample)=>{
    const r=[];for(let p=0;p<sample.paths;p++)r.push(Math.log(sample.gross[0][p*(sample.steps+1)+sample.steps]));
    const m=r.reduce((a,b)=>a+b,0)/r.length;return Math.sqrt(r.reduce((a,b)=>a+(b-m)**2,0)/(r.length-1));
  };
  const reverting=terminalVol(generatePaths(inputs,600,5,52));
  const flat=terminalVol(generatePaths({...inputs,horizonVariance:undefined},600,5,52));
  const spot=Math.sqrt(inputs.covariance[0][0]);
  assert.ok(reverting<flat,`reverting ${reverting} flat ${flat}`);
  assert.ok(reverting<spot && reverting>Math.sqrt(lr*252)*.8);
});
