import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {gunzipSync} from 'node:zlib';
import {
  lastWeekdayCandidate,buildFullEngineCapture,preserveFullEngineCapture,
  recordBlockedMonthlyCapture,
} from '../scripts/capture_full_engine_origin.mjs';

const reg=JSON.parse(readFileSync(new URL('../docs/protocolo-confirmacion-integral-v2.json',import.meta.url)));
const cut='2026-11-30',generated='2026-11-30T22:00:00Z',issued='2026-11-30T23:00:00Z';
const market={price_as_of:cut,generated_at:generated,
  assets:[{symbol:'SPY',price_date:cut,history:[
    {date:'2026-11-27',close:100,adj_close:100},
    {date:cut,close:101,adj_close:101}]}],macro:[]};
const volatility={as_of:cut,source_market_generated_at:generated};
const request={settings:{asOf:cut,informationAsOf:cut,seed:20261024,account:{enabled:false}},
  overrides:{},rules:{}};
const proposal={as_of:cut,information_as_of:cut,calibration_end:cut,
  model_version:'0.35.0',status:'hold',positions:[{symbol:'CASH',weight:1}],
  trade_plan:{orders:[],total:0},settings:{informationAsOf:cut,seed:20261024},
  metrics:{meanReturn:.03,p05:-.1,p95:.2}};
const sourceHashes=Object.fromEntries(Array.from({length:35},(_,i)=>
  ['dist/assets/js/model-'+i+'.mjs','a'.repeat(64)]));
function bundle(){
  return buildFullEngineCapture({market,volatility,
    marketBytes:Buffer.from(JSON.stringify(market)),volatilityBytes:Buffer.from(JSON.stringify(volatility)),
    proposal,request,issuedAt:issued,sourceHashes,registration:reg});
}
test('only a conservative final weekday qualifies as a candidate',()=>{
  assert.equal(lastWeekdayCandidate('2026-11-30'),true);
  assert.equal(lastWeekdayCandidate('2026-11-27'),false);
  assert.equal(lastWeekdayCandidate('2026-11-29'),false);
  assert.throws(()=>lastWeekdayCandidate('2026-02-30'),/Invalid calendar date/);
});
test('first original archive binds the proposal to model, policy and raw inputs',()=>{
  const result=bundle(),r=result.candidate;
  assert.equal(r.cut,cut);
  assert.equal(r.issued_at,issued);
  assert.equal(r.full_engine_confirmatory_eligible,false);
  assert.equal(r.forecast_scope.includes('not certified'),true);
  assert.equal(r.evidence.model_sha256.length,64);
  assert.equal(r.evidence.forecast_sha256.length,64);
  assert.equal(JSON.parse(r.proposal_json).metrics.meanReturn,.03);
  assert.equal(JSON.parse(gunzipSync(result.marketArchiveBytes)).generated_at,generated);
});
test('future inputs and backdated or mismatched proposals are rejected before archive',()=>{
  const laterMarket={...market,generated_at:'2026-12-01T01:00:00Z'};
  assert.throws(()=>buildFullEngineCapture({market:laterMarket,volatility,
    marketBytes:Buffer.from(JSON.stringify(laterMarket)),volatilityBytes:Buffer.from(JSON.stringify(volatility)),
    proposal,request,issuedAt:issued,sourceHashes,registration:reg}),/post-close/);
  const oldProposal={...proposal,calibration_end:'2026-12-01'};
  assert.throws(()=>buildFullEngineCapture({market,volatility,
    marketBytes:Buffer.from(JSON.stringify(market)),volatilityBytes:Buffer.from(JSON.stringify(volatility)),
    proposal:oldProposal,request,issuedAt:issued,sourceHashes,registration:reg}),/calibrated/);
  const earlyRequest={...request,settings:{...request.settings,informationAsOf:'2026-12-01'}};
  assert.throws(()=>buildFullEngineCapture({market,volatility,
    marketBytes:Buffer.from(JSON.stringify(market)),volatilityBytes:Buffer.from(JSON.stringify(volatility)),
    proposal,request:earlyRequest,issuedAt:issued,sourceHashes,registration:reg}),/Reference request/);
});
test('first capture bytes are immutable and a second origin in same month is rejected',()=>{
  const root=mkdtempSync(join(tmpdir(),'trading-origin-'));
  try{
    const data=bundle(),first=preserveFullEngineCapture(root,data);
    assert.equal(first.created,true);
    const second=preserveFullEngineCapture(root,data);
    assert.equal(second.created,false);
    assert.ok(existsSync(resolve(root,first.origin)));
    const changed=bundle();
    changed.candidate.evidence.forecast_sha256='b'.repeat(64);
    assert.throws(()=>preserveFullEngineCapture(root,changed),/Immutable full-engine archive differs/);
    const duplicate=bundle();
    duplicate.candidate.cut='2026-11-27';
    assert.throws(()=>preserveFullEngineCapture(root,duplicate),/already exists/);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('failed month-end proposals leave an immutable non-confirmatory attempt',()=>{
  const root=mkdtempSync(join(tmpdir(),'trading-blocked-origin-'));
  try{
    const args={root,market,volatility,marketBytes:Buffer.from(JSON.stringify(market)),
      volatilityBytes:Buffer.from(JSON.stringify(volatility)),issuedAt:issued,
      stage:'daily-origin-seal',reason:'Cannot seal a probability forecast without feasible model'};
    const first=recordBlockedMonthlyCapture(args);
    assert.equal(first.status,'blocked-attempt-recorded');
    const archived=JSON.parse(readFileSync(resolve(root,first.path),'utf8'));
    assert.equal(archived.original_full_engine_forecast_created,false);
    assert.equal(archived.full_engine_confirmatory_eligible,false);
    assert.equal(archived.future_outcomes,null);
    assert.equal(archived.market_sha256.length,64);
    assert.equal(gunzipSync(readFileSync(resolve(root,
      'data/confirmatory/full-engine-v2',archived.market_archive))).toString('utf8'),
      JSON.stringify(market));
    assert.equal(gunzipSync(readFileSync(resolve(root,
      'data/confirmatory/full-engine-v2',archived.volatility_archive))).toString('utf8'),
      JSON.stringify(volatility));
    const second=recordBlockedMonthlyCapture({...args,reason:'A later diagnostic failure'});
    assert.equal(second.status,'already-recorded');
    assert.deepEqual(JSON.parse(readFileSync(resolve(root,first.path),'utf8')),archived);
    const originalArchive=resolve(root,'data/confirmatory/full-engine-v2',
      archived.market_archive);
    const originalBytes=readFileSync(originalArchive);
    const changedBytes=Buffer.from(originalBytes);
    changedBytes[changedBytes.length-1]^=1;
    writeFileSync(originalArchive,changedBytes);
    assert.throws(()=>recordBlockedMonthlyCapture(args));
    writeFileSync(originalArchive,originalBytes);
    const genuine=preserveFullEngineCapture(root,bundle());
    assert.equal(genuine.created,true);
    assert.throws(()=>recordBlockedMonthlyCapture(args),/already exists/);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('blocked attempts reject future or unregistered capture inputs',()=>{
  const root=mkdtempSync(join(tmpdir(),'trading-blocked-invalid-'));
  try{
    const args={root,market,volatility,marketBytes:Buffer.from(JSON.stringify(market)),
      volatilityBytes:Buffer.from(JSON.stringify(volatility)),issuedAt:issued,
      stage:'monthly-full-engine-capture',reason:'Missing eligible order'};
    assert.equal(recordBlockedMonthlyCapture({...args,market:{...market,price_as_of:'2026-11-27'}}).status,'not-month-end');
    assert.throws(()=>recordBlockedMonthlyCapture({...args,issuedAt:'2026-12-01T23:00:00Z'}),/same-session/);
    assert.throws(()=>recordBlockedMonthlyCapture({...args,issuedAt:'2026-11-30T19:00:00Z'}),/same-session/);
    assert.throws(()=>recordBlockedMonthlyCapture({...args,marketBytes:Buffer.from('{}')}),/do not match/);
    assert.throws(()=>recordBlockedMonthlyCapture({...args,stage:'fake-success'}),/Unknown/);
    assert.deepEqual(existsSync(resolve(root,'data/confirmatory/full-engine-v2/attempts')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});
