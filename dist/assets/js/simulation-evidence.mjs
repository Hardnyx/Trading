/** Sampling uncertainty of independent simulated paths, NOT predictive validity. */
export function cvarStandardError(sortedReturns, alpha = .05) {
  const n = sortedReturns.length, count = Math.max(1, Math.ceil(n * alpha)),
    q = -sortedReturns[count - 1], tail = count / n;
  let total = 0, squares = 0;
  for (const r of sortedReturns) {
    const value = Math.max(0, -r - q) / tail;
    total += value; squares += value * value;
  }
  return Math.sqrt(Math.max(0, squares - total * total / n) / Math.max(1, n - 1) / n);
}

/** Bernoulli KL upper bound, inverted Chernoff; zero events is not zero risk. */
export function probabilityUpperBound(p, n, alpha = .05) {
  if (!(p >= 0 && p <= 1 && n > 0 && alpha > 0 && alpha < 1)) return 1;
  if (p === 1) return 1;
  if (p === 0) return -Math.expm1(Math.log(alpha) / n);
  const threshold = Math.log(1 / alpha) / n;
  let lo = p, hi = 1;
  for (let i = 0; i < 60; i++) {
    const u = (lo + hi) / 2,
      kl = p * Math.log(p / u) + (1 - p) * Math.log((1 - p) / (1 - u));
    if (kl > threshold) hi = u; else lo = u;
  }
  return hi;
}

export function riskSamplingEvidence(metrics, rules, policy, familySize = 30) {
  // Split nominal error budget: .025 for economic gains, .025 for risk.
  const alpha = .025 / familySize, z = Math.sqrt(2 * Math.log(1 / alpha));
  const rows = [
    { id: 'CVaR', value: metrics.cvar95, limit: rules.cvarBudget,
      upper: Math.min(1, metrics.cvar95 + z * metrics.cvar95SE), method: 'asymptotic-tail-influence' },
    ...[
      ['Pérdida', 'lossProbability', rules.maxLossProbability],
      ['Drawdown', 'drawdownProbability', policy.maxDrawdownProbability],
      ['Liquidez', 'liquidityFailureProbability', policy.maxLiquidityFailure],
      ...(policy.capitalFloor ? [['Suelo', 'capitalFloorBreachProbability', policy.maxLiquidityFailure]] : []),
    ].map(([id, key, limit]) => {
      const known=metrics.deterministicCashPortfolio===true||
        (key==='liquidityFailureProbability'&&policy.monthlyWithdrawal===0&&Array.isArray(policy.withdrawals)&&!policy.withdrawals.length);
      return { id, value: metrics[key], limit,
        upper:known?metrics[key]:probabilityUpperBound(metrics[key], metrics.paths, alpha),
        method:known?'analytic-model-structure':'binomial-KL-upper' };
    }),
  ];
  return { alpha, familySize, z, rows,
    failures: rows.filter(r => !Number.isFinite(r.upper) || r.upper > r.limit + 1e-12).map(r => r.id),
    scope: 'Monte Carlo uncertainty only; CVaR interval is approximate, predictive calibration is unverified' };
}
