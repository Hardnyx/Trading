/** Cash-settled, unlevered research account from sealed next-session targets.
 *
 * Raw closes, actual share quantities, dividend receivables, pay-date settlement,
 * splits and external flows. All supplied realizations are outcomes, not inputs
 * to the earlier portfolio choice. No broker orders, imputation or skill claim.
 */
import {tradePlan,DEFAULT_EXECUTION} from '../dist/assets/js/policy.mjs?v=0.35.0';

const fail=msg=>{throw Error(msg)};
const check=(ok,msg)=>{if(!ok)fail(msg)};
const sum=xs=>xs.reduce((s,x)=>s+x,0);
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const positive=x=>finite(x)&&x>0;
const day=x=>typeof x==='string'&&/^\d{4}-\d\d-\d\d$/.test(x)&&
  !Number.isNaN(Date.parse(x+'T12:00:00Z'))&&new Date(x+'T12:00:00Z').toISOString().slice(0,10)===x;
const epsilon=x=>Math.max(1e-7,Math.abs(x)*1e-9);
const bool=x=>x===true;
const weights=entries=>{
  check(Array.isArray(entries)&&entries.length>0,'Missing sealed portfolio positions');
  const out=new Map();
  for(const {symbol,weight} of entries){
    check(typeof symbol==='string'&&/^[A-Z0-9.-]{1,16}$/.test(symbol)&&
      !out.has(symbol)&&finite(weight)&&weight>=0,'Invalid or duplicate target weight');
    out.set(symbol,weight);
  }
  check(Math.abs(sum([...out.values()])-1)<1e-8,'Sealed target weights must sum to one');
  return out;
};
const nyOpenUtc=date=>{
  const local='09:30',localTimestamp=Date.parse(date+'T14:30:00Z');
  check(day(date),'Invalid exchange session date');
  // Iteratively resolve DST from the actual New York calendar date.
  const parts=t=>Object.fromEntries(new Intl.DateTimeFormat('en-US',{
    timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',
    hour:'2-digit',minute:'2-digit',hourCycle:'h23'
  }).formatToParts(new Date(t)).map(r=>[r.type,r.value]));
  let t=localTimestamp;
  for(let i=0;i<3;i++){
    const p=parts(t),actual=Number(p.hour)*60+Number(p.minute),required=9*60+30;
    check(p.year+'-'+p.month+'-'+p.day===date,'New York open timezone day mismatch');
    t+=(required-actual)*60000;
  }
  check(parts(t).hour==='09'&&parts(t).minute==='30','Cannot resolve NYSE open');
  return t;
};
function timestamp(value,label){
  check(typeof value==='string'&&/(?:Z|[+-]\d\d:\d\d)$/.test(value)&&
    Number.isFinite(Date.parse(value)),'Missing timezone-aware '+label);
  return Date.parse(value);
}
const sortedDays=calendar=>{
  check(Array.isArray(calendar)&&calendar.length>1&&
    calendar.every((d,i)=>day(d)&&(!i||calendar[i-1]<d)),
    'Invalid or unsorted observed exchange calendar');
  return new Map(calendar.map((date,i)=>[date,i]));
};
export function verifyAccountInputs({calendar,assets,decisions,flows=[],initialCapital=100000,
 costs=DEFAULT_EXECUTION,mandate={}}){
  const session=sortedDays(calendar);
  check(positive(initialCapital),'Invalid initial cash capital');
  check(mandate.referenceCurrency===undefined||mandate.referenceCurrency==='USD',
    'Account currency conversion requires original FX settlement');
  check(mandate.cashYield===undefined||mandate.cashYield===0,
    'Cash interest cannot be inferred from a forecast yield');
  check(!mandate.monthlyWithdrawal&&!(mandate.withdrawals||[]).length,
    'Scheduled withdrawals require separately sourced settlement events');
  check(mandate.dividendPolicy===undefined||mandate.dividendPolicy==='cash',
    'Reinvestment requires a different explicitly executed cash book');
  const withholding=mandate.dividendWithholding??0;
  check(finite(withholding)&&withholding>=0&&withholding<=1,
    'Invalid dividend withholding rate');
  check((costs.capitalGainsTax??0)===0&&
    Object.values(costs).every(v=>typeof v!=='number'||finite(v)),
    'Unsupported taxes or invalid execution cost');
  const assetMap=new Map();
  for(const asset of assets){
    check(asset&&typeof asset.symbol==='string'&&!assetMap.has(asset.symbol)&&
      asset.symbol!=='CASH'&&asset.currency==='USD'&&
      Array.isArray(asset.history),'Duplicate asset or unsupported currency');
    check(!asset.delisted&&!asset.reorganization&&
      !(asset.price_adjustments||[]).length&&
      !(asset.reorganizations||[]).length,
      'Unreconciled delisting or corporate action for '+asset.symbol);
    const prices=new Map();
    for(const row of asset.history){
      check(day(row.date)&&!prices.has(row.date)&&positive(row.close),
        'Duplicate, invalid or missing raw close for '+asset.symbol);
      prices.set(row.date,row.close);
    }
    const index=asset.distributions;
    check(index?.complete===true&&index.currency==='USD'&&
      day(index.coverage_start)&&day(index.coverage_end)&&
      index.coverage_start<=index.coverage_end&&Array.isArray(index.events),
      'An original complete cash-distribution index is required for '+asset.symbol);
    const events=[],seenEvents=new Set();
    for(const event of index.events){
      check(event.kind==='dividend'&&day(event.ex_date)&&day(event.pay_date)&&
        event.ex_date<=event.pay_date&&finite(event.amount_per_share)&&
        event.amount_per_share>=0&&
        event.ex_date>=index.coverage_start&&event.ex_date<=index.coverage_end,
        'Unreconciled dividend ex/pay dates or gross amount');
      const identity=[event.ex_date,event.pay_date,event.amount_per_share].join('|');
      check(!seenEvents.has(identity),
        'Duplicate dividend event in original cashflow ledger');
      seenEvents.add(identity);
      events.push({...event,symbol:asset.symbol});
    }
    const splits=[],seenSplits=new Set();
    for(const event of asset.splits||[]){
      check(day(event.date)&&positive(event.ratio),
        'Unreconciled split date or share ratio');
      check(!seenSplits.has(event.date),'Duplicate split event for '+asset.symbol);
      seenSplits.add(event.date);
      splits.push({...event,symbol:asset.symbol});
    }
    assetMap.set(asset.symbol,{prices,index,events,splits});
  }
  check(assetMap.has('SPY')&&calendar.every(d=>assetMap.get('SPY').prices.has(d)),
    'Benchmark calendar lacks a matching raw SPY close');
  const allSpySessions=[...assetMap.get('SPY').prices.keys()]
    .filter(date=>date>=calendar[0]&&date<=calendar.at(-1)).sort();
  check(JSON.stringify(allSpySessions)===JSON.stringify(calendar),
    'Observed exchange calendar omits or inserts an original SPY trading session');
  const cuts=new Set(),execs=new Map(),monthCuts=new Set();
  for(const d of decisions){
    check(day(d.cut)&&session.has(d.cut)&&d.cut>=calendar[0]&&
      !cuts.has(d.cut)&&!monthCuts.has(d.cut.slice(0,7)),
      'Noncausal or duplicated monthly decision cut');
    cuts.add(d.cut);monthCuts.add(d.cut.slice(0,7));
    const i=session.get(d.cut);
    check(i+1<calendar.length,'Next-session execution has not yet been observed');
    const execute=calendar[i+1];
    check(d.execute===execute,'Execution must use the FIRST observed session after the decision');
    check(d.publication?.verified===true&&
      /^[a-f0-9]{40}$/.test(d.publication.first_commit||'')&&
      /^[a-f0-9]{64}$/.test(d.forecast_sha256||''),
      'First forecast publication and immutable identity must be audited');
    const issued=timestamp(d.issued_at,'forecast issue'),
      published=timestamp(d.publication.committed_at,'first publication');
    check(issued>=nyOpenUtc(d.cut)+6.5*3600000&&
      issued<=published&&published<nyOpenUtc(execute),
      'Sealed forecast must be issued after the cut close and published before next-session opening');
    check(d.model_status==='proposed'||d.model_status==='hold',
      'No feasible proposal was available at the decision cut');
    const target=weights(d.positions);
    for(const symbol of target.keys())
      check(symbol==='CASH'||assetMap.has(symbol),
        'Held asset is missing from raw-price and dividend event index');
    execs.set(execute,{...d,target});
  }
  const flowByDate=new Map();
  for(const f of flows){
    check(session.has(f.date)&&['deposit','withdrawal','interest'].includes(f.kind)&&
      positive(f.amount)&&/^[a-f0-9]{64}$/.test(f.source_sha256||''),
      'External cash flow is undated, unsourced or invalid');
    if(!flowByDate.has(f.date))flowByDate.set(f.date,[]);
    flowByDate.get(f.date).push(f);
  }
  return {session,assetMap,execs,flowByDate,withholding};
}
function valuation(state,date,assets){
  let total=state.cash+sum(state.receivables.map(r=>r.gross)),stock=0;
  for(const [symbol,quantity] of Object.entries(state.units)){
    const asset=assets.get(symbol),price=asset?.prices.get(date);
    check(positive(price),'Missing observed raw close for held '+symbol+' on '+date);
    check(asset.index.coverage_start<=date&&date<=asset.index.coverage_end,
      'Original dividend coverage is missing on '+date+' for '+symbol);
    stock+=quantity*price;
  }
  total+=stock;
  check(positive(total)&&state.cash>=-epsilon(total),'Insolvent or non-positive account NAV');
  return {nav:total,stock,receivables:sum(state.receivables.map(r=>r.gross))};
}
function closePrices(state,date,assets){
  const result={};
  for(const symbol of Object.keys(state.units)){
    const p=assets.get(symbol)?.prices.get(date);
    check(positive(p),'Missing observed raw close for held '+symbol+' on '+date);
    result[symbol]=p;
  }
  return result;
}
export function replayCashAccount({
  id='full-engine-cash-book',calendar,assets,decisions,flows=[],
  initialCapital=100000,costs=DEFAULT_EXECUTION,mandate={},
}) {
  const {assetMap,execs,flowByDate,withholding}=verifyAccountInputs({
    calendar,assets,decisions,flows,initialCapital,costs,mandate});
  let state={units:{},cash:initialCapital,receivables:[]};
  let lastNav=initialCapital,previousPrices={};
  const nav=[],journal=[],decisionsObserved=[],issues=[];
  let status='complete',blockedOn=null;
  for(const date of calendar){
    const dayState={cash:state.cash,units:{...state.units},
      receivables:state.receivables.map(r=>({...r}))};
    const postings=[];
    const stats={price_pnl:0,entitlements:0,withheld:0,interest:0,
      external_net:0,trading_cost:0,trade_notional:0};
    try{
      const atDate=(symbol)=>assetMap.get(symbol)?.prices.get(date);
      // Corporate actions before the close; no synthetic adjusted-return units.
      for(const [symbol,asset] of assetMap){
        for(const e of asset.splits.filter(e=>e.date===date)){
          const owned=dayState.units[symbol]||0;
          if(owned>0){
            dayState.units[symbol]=owned*e.ratio;
            postings.push({type:'split',date,symbol,ratio:e.ratio,
              shares_before:owned,shares_after:dayState.units[symbol]});
          }
        }
      }
      const pNow=closePrices(dayState,date,assetMap);
      for(const [symbol,quantity] of Object.entries(dayState.units)){
        check(positive(previousPrices[symbol]),
          'Opening held position lacks previous observed session close');
        stats.price_pnl+=quantity*pNow[symbol]-
          state.units[symbol]*previousPrices[symbol];
      }
      // Entitlement uses the shares already held before any close-of-day trade.
      for(const [symbol,asset] of assetMap){
        for(const e of asset.events.filter(e=>e.ex_date===date)){
          const quantity=dayState.units[symbol]||0;
          if(quantity<=0)continue;
          check(asset.index.coverage_start<=date&&date<=asset.index.coverage_end,
            'Dividend event has no complete source coverage');
          const gross=quantity*e.amount_per_share;
          if(gross<=0)continue;
          dayState.receivables.push({symbol,ex_date:date,pay_date:e.pay_date,
            gross,per_share:e.amount_per_share,quantity});
          stats.entitlements+=gross;
          postings.push({type:'dividend-receivable',date,symbol,
            ex_date:date,pay_date:e.pay_date,gross});
        }
      }
      const outstanding=[];
      for(const item of dayState.receivables){
        if(item.pay_date>date){outstanding.push(item);continue;}
        check(item.pay_date===date,
          'A cash dividend payment passed without an observed settlement session');
        const withheld=item.gross*withholding,paid=item.gross-withheld;
        dayState.cash+=paid;stats.withheld+=withheld;
        postings.push({type:'dividend-payment',date,symbol:item.symbol,
          ex_date:item.ex_date,gross:item.gross,withholding:withheld,net_cash:paid});
      }
      dayState.receivables=outstanding;
      for(const f of flowByDate.get(date)||[]){
        const delta=f.kind==='withdrawal'?-f.amount:f.amount;
        dayState.cash+=delta;
        if(f.kind==='interest')stats.interest+=delta;
        else stats.external_net+=delta;
        postings.push({type:f.kind,date,amount:delta,
          source_sha256:f.source_sha256});
      }
      check(dayState.cash>=-epsilon(lastNav),'Insufficient settled cash for withdrawals');
      let marked=valuation(dayState,date,assetMap);
      const decision=execs.get(date);
      if(decision){
        const capital=marked.nav,positions=Object.entries(dayState.units)
          .map(([symbol,quantity])=>({symbol,weight:quantity*atDate(symbol)/capital})),
          target=[...decision.target].map(([symbol,weight])=>({symbol,weight}));
        positions.push({symbol:'CASH',weight:dayState.cash/capital});
        // Unsettled receivables are not free cash for target rebalances.
        check(marked.receivables<=epsilon(capital),
          'Receivables require a funded-cash sizing rule before rebalancing');
        const symbols=new Set([...positions.map(x=>x.symbol),
          ...target.map(x=>x.symbol)]);
        const quotes=[...symbols].filter(x=>x!=='CASH')
          .map(symbol=>({symbol,price:atDate(symbol)}));
        check(quotes.every(x=>positive(x.price)),
          'Missing exact next-session close for target instrument');
        const plan=tradePlan(quotes,target,positions,capital,costs);
        check(plan.complete&&plan.total>=0&&plan.investableCapital>0&&
          plan.turnover<=(costs.maxTurnover??1)+1e-7,
          'Unfunded rebalance, invalid cost basis or turnover limit');
        const newUnits={},tradeRows=[];
        for(const row of plan.rows){
          check(row.quantity>=0&&positive(atDate(row.symbol)),
            'Invalid trade quantity or execution close');
          tradeRows.push({type:'shadow-trade',date,symbol:row.symbol,side:row.side,
            quantity:row.quantity,price:atDate(row.symbol),
            notional:row.notional,cost:row.cost,
            spread:row.spread,slippage:row.slippage,commission:row.commission});
        }
        for(const [symbol,w] of decision.target){
          if(symbol!=='CASH'&&w>0)newUnits[symbol]=
            w*plan.investableCapital/atDate(symbol);
        }
        dayState.units=newUnits;
        dayState.cash=(decision.target.get('CASH')||0)*plan.investableCapital;
        stats.trading_cost=plan.total;
        stats.trade_notional=sum(tradeRows.map(x=>x.notional));
        postings.push(...tradeRows);
        marked=valuation(dayState,date,assetMap);
        check(Math.abs(marked.nav-(capital-plan.total))<=epsilon(capital),
          'Trade settlement violated the self-financing identity');
        decisionsObserved.push({cut:decision.cut,execute:date,
          first_publication:decision.publication.first_commit,
          original_forecast_sha256:decision.forecast_sha256,
          target_weights:target,shadow_trade_count:tradeRows.length,
          trading_cost:plan.total,notional:stats.trade_notional,
          before_nav:capital,after_nav:marked.nav});
      }
      const components=stats.price_pnl+stats.entitlements-
        stats.withheld+stats.interest+stats.external_net-stats.trading_cost;
      check(Math.abs(marked.nav-(lastNav+components))<=epsilon(marked.nav),
        'Account NAV change does not reconcile with price, receivable, payment, flows and costs');
      check(dayState.cash>=-epsilon(marked.nav),
        'The shadow account has negative settled cash');
      state=dayState;
      lastNav=marked.nav;
      previousPrices=closePrices(state,date,assetMap);
      const holdings=Object.entries(state.units).sort(([a],[b])=>a.localeCompare(b))
        .map(([symbol,quantity])=>({symbol,quantity,raw_close:previousPrices[symbol],
          market_value:quantity*previousPrices[symbol]}));
      journal.push(...postings);
      nav.push({date,nav:marked.nav,holdings,cash:state.cash,
        receivables:marked.receivables,
        price_pnl:stats.price_pnl,dividend_entitlements:stats.entitlements,
        withheld_taxes:stats.withheld,external_cash_flow:stats.external_net,
        realized_cash_interest:stats.interest,trade_cost:stats.trading_cost,
        trade_notional:stats.trade_notional,
        identity_residual:marked.nav-(nav.at(-1)?.nav??initialCapital)-components});
    }catch(error){
      status='incomplete';
      blockedOn=date;
      issues.push({date,reason:error.message});
      break;
    }
  }
  return {schema:'full-engine-cash-account-research-v1',id,
    status,issues,blocked_on:blockedOn,
    capital:initialCapital,observed_through:nav.at(-1)?.date||null,
    calendar_sessions:calendar.length,accounted_sessions:nav.length,
    journal,nav,decisions:decisionsObserved,
    final_cash:state.cash,final_units:{...state.units},
    pending_receivables:state.receivables,
    total_trading_cost:sum(decisionsObserved.map(r=>r.trading_cost)),
    original_vintages_certified:false,exchange_execution_certified:false,
    corporate_action_source_certified:false,cash_interest_policy:'observed-posted-only; absent cash interest assumed zero',
    account_outcome_validated:false,predictive_validation:'not-established',
    economic_superiority:'not-established',
    meaning:'Hypothetical fractional-share target rebalance at first observed next-session raw close; not broker orders, verified historical execution or causal full-engine performance'};
}
