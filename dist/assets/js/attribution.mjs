/**
 * Additive terminal-return and left-tail loss attribution for USD, buy-and-hold
 * cases without cashflows. Not a causal factor attribution, portfolio CVaR
 * gradient, or an out-of-sample proof. Same held-out verification scenarios.
 */
import { distributionAccounting,distributionTerminalValue } from "./distribution-ledger.mjs?v=0.19.0";
export function portfolioAttribution(assets, weights, sample, cost=0, capital=100000) {
  if (!Array.isArray(assets) || weights.length !== assets.length ||
      sample.assets.length !== assets.length || !(capital > cost) || cost < 0)
    throw new Error("Atribución incompatible con cartera o capital");
  const policy=sample.policy;
  if ((policy.referenceCurrency && policy.referenceCurrency!=="USD") ||
      (policy.withdrawals||[]).length ||
      (policy.monthlyWithdrawal||0)>0 ||
      Math.abs(policy.fxSpot-1)>1e-10 ||
      Math.abs(policy.fxAnnualChange)>1e-10 ||
      Math.abs(policy.fxVolatility)>1e-10)
    return {available:false,reason:"Requiere cartera USD sin retiros y sin conversión FX"};
  const rows=[],terminal=[];
  const afterCosts=1-cost/capital,
    distributions=distributionAccounting(sample);
  for(let p=0;p<sample.paths;p++){
    const components=weights.map((w,i)=>{
      return w*afterCosts*(distributionTerminalValue(distributions[i],sample,i,p)-1);
    });
    rows.push(components);
    terminal.push(components.reduce((a,b)=>a+b,0)-cost/capital);
  }
  const n=sample.paths;
  const worst=[...Array(n).keys()].sort((a,b)=>terminal[a]-terminal[b])
    .slice(0,Math.max(1,Math.ceil(n*.05)));
  const meanIndices=(ids,i)=>ids.reduce((s,p)=>s+rows[p][i],0)/ids.length;
  const all=[...Array(n).keys()];
  const result=assets.map((a,i)=>({
    symbol:a.symbol,weight:weights[i],
    expectedReturnContribution:meanIndices(all,i),
    leftTailLossContribution:-meanIndices(worst,i),
  }));
  const costLoss=cost/capital;
  const expected=result.reduce((s,v)=>s+v.expectedReturnContribution,0)-costLoss;
  const rawEs=result.reduce((s,v)=>s+v.leftTailLossContribution,0)+costLoss;
  const actualMean=terminal.reduce((a,b)=>a+b,0)/n;
  const actualTailLoss=-worst.reduce((a,p)=>a+terminal[p],0)/worst.length;
  if (Math.abs(expected-actualMean)>1e-8 || Math.abs(rawEs-actualTailLoss)>1e-8)
    throw new Error("El retorno y el ES deben reconciliar con sus aportes");
  return {
    available:true,
    contributions:result.filter(x=>x.weight>1e-8),
    costLoss,
    meanReturn:actualMean,
    rawTailLoss:actualTailLoss,
    cvar95:Math.max(0,actualTailLoss),
    scenarios:n,
    note:"La atribución de pérdidas extremas está condicionada a los peores escenarios de la cartera completa. Aportes negativos representan cobertura, no ausencia de riesgo. Costos asignados por separado.",
  };
}
