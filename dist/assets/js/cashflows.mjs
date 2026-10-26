/* Adjusted close embeds reinvested distributions. Never add them a second time.
 * The trailing yield supplies a smooth, ex-price yield assumption, not a pay
 * calendar. If d is the step yield, P_t = G_t / (1+d)^t and D_t = d * P_t.
 * This preserves G_t/G_(t-1) = (P_t + D_t) / P_(t-1) for ANY price path.
 */
export function annualDistributionYield(asset) {
  if (asset.type === "cash" || !(asset.price > 0)) return 0;
  const dividend = asset.dividend_per_share;
  if (!Number.isFinite(dividend) || dividend <= 0 || dividend / asset.price > .25)
    return 0;
  return dividend / asset.price;
}

export function dividendStep(priorTotalGross, totalGross, annualYield, t, dt, withholding = 0) {
  if (!annualYield) return {priceGross: totalGross, grossCash: 0, netCash: 0};
  const factor = Math.pow(1 + annualYield, dt);
  const priceGross = totalGross / Math.pow(factor, t);
  const grossCash = priceGross * (factor - 1);
  return {priceGross, grossCash, netCash: grossCash * (1 - withholding)};
}

// Coefficients depend only on the mandate, not the scenario. Share the same
// accounting between portfolio valuation, liquidity and terminal attribution.
export function distributionFactors(asset, steps, dt, policy) {
  const yieldRate = annualDistributionYield(asset);
  const d = yieldRate ? Math.expm1(Math.log1p(yieldRate) * dt) : 0;
  const tax = policy.dividendWithholding || 0;
  const toCash = policy.dividendPolicy === "cash";
  const marketValue = new Float64Array(steps + 1).fill(1);
  const grossDistribution = new Float64Array(steps + 1);
  const netCash = new Float64Array(steps + 1);
  const netReinvested = new Float64Array(steps + 1);
  const withheld = new Float64Array(steps + 1);
  const multiplier = toCash ? 1 / (1 + d) : (1 + d * (1 - tax)) / (1 + d);
  for (let t = 1; t <= steps; t++) {
    const exPrice = marketValue[t - 1] / (1 + d);
    marketValue[t] = marketValue[t - 1] * multiplier;
    grossDistribution[t] = exPrice * d;
    withheld[t] = grossDistribution[t] * tax;
    const net = grossDistribution[t] - withheld[t];
    if (toCash) netCash[t] = net;
    else netReinvested[t] = net;
  }
  return {marketValue, grossDistribution, netCash, netReinvested, withheld};
}
