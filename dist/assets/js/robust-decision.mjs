import { generatePaths, evaluatePaths, utilityCertaintyEquivalent } from './path-model.mjs?v=0.33.1';
import { MODEL_VARIANTS, variantInputs } from './robust-core.mjs?v=0.33.1';
import { tradePlan } from './policy.mjs?v=0.33.1';

export const DECISION_MODEL_LABELS = { original: 'Base', no_rerating: 'Sin re-rating',
  margin_stress: 'Margen y crédito', combined: 'Combinado', low_conviction: 'Baja convicción' };

/** Paired utility evidence for the actual mandate, including flows and FX. */
export function pairedDecisionEvidence(candidate, incumbent, policy, capital, familySize = 5) {
  const n = candidate.length;
  if (n < 2 || n !== incumbent.length || !(capital > 0) ||
      !Number.isInteger(familySize) || familySize < 1)
    throw Error('Comparación pareada de utilidad inválida');
  let total = 0, baseline = 0;
  for (let i = 0; i < n; i++) {
    if (![candidate[i], incumbent[i]].every(Number.isFinite))
      throw Error('Utilidad no finita en la comparación');
    total += candidate[i] - incumbent[i]; baseline += incumbent[i];
  }
  const mean = total / n, base = baseline / n;
  let squares = 0;
  for (let i = 0; i < n; i++) squares += (candidate[i] - incumbent[i] - mean) ** 2;
  const se = Math.sqrt(squares / (n - 1) / n);
  const z = Math.sqrt(2 * Math.log(familySize / .05));
  const equivalent = score => utilityCertaintyEquivalent(score, policy, capital);
  return { meanUtilityGain: mean, standardError: se, z, familySize, paths: n,
    gain: equivalent(base + mean) - equivalent(base),
    lowerGain: equivalent(base + mean - z * se) - equivalent(base) };
}

export function decisionRiskFailures(metrics, inputs) {
  const checks = [
    ['CVaR', metrics.cvar95, inputs.rules.cvarBudget],
    ['Pérdida', metrics.lossProbability, inputs.rules.maxLossProbability],
    ['Drawdown', metrics.drawdownProbability, inputs.policy.maxDrawdownProbability],
    ['Liquidez', metrics.liquidityFailureProbability, inputs.policy.maxLiquidityFailure],
  ];
  if (inputs.policy.capitalFloor)
    checks.push(['Suelo', metrics.capitalFloorBreachProbability, inputs.policy.maxLiquidityFailure]);
  return checks.filter(([, value, limit]) => !Number.isFinite(value) || value > limit + 1e-12)
    .map(([name]) => name);
}

/** A fixed candidate must beat holding in every declared alternative model. */
export function reviewRobustDecision(inputs, target, { paths = 1000, seed, validWeights } = {}) {
  const x = inputs, capital = x.current.capital;
  const missing = x.assets.filter((a, i) => {
    if (a.type === 'cash' || !x.current.positions.some(p => p.symbol === a.symbol && p.weight > 0)) return false;
    const own = x.options.assetAssumptions?.[a.symbol];
    return !x.anchors[i].fundamental && !x.anchors[i].bond &&
      !(Number.isFinite(own?.expectedReturn) && own.uncertainty > 0);
  }).map(a => a.symbol);
  if (missing.length) return { method: 'all-declared-models-paired-transition', status: 'incomplete',
    models: [], unanchoredIncumbents: missing, minimumGain: null, minimumLowerGain: null,
    hurdle: null, failingModels: [], currentViolatesRisk: false,
    scope: 'Unknown incumbent anchors prevent an economic comparison; a generic return is not evidence for selling' };
  const weights = positions => x.assets.map(a => positions.find(p => p.symbol === a.symbol)?.weight || 0);
  const current = weights(x.current.positions), proposed = weights(target);
  if (Math.abs(proposed.reduce((s, w) => s + w, 0) - 1) > 1e-8)
    throw Error('La propuesta contiene activos fuera del universo verificado');
  const plan = tradePlan(x.assets, target, x.current.positions, capital, x.costs);
  const initial = x.current.source === 'Capital inicial en efectivo';
  const executionOK = plan.complete && !plan.smallTrades &&
    (initial || plan.turnover <= x.costs.maxTurnover + 1e-8);
  const hurdle = Math.max(x.costs.minBenefit, plan.total * x.costs.benefitCostRatio);
  const verificationSeed = seed ?? (((x.options.seed >>> 0) ^ 0x79bdf135) >>> 0);
  const rows = [];
  for (const model of MODEL_VARIANTS) {
    const altered = variantInputs(x, model);
    const sample = generatePaths(altered, paths, verificationSeed, 52);
    const hold = evaluatePaths(current, sample, { capital, cost: 0, pathUtilities: true });
    const candidate = evaluatePaths(proposed, sample, { capital, cost: plan.total, pathUtilities: true });
    const evidence = pairedDecisionEvidence(candidate.pathUtilities, hold.pathUtilities,
      x.policy, capital, MODEL_VARIANTS.length);
    const failures = decisionRiskFailures(candidate, altered);
    if (validWeights && !validWeights(proposed, altered)) failures.push('Composición');
    if (!executionOK) failures.push('Costes u operativa');
    const { pathUtilities: heldPaths, ...holdMetrics } = hold;
    const { pathUtilities: candidatePaths, ...candidateMetrics } = candidate;
    rows.push({ id: model.id, description: model.description, evidence,
      hold: holdMetrics, candidate: candidateMetrics, failures,
      holdFailures: decisionRiskFailures(hold, altered),
      passes: !failures.length && evidence.meanUtilityGain > 0 && evidence.lowerGain >= hurdle });
  }
  return { method: 'all-declared-models-paired-transition', status: rows.every(r => r.passes) ? 'passed' : 'rejected',
    seed: verificationSeed, paths, models: rows, hurdle,
    minimumGain: Math.min(...rows.map(r => r.evidence.gain)),
    minimumLowerGain: Math.min(...rows.map(r => r.evidence.lowerGain)),
    failingModels: rows.filter(r => !r.passes).map(r => r.id),
    currentViolatesRisk: rows.some(r => r.holdFailures.length) ||
      !!(validWeights && !validWeights(current, { ...x, buyAllowed: x.assets.map(() => true) })),
    scope: 'Five declared sensitivity models, paired fresh scenarios and approximate Monte Carlo bounds; not all parameter uncertainty or predictive validation' };
}
