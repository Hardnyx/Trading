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
    // Never trust 'accepted' from an older, weaker research screen:
    // the published evidence must satisfy the current confidence gate.
    const validation = f?.verification;
    const lower = validation?.weekly_block_confidence?.lower_95_one_sided;
    if (!f || f.status !== "accepted" ||
        !(validation?.observations >= 126) ||
        !(validation?.qlike_improvement > 0.015) ||
        !(lower > 0) ||
        f.fitted_through !== asOf ||
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
    innovationLaw: options.innovationLaw === 'student-t-research'
      ? 'student-t-marginals-gaussian-copula-research' : 'conditional-gaussian',
    estimationLaw: 'student-t',
    reason: "GJR estimado con verosimilitud t sobre retornos totales; innovaciones gaussianas en precios para preservar la media condicional. Student-t en precios queda como estrés de colas, sin interpretación de media económica. EWMA diario para los demás.",
    evaluatedAsOf: asOf,
  };
}

// Lanczos approximation (g=7, n=9); relative error below 1e-13 for x > 0.
const LANCZOS = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
  771.32342877765313, -176.61502916214059, 12.507343278686905,
  -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
function logGamma(x) {
  if (x < .5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
  x -= 1;
  let a = LANCZOS[0];
  const t = x + 7.5;
  for (let i = 1; i < 9; i++) a += LANCZOS[i] / (x + i);
  return .5 * Math.log(2 * Math.PI) + (x + .5) * Math.log(t) - t + Math.log(a);
}
// Modified Lentz continued fraction for the regularized incomplete beta.
function betaFraction(a, b, x) {
  const tiny = 1e-300;
  let c = 1, d = 1 - (a + b) * x / (a + 1);
  d = 1 / (Math.abs(d) < tiny ? tiny : d);
  let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m;
    let aa = m * (b - m) * x / ((a + m2 - 1) * (a + m2));
    d = 1 + aa * d; d = 1 / (Math.abs(d) < tiny ? tiny : d);
    c = 1 + aa / c; c = Math.abs(c) < tiny ? tiny : c;
    h *= d * c;
    aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1));
    d = 1 + aa * d; d = 1 / (Math.abs(d) < tiny ? tiny : d);
    c = 1 + aa / c; c = Math.abs(c) < tiny ? tiny : c;
    const step = d * c;
    h *= step;
    if (Math.abs(step - 1) < 1e-15) break;
  }
  return h;
}
function incompleteBeta(a, b, x) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const front = Math.exp(logGamma(a + b) - logGamma(a) - logGamma(b) +
    a * Math.log(x) + b * Math.log1p(-x));
  return x < (a + 1) / (a + b + 2)
    ? front * betaFraction(a, b, x) / a
    : 1 - front * betaFraction(b, a, 1 - x) / b;
}
/** P(T > x) for Student-t with nu degrees of freedom and x >= 0. */
export function studentUpperTail(x, nu) {
  return .5 * incompleteBeta(nu / 2, .5, nu / (nu + x * x));
}
/** Standard normal upper tail with relative error below 1.2e-7 (Chebyshev erfc). */
export function normalUpperTail(z) {
  const a = Math.abs(z) / Math.SQRT2, t = 1 / (1 + .5 * a);
  const erfc = t * Math.exp(-a * a - 1.26551223 + t * (1.00002368 + t * (.37409196 +
    t * (.09678418 + t * (-.18628806 + t * (.27886807 + t * (-1.13520398 +
    t * (1.48851587 + t * (-.82215223 + t * .17087277)))))))));
  return z >= 0 ? erfc / 2 : 1 - erfc / 2;
}

const STUDENT_GRID = 0.005, STUDENT_LIMIT = 8.5;
const studentTables = new Map();
/**
 * Monotone map from a standard normal draw to a UNIT-VARIANCE Student-t
 * draw with the same quantile. Applied per instrument it changes marginal
 * tails only: the dependence remains a Gaussian copula, with no tail
 * dependence beyond what correlation implies.
 */
export function studentMarginal(nu) {
  if (!(nu > 2 && nu < 1e6)) throw new Error("Grados de libertad Student-t inválidos");
  const key = nu.toFixed(6);
  if (!studentTables.has(key)) {
    const size = Math.round(STUDENT_LIMIT / STUDENT_GRID) + 1,
      table = new Float64Array(size),
      scale = Math.sqrt((nu - 2) / nu);
    let lower = 0;
    for (let k = 1; k < size; k++) {
      const target = normalUpperTail(k * STUDENT_GRID);
      let low = lower, high = Math.max(1, 2 * lower);
      while (studentUpperTail(high, nu) > target) high *= 2;
      for (let iteration = 0; iteration < 80 && high - low > 1e-12 * high; iteration++) {
        const middle = (low + high) / 2;
        if (studentUpperTail(middle, nu) > target) low = middle; else high = middle;
      }
      lower = (low + high) / 2;
      table[k] = lower * scale;
    }
    studentTables.set(key, table);
  }
  const table = studentTables.get(key), last = table.length - 1;
  return (z) => {
    const position = Math.min(last, Math.abs(z) / STUDENT_GRID),
      k = Math.min(last - 1, Math.floor(position)),
      value = table[k] + (table[k + 1] - table[k]) * (position - k);
    return z < 0 ? -value : value;
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

// Daily persistence of the horizon variance for instruments without an
// accepted GJR fit. Fixed a priori at the usual practitioner GARCH value;
// out-of-sample QLIKE at 21, 63 and 252 sessions favours mean reversion over
// the flat EWMA for 0.97, 0.99 and 0.995 alike (docs/estado-validacion.md).
export const HORIZON_PERSISTENCE = 0.99;
/**
 * EWMA reaction (alpha = 1 - lambda) with mean reversion toward the
 * long-run variance: a variance-targeted GARCH(1,1). The plain EWMA is a
 * martingale and carries last month's variance through a 12-month horizon.
 */
export function updateTargetedVariance(varianceDaily, innovation, longRunDaily,
                                       lambda=0.94, persistence=HORIZON_PERSISTENCE) {
  const alpha=1-lambda, beta=persistence-alpha;
  if (!Number.isFinite(varianceDaily) || varianceDaily<0 ||
      !Number.isFinite(innovation) || !Number.isFinite(longRunDaily) ||
      longRunDaily<0 || !(lambda>0&&lambda<1) || !(beta>=0&&persistence<1))
    throw new Error("Actualización de varianza con reversión inválida");
  const next=(1-persistence)*longRunDaily+alpha*innovation*innovation+beta*varianceDaily;
  return Math.max(0,Math.min(.25,next));
}

/** Plain daily EWMA recursion (comparator; no mean reversion). */
export function updateEwmaVariance(varianceDaily, innovation, lambda=0.94) {
  if (!Number.isFinite(varianceDaily) || varianceDaily<0 ||
      !Number.isFinite(innovation) || !(lambda>0&&lambda<1))
    throw new Error("Actualización EWMA inválida");
  const next=lambda*varianceDaily+(1-lambda)*innovation*innovation;
  return Math.max(0,Math.min(.25,next));
}
