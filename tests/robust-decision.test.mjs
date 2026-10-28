import test from 'node:test';
import assert from 'node:assert/strict';
import { pairedDecisionEvidence, reviewRobustDecision, tailStressInputs } from '../dist/assets/js/robust-decision.mjs?v=0.34.1';
import {generatePaths,evaluatePaths} from '../dist/assets/js/path-model.mjs?v=0.34.1';
import { prepareComposition, finalizeCompositionDecision } from '../dist/assets/js/composer.mjs?v=0.34.1';
import { DEFAULT_MANDATE } from '../dist/assets/js/policy.mjs?v=0.34.1';

test('decision evidence uses the mandate utility rather than a log-return shortcut', () => {
  const growth = { ...DEFAULT_MANDATE };
  const log = pairedDecisionEvidence([Math.log(1.02), Math.log(1.02)], [0, 0], growth, 10000);
  assert.ok(Math.abs(log.lowerGain - 200) < 1e-8);
  const preservation = { ...growth, objective: 'preservation', riskAversion: 2 };
  const crra = pairedDecisionEvidence([1 - 1 / 1.02, 1 - 1 / 1.02], [0, 0], preservation, 10000);
  assert.ok(Math.abs(crra.lowerGain - 200) < 1e-8);
  const target = { ...growth, objective: 'target', terminalTarget: 12000 };
  const goal = pairedDecisionEvidence([-.01, -.01], [-.04, -.04], target, 10000);
  assert.ok(Math.abs(goal.lowerGain - 1000) < 1e-8);
  assert.throws(() => pairedDecisionEvidence([NaN, 0], [0, 0], growth, 10000), /no finita/);
});

function fixture() {
  const cut = '2026-10-23';
  const history = Array.from({ length: 301 }, (_, k) => ({
    date: new Date(Date.parse(cut + 'T12:00:00Z') - (300-k) * 86400000).toISOString().slice(0, 10),
    close: 100, adj_close: 100, volume: 1e6,
  }));
  const snapshot = { price_as_of: cut, generated_at: cut + 'T23:00:00Z', macro: [{id:'DGS3MO',date:cut,value:4}], assets: [
    { symbol: 'AAA', type: 'stock', sector: 'Industria', price: 100, price_date: cut, history,
      assumptions: { growth: -.05, multiple: 20, horizon: 3, discount: .1 }, dividend_per_share: 0,
      financials: { eps: { value: 10, filed: '2026-08-01', period_end: '2026-06-30', method: 'TTM' } } },
    { symbol: 'SHY', type: 'etf', sector: 'Treasuries cortos', price: 100, price_date: cut, history,
      bond_profile: { date: cut, yieldToMaturity: .045, duration: 1, expenseRatio: 0 }, dividend_per_share: 0 },
  ] };
  const settings = { seed: 7, asOf: cut, informationAsOf: cut, volatilityMode: 'legacy', model: 'gbm',
    horizon: 1, capital: 100000, account: { enabled: true, cash: 5000,
      positions: [{ symbol: 'SHY', quantity: 950 }] },
    execution: { minBenefit: 100, spreadBps: 0, slippageBps: 0 },
    macroRegimes: [{ id: 'base', probability: 1, earningsShift: 0, multipleShift: 0, rateShift: 0, rateJumpBps: 0 }] };
  return prepareComposition(snapshot, settings, { AAA: { multiple: 30 } },
    { maxGlobal: 1, maxPosition: 1, maxTreasury: 1, maxSector: 1 });
}

test('a base-model winner is rejected when no-rerating loses to the real incumbent', () => {
  const x = fixture(), before = JSON.stringify(x);
  const target = [{ symbol: 'AAA', weight: .95 }, { symbol: 'CASH', weight: .05 }];
  const audit = reviewRobustDecision(x, target, { paths: 100 });
  assert.equal(audit.models.length, 5);
  assert.ok(audit.models.find(r => r.id === 'original').evidence.gain > 100);
  assert.ok(audit.models.find(r => r.id === 'no_rerating').evidence.gain < 0);
  assert.equal(audit.status, 'rejected');
  const result = finalizeCompositionDecision({ status: 'proposed', positions: target,
    metrics: {}, trade_plan: {}, diagnostics: {} }, x, 100);
  assert.equal(result.status, 'hold');
  assert.match(result.reason, /transición descartada.*Composición/);
  assert.deepEqual(result.positions, x.current.positions);
  assert.equal(result.trade_plan.total, 0);
  assert.deepEqual(result.candidate_review.positions, target);
  assert.equal(JSON.stringify(x), before);
});

test('the normal gate evaluates preservation, target, withdrawals and FX without dropping the mandate', () => {
  for (const change of [
    { objective: 'preservation', riskAversion: 3 },
    { objective: 'target', terminalTarget: 115000 },
    { monthlyWithdrawal: 100 },
    { referenceCurrency: 'PEN', fxConfirmed: true, fxSpot: 3.8, fxAnnualChange: -.02 },
  ]) {
    const x = fixture(); x.policy = { ...x.policy, ...change };
    x.options = { ...x.options, mandate: x.policy };
    const report = reviewRobustDecision(x, x.current.positions, { paths: 100 });
    assert.equal(report.models.length, 5);
    assert.ok(report.models.every(r => Math.abs(r.evidence.gain) < 1e-7));
    assert.equal(report.status, 'rejected');
  }
});

test('a generic anchor cannot supply evidence for liquidating an existing holding', () => {
  const x = fixture();
  x.anchors[x.assets.findIndex(a => a.symbol === 'SHY')].bond = null;
  const target = [{ symbol: 'AAA', weight: .95 }, { symbol: 'CASH', weight: .05 }];
  const result = finalizeCompositionDecision({ status: 'proposed', positions: target,
    diagnostics: {} }, x, 100);
  assert.equal(result.status, 'hold');
  assert.equal(result.diagnostics.robustDecision.status, 'incomplete');
  assert.deepEqual(result.diagnostics.robustDecision.unanchoredIncumbents, ['SHY']);
  assert.equal(result.metrics, null);
  assert.equal(result.trade_plan.total, 0);
});

test('a missing observed short rate makes the economic comparison incomplete',()=>{
  const x=fixture();x.riskFree=NaN;
  const r=reviewRobustDecision(x,x.current.positions,{paths:1000});
  assert.equal(r.status,'incomplete');assert.deepEqual(r.models,[]);
  assert.match(r.missingEconomicInputs[0],/DGS3MO/);
});
test('the separate Student risk stress runs its actual law when economics uses the legacy comparator',()=>{
  const x=fixture(),before=JSON.stringify(x),tail=tailStressInputs(x),
    sample=generatePaths(tail,100,23,52);
  assert.equal(x.conditional.dynamic,false);
  assert.equal(tail.conditional.dynamic,true);
  assert.equal(sample.meanPreservingPriceInnovations,false);
  const weights=tail.assets.map(a=>a.symbol==='SHY'?.95:a.symbol==='CASH'?.05:0);
  assert.throws(()=>evaluatePaths(weights,sample),/solo estrés/);
  assert.ok(Number.isFinite(evaluatePaths(weights,sample,{riskOnly:true}).cvar95));
  assert.equal(JSON.stringify(x),before);
});
