import test from 'node:test';
import assert from 'node:assert/strict';
import {economicInputs,sensitivityEvidence,ECONOMIC_CASES} from '../scripts/economic_sensitivity_research.mjs';
import {prepareComposition} from '../dist/assets/js/composer.mjs?v=0.35.0';
import {buildReturnAnchors} from '../dist/assets/js/return-model.mjs?v=0.35.0';
import {DEFAULT_MANDATE} from '../dist/assets/js/policy.mjs?v=0.35.0';
function fixture(){
 const cut='2026-10-23',history=Array.from({length:300},(_,k)=>({date:new Date(Date.UTC(2025,11,k+1)).toISOString().slice(0,10),close:100,adj_close:100}));
 const m={generated_at:cut+'T23:00:00Z',price_as_of:cut,macro:[{id:'DGS3MO',date:cut,value:4}],assets:[
  {symbol:'LQD',type:'etf',sector:'Credit',price:100,price_date:cut,history,bond_profile:{date:cut,yieldToMaturity:.06,duration:7,expenseRatio:.001}},
  {symbol:'SHY',type:'etf',sector:'Treasury',price:100,price_date:cut,history,bond_profile:{date:cut,yieldToMaturity:.045,duration:2,expenseRatio:.001}}]};
 const x=prepareComposition(m,{horizon:1,seed:41,volatilityMode:'ewma',macroRegimes:[{id:'base',probability:1,earningsShift:0,multipleShift:0,rateShift:.01,rateJumpBps:50}]},{},{});
 return {...x,assets:m.assets,anchorUniverse:m.assets,anchors:buildReturnAnchors(m.assets,x.options,{},m.assets)};
}
test('credit losses and spread exposure change independently, retaining issuer observations',()=>{
 const x=fixture(),before=JSON.stringify(x),loss=economicInputs(x,{id:'loss',lossMultiplier:3}),spread=economicInputs(x,{id:'spread',spreadMultiplier:3}),i=x.assets.findIndex(a=>a.symbol==='LQD');
 assert.ok(Math.abs(loss.anchors[i].annual-(x.anchors[i].annual-.005))<1e-10);
 assert.equal(loss.anchors[i].bond.spreadBeta,x.anchors[i].bond.spreadBeta);
 assert.equal(spread.anchors[i].annual,x.anchors[i].annual);assert.equal(spread.anchors[i].bond.spreadBeta,3*x.anchors[i].bond.spreadBeta);
 assert.equal(JSON.stringify(x),before);
});
test('rate sensitivity preserves the anchor mean and covariance while changing declared shocks',()=>{
 const x=fixture(),a=economicInputs(x,{id:'rates',rateScale:2});
 assert.deepEqual(a.anchors.map(a=>a.annual),x.anchors.map(a=>a.annual));assert.deepEqual(a.covariance,x.covariance);
 assert.equal(a.regimes[0].rateShift,2*x.regimes[0].rateShift);assert.equal(a.regimes[0].rateJumpBps,2*x.regimes[0].rateJumpBps);
});
test('a combined block retains the no-rerating override and touches unseen constituents without altering accounting',()=>{
 const x=fixture(),stock={symbol:'AAA',type:'stock',price:100,sector:'A',assumptions:{growth:.06,multiple:20,horizon:3,discount:.1},financials:{eps:{value:10,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}};
 x.anchorUniverse=[...x.assets,stock];const before=JSON.stringify(x),r=economicInputs(x,{id:'combined',variant:{noRerating:true},lossMultiplier:2,growthScale:.5});
 assert.ok(r.valuationOverrides.AAA.multiple<=10);assert.equal(r.valuationOverrides.AAA.growth,.03);assert.equal(JSON.stringify(x),before);
});
test('signed sensitivity bounds preserve resolved negative changes instead of clipping them to zero',()=>{
 const u=Array(100).fill(Math.log1p(.04)),v=Array(100).fill(Math.log1p(.05)),e=sensitivityEvidence(u,v,DEFAULT_MANDATE,100000,100);
 assert.ok(Math.abs(e.gain+1000)<1e-8);assert.ok(e.upperGain<0);assert.ok(Math.abs(e.upperGain-e.lowerGain)<1e-8);
 assert.throws(()=>sensitivityEvidence([NaN,0],[0,0],DEFAULT_MANDATE,100000,100));
});
test('the exploratory grid has unique explicit cases and keeps the established low-conviction comparator',()=>{
 assert.equal(new Set(ECONOMIC_CASES.map(c=>c.id)).size,ECONOMIC_CASES.length);
 assert.ok(ECONOMIC_CASES.some(c=>c.id==='declared_low_conviction'&&c.variant.equityPremium===0));
});
