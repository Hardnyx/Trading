import { generatePaths, evaluatePaths, utilityCertaintyEquivalent } from './path-model.mjs?v=0.34.0';
import { MODEL_VARIANTS, variantInputs } from './robust-core.mjs?v=0.34.0';
import { tradePlan } from './policy.mjs?v=0.34.0';
import { riskSamplingEvidence } from './simulation-evidence.mjs?v=0.34.0';

// Discovery seeds never reroll the evidence for a fixed transition. These
// experiments are independent inside a run, not unseen future market data.
export const DECISION_EXPERIMENT_SEEDS = Object.freeze({ screen: 0x31b749a5,
  selection: 0x2545f491, confirmation: 0x79bdf135 });

export function tailStressInputs(x) {
  const altered = variantInputs(x, MODEL_VARIANTS.find(v => v.id === 'low_conviction'));
  return {...altered,options:{...altered.options,innovationLaw:'student-t-research',researchShadowMode:true}};
}

export const DECISION_MODEL_LABELS = { original: 'Base', no_rerating: 'Sin re-rating',
  margin_stress: 'Margen y crédito', combined: 'Combinado', low_conviction: 'Baja convicción',
  tail_student: 'Colas Student · solo riesgo' };

/** Paired utility evidence for the actual mandate, including flows and FX. */
export function pairedDecisionEvidence(candidate, incumbent, policy, capital, familySize = 5, alpha = .025) {
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
  const z = Math.sqrt(2 * Math.log(familySize / alpha));
  const equivalent = score => utilityCertaintyEquivalent(score, policy, capital);
  return { meanUtilityGain: mean, standardError: se, z, familySize, alpha, paths: n,
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
  if(x.options.innovationLaw==='student-t-research')throw Error('El estrés Student no puede autorizar una decisión económica');
  if(!Number.isFinite(x.riskFree))return {method:'all-declared-models-paired-transition',status:'incomplete',
    models:[],unanchoredIncumbents:[],missingEconomicInputs:['tasa corta DGS3MO al corte'],
    minimumGain:null,minimumLowerGain:null,hurdle:null,failingModels:[],currentViolatesRisk:false,
    scope:'Missing economic input; do not invent a risk-free rate or silently invalidate a model'};
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
  const verificationSeed = seed ?? DECISION_EXPERIMENT_SEEDS.confirmation;
  const rows = [];
  for (const model of MODEL_VARIANTS) {
    const altered = variantInputs(x, model);
    const sample = generatePaths(altered, paths, verificationSeed, 52);
    const hold = evaluatePaths(current, sample, { capital, cost: 0, pathUtilities: true });
    const candidate = evaluatePaths(proposed, sample, { capital, cost: plan.total, pathUtilities: true });
    const evidence = pairedDecisionEvidence(candidate.pathUtilities, hold.pathUtilities,
      x.policy, capital, MODEL_VARIANTS.length);
    const riskEvidence = riskSamplingEvidence(candidate, altered.rules, altered.policy),
      failures = [...riskEvidence.failures];
    if (validWeights && !validWeights(proposed, altered)) failures.push('Composición');
    if (!executionOK) failures.push('Costes u operativa');
    const { pathUtilities: heldPaths, ...holdMetrics } = hold;
    const { pathUtilities: candidatePaths, ...candidateMetrics } = candidate;
    rows.push({ id: model.id, description: model.description, evidence,
      hold: holdMetrics, candidate: candidateMetrics, failures, riskEvidence,
      holdFailures: riskSamplingEvidence(hold, altered.rules, altered.policy).failures,
      passes: !failures.length && evidence.meanUtilityGain > 0 && evidence.lowerGain >= hurdle });
  }
  const tailRequired = x.assets.some((a, i) => a.type!=='cash' && x.covariance[i][i]>0 &&
    (proposed[i] > 0 || current[i] > 0));
  let tailStress = { required: false, passes: true, role: 'risk-only' };
  if (tailRequired) {
    const altered = tailStressInputs(x);
    const sample = generatePaths(altered, paths, verificationSeed, 52),
      candidate = evaluatePaths(proposed, sample, { capital, cost: plan.total, riskOnly: true }),
      hold = evaluatePaths(current, sample, { capital, cost: 0, riskOnly: true }),
      riskEvidence = riskSamplingEvidence(candidate, altered.rules, altered.policy);
    tailStress = { required: true, role: 'risk-only', passes: !riskEvidence.failures.length,
      cvar95: candidate.cvar95, riskEvidence,
      holdFailures: riskSamplingEvidence(hold, altered.rules, altered.policy).failures,
      note: 'Student-t price stress: fitted nu or declared stress nu=4 for fallback assets. No economic mean, utility or return forecasts are reported' };
  }
  return { method: 'all-declared-models-paired-transition', status: rows.every(r => r.passes) && tailStress.passes ? 'passed' : 'rejected',
    seed: verificationSeed, paths, models: rows, hurdle,
    minimumGain: Math.min(...rows.map(r => r.evidence.gain)),
    minimumLowerGain: Math.min(...rows.map(r => r.evidence.lowerGain)),
    failingModels: [...rows.filter(r => !r.passes).map(r => r.id), ...(!tailStress.passes ? ['tail_student'] : [])],
    tailStress, priceInnovations: 'conditional-gaussian',
    currentViolatesRisk: rows.some(r => r.holdFailures.length) || !!tailStress.holdFailures?.length ||
      !!(validWeights && !validWeights(current, { ...x, buyAllowed: x.assets.map(() => true) })),
    scope: 'Five economic models plus risk-only Student stress; fresh confirmation paths, gain and risk sampling margins; not all parameter uncertainty or predictive validation' };
}
