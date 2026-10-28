/** Chronological price-only falsification of the deployed fallback variance.
 * Current adjusted histories are reconstructed data, not original vintages.
 * Today's fixed basket is an exposure stress, never a historical strategy.
 */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {preparePaths,generatePaths,BASE_REGIME,PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {distributionSummary,scoreDistribution} from './simulator_validation.mjs';

export const REPLAY_PROTOCOL=Object.freeze({id:'price-only-fallback-risk-v1',lead:2,horizons:[1,5,21],
  minimumTraining:126,lookback:500,paths:2000,seed:0x2419b52f,
  models:['targeted_ewma','dynamic_ewma','flat_ewma'],
  symbols:['SPY','SGOV','SHV','IGSB','SHY','IEF','TLT','LQD','HYG','EMB','GLD','NVDA'],
  baskets:{current_exposure:{SGOV:.35,IGSB:.35,SHV:.25,CASH:.05},
    balanced_reference:{SPY:.35,SHY:.35,IEF:.25,CASH:.05},
    long_treasury_equity:{TLT:.35,IEF:.25,SPY:.35,CASH:.05},
    credit_equity:{SPY:.35,HYG:.2,IGSB:.15,SHY:.25,CASH:.05}}});

export function replayInputs(assets,cut,protocol=REPLAY_PROTOCOL){
  const past=protocol.symbols.map(symbol=>{
    const asset=assets.find(a=>a.symbol===symbol);if(!asset)throw Error('Missing predeclared instrument '+symbol);
    const history=asset.history.filter(r=>r.date<=cut).map(r=>({...r}));
    if(history.length<protocol.minimumTraining+1||history.at(-1)?.date!==cut)
      throw Error('Insufficient original training outcomes at '+cut+' for '+symbol);
    return {symbol,type:asset.type,sector:asset.sector,history,price_date:cut,price:history.at(-1).close};
  });
  const x=preparePaths(past,{horizon:1,model:'gbm',volatilityMode:'ewma',asOf:cut,informationAsOf:cut,
    driftMode:'manual',manualReturn:0,uncertainFundamentals:false,macroRegimes:[BASE_REGIME],
    mandate:{cashYield:0,referenceCurrency:'USD'}},{},past);
  // All models share a causal historical-mean nuisance. It is not the live
  // economic anchor: no past SEC, issuer yields or macro vintages are invented.
  x.anchors=x.anchors.map((a,i)=>{
    const prices=past[i].history.slice(-(protocol.lookback+1)),
      logs=prices.slice(1).map((r,k)=>Math.log(r.adj_close/prices[k].adj_close)),
      annualLog=252*logs.reduce((s,r)=>s+r,0)/logs.length+x.covariance[i][i]/2,
      annual=Math.expm1(annualLog);
    return {...a,annual,mu:annualLog,low:annual,high:annual,distributionMean:annual};
  });
  return x;
}

export function runPriceRiskReplay(market,{protocol=REPLAY_PROTOCOL,paths=protocol.paths,lastOrigins=null,onProgress=()=>{}}={}){
  const spy=market.assets.find(a=>a.symbol==='SPY'),dates=spy.history.filter(r=>r.date<=market.price_as_of).map(r=>r.date),
    months=new Map();dates.forEach((day,i)=>months.set(day.slice(0,7),i));
  let indices=[...months.values()].filter(i=>i>=protocol.minimumTraining&&i+protocol.lead+1<dates.length);
  if(lastOrigins)indices=indices.slice(-lastOrigins);
  const prices=new Map(market.assets.map(a=>[a.symbol,new Map(a.history.map(r=>[r.date,r.adj_close]))])),
    targets=[...protocol.symbols.map(symbol=>({name:symbol,weights:{[symbol]:1},scope:'instrument'})),
      ...Object.entries(protocol.baskets).map(([name,weights])=>({name:'PORTFOLIO:'+name,weights,
        scope:name==='current_exposure'?'ex-post-fixed-exposure':'predeclared-fixed-basket'}))],records=[];
  for(const index of indices){
    const cut=dates[index],x=replayInputs(market.assets,cut,protocol);
    const models={targeted_ewma:x,dynamic_ewma:{...x,horizonVariance:null},
      flat_ewma:{...x,conditional:{...x.conditional,dynamic:false},factorization:null}};
    for(const id of protocol.models){
      const sample=generatePaths(models[id],paths,protocol.seed,252,{maxSteps:protocol.lead+Math.max(...protocol.horizons)});
      for(const horizon of protocol.horizons){
        const start=dates[index+protocol.lead],end=dates[index+protocol.lead+horizon];
        if(!end)continue;
        for(const target of targets){
          let realized=0;
          for(const [symbol,w] of Object.entries(target.weights)){
            if(symbol==='CASH')continue;
            const p=prices.get(symbol)?.get(start),q=prices.get(symbol)?.get(end);
            if(!(p>0&&q>0))throw Error('Missing original outcome '+symbol+' '+start+' '+end);
            realized+=w*(q/p-1);
          }
          const values=Array.from({length:paths},(_,p)=>Object.entries(target.weights).reduce((total,[symbol,w])=>{
            if(symbol==='CASH')return total;
            const i=x.assets.findIndex(a=>a.symbol===symbol),offset=p*(sample.steps+1);
            return total+w*(sample.gross[i][offset+protocol.lead+horizon]/sample.gross[i][offset+protocol.lead]-1);
          },0)),distribution=distributionSummary(values);
          records.push({cut,origin_date:start,maturity_date:end,horizon,target:target.name,model:id,
            weights:target.weights,selection_scope:target.scope,training_sessions:x.observations,
            ...scoreDistribution(distribution,realized),q05:distribution.q05,es_loss_signed:distribution.es_loss_signed});
        }
      }
    }
    onProgress({cut,records:records.length});
  }
  return {method:protocol.id,price_kernel_version:PRICE_KERNEL_VERSION,protocol:{...protocol,paths},
    data_price_cut:market.price_as_of,created_at:new Date().toISOString(),records,
    prospective:false,original_vintages_verified:false,historical_universe_verified:false,
    production_eligible:false,
    scope:'Reconstructed chronological risk-component test. Same deployed Gaussian price/variance kernel, with GJR disabled and no economic/macro history. All models share causal past-price drift. The current basket is selected ex post, not a historical trading strategy. No proof of live mean anchors, net strategy utility, conditional jumps or full portfolio risk.'};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const quick=process.argv.includes('--quick'),path='dist/data/market.json',bytes=readFileSync(path),
    report=runPriceRiskReplay(JSON.parse(bytes),{paths:quick?1000:REPLAY_PROTOCOL.paths,lastOrigins:quick?24:null,
      onProgress:p=>console.log(JSON.stringify(p))});
  report.market_sha256=createHash('sha256').update(bytes).digest('hex');
  report.source_sha256=createHash('sha256').update(readFileSync(fileURLToPath(import.meta.url))).digest('hex');
  mkdirSync('out',{recursive:true});writeFileSync('out/price-risk-replay.json',JSON.stringify(report)+'\n');
  console.log(JSON.stringify({records:report.records.length,production_eligible:false}));
}
