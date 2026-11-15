/** Run the engine's reference decision on the reconstructed first-cut market.
 *
 * Reads the as-of snapshot and its volatility calibration, both cut to what
 * was public on the cut, and records the proposal the current engine makes
 * there. A development-period reconstruction: no outcome after the cut is
 * read here and the record is never a prospective forecast.
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { composeMultiStart } from '../dist/assets/js/composer.mjs?v=0.35.0';
import { referenceRequest } from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import { MODEL_VERSION } from '../dist/assets/js/policy.mjs?v=0.35.0';
import { PRICE_KERNEL_VERSION } from '../dist/assets/js/path-model.mjs?v=0.35.0';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const BASE = 'data/historical/first-cut-snapshot-v1';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export const SEARCH = { candidates: 300, paths: 600, finalPaths: 3000 };

export function decisionAtCut(market, volatility, search = SEARCH) {
  if (volatility.as_of !== market.price_as_of) throw Error('Volatility is not calibrated on the snapshot cut');
  const snapshot = { ...market, volatility };
  const preset = referenceRequest(snapshot);
  if (preset.settings.informationAsOf !== market.requested_as_of) throw Error('Information date is not the cut');
  const model = composeMultiStart(snapshot, preset.settings, preset.overrides, preset.rules, search);
  return { preset, model };
}

function main() {
  const name = process.argv[2] || '2024-12-31';
  const marketBytes = gunzipSync(readFileSync(resolve(ROOT, BASE, name + '.json.gz')));
  const volatilityBytes = gunzipSync(readFileSync(resolve(ROOT, BASE, name + '.volatility.json.gz')));
  const market = JSON.parse(marketBytes), volatility = JSON.parse(volatilityBytes);
  const started = Date.now();
  const { preset, model } = decisionAtCut(market, volatility);
  const record = {
    schema: 'first-cut-engine-decision-v1', cut: market.requested_as_of, price_as_of: market.price_as_of,
    computed_at: new Date().toISOString(), seconds: Math.round((Date.now() - started) / 1000),
    engine_version: MODEL_VERSION, price_kernel_version: PRICE_KERNEL_VERSION,
    market_sha256: sha(marketBytes), volatility_sha256: sha(volatilityBytes),
    universe: { assets: market.assets.length, stocks: market.assets.filter(a => a.type === 'stock').length },
    settings: { seed: preset.settings.seed, horizon: preset.settings.horizon, mandate: preset.settings.mandate,
      volatility_mode: preset.settings.volatilityMode, search: SEARCH },
    status: model.status, positions: model.positions || [],
    metrics: model.metrics ? { mean: model.metrics.meanReturn, median: model.metrics.medianReturn,
      p05: model.metrics.p05, p95: model.metrics.p95, loss_probability: model.metrics.lossProbability,
      cvar95: model.metrics.cvar95, volatility: model.metrics.volatility } : null,
    warnings: model.warnings || [],
    outcomes_read: false, prospective: false,
    note: 'Development-period reconstruction with the current engine; it says nothing about predictive skill until scored under a registered protocol.',
  };
  mkdirSync(resolve(ROOT, BASE), { recursive: true });
  writeFileSync(resolve(ROOT, BASE, name + '.decision.json'), JSON.stringify(record, null, 1) + '\n');
  console.log(JSON.stringify({ status: record.status, seconds: record.seconds,
    positions: record.positions.map(p => [p.symbol, +p.weight.toFixed(4)]), metrics: record.metrics }));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
