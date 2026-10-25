"""GJR-GARCH-t experimental: pronósticos congelados y comparación walk-forward.

No reemplaza EWMA en la aplicación ni afecta recomendaciones de compra.
Requiere numpy/scipy (requirements-research.txt); nunca atribuye causalidad
a una noticia observada después de emitida la predicción.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math

import numpy as np
from scipy.optimize import minimize
from scipy.stats import t as student_t


MIN_FIT = 252
PERSISTENCE_LIMIT = 0.995


@dataclass(frozen=True)
class VolatilityFit:
    name: str
    omega: float
    alpha: float
    gamma: float
    beta: float
    nu: float
    mean_pct: float
    training_end: str
    train_size: int
    aic: float
    log_likelihood: float
    next_variance_pct2: float
    success: bool

    @property
    def persistence(self) -> float:
        return self.alpha + self.beta + self.gamma / 2


def _unpack(theta: np.ndarray, sample_var: float, asymmetric: bool):
    """Softmax parameterization: omega positive, finite unconditional variance."""
    logits = theta[1:4] if asymmetric else np.array([theta[1], theta[2]])
    scale = max(0., float(np.max(logits)))
    weights = np.exp(logits - scale)
    denom = math.exp(-scale) + float(np.sum(weights))
    parts = (PERSISTENCE_LIMIT * weights / denom).tolist()
    if asymmetric:
        alpha, half_gamma, beta = parts
    else:
        alpha, beta = parts
        half_gamma = 0.
    gamma = 2 * half_gamma
    persistence = alpha + beta + half_gamma
    omega = max(1e-12, (1 - persistence) * sample_var * math.exp(theta[0]))
    nu = 2 + math.exp(theta[-1])
    return omega, alpha, gamma, beta, nu


def _filter(eps: np.ndarray, omega: float, alpha: float, gamma: float,
            beta: float, initial: float) -> tuple[np.ndarray, float]:
    h = max(1e-10, initial)
    fitted = np.empty(len(eps), dtype=float)
    for i, innovation in enumerate(eps):
        fitted[i] = h  # One-step variance, known before innovation i.
        h = omega + (alpha + (gamma if innovation < 0 else 0.)) * innovation**2 + beta*h
        if not math.isfinite(h) or h <= 0:
            raise ValueError("Varianza condicional inválida.")
    return fitted, h  # h is the next-day variance forecast.


def _loglik(eps: np.ndarray, h: np.ndarray, nu: float) -> float:
    # Standardized Student t has E[z^2] = 1 for nu > 2.
    constant = (math.lgamma((nu+1)/2) - math.lgamma(nu/2)
                - .5 * math.log((nu-2) * math.pi))
    return float(np.sum(constant - .5*np.log(h) -
                        (nu+1)/2*np.log1p(eps**2/((nu-2)*h))))


def fit_gjr_t(log_returns: list[float] | np.ndarray,
              training_end: str, asymmetric: bool = True) -> VolatilityFit:
    """Maximum-likelihood fit on DAILY decimal log returns; no future prices."""
    r = np.asarray(log_returns, dtype=float)
    if len(r) < MIN_FIT or not np.all(np.isfinite(r)):
        raise ValueError(f"Se requieren al menos {MIN_FIT} retornos diarios válidos.")
    # Work in percent units for conditioning. Mean is only a nuisance
    # parameter in volatility diagnostics, not the 12-month expected return.
    y = 100*r
    mu = float(np.mean(y))
    eps = y - mu
    v = max(float(np.var(eps)), 1e-7)
    starts = [
        [0., -0.5, -0.7, 2.7, math.log(6.)],
        [0., -1.5, -2.5, 3.5, math.log(12.)],
        [0.1, -0.2, -1.0, 2.0, math.log(4.)],
    ] if asymmetric else [
        [0., -0.6, 2.7, math.log(6.)],
        [0., -1.2, 3.6, math.log(12.)],
    ]
    bounds = [(-1.5, 1.5), (-8., 6.), (-8., 7.),
              (-8., 7.), (math.log(2.), math.log(60.))] if asymmetric else [
                  (-1.5, 1.5), (-8., 6.), (-8., 7.),
                  (math.log(2.), math.log(60.)),
              ]

    def objective(theta):
        try:
            omega, alpha, gamma, beta, nu = _unpack(theta, v, asymmetric)
            fitted, _ = _filter(eps, omega, alpha, gamma, beta, v)
            loss = -_loglik(eps, fitted, nu)
            return loss if math.isfinite(loss) else 1e15
        except (ValueError, OverflowError, FloatingPointError):
            return 1e15

    candidates = [minimize(objective, start, method="L-BFGS-B", bounds=bounds,
                           options={"maxiter": 300, "ftol": 1e-9})
                  for start in starts]
    valid = [row for row in candidates if row.success and np.isfinite(row.fun)]
    if not valid:
        raise RuntimeError("GJR-GARCH-t no convergió: se conserva referencia EWMA.")
    best = min(valid, key=lambda row: row.fun)
    omega, alpha, gamma, beta, nu = _unpack(best.x, v, asymmetric)
    fitted, next_h = _filter(eps, omega, alpha, gamma, beta, v)
    likelihood = _loglik(eps, fitted, nu)
    return VolatilityFit(
        name="gjr-garch-t" if asymmetric else "garch-t",
        omega=omega, alpha=alpha, gamma=gamma, beta=beta,
        nu=nu, mean_pct=mu, training_end=training_end,
        train_size=len(r), aic=2*len(best.x)-2*likelihood,
        log_likelihood=likelihood,
        next_variance_pct2=next_h, success=True,
    )


def updated_variance(fit: VolatilityFit, current_h: float,
                     observed_log_return: float) -> float:
    eps = 100*observed_log_return - fit.mean_pct
    return (fit.omega + fit.alpha*eps**2 +
            (fit.gamma*eps**2 if eps < 0 else 0) + fit.beta*current_h)


def ewma_next(training: np.ndarray, center: float,
              decay: float = 0.94) -> float:
    if not 0 < decay < 1:
        raise ValueError("Decay de EWMA fuera de rango")
    r = np.asarray(training, dtype=float)*100-center
    h = max(float(np.var(r)), 1e-7)
    for e in r:
        h = decay*h + (1-decay)*float(e)**2
    return h


def qlike(h_pct2: float, observed_pct: float, mean_pct: float) -> float:
    if h_pct2 <= 0 or not math.isfinite(h_pct2):
        raise ValueError("Pronóstico de varianza inválido")
    return math.log(h_pct2)+(observed_pct-mean_pct)**2/h_pct2


def prices_to_returns(history: list[dict], as_of: str):
    """Reject duplicate dates and absent adjusted closes. No interpolation."""
    eligible = [r for r in history if r.get("date", "") <= as_of]
    eligible.sort(key=lambda r: r["date"])
    dates = [r["date"] for r in eligible]
    if len(set(dates)) != len(dates):
        raise ValueError("Fechas de precios duplicadas")
    values = [float(r.get("adj_close") or 0) for r in eligible]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Precio ajustado ausente/no válido; no se rellena")
    return dates[1:], np.diff(np.log(np.asarray(values)))


def link_known_events(date: str, events: list[dict], forecast_issued_at: str):
    """No causal claim; an event never deletes a forecast error."""
    related = []
    for e in events:
        known = e.get("known_at_utc")
        published = e.get("published_at_utc")
        if not known or not published or not e.get("source_url"):
            continue
        if published[:10] != date or known < published:
            continue
        # The event is diagnostic only. It was not necessarily known at issuance.
        related.append({
            "event_id": str(e["event_id"]),
            "known_at_utc": known,
            "known_before_forecast": known <= forecast_issued_at,
            "classification": "temporal_coincidence_not_causality",
        })
    return related


def walk_forward(history: list[dict], as_of: str, *,
                 train_window: int = 500, test_days: int = 126,
                 refit_every: int = 63, ewma_decay: float = 0.94,
                 events: list[dict] | None = None) -> dict:
    """Sequentially record one-day variance forecasts BEFORE realized returns."""
    dates, returns = prices_to_returns(history, as_of)
    if train_window < MIN_FIT or test_days < 20 or refit_every < 1:
        raise ValueError("Ventanas de calibración inválidas")
    if len(returns) < train_window+test_days:
        raise ValueError("Historia insuficiente para walk-forward")
    start = len(returns)-test_days
    fit = None
    rows = []
    ewma_h = None
    gh = None
    errors = []
    for i in range(start, len(returns)):
        training = returns[i-train_window:i]
        if i == start or (i-start) % refit_every == 0:
            fit = None
            try:
                fit = fit_gjr_t(training, dates[i-1], True)
                gh = fit.next_variance_pct2
            except (ValueError, RuntimeError) as exc:
                errors.append({"at": dates[i-1], "reason": str(exc)})
            # Each EWMA refit uses exactly the same known training window.
            ewma_h = ewma_next(training, float(np.mean(training)*100), ewma_decay)
        common_mu = float(np.mean(training)*100)
        obs_pct = float(returns[i]*100)
        issued_at = dates[i-1] + "T23:59:59Z"  # end-of-day research cut, not intraday
        row = {
            "for_date": dates[i],
            "issued_after_close": dates[i-1],
            "observation_pct": obs_pct,
            "ewma_variance_pct2": float(ewma_h),
            "ewma_qlike": qlike(ewma_h, obs_pct, common_mu),
            "gjr_variance_pct2": float(gh) if fit else None,
            "gjr_qlike": qlike(gh, obs_pct, fit.mean_pct) if fit else None,
            "gjr_parameters_trained_through": fit.training_end if fit else None,
            "gjr_nu": fit.nu if fit else None,
            "standardized_surprise": (obs_pct-fit.mean_pct)/math.sqrt(gh)
                                    if fit else None,
            "events": link_known_events(dates[i], events or [], issued_at),
            "predictive_error_retained": True,
        }
        if fit:
            q = student_t.ppf(.05, fit.nu)*math.sqrt((fit.nu-2)/fit.nu)
            row["var95_log_return"] = (fit.mean_pct+math.sqrt(gh)*q)/100
            gh = updated_variance(fit, gh, float(returns[i]))
        ewma_h = ewma_decay*ewma_h + (1-ewma_decay)*(obs_pct-common_mu)**2
        rows.append(row)
    pairs = [row for row in rows if row["gjr_qlike"] is not None]
    mean_ewma = float(np.mean([row["ewma_qlike"] for row in pairs])) if pairs else None
    mean_gjr = float(np.mean([row["gjr_qlike"] for row in pairs])) if pairs else None
    exceptions = [row["observation_pct"]/100 < row["var95_log_return"]
                  for row in pairs]
    return {
        "method": "shadow-gjr-garch-student-t-v1",
        "as_of": as_of, "train_window": train_window,
        "refit_every": refit_every, "out_of_sample_days": len(rows),
        "gjr_valid_days": len(pairs), "ewma_qlike": mean_ewma,
        "gjr_qlike": mean_gjr,
        "qlike_improvement": mean_ewma-mean_gjr if pairs else None,
        "gjr_var95_exceptions": sum(exceptions),
        "gjr_var95_exception_rate": (sum(exceptions)/len(exceptions)) if exceptions else None,
        "errors": errors,
        "forecasts": rows,
        "not_promoted": True,
        "warning": "La coincidencia temporal de una noticia no justifica ni elimina errores. La métrica diaria usa residuos cuadrados, proxy ruidoso de varianza latente. No hay validación económica ni causal.",
    }
