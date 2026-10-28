import { alignReturns } from "./analytics.mjs?v=0.30.0";
import { cholesky, ewmaCovariance } from "./risk-math.mjs?v=0.30.0";

/**
 * One observed SPY factor, projected from a SINGLE joint EWMA covariance.
 * Its Schur complement is PSD: no variance is removed or counted twice.
 * Sector/bull-bear residual correlations remain separate diagnostics, not
 * silently substituted for a joint generative covariance model.
 */
export function marketFactorCovariance(assets, references, asOf, lambda=0.94, lookback=500) {
  const fallback = (reason) => ({available:false,reason});
  const spy = assets.find(a=>a.symbol==="SPY") ||
    references.find(a=>a.symbol==="SPY");
  if (!spy || assets.length<1)
    return fallback("SPY no disponible para factorizar riesgo sistémico");
  const included = assets.some(a=>a.symbol==="SPY");
  const input = [...assets, ...(included?[]:[spy])].map(a=>({
    ...a,history:(a.history||[]).filter(r=>r.date<=asOf),
  }));
  const aligned=alignReturns(input,lookback);
  if (aligned.dates.length<126 || aligned.dates.at(-1)!==asOf)
    return fallback("Insuficientes observaciones conjuntas al corte");
  const annual=ewmaCovariance(aligned.columns.map(c=>c.map(Math.log1p)),lambda);
  const n=assets.length, m=included?assets.findIndex(a=>a.symbol==="SPY"):n,
    v=annual[m][m];
  if (!(v>1e-8))return fallback("Varianza de SPY insuficiente");
  const loading=Array.from({length:n},(_,i)=>annual[i][m]/Math.sqrt(v));
  const covariance=annual.slice(0,n).map(row=>row.slice(0,n));
  const residualCovariance=covariance.map((row,i)=>row.map((value,j)=>{
    const adjusted=value-loading[i]*loading[j];
    return i===j?Math.max(0,adjusted):adjusted;
  }));
  // A zero SPY residual is expected; numerical failures must not be hidden.
  try { cholesky(residualCovariance); }
  catch {return fallback("El complemento de Schur no es PSD");}
  const reconstructed=covariance.map((row,i)=>row.map((value,j)=>
    residualCovariance[i][j]+loading[i]*loading[j]));
  const tolerance=1e-9;
  if (covariance.some((row,i)=>row.some((value,j)=>
      Math.abs(value-reconstructed[i][j])>tolerance)))
    return fallback("Error en la reconstrucción de covarianza");
  return {
    available:true,method:"joint-EWMA-SPY-Schur",
    covariance,loading,residualCovariance,observations:aligned.dates.length,
    asOf,inputEnd:aligned.dates.at(-1),
    note:"Un factor de SPY más covarianza residual PSD, estimados conjuntamente. Los sectores siguen en el residual; no se simulan shocks sectoriales propios todavía.",
  };
}

export function conditionalFactorization(model, multipliers) {
  if (!model?.available)return null;
  const n=model.loading.length,
    ratio=multipliers||Array(n).fill(1);
  if (ratio.length!==n || ratio.some(v=>!Number.isFinite(v)||v<=0))
    throw new Error("Escaladores de factores inválidos");
  const loading=model.loading.map((v,i)=>v*ratio[i]);
  const residualCovariance=model.residualCovariance.map((row,i)=>
    row.map((v,j)=>v*ratio[i]*ratio[j]));
  return {loading,residualFactor:cholesky(residualCovariance),
    residualCovariance,method:model.method,observations:model.observations};
}

/**
 * Rebuild an exact market-factor decomposition from a stressed TOTAL covariance.
 * A stale Cholesky factor would otherwise silently undo correlation shocks
 * during dynamic GJR/EWMA simulations.
 */
export function factorizeStressedCovariance(covariance, assets) {
  const n = assets.length;
  if (covariance.length !== n || covariance.some(row => row.length !== n))
    throw new Error("Covarianza estresada con dimensiones incompatibles");
  const m = assets.findIndex(asset => asset.symbol === "SPY");
  if (m < 0 || covariance[m][m] <= 1e-12) return null;
  const v = Math.sqrt(covariance[m][m]);
  const loading = assets.map((_, i) => covariance[i][m] / v);
  const residualCovariance = covariance.map((row, i) =>
    row.map((value, j) => value - loading[i] * loading[j]));
  const residualFactor = cholesky(residualCovariance);
  return { loading, residualCovariance, residualFactor,
    method: "stress-total-covariance-SPY-Schur" };
}
