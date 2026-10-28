import test from 'node:test';
import assert from 'node:assert/strict';
import {priceObservation,priceMonitor} from '../dist/assets/js/price-monitor.mjs?v=0.33.0';
const asset=()=>{
 const history=Array.from({length:300},(_,i)=>({date:new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10),adj_close:100*Math.exp(i*.001),close:100*Math.exp(i*.001)}));
 return {symbol:'AAA',type:'stock',price:history.at(-1).close,price_date:history.at(-1).date,history};
};
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
test('monitor uses past adjusted closes, excludes today from breakout bounds and does not create return forecasts',()=>{
 const a=asset(),asOf=a.price_date;const p=priceObservation(a,asOf);
 assert.equal(p.available,true);assert.equal(p.event,'Máximo de 63 sesiones');
 assert.equal(p.trend,'Sobre MA50 y MA200');close(p.momentum126,Math.expm1(.126));
 close(p.drawdown252,0);assert.equal(p.volatilityRatio,null);
 assert.equal(p.expectedReturn,undefined);
 a.history.push({date:'2030-01-01',adj_close:1e6});
 assert.deepEqual(priceObservation(a,asOf),p);
 const scaled={...a,history:a.history.map(r=>({...r,adj_close:r.adj_close*10}))};
 close(priceObservation(scaled,asOf).momentum126,p.momentum126);
});
test('insufficient, stale and invalid histories cannot produce entry/exit observations',()=>{
 const a=asset();assert.equal(priceObservation({...a,history:a.history.slice(-100)},a.price_date).available,false);
 assert.match(priceObservation(a,'2026-01-01').reason,/rezagado/);
 a.history[4].date=a.history[3].date;assert.equal(priceObservation(a,a.price_date).available,false);
});
test('coverage and holding filters keep price-only stocks visible without changing portfolio inputs',()=>{
 const a=asset(),b={...asset(),symbol:'BBB',financials:{eps:{value:4,method:'TTM',period_end:'2025-06-30',filed:'2025-07-30'}}};
 const snapshot={price_as_of:a.price_date,assets:[a,b,{symbol:'CASH',type:'cash'}]};
 const positions=[{symbol:'AAA',quantity:2}],before=JSON.stringify({snapshot,positions});
 const m=priceMonitor(snapshot,positions,'price_only');assert.equal(m.total,2);assert.equal(m.rows.length,1);
 assert.equal(m.rows[0].symbol,'AAA');assert.equal(m.rows[0].held,true);
 assert.equal(priceMonitor(snapshot,positions,'held').rows.length,1);
 assert.equal(JSON.stringify({snapshot,positions}),before);
});
