import {financialFreshness} from './financial-freshness.mjs?v=0.29.0';
const mean=x=>x.reduce((s,v)=>s+v,0)/x.length;
const vol=x=>{const m=mean(x);return Math.sqrt(x.reduce((s,v)=>s+(v-m)**2,0)/(x.length-1)*252);};

// Descriptive end-of-day observations. Never supply expected-return anchors.
export function priceObservation(asset,asOf){
 const rows=(asset.history||[]).filter(r=>r.date<=asOf);
 if(rows.some((r,i)=>!(r.adj_close>0)||!Number.isFinite(r.adj_close)||(i&&r.date<=rows[i-1].date)))
  return {available:false,reason:'Historia ajustada inválida o desordenada'};
 if(rows.length<252)return {available:false,reason:'Se requieren 252 cierres ajustados'};
 if(rows.at(-1).date!==asOf||asset.price_date!==asOf)
  return {available:false,reason:'Precio rezagado frente al corte común',lastDate:rows.at(-1).date};
 const x=rows.map(r=>r.adj_close),n=x.length,last=x.at(-1),previous=x.at(-2);
 const ma50=mean(x.slice(-50)),ma200=mean(x.slice(-200));
 const previous50=mean(x.slice(-51,-1));
 const earlier=x.slice(-64,-1);
 let event='Sin ruptura o cruce';
 if(last>Math.max(...earlier))event='Máximo de 63 sesiones';
 else if(last<Math.min(...earlier))event='Mínimo de 63 sesiones';
 else if(previous<=previous50&&last>ma50)event='Cruce al alza de MA50';
 else if(previous>=previous50&&last<ma50)event='Cruce a la baja de MA50';
 const returns=x.slice(-64).slice(1).map((v,i)=>Math.log(v/x[n-64+i]));
 const v63=vol(returns),v21=vol(returns.slice(-21));
 return {available:true,lastDate:asOf,observations:n,
  trend:last>ma50&&ma50>ma200?'Sobre MA50 y MA200':last<ma50&&ma50<ma200?'Bajo MA50 y MA200':'Tendencia mixta',
  event,hasEvent:event!=='Sin ruptura o cruce',
  momentum126:last/x[n-127]-1,distance200:last/ma200-1,
  drawdown252:last/Math.max(...x.slice(-252))-1,volatility63:v63,
  volatilityRatio:v63>1e-12?v21/v63:null};
}

export function priceMonitor(snapshot,positions=[],filter='all'){
 const held=new Set(positions.filter(p=>p.weight>0||p.quantity>0).map(p=>p.symbol));
 const info=(snapshot.generated_at||snapshot.price_as_of).slice(0,10);
 const all=snapshot.assets.filter(a=>a.type!=='cash').map(a=>{
  const f=a.type==='stock'?financialFreshness(a,info):null;
  return {symbol:a.symbol,type:a.type,price:a.price,priceDate:a.price_date,held:held.has(a.symbol),
   observedAt:a.price_observed_at||a.distribution_index?.observed_at||null,
   coverage:f?(f.blocked?'BPA no conciliado o ausente':'BPA disponible; sin calibración predictiva'):
    a.bond_profile?'ETF con perfil de renta fija':'ETF: valorar mandato y subyacentes',
   priceOnly:a.type==='stock'&&f.blocked,
   ...priceObservation(a,snapshot.price_as_of)};
 });
 const rows=all.filter(r=>filter==='held'?r.held:filter==='price_only'?r.priceOnly:filter==='events'?r.hasEvent:true);
 rows.sort((a,b)=>Number(b.held)-Number(a.held)||Number(b.priceOnly)-Number(a.priceOnly)||a.symbol.localeCompare(b.symbol));
 return {rows,total:all.length,available:all.filter(r=>r.available).length,
  priceOnly:all.filter(r=>r.priceOnly).length,asOf:snapshot.price_as_of};
}
