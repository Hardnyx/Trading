import {tradePlan} from './policy.mjs?v=0.21.0';

// One cost calculation supplies both the simulation and its visible transition.
export function robustTransition(assets,current,target,capital,assumptions={}){
 const plan=tradePlan(assets,target,current,capital,assumptions);
 const before=new Map(current.map(p=>[p.symbol,p.weight]));
 const after=new Map(target.map(p=>[p.symbol,p.weight]));
 const prices=new Map(assets.map(a=>[a.symbol,a.price]));
 const trades=new Map(plan.rows.map(r=>[r.symbol,r]));
 const symbols=[...new Set([...before.keys(),...after.keys()])];
 const rows=symbols.map(symbol=>{
  const from=before.get(symbol)||0,to=after.get(symbol)||0;
  const currentValue=from*capital,targetValue=to*plan.investableCapital;
  const change=targetValue-currentValue,price=prices.get(symbol),trade=trades.get(symbol);
  return {symbol,from,to,currentValue,targetValue,change,price,
   quantity:symbol==='CASH'?null:Math.abs(change)/price,
   action:symbol==='CASH'?'reserve':Math.abs(change)<1e-7?'hold':
     change<0?(to===0?'exit':'reduce'):(from===0?'open':'increase'),
   cost:trade?.cost||0,small:trade?.small||false};
 });
 const buys=plan.rows.filter(r=>r.side==='buy').reduce((s,r)=>s+r.notional,0);
 const sells=plan.rows.filter(r=>r.side==='sell').reduce((s,r)=>s+r.notional,0);
 const initialCash=(before.get('CASH')||0)*capital;
 const endingCash=(after.get('CASH')||0)*plan.investableCapital;
 const cashResidual=initialCash+sells-buys-plan.total-endingCash;
 return {...plan,positions:rows,buys,sells,initialCash,endingCash,cashResidual,
  reconciled:plan.complete&&Math.abs(cashResidual)<1e-5,
  costBreakdown:Object.fromEntries(['commission','spread','slippage','tax'].map(key=>
   [key,plan.rows.reduce((s,r)=>s+r[key],0)]))};
}
