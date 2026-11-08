import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {decodeOriginalDecision,selectFirstPublishedCloses,buildForwardAccount,runForwardAccount,
  auditForwardAccount,classifyDailySnapshot,partitionDailyArchives}
  from '../scripts/forward_account_bridge.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const days=['2026-11-30','2026-12-01','2026-12-02','2026-12-03'];
const market={price_as_of:days[0],generated_at:'2026-11-30T22:00:00Z',assets:[
 {symbol:'SPY',price_date:days[0],history:[{date:days[0],close:100}]},
 {symbol:'AAA',price_date:days[0],history:[{date:days[0],close:100}]}]};
const rawMarket=Buffer.from(JSON.stringify(market));
const policy={settings:{asOf:days[0],informationAsOf:days[0],account:{enabled:false},
 capital:1000,execution:{commissionFixed:0,commissionBps:0,spreadBps:0,
 slippageBps:0,capitalGainsTax:0,maxTurnover:1,minTrade:0},
 mandate:{referenceCurrency:'USD',cashYield:0,dividendPolicy:'cash',dividendWithholding:0}}};
const proposal={as_of:days[0],information_as_of:days[0],calibration_end:days[0],
 model_version:'0.35.0',status:'proposed',
 positions:[{symbol:'AAA',weight:.5},{symbol:'CASH',weight:.5}],
 current_account:{capital:1000,positions:[]},trade_plan:{rows:[{symbol:'AAA',side:'buy'}]}};
const json={policy_json:JSON.stringify(policy),proposal_json:JSON.stringify(proposal),
 source_hashes_json:JSON.stringify({}),input_manifest_json:JSON.stringify({})};
const origin={schema:'full-engine-first-capture-v2',
 study:'full-engine-prospective-registration-v2',role:'new-full-engine-only',
 cut:days[0],month:'2026-11',issued_at:'2026-11-30T23:00:00Z',
 market_collected_at:market.generated_at,engine_version:'0.35.0',
 status:'proposed',full_engine_confirmatory_eligible:false,
 predictive_validation:'not-established',...json,
 evidence:{market_sha256:sha(rawMarket),policy_sha256:sha(json.policy_json),
 forecast_sha256:sha(json.proposal_json),model_sha256:sha(json.source_hashes_json),
 inputs_sha256:sha(json.input_manifest_json)}};
const firstPublication={verified:true,first_commit:'a'.repeat(40),
 committed_at:'2026-12-01T00:00:00Z'};
const capture={origin,marketBytes:rawMarket,firstPublication};
const daily=days.slice(1).map((day,i)=>{
 const snapshot={schema_version:1,requested_as_of:day,price_as_of:day,
  collection_mode:'current',collected_at:day+'T22:00:00Z',
  assets:[{symbol:'SPY',currency:'USD',price_date:day,quote:{date:day,close:101+i}},
   {symbol:'AAA',currency:'USD',price_date:day,quote:{date:day,close:100+i*10}}]};
 const bytes=Buffer.from(JSON.stringify(snapshot));
 return {snapshot,bytes,source_sha256:sha(bytes),path:day,
  publication:{verified:true,first_commit:String(i+1).repeat(40),
  committed_at:day+'T23:00:00Z'}};
});
const issuer=symbol=>({schema:'issuer-cash-settlement-v1',symbol,
 currency:'USD',complete:true,original_source_verified:true,
 source_sha256:'b'.repeat(64),coverage_start:days[0],
 coverage_end:days.at(-1),events:[],splits:[]});
const evidence={AAA:issuer('AAA'),SPY:issuer('SPY')};
const sessions={schema:'verified-us-exchange-sessions-v1',
 original_source_verified:true,source_sha256:'f'.repeat(64),sessions:days};

test('weekend copy of Friday close is excluded regardless of legacy current label',()=>{
 const friday={...daily[0].snapshot,price_as_of:'2026-11-06',
  requested_as_of:'2026-11-08',collected_at:'2026-11-08T05:38:57Z',
  collection_mode:'current'};
 const classification=classifyDailySnapshot(friday);
 assert.equal(classification.eligible,false);
 assert.equal(classification.reason,'stale-market-close');
 const filtered=partitionDailyArchives([daily[0],{
  snapshot:friday,path:'weekend-legacy-republication'}]);
 assert.equal(filtered.accepted.length,1);
 assert.equal(filtered.excluded.length,1);
 assert.deepEqual(filtered.reasons,{'stale-market-close':1});
 const altered={...friday,collection_mode:'stale_market_close'};
 assert.equal(classifyDailySnapshot(altered).eligible,false);
});
test('pre-close, historical request and absent raw SPY quote cannot qualify',()=>{
 const original=daily[0].snapshot;
 const before={...original,collected_at:'2026-12-01T15:00:00Z'};
 assert.equal(classifyDailySnapshot(before).eligible,false);
 const historical={...original,requested_as_of:'2026-10-01'};
 assert.equal(classifyDailySnapshot(historical).reason,'historical-request');
 const missing={...original,assets:original.assets.filter(a=>a.symbol!=='SPY')};
 assert.equal(classifyDailySnapshot(missing).reason,'benchmark-original-close-missing');
 assert.throws(()=>selectFirstPublishedCloses([{
  ...daily[0],snapshot:{...original,requested_as_of:'2026-12-02'}}]),
  /not its original current-market archive/);
});

test('original hashes and original Git publication bind the proposed orders',()=>{
 const d=decodeOriginalDecision(capture);
 assert.equal(d.decision.positions[0].symbol,'AAA');
 const changed=structuredClone(origin);
 changed.proposal_json=changed.proposal_json.replace('proposed','hold');
 assert.throws(()=>decodeOriginalDecision({...capture,origin:changed}),/Modified original proposal_json/);
 assert.throws(()=>decodeOriginalDecision({...capture,
  firstPublication:{...firstPublication,committed_at:'2026-12-01T15:00:00Z'}}),
  /before the conservative next opening/);
});
test('first publication for a trading date is chosen before a later revised price',()=>{
 const revised=structuredClone(daily[0]);
 revised.snapshot.assets[1].quote.close=900;
 revised.snapshot.collected_at=days[1]+'T23:30:00Z';
 revised.bytes=Buffer.from(JSON.stringify(revised.snapshot));
 revised.source_sha256=sha(revised.bytes);
 revised.publication.committed_at='2026-12-02T00:00:00Z';
 revised.path='later';
 const got=selectFirstPublishedCloses([revised,...daily]);
 assert.equal(got.first.get(days[1]).snapshot.assets[1].quote.close,100);
 assert.equal(got.revisions.length,1);
});
test('one first-published decision becomes an accounting prefix without a refit',()=>{
 const inputs=buildForwardAccount({capture,daily,sessionEvidence:sessions,issuerEvidence:evidence});
 assert.deepEqual(inputs.prepared.calendar,days);
 assert.equal(inputs.prepared.decisions[0].execute,days[1]);
 const result=runForwardAccount(inputs);
 assert.equal(result.status,'complete',JSON.stringify(result.issues));
 assert.equal(result.nav[0].nav,1000);
 assert.equal(result.nav[1].holdings[0].quantity,5);
 assert.equal(result.nav.at(-1).nav,1100);
 assert.ok(result.nav.every(n=>Math.abs(n.identity_residual)<1e-6));
 assert.equal(result.formal_validation,false);
});
test('unobserved first execution session cannot be skipped',()=>{
 assert.throws(()=>buildForwardAccount({capture,daily:daily.slice(1),
  sessionEvidence:sessions,issuerEvidence:evidence}),/lacks its original first-published close/);
});
test('missing issuer settlement source does not become zero dividend income',()=>{
 assert.throws(()=>buildForwardAccount({capture,daily,
  sessionEvidence:sessions,issuerEvidence:{SPY:evidence.SPY}}),
  /Missing verified issuer dividend/);
});
test('a later return cannot change earlier simulated trades',()=>{
 const a=runForwardAccount(buildForwardAccount({capture,daily,sessionEvidence:sessions,issuerEvidence:evidence}));
 const altered=daily.map(row=>({...row,snapshot:structuredClone(row.snapshot)}));
 altered.at(-1).snapshot.assets[1].quote.close=300;
 altered.at(-1).bytes=Buffer.from(JSON.stringify(altered.at(-1).snapshot));
 altered.at(-1).source_sha256=sha(altered.at(-1).bytes);
 const b=runForwardAccount(buildForwardAccount({capture,daily:altered,sessionEvidence:sessions,issuerEvidence:evidence}));
 assert.deepEqual(a.nav.slice(0,-1),b.nav.slice(0,-1));
 assert.deepEqual(a.decisions,b.decisions);
 assert.notEqual(a.nav.at(-1).nav,b.nav.at(-1).nav);
});
test('a sell-off cannot make an unverified issuer or session calendar admissible',()=>{
 assert.throws(()=>buildForwardAccount({capture,daily,
  sessionEvidence:{...sessions,original_source_verified:false},issuerEvidence:evidence}),
  /separately verified exchange-session/);
 assert.throws(()=>buildForwardAccount({capture,daily,
  sessionEvidence:sessions,issuerEvidence:{...evidence,AAA:{...evidence.AAA,
    original_source_verified:false}}}),/verified issuer/);
});
test('current repo has zero original monthly full-engine origins, not fabricated account returns',()=>{
 const status=auditForwardAccount();
 assert.equal(status.status,'blocked-no-original-full-engine-capture');
 assert.equal(status.original_months,0);
 assert.equal(status.causally_certified_origins,0);
 assert.equal(status.formal_validation,false);
});
