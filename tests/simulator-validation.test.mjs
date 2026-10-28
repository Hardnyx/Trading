import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {buildKernelForecast,scoreKernelForecast,scoreDistribution,distributionSummary,
  summarizeKernelValidation,updateKernelLedger} from '../scripts/simulator_validation.mjs';
import {PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs?v=0.35.0';

const constant=value=>distributionSummary(Array(100).fill(value));
function origin(issue='2026-10-23'){
  return {horizons:[1,5,21],input_price_as_of:'2026-10-23',issue_ny_date:issue,issued_at:issue+'T23:00:00Z',
    lead_sessions:2,price_kernel_version:PRICE_KERNEL_VERSION,
    records:[{symbol:'AAA',horizon_sessions:1,kernel:constant(.1),ewma_zero_mean:constant(0)}]};
}
function realized(cut='2026-10-28'){
  const history=[{date:'2026-10-23',adj_close:50},{date:'2026-10-26',adj_close:52},
    {date:'2026-10-27',adj_close:55},{date:'2026-10-28',adj_close:60.5}];
  return {price_as_of:cut,assets:['AAA','SPY'].map(symbol=>({symbol,history}))};
}
test('the score waits for the exact future origin and maturity, using only observed sessions',()=>{
  assert.equal(scoreKernelForecast(origin(),realized('2026-10-27'),1),null);
  const score=scoreKernelForecast(origin(),realized(),1);
  assert.equal(score.origin_date,'2026-10-27');assert.equal(score.maturity_date,'2026-10-28');
  assert.ok(Math.abs(score.rows[0].kernel.realized-.1)<1e-12);
  assert.equal(score.rows[0].kernel.var95_exception,false);
  assert.ok(score.rows[0].kernel.crps<score.rows[0].ewma_zero_mean.crps);
  assert.equal(scoreKernelForecast(origin('2026-10-27'),realized(),1).status,'nonprospective');
});
test('missing original outcome is visible and cannot silently shift to another date',()=>{
  const snapshot=realized();snapshot.assets[0]={...snapshot.assets[0],history:snapshot.assets[0].history.slice(0,-1)};
  const score=scoreKernelForecast(origin(),snapshot,1);
  assert.equal(score.rows[0].status,'missing-original-outcome');assert.equal(score.maturity_date,'2026-10-28');
});
test('proper distribution score and signed expected shortfall handle entirely positive returns',()=>{
  const f=constant(.1),same=scoreDistribution(f,.1),wrong=scoreDistribution(constant(-.1),.1);
  assert.ok(Math.abs(same.crps)<1e-12);assert.ok(wrong.crps>.19);
  assert.ok(Math.abs(same.es_residual)<1e-12);assert.ok(f.es_loss_signed<0);
  assert.throws(()=>distributionSummary([NaN]),/Nonfinite/);
});
test('overlapping weekly origins do not masquerade as independent observations or validation',()=>{
  const one=(start,end)=>({status:'scored',price_kernel_version:PRICE_KERNEL_VERSION,horizon_sessions:5,
    origin_date:start,maturity_date:end,rows:[{status:'scored',kernel:scoreDistribution(constant(.1),.1),
      ewma_zero_mean:scoreDistribution(constant(0),.1)}]});
  const summary=summarizeKernelValidation([origin()],
    [one('2026-01-01','2026-01-08'),one('2026-01-02','2026-01-09'),one('2026-01-08','2026-01-15')],'2026-10-28T12:00:00Z');
  assert.equal(summary.horizons[5].scored_origins,3);assert.equal(summary.horizons[5].nonoverlapping_origins,2);
  assert.equal(summary.horizons[5].status,'accumulating');assert.equal(summary.predictive_validation,'not-established');
  assert.equal(summary.automatic_promotion,false);
});
test('old kernels and portfolio rows cannot inflate evidence for the current asset forecast',()=>{
  const rows=['AAA','PORTFOLIO:reference-decision'].map(symbol=>({symbol,status:'scored',
    kernel:scoreDistribution(constant(.1),.1),ewma_zero_mean:scoreDistribution(constant(0),.1)}));
  const current={status:'scored',price_kernel_version:PRICE_KERNEL_VERSION,horizon_sessions:1,
    origin_date:'2026-10-27',maturity_date:'2026-10-28',rows};
  const summary=summarizeKernelValidation([origin(),{...origin(),price_kernel_version:'old'}],
    [current,{...current,price_kernel_version:'old'}],'2026-10-28T12:00:00Z');
  assert.equal(summary.sealed,1);assert.equal(summary.historical_sealed,2);
  assert.equal(summary.horizons[1].scored_origins,1);assert.equal(summary.horizons[1].asset_observations,1);
  assert.equal(summary.horizons[1].nonoverlapping_asset_observations,1);
  assert.equal(summary.horizons[1].portfolios['PORTFOLIO:reference-decision'].observations,1);
  assert.equal(summary.horizons[1].origin_block95_crps_gain,null);
});
function fixture(){
  const cut='2026-10-23',stamp=cut+'T23:00:00Z',history=Array.from({length:300},(_,k)=>({
    date:new Date(Date.parse(cut+'T12:00:00Z')-(299-k)*86400000).toISOString().slice(0,10),
    close:100*Math.exp(.01*Math.sin(k)),adj_close:100*Math.exp(.01*Math.sin(k)),volume:1e6}));
  const snapshot={price_as_of:cut,requested_as_of:cut,generated_at:stamp,macro:[{id:'DGS3MO',date:cut,value:4}],assets:[
    {symbol:'AAA',type:'stock',sector:'Industria',history,price:history.at(-1).close,price_date:cut,
      dividend_per_share:0,assumptions:{growth:.06,multiple:20,horizon:3,discount:.1},
      financials:{eps:{value:5,filed:'2026-08-01',period_end:'2026-06-30',method:'TTM'}}},
    {symbol:'SPY',type:'etf',sector:'Índice amplio',history,price:history.at(-1).close,price_date:cut,
      dividend_per_share:0},
    {symbol:'SHY',type:'etf',sector:'Treasuries cortos',history,price:history.at(-1).close,price_date:cut,
      dividend_per_share:0,bond_profile:{date:cut,yieldToMaturity:.045,duration:1,expenseRatio:0}}]};
  return {snapshot,volatility:{schema_version:1,as_of:cut,source_market_generated_at:stamp,
    no_news_attribution:true,instruments:{}}};
}
test('the forecast is built from the production prefix and cannot be backdated',()=>{
  const {snapshot,volatility}=fixture(),before=JSON.stringify(snapshot),
    f=buildKernelForecast(snapshot,volatility,'2026-10-23T23:30:00Z',{paths:100});
  assert.equal(f.records.length,9);assert.deepEqual(f.horizons,[1,5,21]);assert.equal(f.lead_sessions,2);
  assert.ok(f.records.some(r=>r.symbol==='PORTFOLIO:risk-comparator'));
  assert.equal(f.price_kernel_version,PRICE_KERNEL_VERSION);
  assert.equal(JSON.stringify(snapshot),before);
  assert.throws(()=>buildKernelForecast(snapshot,volatility,'2026-10-23T22:00:00Z',{paths:100}),/predate/);
});
test('a source refresh cannot overwrite the first sealed forecast for a cut',()=>{
  const root=mkdtempSync(resolve(tmpdir(),'trading-kernel-ledger-'));
  try{
    const {snapshot,volatility}=fixture();mkdirSync(resolve(root,'dist/data'),{recursive:true});
    const save=()=>{writeFileSync(resolve(root,'dist/data/market.json'),JSON.stringify(snapshot));
      writeFileSync(resolve(root,'dist/data/volatility.json'),JSON.stringify(volatility));};save();
    updateKernelLedger({root,issuedAt:'2026-10-23T23:30:00Z'});
    const path=resolve(root,'data/simulator-validation/forecasts/2026-10-23.json.gz'),first=readFileSync(path);
    snapshot.assets[0].financials.eps.value=50;save();
    const next=updateKernelLedger({root,issuedAt:'2026-10-23T23:40:00Z'});
    assert.deepEqual(readFileSync(path),first);assert.equal(next.sealed,1);
    assert.equal(next.horizons[1].scored_origins,0);
  }finally{rmSync(root,{recursive:true,force:true});}
});
