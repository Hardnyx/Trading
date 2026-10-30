/** Self-financing research accounts in synthetic total-return units.
 * No strategy selection, fitted parameters, price imputation or broker claims.
 */
import {tradePlan} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {seededRandom} from '../dist/assets/js/random.mjs?v=0.35.0';

const sum=a=>a.reduce((s,v)=>s+v,0),mean=a=>a.length?sum(a)/a.length:null;
const validPrice=p=>Number.isFinite(p)&&p>0;
const iso=d=>/^\d{4}-\d{2}-\d{2}$/.test(d||'')&&new Date(d+'T12:00:00Z').toISOString().slice(0,10)===d;
const copyWeights=w=>Object.fromEntries(Object.entries(w).filter(([,v])=>v>1e-12).sort(([a],[b])=>a.localeCompare(b)));

export function validateTarget(weights){
 if(!weights||typeof weights!=='object'||Array.isArray(weights)||!Object.keys(weights).length||
  Object.entries(weights).some(([s,w])=>!s||!Number.isFinite(w)||w<0)||Math.abs(sum(Object.values(weights))-1)>1e-8)
  throw Error('Invalid target weights');
 return copyWeights(weights);
}

/** Strict lookup: a duplicate or missing original price never becomes a fill. */
export function totalReturnPrices(assets){
 const prices=new Map();
 for(const asset of assets){
  if(prices.has(asset.symbol))throw Error('Duplicate instrument '+asset.symbol);
  const rows=new Map();
  for(const r of asset.history||[]){
   if(!iso(r.date)||rows.has(r.date))throw Error('Ambiguous price date '+asset.symbol+' '+r.date);
   rows.set(r.date,r.adj_close);
  }
  prices.set(asset.symbol,rows);
 }
 return prices;
}

/** Orders are fixed at cut. Only the account's valuation and sizing use fills. */
export function replayAccount({id,dates,prices,orders,initialCapital=100000,costs={}}){
 if(!dates.length||dates.some((d,i)=>!iso(d)||(i&&d<=dates[i-1]))||!validPrice(initialCapital))
  throw Error('Invalid account calendar or capital');
 const dateSet=new Set(dates),byDate=new Map();
 let priorCut='',priorFill='';
 for(const order of orders){
  if(!dateSet.has(order.cut)||!dateSet.has(order.execute)||order.cut>=order.execute||
    order.cut<=priorCut||order.execute<=priorFill)throw Error('Noncausal or unordered execution');
  if(order.target!==null)validateTarget(order.target);
  byDate.set(order.execute,order);priorCut=order.cut;priorFill=order.execute;
 }
 if((costs.capitalGainsTax||0)!==0)throw Error('Synthetic units cannot certify taxable cost basis');
 let units={},cash=initialCapital,status='complete',totalCost=0,totalNotional=0,totalTurnover=0;
 const nav=[],transitions=[],issues=[];
 const price=(symbol,date)=>{const p=prices.get(symbol)?.get(date);
  if(!validPrice(p))throw Error('Missing or invalid original price '+symbol+' '+date);return p;};
 for(const date of dates){
  try{
   const values=Object.fromEntries(Object.entries(units).map(([s,q])=>[s,q*price(s,date)])),
    before=cash+sum(Object.values(values)),beforeWeights=copyWeights({...Object.fromEntries(Object.entries(values).map(([s,v])=>[s,v/before])),CASH:cash/before}),
    order=byDate.get(date);
   if(!validPrice(before))throw Error('Nonpositive account value');
   let paid=0;
   if(order){
    let afterWeights=beforeWeights,rows=[],turnover=0,notional=0;
    if(order.target!==null){
     const target=validateTarget(order.target),symbols=[...new Set([...Object.keys(units),...Object.keys(target)])].filter(s=>s!=='CASH'),
      assets=symbols.map(symbol=>({symbol,price:price(symbol,date)})),
      current=Object.entries(beforeWeights).map(([symbol,weight])=>({symbol,weight})),
      plan=tradePlan(assets,Object.entries(target).map(([symbol,weight])=>({symbol,weight})),current,before,costs);
     if(!plan.complete)throw Error('Unreconciled trade budget');
     const nextUnits={},nextCash=(target.CASH||0)*plan.investableCapital;
     for(const s of symbols)if(target[s]>0)nextUnits[s]=target[s]*plan.investableCapital/price(s,date);
     const after=nextCash+sum(Object.entries(nextUnits).map(([s,q])=>q*price(s,date)));
     if(Math.abs(before-plan.total-after)>Math.max(1e-6,before*1e-10)||nextCash<0)
      throw Error('Account is not self-financing');
     units=nextUnits;cash=nextCash;paid=plan.total;rows=plan.rows;turnover=plan.turnover;
     notional=sum(rows.map(r=>r.notional));afterWeights=target;
    }
    const symbols=[...new Set([...Object.keys(beforeWeights),...Object.keys(afterWeights)])],
     oldNames=Object.keys(beforeWeights).filter(s=>s!=='CASH'),newNames=Object.keys(afterWeights).filter(s=>s!=='CASH');
    transitions.push({cut:order.cut,execute:date,decision:order.decision||null,
     before_nav:before,after_nav:before-paid,before_weights:beforeWeights,after_weights:afterWeights,
     units:{...units},cash,cost:paid,notional,turnover,
     reallocation:sum(symbols.map(s=>Math.abs((beforeWeights[s]||0)-(afterWeights[s]||0))))/2,
     entered:newNames.filter(s=>!oldNames.includes(s)),exited:oldNames.filter(s=>!newNames.includes(s)),
     initial_allocation:oldNames.length===0&&newNames.length>0,trades:rows});
    totalCost+=paid;totalNotional+=notional;totalTurnover+=turnover;
   }
   const marked=Object.fromEntries(Object.entries(units).map(([s,q])=>[s,q*price(s,date)])),value=cash+sum(Object.values(marked));
   nav.push({date,nav:value,cash,cost:paid,
    weights:copyWeights({...Object.fromEntries(Object.entries(marked).map(([s,v])=>[s,v/value])),CASH:cash/value})});
  }catch(error){status='incomplete';issues.push({date,reason:error.message});break;}
 }
 const prefix=accountMetrics(nav,initialCapital);
 return {id,status,issues,initial_capital:initialCapital,scheduled_start:dates[0],scheduled_end:dates.at(-1),
  observed_through:nav.at(-1)?.date||null,metrics:status==='complete'?prefix:null,observed_prefix:prefix,
  costs:totalCost,notional:totalNotional,turnover:totalTurnover,trade_count:sum(transitions.map(t=>t.trades.length)),
  large_reallocations:transitions.filter(t=>!t.initial_allocation&&t.reallocation>=.1).length,
  transitions,nav,final_units:units,final_cash:cash,final_weights:nav.at(-1)?.weights||{CASH:1}};
}

export function accountMetrics(nav,initialCapital){
 if(!nav.length)return null;
 let peak=initialCapital,dd=0,previous=initialCapital;
 const returns=[],yearly=new Map(),monthly=[];
 for(let i=0;i<nav.length;i++){
  const row=nav[i],r=row.nav/previous-1;peak=Math.max(peak,row.nav);dd=Math.max(dd,1-row.nav/peak);
  if(i>0)returns.push(r);
  const year=row.date.slice(0,4);if(!yearly.has(year))yearly.set(year,{year,start:row.date,end:row.date,opening_nav:previous});
  const y=yearly.get(year);y.end=row.date;y.ending_nav=row.nav;y.return=row.nav/y.opening_nav-1;
  const next=nav[i+1];
  if((!next||next.date.slice(0,7)!==row.date.slice(0,7))&&row.date.slice(0,7)<nav.at(-1).date.slice(0,7)){
   const month=row.date.slice(0,7),j=nav.findIndex(r=>r.date.slice(0,7)===month);
   if(j>0)monthly.push({month,return:row.nav/nav[j-1].nav-1,log_return:Math.log(row.nav/nav[j-1].nav)});
  }
  previous=row.nav;
 }
 const n=returns.length,m=mean(returns),variance=n>1?sum(returns.map(r=>(r-m)**2))/(n-1):null;
 return {ending_nav:nav.at(-1).nav,total_return:nav.at(-1).nav/initialCapital-1,
  cagr:n?Math.expm1(Math.log(nav.at(-1).nav/initialCapital)*252/n):null,
  max_drawdown:dd,annualized_daily_volatility:variance===null?null:Math.sqrt(252*variance),
  observed_sessions:nav.length,return_intervals:n,yearly:[...yearly.values()],complete_months:monthly,
  mean_noncash_exposure:nav.every(r=>Number.isFinite(r.cash))?mean(nav.map(r=>1-r.cash/r.nav)):null,
  maximum_noncash_exposure:nav.every(r=>Number.isFinite(r.cash))?Math.max(...nav.map(r=>1-r.cash/r.nav)):null,
  final_noncash_exposure:Number.isFinite(nav.at(-1).cash)?1-nav.at(-1).cash/nav.at(-1).nav:null,
  maximum_single_security_weight:nav.every(r=>r.weights)?Math.max(0,...nav.flatMap(r=>Object.entries(r.weights).filter(([s])=>s!=='CASH').map(([,w])=>w))):null};
}

/** Descriptive paired calendar blocks, never an automatic promotion test. */
export function compareAccounts(a,b,{block=12,draws=2000,seed=20261029}={}){
 const result={candidate:a.id,reference:b.id,formal_test:false,superiority:'not-established'};
 if(a.status!=='complete'||b.status!=='complete')return {...result,status:'incomplete-account'};
 const left=a.metrics.complete_months,right=new Map(b.metrics.complete_months.map(r=>[r.month,r]));
 if(left.length!==right.size||left.some(r=>!right.has(r.month)))return {...result,status:'unmatched-months'};
 const values=left.map(r=>r.log_return-right.get(r.month).log_return),indices=left.map(r=>Number(r.month.slice(0,4))*12+Number(r.month.slice(5,7))),
  contiguous=indices.every((m,i)=>!i||m===indices[i-1]+1),n=values.length;
 let interval=null;
 if(contiguous&&n>=2*block){
  const rng=seededRandom(seed),sample=[];
  for(let draw=0;draw<draws;draw++){
   const rows=[];while(rows.length<n){const k=Math.floor(rng()*(n-block+1));rows.push(...values.slice(k,k+block));}
   sample.push(12*mean(rows.slice(0,n)));
  }
  sample.sort((a,b)=>a-b);interval=[sample[Math.floor(.025*(draws-1))],sample[Math.floor(.975*(draws-1))]];
 }
 return {...result,status:'descriptive-only',complete_months:n,contiguous_months:contiguous,
  nonoverlapping_annual_blocks:Math.floor(n/12),terminal_nav_difference:a.metrics.ending_nav-b.metrics.ending_nav,
  annualized_mean_log_return_difference:n?12*mean(values):null,moving_block_95:interval,
  block_months:block,bootstrap_draws:draws,seed,
  scope:'Paired monthly log-return differences on one reconstructed path. Pointwise descriptive interval, not CAGR difference, causal attribution or multiplicity-adjusted predictive evidence.'};
}
