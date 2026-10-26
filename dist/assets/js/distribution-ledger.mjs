import { annualDistributionYield, distributionFactors } from "./cashflows.mjs?v=0.13.0";

const DAY=86400000, YEAR=365.25*DAY, cache=new WeakMap();
export const yearFraction=(start,end)=>(Date.parse(end+"T12:00:00Z")-Date.parse(start+"T12:00:00Z"))/YEAR;
const validDay=s=>/^\d{4}-\d\d-\d\d$/.test(s||"") &&
  Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0,10)===s;
const knownAt=(record,cut)=>typeof record?.observed_at==="string" &&
  Number.isFinite(Date.parse(record.observed_at)) && record.observed_at.slice(0,10)<=cut;

export function projectionCalendar(asset,asOf,informationAsOf,horizon){
  if(!validDay(asOf) || !validDay(informationAsOf) || !(horizon>0))
    return {available:false,reason:"Falta corte de calendario"};
  const c=asset.distribution_calendar;
  const end=new Date(Date.parse(asOf+"T12:00:00Z")+horizon*YEAR).toISOString().slice(0,10);
  if(!c || c.source_layer!=="issuer-planned-calendar" || !knownAt(c,informationAsOf) ||
     !validDay(c.published_on) || c.published_on>informationAsOf ||
     !validDay(c.coverage_start) || c.coverage_start>asOf ||
     !validDay(c.coverage_end) || c.coverage_end<end ||
     !Number.isInteger(c.frequency) || c.frequency<1 || c.frequency>366 ||
     !Array.isArray(c.records) || !c.records.length)
    return {available:false,reason:"Sin calendario completo conocido al corte"};
  const seen=new Set(),events=[];
  for(const r of c.records){
    if(!validDay(r.ex_date) || !validDay(r.pay_date) || r.pay_date<r.ex_date ||
       seen.has(r.ex_date))return {available:false,reason:"Calendario no conciliable"};
    seen.add(r.ex_date);
    if(r.ex_date<=asOf || r.ex_date>end)continue;
    const declared=asset.issuer_distributions?.source_layer==="issuer"
      ? asset.issuer_distributions.records?.find(d=>d.ex_date===r.ex_date &&
        d.pay_date===r.pay_date && d.currency==="USD" &&
        knownAt(d,informationAsOf) && Number.isFinite(d.amount_per_share) && d.amount_per_share>=0)
      : null;
    if(r.conditional && !declared)continue;
    events.push({...r,amount_per_share:declared?.amount_per_share??null,
      amount_basis:declared?"issuer-declared":"trailing-yield-assumption",
      exYear:yearFraction(asOf,r.ex_date),payYear:yearFraction(asOf,r.pay_date)});
  }
  events.sort((a,b)=>a.exYear-b.exYear);
  return {available:true,events,frequency:c.frequency,source_url:c.source_url,
    observed_at:c.observed_at,published_on:c.published_on,coverage_end:c.coverage_end};
}

function grossAt(column,p,steps,dt,year){
  const u=Math.max(0,Math.min(steps,year/dt)),lo=Math.floor(u),hi=Math.min(steps,lo+1);
  const offset=p*(steps+1),a=column[offset+lo],b=column[offset+hi];
  return Math.exp(Math.log(a)+(Math.log(b)-Math.log(a))*(u-lo));
}

function datedAccounting(asset,column,sample,calendar){
  const {paths,steps,policy}=sample,dt=sample.dt??(policy.horizon||1)/steps;
  const size=paths*(steps+1),events=calendar.events;
  const values=new Float64Array(size),cash=new Float64Array(size),receivables=new Float64Array(size);
  const grossIncome=new Float64Array(paths),netIncome=new Float64Array(paths),
    tax=new Float64Array(paths),reinvested=new Float64Array(paths),paidGross=new Float64Array(paths);
  const payOrder=events.map((r,index)=>({year:r.payYear,index})).sort((a,b)=>a.year-b.year||a.index-b.index);
  const payRank=new Map(payOrder.map((r,i)=>[r.index,i]));
  const payments=new Float64Array(paths*events.length);
  const actions=events.flatMap((r,index)=>[
    {year:r.exYear,kind:0,index},{year:r.payYear,kind:1,index}])
    .sort((a,b)=>a.year-b.year||a.kind-b.kind||a.index-b.index);
  const assumedStepYield=Math.expm1(Math.log1p(annualDistributionYield(asset))/calendar.frequency);
  const withholding=policy.dividendWithholding||0,toCash=policy.dividendPolicy==="cash";
  let capped=0;
  for(let p=0;p<paths;p++){
    let shares=1,divisor=1,pending=0,balance=0,next=0;
    const entitlements=new Float64Array(events.length);
    const grossEntitlements=new Float64Array(events.length);
    for(let t=0;t<=steps;t++){
      while(next<actions.length && actions[next].year<=t*dt+1e-10){
        const a=actions[next++],event=events[a.index],g=grossAt(column,p,steps,dt,a.year);
        if(a.kind===0){
          const before=g/divisor;
          let distribution;
          if(event.amount_per_share!==null){
            const requested=event.amount_per_share/asset.price;
            distribution=Math.min(requested,before*(1-1e-12));
            if(distribution+1e-12<requested)capped++;
            divisor=g/(before-distribution);
          }else{
            divisor*=1+assumedStepYield;
            distribution=g/divisor*assumedStepYield;
          }
          const gross=shares*distribution,net=gross*(1-withholding);
          grossEntitlements[a.index]=gross;entitlements[a.index]=net;
          pending+=net;grossIncome[p]+=gross;netIncome[p]+=net;tax[p]+=gross-net;
        }else{
          const amount=entitlements[a.index];pending=Math.max(0,pending-amount);
          paidGross[p]+=grossEntitlements[a.index];
          if(toCash)balance+=amount;
          else {shares+=amount/(g/divisor);reinvested[p]+=amount;}
          payments[p*events.length+payRank.get(a.index)]=balance;
        }
      }
      const k=p*(steps+1)+t;
      values[k]=shares*column[k]/divisor+pending;
      cash[k]=balance;receivables[k]=pending;
    }
  }
  return {dated:true,calendar,values,cash,receivables,grossIncome,netIncome,tax,reinvested,paidGross,capped,
    cashAt(p,year){
      let lo=0,hi=payOrder.length;
      while(lo<hi){const mid=(lo+hi)>>1;if(payOrder[mid].year<=year+1e-10)lo=mid+1;else hi=mid;}
      return lo?payments[p*events.length+lo-1]:0;
    }};
}

export function distributionAccounting(sample){
  if(cache.has(sample))return cache.get(sample);
  const dt=sample.dt??(sample.policy.horizon||1)/sample.steps;
  const result=sample.assets.map((asset,i)=>{
    const calendar=projectionCalendar(asset,sample.asOf,
      sample.informationAsOf||sample.asOf,sample.steps*dt);
    if(asset.type!=="cash" && calendar.available)
      return datedAccounting(asset,sample.gross[i],sample,calendar);
    return {dated:false,factors:distributionFactors(asset,sample.steps,dt,sample.policy),reason:calendar.reason};
  });
  cache.set(sample,result);return result;
}

export function distributionTerminalValue(view,sample,i,p){
  const offset=p*(sample.steps+1)+sample.steps;
  if(view.dated)return view.values[offset]+view.cash[offset];
  let cash=0;
  for(let t=1;t<=sample.steps;t++)cash+=sample.gross[i][p*(sample.steps+1)+t]*view.factors.netCash[t];
  return sample.gross[i][offset]*view.factors.marketValue[sample.steps]+cash;
}

// Realization under the model's tax/reinvestment conventions, not a broker P&L.
export function reconcileDistributionReturn(asset,start,end,policy={}){
  if(!validDay(start) || !validDay(end) || end<start)
    return {available:false,reason:"Intervalo de conciliación inválido"};
  if(asset.type==="cash")return {available:true,return:0,basis:"synthetic-cash"};
  const rate=policy.dividendWithholding??0;
  if(!Number.isFinite(rate) || rate<0 || rate>1 ||
     (policy.dividendPolicy && !["cash","reinvest"].includes(policy.dividendPolicy)))
    return {available:false,reason:"Política de distribuciones inválida"};
  const index=asset.distribution_index;
  if(!index?.complete_ex_date_index || index.currency!=="USD" ||
     (asset.currency && asset.currency!=="USD") ||
     !validDay(index.coverage_start) || !validDay(index.coverage_end) ||
     index.coverage_start>start || index.coverage_end<end || !Array.isArray(index.records))
    return {available:false,reason:"Falta índice completo de fechas exdividendo"};
  if(index.records.some(r=>!validDay(r.ex_date) || !Number.isFinite(r.amount_per_share) ||
     r.amount_per_share<0 || r.ex_date<index.coverage_start || r.ex_date>index.coverage_end) ||
     new Set(index.records.map(r=>r.ex_date)).size!==index.records.length)
    return {available:false,reason:"Índice de distribuciones inválido"};
  if((asset.splits||[]).some(r=>r.date>start))
    return {available:false,reason:"Split pendiente de conciliación de la base por participación"};
  // Imported histories need not arrive in chronological order. A pay-date
  // reinvestment uses the first trading close by date, never array position.
  const history=[...(asset.history||[])].sort((a,b)=>String(a.date).localeCompare(String(b.date)));
  const relevant=history.filter(r=>r.date>=start && r.date<=end);
  if(relevant.some(r=>!validDay(r.date) || !Number.isFinite(r.close) || r.close<=0) ||
     new Set(relevant.map(r=>r.date)).size!==relevant.length)
    return {available:false,reason:"Histórico de precios inválido o ambiguo"};
  const initial=history.find(r=>r.date===start)?.close,
    final=history.find(r=>r.date===end)?.close;
  if(!(Number.isFinite(initial)&&initial>0 && Number.isFinite(final)&&final>0))return {available:false,reason:"Faltan precios comparables"};
  const expected=index.records.filter(r=>r.ex_date>start && r.ex_date<=end && r.amount_per_share>0);
  const issuer=asset.issuer_distributions;
  const actual=issuer?.source_layer==="issuer" && Array.isArray(issuer.records)
    ? issuer.records.filter(r=>r.ex_date>start&&r.ex_date<=end&&r.amount_per_share>0):[];
  if(expected.length!==actual.length)
    return {available:false,reason:"Faltan importes o fechas de pago contrastadas con el emisor"};
  if(!expected.length){
    const a=history.find(r=>r.date===start),b=history.find(r=>r.date===end);
    if(!(Number.isFinite(a.adj_close) && a.adj_close>0 &&
         Number.isFinite(b.adj_close) && b.adj_close>0) ||
       Math.abs((b.adj_close/a.adj_close)/(final/initial)-1)>1e-5)
      return {available:false,reason:"El ajuste de precios revela distribuciones o eventos sin conciliar"};
  }
  // Yahoo currently reports this index on a three-decimal grid. Accept only
  // amounts that round onto the observed grid, retaining the issuer amount.
  const decimalPlaces=value=>{
    const [mantissa,exponent="0"]=String(value).toLowerCase().split("e");
    return Math.max(0,(mantissa.split(".")[1]||"").length-Number(exponent));
  };
  const indexPrecision=Math.max(0,...index.records.map(r=>decimalPlaces(r.amount_per_share)));
  const roundedYahooIndex=/^https:\/\/finance\.yahoo\.com\/quote\/[^/]+\/history\/$/.test(index.source_url||"") &&
    indexPrecision===3;
  const amountMatches=(issuerAmount,indexAmount)=>Math.abs(issuerAmount-indexAmount)<=1e-6 ||
    (roundedYahooIndex && Math.abs(Math.round(issuerAmount*1000)/1000-indexAmount)<=1e-12);
  const records=[];
  let roundedIndexMatches=0;
  for(const r of expected){
    const match=actual.find(a=>a.ex_date===r.ex_date && a.currency==="USD" &&
      validDay(a.pay_date) && a.pay_date>=a.ex_date &&
      amountMatches(a.amount_per_share,r.amount_per_share));
    if(!match)return {available:false,reason:"La distribución del emisor no concilia con la serie de precios"};
    if(Math.abs(match.amount_per_share-r.amount_per_share)>1e-6)roundedIndexMatches++;
    records.push(match);
  }
  const actions=records.flatMap((r,i)=>[
    {date:r.ex_date,kind:0,index:i},{date:policy.dividendPolicy==="cash"?r.pay_date:
      history.find(h=>h.date>=r.pay_date)?.date||r.pay_date,kind:1,index:i}])
    .filter(a=>a.date<=end).sort((a,b)=>a.date.localeCompare(b.date)||a.kind-b.kind||a.index-b.index);
  let shares=1,cash=0,pending=0,gross=0,withheld=0;
  const owed=new Map();
  for(const a of actions){
    const r=records[a.index];
    if(a.kind===0){const amount=shares*r.amount_per_share,net=amount*(1-rate);
      owed.set(a.index,net);pending+=net;gross+=amount;withheld+=amount-net;
    }else{
      const net=owed.get(a.index)||0;pending=Math.max(0,pending-net);
      if(policy.dividendPolicy==="cash")cash+=net;
      else{
        const price=history.find(h=>h.date>=a.date && h.date<=end)?.close;
        if(!(Number.isFinite(price)&&price>0))return {available:false,reason:"Falta precio para reinversión al pago"};
        shares+=net/price;
      }
    }
  }
  return {available:true,return:(shares*final+cash+pending)/initial-1,
    basis:"issuer-pay-date-close-with-model-tax-assumption",cash:cash/initial,
    receivable:pending/initial,grossDistributions:gross/initial,assumedWithholding:withheld/initial,
    events:records.length,rounded_index_matches:roundedIndexMatches,
    rounding_basis:roundedIndexMatches?"Observed Yahoo index grid: 3 decimals; issuer amounts used without rounding":null,
    source_url:issuer?.source_url||index.source_url,
    source_sha256:issuer?.source_sha256||null};
}

export function reconcilePortfolioDistributions(assets,positions,start,end,policy){
  const lookup=new Map(assets.map(a=>[a.symbol,a])),evidence=[];
  let realized=0;
  for(const p of positions){
    if(!(p.weight>0))continue;
    const asset=p.symbol==="CASH"?{symbol:"CASH",type:"cash"}:lookup.get(p.symbol);
    if(!asset)return {available:false,reason:"Activo ausente: "+p.symbol};
    const r=reconcileDistributionReturn(asset,start,end,policy);
    if(!r.available)return {...r,symbol:p.symbol};
    realized+=p.weight*r.return;evidence.push({symbol:p.symbol,weight:p.weight,...r});
  }
  return {available:true,return:realized,evidence,
    basis:"Issuer payments, close-price reinvestment and the mandate's assumed withholding; not broker execution"};
}
