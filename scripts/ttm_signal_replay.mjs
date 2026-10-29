/** Reuse production valuation and exposure on reconstructed, dated TTM inputs. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {valuation,resolveAssumptions} from '../dist/assets/js/analytics.mjs?v=0.35.0';
import {marketExposure,ALPHA_SCORE_LIMIT} from '../dist/assets/js/return-model.mjs?v=0.35.0';

const hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
export function trailingDividends(asset,origin){
 const x=asset.distribution_index,lower=new Date(Date.parse(origin+'T12:00:00Z')-364*86400000).toISOString().slice(0,10);
 if(!x?.complete_ex_date_index||x.currency!=='USD'||x.coverage_start>lower||x.coverage_end<origin)return null;
 const rows=x.records.filter(r=>lower<=r.ex_date&&r.ex_date<=origin);
 if(rows.some(r=>!Number.isFinite(r.amount_per_share)||r.amount_per_share<0)||new Set(rows.map(r=>r.ex_date)).size!==rows.length)return null;
 return rows.reduce((s,r)=>s+r.amount_per_share,0);
}

export function rawSignal(asset,eps,benchmark,origin){
 if(!eps||eps.filed>=origin||eps.period_end>=origin||!(eps.value>0))return {reason:'unavailable_ttm'};
 // Today's historical closes can carry non-share corporate-action adjustments.
 // A future spin-off cannot be repaired by dividing EPS by a split ratio.
 const cut=asset.price_date||asset.history.at(-1)?.date;
 if((asset.price_adjustments||[]).some(a=>origin<a.date&&a.date<=cut))return {reason:'unreconciled_future_price_adjustment'};
 const history=asset.history.filter(r=>r.date<=origin),price=history.at(-1);
 if(price?.date!==origin||!(price.close>0))return {reason:'missing_origin_price'};
 const dividends=trailingDividends(asset,origin);
 if(dividends===null)return {reason:'incomplete_dividend_window'};
 const at={...asset,history,price:price.close,price_date:origin,dividend_per_share:dividends,
  splits:asset.splits?.filter(s=>s.date<=origin),financials:{eps}};
 const a=resolveAssumptions(at),model=valuation(at,a),exposure=marketExposure(at,benchmark,origin);
 if(!model||!Number.isFinite(model.annualReturn)||!exposure||!(exposure.omega>0))return {reason:'invalid_signal_or_exposure'};
 return {symbol:asset.symbol,signal:model.annualReturn,earnings_yield:eps.value/price.close,
  origin_close:price.close,origin_adj_close:price.adj_close,trailing_dividends:dividends,
  eps,exposure,catalogue_assumptions:asset.assumptions,rerating:a.rerating};
}

export function replay(market,facts){
 if(market.price_as_of!==facts.price_cut)throw Error('Mismatched frozen cut');
 const bySymbol=new Map(market.assets.map(a=>[a.symbol,a])),benchmark=bySymbol.get('SPY'),
  benchmarkPrice=new Map(benchmark.history.map(r=>[r.date,r.adj_close])),origins=[],exclusions={...facts.exclusions};
 const exclude=reason=>exclusions[reason]=(exclusions[reason]||0)+1;
 for(const input of facts.origins){
  const rows=[];
  for(const fact of input.facts){
   const asset=bySymbol.get(fact.symbol);if(!asset)throw Error('Unknown reconstructed constituent');
   const r=rawSignal(asset,fact.eps,benchmark,input.origin);
   if(r.reason){exclude(r.reason);continue;}rows.push(r);
  }
  const mean=rows.reduce((s,r)=>s+r.signal,0)/rows.length,
   sd=Math.sqrt(rows.reduce((s,r)=>s+(r.signal-mean)**2,0)/rows.length);
  if(!(sd>0)){exclude('constant_cross_section');continue;}
  for(const row of rows){
   row.score=Math.max(-ALPHA_SCORE_LIMIT,Math.min(ALPHA_SCORE_LIMIT,(row.signal-mean)/sd));
   row.outcomes={};const history=new Map(bySymbol.get(row.symbol).history.map(r=>[r.date,r.adj_close]));
   for(const [h,maturity] of Object.entries(input.outcomes)){
    const q=history.get(maturity),p=history.get(input.origin),m=benchmarkPrice.get(maturity),m0=benchmarkPrice.get(input.origin);
    if(![q,p,m,m0].every(v=>Number.isFinite(v)&&v>0)){exclude('missing_outcome');continue;}
    const total=Math.log(q/p),marketReturn=Math.log(m/m0),residual=total-row.exposure.beta*marketReturn;
    row.outcomes[h]={total_log_return:total,benchmark_log_return:marketReturn,residual_log_return:residual,
     standardized_residual:residual/(row.exposure.omega*Math.sqrt(Number(h)/252))};
   }
  }
  origins.push({origin:input.origin,outcomes:input.outcomes,observations:rows});
 }
 return {method:'production-valuation-reconstructed-ttm-v1',price_cut:market.price_as_of,
  input_market_sha256:facts.input_market_sha256,origins,exclusions,production_eligible:false,
  scope:'Exact valuation, rerating and marketExposure functions on reconstructed TTM, current catalogue and provider-adjusted histories. Not original vintages, historical universe, full confidence/holdings-neutralized anchors or a strategy backtest.'};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const value=(f,d)=>{const i=process.argv.indexOf(f);return i<0?d:process.argv[i+1];},
  marketFile=value('--market','dist/data/market.json'),factsFile=value('--facts','out/ttm-signal-facts.json'),
  facts=JSON.parse(readFileSync(factsFile));
 if(hash(marketFile)!==facts.input_market_sha256)throw Error('Frozen market hash mismatch');
 const result=replay(JSON.parse(readFileSync(marketFile)),facts);
 result.input_facts_sha256=hash(factsFile);
 result.source_hashes=Object.fromEntries(['scripts/ttm_signal_replay.mjs','dist/assets/js/analytics.mjs','dist/assets/js/return-model.mjs',
  'dist/assets/js/financial-freshness.mjs'].map(p=>[p,hash(p)]));
 mkdirSync('out',{recursive:true});writeFileSync(value('--output','out/ttm-signal-replay.json'),JSON.stringify(result)+'\n');
 console.log(JSON.stringify({origins:result.origins.length,exclusions:result.exclusions,production_eligible:false}));
}
