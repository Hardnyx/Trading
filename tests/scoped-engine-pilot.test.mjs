import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { referenceRequest } from '../dist/assets/js/reference-preset.mjs';
import { validateOrigin, pilotRequest } from '../scripts/scoped_engine_pilot.mjs';

const protocol=JSON.parse(readFileSync(new URL('../docs/protocolo-piloto-integrado-v1.json',import.meta.url)));
function origin() {
  const cut='2024-12-31', price={price:100,price_date:cut,
    history:[{date:'2024-12-30',close:99,adj_close:99},{date:cut,close:100,adj_close:100}]};
  return {cut,snapshot:{price_as_of:cut,requested_as_of:cut,generated_at:'2026-10-31T12:00:00Z',positions:[],macro:[],
    assets:[{symbol:'AAA',type:'stock',...structuredClone(price),splits:[],dividend_per_share:1,
      financials:{eps:{value:2,filed:'2024-11-01',period_end:'2024-09-30',
        components:[{filed:'2024-11-01',end:'2024-09-30'}]},history:[]},filings:[]},
    {symbol:'SPY',type:'etf',...structuredClone(price),financials:{},
      holdings:{as_of:'2024-09-30',observed_at:'2024-12-11T12:00:00Z',retrieved_at:'2026-10-30T12:00:00Z',
        observed_at_semantics:'virtual-public-availability-clock-for-research-not-capture',original_capture_verified:false}}]}};
}

test('pilot preserves reference policy, seed, cash account and guards; only uses the registered risk variant',()=>{
  const o=origin(), expected=referenceRequest(o.snapshot);
  expected.settings.volatilityMode='ewma';expected.settings.volatilityData=null;
  const actual=pilotRequest(o,protocol);
  assert.deepEqual(actual,expected);
  assert.equal(actual.settings.seed,20261024);
  assert.equal(actual.settings.account.enabled,false);
  assert.equal(actual.settings.baseline,null);
  assert.equal(actual.settings.mandate.dividendPolicy,'cash');
});

test('later prices, EPS and filings fail closed before the engine runs',()=>{
  const mutations=[o=>o.snapshot.assets[0].history.push({date:'2025-01-02',close:999,adj_close:999}),
    o=>o.snapshot.assets[0].financials.eps.filed=o.cut,
    o=>o.snapshot.assets[0].financials.eps.components[0].filed='2025-01-01',
    o=>o.snapshot.assets[0].filings.push({filing_date:'2025-01-01',report_date:'2024-12-01'})];
  for(const mutate of mutations){const o=origin();mutate(o);assert.throws(()=>validateOrigin(o));}
});

test('current profiles, financial quality and volatility calibrations cannot leak into a pilot',()=>{
  for(const mutate of [o=>o.snapshot.volatility={},o=>o.snapshot.assets[0].analyst_estimates={},
      o=>o.snapshot.assets[0].bond_profile={},o=>o.snapshot.assets[0].financials.revenue={value:999},
      o=>o.snapshot.validated_opportunities={AAA:{}}]) {
    const o=origin();mutate(o);assert.throws(()=>validateOrigin(o));
  }
});

test('historical public knowledge clock never becomes a claimed original capture',()=>{
  const o=origin();validateOrigin(o);
  o.snapshot.assets[1].holdings.original_capture_verified=true;
  assert.throws(()=>validateOrigin(o),/clock/);
  o.snapshot.assets[1].holdings.original_capture_verified=false;
  o.snapshot.assets[1].holdings.observed_at='2025-01-01T12:00:00Z';
  assert.throws(()=>validateOrigin(o),/clock/);
});

test('future macro observations, variants and current accounts are rejected',()=>{
  const o=origin();o.snapshot.macro=[{date:'2024-12-30',vintage_date:'2024-12-30',
    known_by_day:'2024-12-30',history:[{date:'2025-01-01',value:999}]}];
  assert.throws(()=>validateOrigin(o),/macro/);
  assert.throws(()=>pilotRequest(origin(),{...protocol,seed:99}),/policy/);
  const p=origin();p.snapshot.positions=[{symbol:'AAA',weight:1}];
  assert.throws(()=>validateOrigin(p),/account/);
});
