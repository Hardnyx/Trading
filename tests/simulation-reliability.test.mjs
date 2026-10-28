import test from 'node:test';
import assert from 'node:assert/strict';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {factorizeStressedCovariance} from '../dist/assets/js/factor-covariance.mjs?v=0.35.0';
import {studentMarginal,normalUpperTail} from '../dist/assets/js/conditional-risk.mjs?v=0.35.0';
import {cvarStandardError,probabilityUpperBound,riskSamplingEvidence} from '../dist/assets/js/simulation-evidence.mjs?v=0.35.0';

function fixture(stress=false){
  const assets=['BBB','SPY','AAA','CASH'].map(symbol=>({symbol,type:symbol==='CASH'?'cash':'stock',sector:symbol==='BBB'?'B':'A'})),
    covariance=[[.06,.02,.01,0],[.02,.04,.015,0],[.01,.015,.05,0],[0,0,0,0]],
    fits=assets.map(a=>a.symbol==='AAA'?{omega:.00003,alpha:.04,gamma:.03,beta:.88,nu:4.5,hInitial:.05/252}:null);
  return {assets,covariance,factorization:factorizeStressedCovariance(covariance,assets),
    conditional:{dynamic:true,fits},options:{horizon:.25,asOf:'2026-10-23',model:'gbm',
      innovationLaw:stress?'student-t-research':'gaussian',researchShadowMode:stress,
      mandate:{fxSpot:3.8,referenceCurrency:'PEN',fxConfirmed:true,fxVolatility:.1,fxMarketCorrelation:.3}},
    anchors:assets.map(a=>({symbol:a.symbol,sector:a.sector,annual:a.type==='cash'?0:.06,
      low:a.type==='cash'?0:-.08,high:a.type==='cash'?0:.2})),
    regimes:[{id:'base',probability:.8,earningsShift:0,multipleShift:0,rateShift:0,rateJumpBps:0},
      {id:'recession',probability:.2,earningsShift:-.1,multipleShift:-.1,rateShift:-.01,rateJumpBps:-50}]};
}
function reorder(x,indices){
  return {...x,assets:indices.map(i=>x.assets[i]),anchors:indices.map(i=>x.anchors[i]),
    covariance:indices.map(i=>indices.map(j=>x.covariance[i][j])),
    conditional:{...x.conditional,fits:indices.map(i=>x.conditional.fits[i])},
    factorization:{...x.factorization,loading:indices.map(i=>x.factorization.loading[i]),
      residualCovariance:indices.map(i=>indices.map(j=>x.factorization.residualCovariance[i][j]))}};
}
function compare(a,b){
  assert.deepEqual(a.scenarioCounts,b.scenarioCounts);assert.deepEqual(a.fx,b.fx);
  for(let i=0;i<a.assets.length;i++)assert.deepEqual(a.gross[i],b.gross[b.assets.findIndex(v=>v.symbol===a.assets[i].symbol)]);
}
test('permuting instruments or macro rows cannot reroll a fixed numerical experiment',()=>{
  for(const stress of [false,true]){
    const x=fixture(stress),before=JSON.stringify(x),a=generatePaths(x,150,919,52),
      y=reorder(x,[3,2,0,1]);y.regimes=[...x.regimes].reverse();
    compare(a,generatePaths(y,150,919,52));assert.equal(JSON.stringify(x),before);
  }
});
test('a deterministic zero-weight position cannot affect any existing path or FX',()=>{
  const x=fixture(),n=x.assets.length,zero={symbol:'000_ZERO',type:'cash',sector:'new-sector'},
    y={...x,assets:[...x.assets,zero],anchors:[...x.anchors,{symbol:zero.symbol,sector:zero.sector,annual:0,low:0,high:0}],
      covariance:[...x.covariance.map(row=>[...row,0]),Array(n+1).fill(0)],
      conditional:{...x.conditional,fits:[...x.conditional.fits,null]},
      factorization:{...x.factorization,loading:[...x.factorization.loading,0],
        residualCovariance:[...x.factorization.residualCovariance.map(row=>[...row,0]),Array(n+1).fill(0)]}};
  compare(generatePaths(x,150,919,52),generatePaths(y,150,919,52));
});
test('daily price and FX processes are independent of the reporting grid',()=>{
  const x=fixture(),a=generatePaths(x,150,919,12),b=generatePaths(x,150,919,52);
  for(let p=0;p<a.paths;p++){
    for(let i=0;i<x.assets.length;i++)assert.equal(a.gross[i][p*(a.steps+1)+a.steps],b.gross[i][p*(b.steps+1)+b.steps]);
    assert.equal(a.fx[p*(a.steps+1)+a.steps],b.fx[p*(b.steps+1)+b.steps]);
  }
});
test('finite Gaussian exponential moment is preserved; the old t correction is invalid',()=>{
  const h=4.62096310041733/10000,nu=4.086967405531595,
    lower=(normalUpperTail(8)-normalUpperTail(8.5))*Math.exp(Math.sqrt(h)*studentMarginal(nu)(8)-h/2);
  assert.ok(lower>1e20,'A Gaussian compensator cannot center the published t quantile map');
  for(const variance of [.0001,.01,.25]){
    let integral=0;const step=.002;
    for(let z=-8.5;z<=8.5;z+=step)integral+=step*Math.exp(Math.sqrt(variance)*z-variance/2-z*z/2)/Math.sqrt(2*Math.PI);
    assert.ok(Math.abs(integral-1)<1e-8);
  }
  assert.equal(generatePaths(fixture(),100,4).meanPreservingPriceInnovations,true);
  assert.equal(generatePaths(fixture(true),100,4).meanPreservingPriceInnovations,false);
  const stressed=generatePaths(fixture(true),100,4);
  assert.throws(()=>evaluatePaths([.3,.3,.3,.1],stressed),/solo estrés/);
  const risk=evaluatePaths([.3,.3,.3,.1],stressed,{riskOnly:true});
  assert.ok(Number.isFinite(risk.cvar95));assert.equal(risk.meanReturn,undefined);
  assert.equal(risk.score,undefined);assert.equal(risk.certaintyEquivalent,undefined);
  const illegal=fixture(true);illegal.options.researchShadowMode=false;
  assert.throws(()=>generatePaths(illegal,100,4),/fuera de rango/);
});
test('validation prefixes match the full price kernel and cannot evaluate a full mandate',()=>{
  const x=fixture(),a=generatePaths(x,100,17,252),b=generatePaths(x,100,17,252,{maxSteps:23});
  assert.equal(b.partial,true);
  for(let i=0;i<x.assets.length;i++)for(let p=0;p<a.paths;p++)for(let t=0;t<=b.steps;t++)
    assert.equal(a.gross[i][p*(a.steps+1)+t],b.gross[i][p*(b.steps+1)+t]);
  assert.throws(()=>evaluatePaths([0,0,0,1],b),/prefijo/);
});
test('sampling margins reject unresolved risk limits and do not mistake zero events for certainty',()=>{
  assert.equal(cvarStandardError(Array(1000).fill(0)),0);
  assert.ok(cvarStandardError(Array.from({length:1000},(_,i)=>-i/1000))>0);
  assert.ok(probabilityUpperBound(0,1000,.05/30)>0);
  assert.ok(probabilityUpperBound(0,1000,.05/30)<.01);
  assert.ok(probabilityUpperBound(0,100,.05/30)>.01);
  assert.ok(probabilityUpperBound(.05,1000,.001)>.05);
  const m={paths:1000,cvar95:.19,cvar95SE:.01,lossProbability:.2,drawdownProbability:0,liquidityFailureProbability:0};
  const e=riskSamplingEvidence(m,{cvarBudget:.2,maxLossProbability:.5},{maxDrawdownProbability:.1,maxLiquidityFailure:.01});
  assert.deepEqual(e.failures,['CVaR']);assert.ok(e.rows[0].upper>.2);
});
