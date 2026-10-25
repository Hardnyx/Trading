/**
 * Applies point-in-time validated one-day GJR-GARCH-t variance to the
 * historical TOTAL covariance. Residual-sector correlations are diagnostic,
 * never substituted for full market risk in Monte Carlo.
 */
export function conditionalRisk(assets, baseCov, options = {}) {
  const empty = (reason) => ({
    covariance: baseCov, fits: Array(assets.length).fill(null),
    active: 0, fallback: assets.length, enabled: false,
    // Uncalibrated legacy Merton remains the explicit comparator; with
    // accepted GJR, fallback instruments always receive DAILY EWMA updates.
    // Hybrid never silently switches to uncalibrated Merton jumps when GJR
    // is unavailable. Legacy Merton is an explicit research-only selection.
    dynamic: options.volatilityMode !== "legacy", mode: "ewma", reason, studentNu: null,
    innovationLaw: "gaussian-factor-residual",
    multipliers: Array(assets.length).fill(1),
  });
  if (options.volatilityMode === "ewma") return empty("EWMA seleccionado");
  if (options.volatilityMode === "legacy")
    return empty("Comparador Merton antiguo solicitado explícitamente; saltos sin calibración informativa");
  const source = options.volatilityData;
  const asOf = options.asOf;
  if (!source || source.schema_version !== 1 ||
      source.as_of !== asOf || !source.no_news_attribution ||
      !source.instruments || typeof source.instruments !== "object")
    return empty("Sin calibración GJR compatible con el corte: se conserva EWMA");
  const fits = assets.map((asset, i) => {
    const f = source.instruments[asset.symbol], ewma = baseCov[i][i];
    if (!f || f.status !== "accepted" || f.fitted_through !== asOf ||
        f.last_price_date !== asOf || !(ewma > 0) ||
        ![f.omega, f.alpha, f.gamma, f.beta, f.nu, f.variance_next_pct2]
          .every(Number.isFinite) ||
        f.omega <= 0 || f.alpha < 0 || f.gamma < 0 || f.beta < 0 ||
        f.nu <= 2 || f.nu > 62 ||
        f.alpha + f.beta + f.gamma / 2 >= 0.995 ||
        f.variance_next_pct2 <= 0) return null;
    // Caps limit estimation error without silently assuming extreme precision.
    const targetDaily = f.variance_next_pct2 / 10000,
      baselineDaily = ewma / 252;
    const multiplier = Math.max(.5, Math.min(2, Math.sqrt(targetDaily / baselineDaily)));
    return {
      omega: f.omega,
      alpha: f.alpha,
      gamma: f.gamma,
      beta: f.beta,
      nu: f.nu,
      hInitial: baselineDaily * multiplier * multiplier,
      estimatedDaily: targetDaily,
      multiplier,
      symbol: asset.symbol,
    };
  });
  const active = fits.filter(Boolean).length;
  if (!active) return empty("Ningún activo superó el umbral de validación walk-forward");
  const ratio = fits.map((f) => f?.multiplier ?? 1);
  const covariance = baseCov.map((row, i) =>
    row.map((value, j) => value * ratio[i] * ratio[j]));
  return {
    covariance,
    fits,
    active,
    fallback: assets.length-active,
    enabled: true,
    dynamic: true,
    mode: "hybrid",
    multipliers: ratio,
    studentNu: null,
    fittedStudentNu: fits.filter(Boolean).map(f=>f.nu),
    innovationLaw: "gaussian-factor-residual",
    reason: "GJR-t estimado en retornos totales; EWMA diario para los demás. Innovaciones conjuntas gaussianas hasta validar colas y residuos por separado.",
    evaluatedAsOf: asOf,
  };
}

/** Draw Gamma(k, theta=1) using Marsaglia–Tsang. */
export function gammaUnit(k, random, normal) {
  if (!(k > 0)) throw new Error("Parámetro gamma inválido");
  if (k < 1) return gammaUnit(k+1, random, normal) * random() ** (1 / k);
  const d = k-1/3, c = 1/Math.sqrt(9*d);
  for (let tries=0;tries<10000;tries++) {
    const z=normal(), v0=1+c*z;
    if (v0 <= 0) continue;
    const v=v0**3, u=random();
    if (u < 1-.0331*z**4 ||
        Math.log(Math.max(1e-15,u)) < .5*z*z+d*(1-v+Math.log(v)))
      return d*v;
  }
  throw new Error("No se pudo generar variable gamma");
}

/** Standardized common Student-t radial shock: E[scale^2]=1. */
export function studentScale(nu, random, normal) {
  if (!(nu > 2)) return 1;
  const chi2=2*gammaUnit(nu/2, random, normal);
  return Math.sqrt((nu-2)/chi2);
}

export function updateGjrVariance(fit, varianceDaily, logInnovation) {
  // Innovations and h are in daily DECIMAL units; omega is %^2.
  const epsPct=100*logInnovation;
  const next=(fit.omega+
    (fit.alpha+(epsPct<0?fit.gamma:0))*epsPct**2+
    fit.beta*varianceDaily*10000)/10000;
  if (!Number.isFinite(next) || next < 0)
    throw new Error("Varianza GJR fuera de rango");
  // A per-step guard limits numerical explosions in extreme Monte Carlo tails.
  return Math.max(1e-12, Math.min(.25, next));
}

/** Daily EWMA recursion, applied to EVERY unaccepted GJR instrument. */
export function updateEwmaVariance(varianceDaily, innovation, lambda=0.94) {
  if (!Number.isFinite(varianceDaily) || varianceDaily<0 ||
      !Number.isFinite(innovation) || !(lambda>0&&lambda<1))
    throw new Error("Actualización EWMA inválida");
  const next=lambda*varianceDaily+(1-lambda)*innovation*innovation;
  return Math.max(0,Math.min(.25,next));
}
