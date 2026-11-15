import test from 'node:test';
import assert from 'node:assert/strict';
import { decisionAtCut } from '../scripts/first_cut_engine.mjs';

test('first-cut engine refuses a calibration from another cut', () => {
  assert.throws(() => decisionAtCut({ price_as_of: '2024-12-31', requested_as_of: '2024-12-31', assets: [] },
    { as_of: '2026-11-13' }), /not calibrated on the snapshot cut/);
});

test('first-cut engine refuses a snapshot whose information date is not the cut', () => {
  assert.throws(() => decisionAtCut({ price_as_of: '2024-12-31', requested_as_of: '2025-01-15',
    generated_at: '2024-12-31T22:00:00Z', macro: [], assets: [] }, { as_of: '2024-12-31' }), /Information date is not the cut/);
});
