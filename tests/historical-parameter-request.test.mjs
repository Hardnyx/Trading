// Reconstruct the registered request without rerunning simulation or selection.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {pilotRequest} from '../scripts/scoped_engine_pilot.mjs';

const root = new URL('../', import.meta.url);
const loadGz = p => JSON.parse(gunzipSync(readFileSync(new URL(p,root))));
const pilot = JSON.parse(readFileSync(new URL('docs/protocolo-piloto-integrado-v1.json',root)));
const bundle = loadGz('data/historical/scoped-engine-pilot-v1/inputs.json.gz');
const full = loadGz('data/historical/scoped-engine-pilot-v1/results.json.gz');
const summary = JSON.parse(readFileSync(new URL('data/historical/scoped-engine-pilot-v1/report.json',root)));
const hash = x => createHash('sha256').update(JSON.stringify(x)).digest('hex');

test('registered request seed and settings reproduce the frozen pre-search hashes',()=>{
  assert.equal(bundle.origins.length,2);
  assert.equal(full.results.length,bundle.origins.length);
  for(let i=0;i<bundle.origins.length;i++) {
    const origin=bundle.origins[i], saved=full.results[i], review=summary.results[i];
    const {settings,overrides,rules}=pilotRequest(origin,pilot);
    const observed=hash({settings,overrides,rules});
    assert.equal(settings.seed,pilot.seed);
    assert.equal(settings.informationAsOf,origin.cut);
    assert.equal(settings.volatilityMode,'ewma');
    assert.equal(settings.volatilityData,null);
    assert.equal(observed,saved.request_sha256,
      'Registered request differs from frozen pre-search engine input at '+origin.cut);
    assert.equal(observed,review.request_sha256);
    assert.equal(saved.cut,origin.cut);
    assert.equal(review.cut,origin.cut);
    assert.equal(saved.proposal.settings.volatilityMode,'ewma');
  }
});
