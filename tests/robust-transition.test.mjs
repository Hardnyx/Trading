import test from 'node:test';
import assert from 'node:assert/strict';
import {robustTransition} from '../dist/assets/js/robust-transition.mjs?v=0.18.0';

const assets=[{symbol:'AAA',price:100},{symbol:'BBB',price:50},{symbol:'CASH',price:1}];
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-5,`${a} != ${b}`);

test('transition reconciles sales, purchases, taxes and ending cash after costs',()=>{
 const current=[{symbol:'AAA',weight:.6,costBasis:80},{symbol:'BBB',weight:.2,costBasis:45},{symbol:'CASH',weight:.2}];
 const target=[{symbol:'BBB',weight:.7},{symbol:'CASH',weight:.3}];
 const p=robustTransition(assets,current,target,100000,{capitalGainsTax:.15,commissionFixed:5,spreadBps:10,slippageBps:5});
 assert.equal(p.reconciled,true);
 assert.equal(p.positions.find(r=>r.symbol==='AAA').action,'exit');
 assert.equal(p.positions.find(r=>r.symbol==='BBB').action,'increase');
 close(p.initialCash+p.sells-p.buys-p.total,p.endingCash);
 close(p.positions.reduce((s,r)=>s+r.targetValue,0)+p.total,100000);
 close(Object.values(p.costBreakdown).reduce((s,v)=>s+v,0),p.total);
 close(p.costBreakdown.tax,1800);
 close(p.positions.find(r=>r.symbol==='AAA').quantity,600);
});

test('holding has zero trades and newly opened positions use net investable capital',()=>{
 const current=[{symbol:'AAA',weight:.5},{symbol:'CASH',weight:.5}];
 const hold=robustTransition(assets,current,current,10000,{commissionFixed:5});
 close(hold.total,0);assert.equal(hold.positions[0].action,'hold');
 const open=robustTransition(assets,current,[{symbol:'AAA',weight:.2},{symbol:'BBB',weight:.5},{symbol:'CASH',weight:.3}],10000,{commissionFixed:5});
 assert.equal(open.positions.find(r=>r.symbol==='AAA').action,'reduce');
 const b=open.positions.find(r=>r.symbol==='BBB');
 assert.equal(b.action,'open');close(b.quantity,b.targetValue/50);
 assert.equal(open.reconciled,true);
});

test('missing taxable cost basis cannot be presented as a reconciled transition',()=>{
 const p=robustTransition(assets,[{symbol:'AAA',weight:1}],[{symbol:'CASH',weight:1}],10000,{capitalGainsTax:.15});
 assert.equal(p.taxComplete,false);assert.equal(p.reconciled,false);
});
