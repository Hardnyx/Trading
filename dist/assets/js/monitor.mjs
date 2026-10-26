import {
  normalizeWeights,
  metrics,
  valuation,
  portfolioAnalysis,
  finite,
} from "./analytics.mjs?v=0.8.3";

import { evaluateThesis } from "./research-model.mjs?v=0.8.3";
import { adjustedReturn, factorModel } from "./factors.mjs?v=0.8.3";

import { informationDate } from "./policy.mjs?v=0.8.3";

export const DEFAULT_RULES = {
  weightDrift: 0.05,
  valuationPremium: 0.2,
  earningsDrop: 0.15,
  volatilityIncrease: 0.25,
  drawdown: 0.1,
};

export function registerPortfolio(
  snapshot,
  positions,
  capital,
  overrides = {},
  now = new Date().toISOString(),
) {
  const weights = normalizeWeights(positions),
    lookup = new Map(snapshot.assets.map((a) => [a.symbol, a]));
  if (
    !weights.length ||
    !finite(capital) ||
    capital <= 0 ||
    weights.some((p) => !lookup.has(p.symbol))
  )
    throw new Error("La composición necesita posiciones y capital válidos.");
  const analysis = portfolioAnalysis(
    snapshot.assets,
    weights,
    252,
    (snapshot.macro.find((s) => s.id === "DGS3MO")?.value ?? 4) / 100,
  );
  return {
    version: 1,
    id: now,
    registered_at: now,
    as_of: snapshot.price_as_of,
    capital,
    overrides: structuredClone(overrides),
    positions: weights.map((p) => {
      const a = lookup.get(p.symbol),
        m = metrics(a),
        v = valuation(a, overrides[a.symbol] || {});
      return {
        ...p,
        price: a.price,
        adj_close: a.history.at(-1).adj_close,
        eps: m.eps,
        fcf: m.fcf,
        financial_period: m.period,
        financial_filed: m.filed,
        fair_value: v?.fairValue ?? null,
      };
    }),
    initial_risk: analysis?.stats ?? null,
    factor_exposures: factorModel(
      snapshot.assets,
      weights,
      snapshot.price_as_of,
    ),
    macro: snapshot.macro.map((s) => ({
      id: s.id,
      value: s.value,
      date: s.date,
    })),
    known_filings: snapshot.assets
      .flatMap((a) => (a.filings || []).map((f) => f.accession))
      .filter(Boolean),
  };
}

export function reviewPortfolio(
  snapshot,
  baseline,
  rules = DEFAULT_RULES,
  research = baseline?.research || {},
) {
  if (!baseline) return null;
  rules = { ...DEFAULT_RULES, ...rules };
  const lookup = new Map(snapshot.assets.map((a) => [a.symbol, a]));
  const positions = baseline.positions.map((p) => {
    const a = lookup.get(p.symbol);
    if (!a) return { ...p, missing: true };
    const origin = a.history.find((row) => row.date === baseline.as_of);
    const ratio =
      origin?.adj_close > 0
        ? a.history.at(-1).adj_close / origin.adj_close
        : a.history.at(-1).adj_close / p.adj_close;
    const currentValue = baseline.capital * p.weight * ratio;
    const m = metrics(a),
      v = valuation(a, baseline.overrides?.[p.symbol] || {});
    return {
      ...p,
      asset: a,
      currentValue,
      return: ratio - 1,
      adjustmentQuality: origin
        ? "same_current_series"
        : "legacy_fallback_unreconciled",
      currentModel: v,
      currentMetrics: m,
    };
  });
  const missing = positions.filter((p) => p.missing).map((p) => p.symbol),
    available = positions.filter((p) => !p.missing);
  const currentCapital = available.reduce((s, p) => s + p.currentValue, 0);
  available.forEach((p) => (p.currentWeight = p.currentValue / currentCapital));
  const alerts = [];
  const push = (
    type,
    symbol,
    title,
    reason,
    review,
    priority = "media",
    suffix = "",
  ) =>
    alerts.push({
      id: `${baseline.id}:${type}:${symbol}:${suffix}`,
      type,
      symbol,
      title,
      reason,
      review,
      priority,
      as_of: snapshot.price_as_of,
    });
  for (const p of available) {
    const thesis = evaluateThesis(
      p.asset,
      research[p.symbol] || {},
      snapshot.generated_at ? informationDate(snapshot) : snapshot.price_as_of,
    );
    p.thesis = thesis;
    if (thesis.status === "contradicted")
      push(
        "thesis",
        p.symbol,
        "Una hipótesis de la tesis se contradice",
        thesis.observations
          .filter((r) => r.status === "contradicted")
          .map(
            (r) =>
              `${r.label}: ${r.value.toFixed(3)}; umbral ${r.threshold}. Presentación ${r.filed || "sin fecha"}.`,
          )
          .join(" "),
        "Actualizar previsión y volver a evaluar mantener o cambiar después de costos.",
        "alta",
        thesis.observations.map((r) => r.filed).join(),
      );
    if (thesis.overdue)
      push(
        "thesis_review",
        p.symbol,
        "Fecha de revisión de tesis alcanzada",
        thesis.thesis || "Revisión programada de hipótesis.",
        "Revisar evidencia, invalidación y catalizador.",
        "media",
        thesis.reviewDate,
      );

    const delta = p.currentWeight - p.weight;
    if (Math.abs(delta) >= rules.weightDrift)
      push(
        "weight",
        p.symbol,
        "Desvío del peso registrado",
        `Peso actual ${(p.currentWeight * 100).toFixed(1)}%; registrado ${(p.weight * 100).toFixed(1)}%.`,
        delta > 0
          ? "Revisar reducción o rebalanceo."
          : "Revisar si corresponde recuperar el peso.",
        "media",
        Math.floor(Math.abs(delta) / rules.weightDrift),
      );
    const value = p.currentModel?.fairValue;
    const premium = value > 0 ? p.asset.price / value - 1 : null;
    if (premium >= rules.valuationPremium)
      push(
        "valuation",
        p.symbol,
        "Precio por encima del valor del modelo",
        `Precio ${p.asset.price.toFixed(2)}; valor del modelo ${value.toFixed(2)}. Prima ${(premium * 100).toFixed(1)}%.`,
        "Revisar supuestos y exposición antes de mantener o reducir.",
        "media",
        Math.floor(premium / 0.2),
      );
    if (
      p.eps > 0 &&
      finite(p.currentMetrics.eps) &&
      p.currentMetrics.period !== p.financial_period &&
      p.currentMetrics.eps / p.eps - 1 <= -rules.earningsDrop
    )
      push(
        "earnings",
        p.symbol,
        "Caída del BPA frente a la base registrada",
        `BPA de referencia ${p.eps.toFixed(2)}; último ${p.currentMetrics.eps.toFixed(2)}. Período ${p.currentMetrics.period}.`,
        "Actualizar proyecciones y revisar el múltiplo de salida.",
        "alta",
        p.currentMetrics.period,
      );
    if (p.fcf > 0 && finite(p.currentMetrics.fcf) && p.currentMetrics.fcf < 0)
      push(
        "cashflow",
        p.symbol,
        "El FCF simple pasó a negativo",
        "El flujo de operación menos capex cambió de signo desde el registro.",
        "Revisar inversión, financiamiento y la tesis de generación de caja.",
        "alta",
        p.currentMetrics.period,
      );
    for (const filing of p.asset.filings || []) {
      if ((baseline.known_filings || []).includes(filing.accession)) continue;
      const accepted = filing.accepted_at || filing.filing_date + "T23:59:59Z";
      if (accepted <= baseline.registered_at) continue;
      push(
        "filing",
        p.symbol,
        `Nueva presentación ${filing.form}`,
        `${filing.description || filing.form} · ${filing.filing_date}.`,
        "Leer la presentación. Su publicación no determina por sí sola una compra o venta.",
        "informativa",
        filing.accession,
      );
      alerts.at(-1).url = filing.url;
    }
  }
  const analysis = missing.length
    ? null
    : portfolioAnalysis(
        snapshot.assets,
        available.map((p) => ({ symbol: p.symbol, weight: p.currentWeight })),
        252,
        (snapshot.macro.find((s) => s.id === "DGS3MO")?.value ?? 4) / 100,
      );
  if (
    analysis &&
    baseline.initial_risk?.volatility > 0 &&
    analysis.stats.volatility / baseline.initial_risk.volatility - 1 >=
      rules.volatilityIncrease
  )
    push(
      "risk",
      "CARTERA",
      "Aumento de volatilidad",
      `Volatilidad anual ${(analysis.stats.volatility * 100).toFixed(1)}%; al registro ${(baseline.initial_risk.volatility * 100).toFixed(1)}%.`,
      "Revisar concentración y presupuesto de riesgo.",
      "alta",
    );
  if (
    !missing.length &&
    currentCapital / baseline.capital - 1 <= -rules.drawdown
  )
    push(
      "loss",
      "CARTERA",
      "Pérdida desde la composición",
      `Retorno ajustado desde el registro: ${((currentCapital / baseline.capital - 1) * 100).toFixed(1)}%.`,
      "Revisar tesis y tolerancia a pérdidas; no implica vender automáticamente.",
      "alta",
    );
  const order = { alta: 0, media: 1, informativa: 2 };
  alerts.sort((a, b) => order[a.priority] - order[b.priority]);
  return {
    positions: available,
    missing,
    currentCapital,
    totalReturn: missing.length ? null : currentCapital / baseline.capital - 1,
    analysis,
    alerts,
    baselineAsOf: baseline.as_of,
    currentAsOf: snapshot.price_as_of,
    newCut: snapshot.price_as_of > baseline.as_of,
  };
}
