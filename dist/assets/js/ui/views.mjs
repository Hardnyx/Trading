import {
  finite,
  sum,
  normalizeWeights,
  metrics,
  scenarios,
  resolveAssumptions,
  returnDecomposition,
  valuation,
} from "../analytics.mjs?v=0.23.0";
import {
  sparkline,
  portfolioChart,
  lineChart,
  heatmap,
  scatter,
  forecastCone,
  histogram,
} from "../charts.mjs?v=0.23.0";
import {
  esc,
  url,
  fmt,
  pct,
  money,
  compact,
  color,
  dateLabel,
  timestampLabel,
} from "./format.mjs?v=0.23.0";
import { template } from "./templates.mjs?v=0.23.0";
import { DEFAULT_COMPOSITION_RULES } from "../composer.mjs?v=0.23.0";
import { factorModel } from "../factors.mjs?v=0.23.0";
import { MODEL_VERSION, informationDate } from "../policy.mjs?v=0.23.0";
import { fundamentalForecast } from "../research-model.mjs?v=0.23.0";
import { financialFreshness } from '../financial-freshness.mjs?v=0.23.0';
import { priceMonitor } from '../price-monitor.mjs?v=0.23.0';

import { createDecisionViews } from "./decision-views.mjs?v=0.23.0";

/**
 * Describes the process the Monte Carlo actually runs. Jumps and the GBM /
 * Merton choice only apply to the explicit legacy comparator; hybrid and EWMA
 * modes simulate daily variance recursions without jumps.
 */
export function simulatedProcess(settings = {}, volatility = null) {
  const mode = settings.volatilityMode || "hybrid";
  if (mode === "legacy") {
    const merton = settings.model !== "gbm";
    return {
      legacy: true, jumps: merton,
      label: merton ? "Merton legado · EWMA + saltos no calibrados" : "GBM legado · covarianza EWMA",
      subtitle: merton
        ? "Comparador legado: difusión con covarianza EWMA y saltos genéricos de parámetros propios, no estimados."
        : "Comparador legado: difusión lognormal con covarianza EWMA constante, sin saltos.",
    };
  }
  const accepted = volatility?.accepted ?? 0;
  const gjr = mode === "hybrid" && accepted > 0;
  return {
    legacy: false, jumps: false,
    label: gjr ? `GJR-t validado (${accepted}) + EWMA con reversión` : "EWMA con reversión",
    subtitle: gjr
      ? `Varianza GJR-t validada en ${accepted} activo${accepted === 1 ? "" : "s"}, con su innovación Student-t, y en los demás EWMA gaussiano que revierte a su varianza de 500 sesiones (persistencia diaria 0,99). Dependencia por cópula gaussiana; sin saltos.`
      : "EWMA diario que revierte a la varianza de 500 sesiones (persistencia 0,99) sobre la covarianza total. Innovaciones conjuntas gaussianas; sin saltos.",
  };
}

/**
 * Price and model positions on the valuation ruler. Labels that would
 * overlap open outward, each toward its own side of the track.
 */
export function rulerMarkers(price, fairValue) {
  const top = Math.max(price, fairValue),
    place = (value) => Math.max(8, Math.min(92, (value / top) * 75)),
    max = place(price), max7 = place(fairValue),
    close = Math.abs(max - max7) < 12;
  return {
    max, max7,
    priceLabelSide: close ? (max <= max7 ? "label-start" : "label-end") : "",
    modelLabelSide: close ? (max <= max7 ? "label-end" : "label-start") : "",
  };
}

/** Summary of the sealed one-session risk ledger (data/risk-forecasts). */
export function riskCalibrationNote(summary) {
  const version = summary?.current_risk_model_version;
  const v = summary?.versions?.[version];
  if (!v) return "Registro diario sellado de riesgo: todavía sin sesiones selladas.";
  const used = v.models?.hybrid_reference || v.models?.production || {};
  const p = (x) => finite(x) ? fmt(x, 2) : "—";
  const paired = v.paired_qlike_ewma_minus_gjr || {};
  return `Registro diario sellado · modelo de riesgo ${version}: ${v.scored_sessions} de ${v.sealed_sessions} sesiones puntuadas, ${used.observations || 0} activo-días. ` +
    (used.observations
      ? `Excepciones VaR95 de la referencia estadística híbrida ${pct(used.var95_exception_rate, 1)} (esperado 5%; Kupiec p=${p(used.kupiec?.p_value)}; agrupamiento Christoffersen p=${p(used.christoffersen?.p_value)}). QLIKE EWMA − GJR ${p(paired.mean)} en ${paired.observations || 0} pares. `
      : "") +
    `Sesiones completas ${v.fully_scored_sessions??v.scored_sessions}, parciales ${v.partial_sessions||0}; resultados pendientes ${v.pending_instruments||0}. EWMA centrada y GJR sin los límites del simulador: este registro no valida el motor exacto ni el CVaR de la cartera. `+
    (v.status === "evaluable"
      ? "Evaluable con cautelas: activos no independientes; no promueve parámetros."
      : `Acumulando: se interpreta desde ${summary.minimum_sessions} sesiones y ${summary.minimum_observations} observaciones.`);
}

export function compositionValuationEvidence(signal) {
  if(!signal.filed)return "";
  const v=signal.valuationEvidence;
  if(!v)return "Supuestos sin guardar en esta propuesta: vuelve a proponer cartera.";
  const a=v.assumptions;
  const base=finite(v.effectiveBaseEPS)?` · BPA de partida ${money(v.effectiveBaseEPS)} (${v.earningsBasis==='continuing'?'operaciones continuadas':'base de valoración'})`:"";
  const sensitivity=v.accountingSensitivity>0?` · sensibilidad a base contable ${pct(v.accountingSensitivity)} / año`:"";
  const growthSource=v.growthEvidence?` (${v.growthEvidence.source}${v.growthEvidence.sourceVintage?' · captura '+timestampLabel(v.growthEvidence.sourceVintage):'; sin vintage predictivo'})`:'';
  return `Supuestos: ${v.source}${base}${sensitivity} · crecimiento ${pct(a.growth)}${growthSource} · ${reratingText(v.rerating,a)} · valoración a ${fmt(a.horizon,0)} años · confianza asignada ${pct(v.confidence)}. Sin calibración predictiva.`;
}
/** Exit multiple: explicit user value or partial reversion to the sector reference. */
export function reratingText(r,a){
  if(r?.applied)return `P/E actual ${fmt(r.current,1)} → salida ${fmt(r.effective,1)} (${pct(r.share,0)} de la brecha al sectorial ${fmt(r.reference,1)}; vida media ${fmt(r.halfLife,0)} años)`;
  return `P/E de salida ${fmt(a.multiple,1)}${r?.explicit?" fijado por ti":""}`;
}
/** One-line split of the model return; the parts sum to the total. */
export function compositionReturnSplit(signal){
  const d=signal.valuationEvidence?.decomposition;
  if(!d)return "";
  return `Modelo ${pct(d.total,1,true)}/año = BPA ${pct(d.growth,1,true)} · múltiplo ${pct(d.rerating,1,true)} · dividendos ${pct(d.dividends,1,true)}`;
}
export function compositionRole(signal, proposal={}) {
  if (signal.symbol === 'CASH') return proposal.mandate?.cashYield > 0
    ? `Liquidez · ${pct(proposal.mandate.cashYield,1)} neto declarado`
    : 'Liquidez sin remuneración';
  const bonds={TLT:'Treasuries largos',IEF:'Treasuries intermedios',IEI:'Treasuries intermedios',
    SHY:'Treasuries cortos',SHV:'Treasuries de vencimiento corto',SGOV:'Letras del Tesoro'};
  if (bonds[signal.symbol]) return bonds[signal.symbol]+(signal.symbol==='TLT'?' · sensibilidad a tasas':'');
  if (finite(signal.holdingsCoverage))
    return `Fondo de acciones · ${pct(signal.holdingsCoverage,0)} del peso con ancla de sus constituyentes`;
  const growth=signal.valuationEvidence?.assumptions?.growth;
  const dividend=signal.valuationEvidence?.decomposition?.dividends;
  return finite(growth) ? (dividend>.001
      ? `BPA ${pct(growth,0)} y dividendo ${pct(dividend,1)} · supuestos`
      : `Acción · crecimiento BPA supuesto ${pct(growth,0)}`)
    : 'Supuesto de retorno explícito';
}
export function compositionCashExplanation(proposal) {
  const weight=proposal.positions?.find(p=>p.symbol==='CASH')?.weight||0;
  const a=proposal.diagnostics?.cashAllocation;
  if (!a) return `Efectivo ${pct(weight,1)}. Falta comprobar su exceso sobre la reserva exigida; volver a proponer.`;
  const label=`Efectivo ${pct(a.cashWeight,1)} · reserva exigida ${pct(a.requiredCash,1)}`;
  const reasons={
    required_reserve:'Se conserva el mínimo exigido por el mandato y los retiros.',
    allocation_step:'El excedente es menor que el tramo de 5 puntos de la búsqueda.',
    structural_limits:'Los topes impiden las reasignaciones locales probadas.',
    risk_or_execution_limits:'Las reasignaciones probadas incumplen límites de riesgo, costes u operativa.',
    no_local_improvement:'Ninguna reasignación local probada mejoró el objetivo cumpliendo los límites.',
    search_budget:'Se agotó la revisión local; este nivel de efectivo requiere más búsqueda.',
  };
  return `${label}. ${reasons[a.status]||'Revisión local pendiente.'}`;
}
export function returnSplitRows(d){
  if(!d)return [];
  return [["BPA",d.growth],["Múltiplo",d.rerating],["Dividendos",d.dividends],["Retorno del modelo",d.total]]
    .map(([label,value])=>({label,value:pct(value,1,true),tone:color(value)}));
}

export function financialCoverageView(data){
 const asOf=data.generated_at?informationDate(data):data.price_as_of;
 const rows=data.assets.filter(a=>a.type==='stock').map(a=>({a,f:financialFreshness(a,asOf)}));
 const gaps=rows.filter(r=>r.f.status==='newer_report').length;
 const missing=rows.filter(r=>['missing','split_basis_unverified'].includes(r.f.status)).length;
 return template('financial-coverage',{
  gaps,missing,total:rows.length,
  rows:rows.sort((x,y)=>Number(y.f.blocked)-Number(x.f.blocked)||x.a.symbol.localeCompare(y.a.symbol))
   .map(({a,f})=>template('financial-coverage-row',{
    symbol:a.symbol,period:dateLabel(f.period),filed:dateLabel(f.filed),method:f.method||'—',
    observed:f.observedAt?timestampLabel(f.observedAt):'No registrada',
    originalObserved:f.originalRecovery?.observed_at?'Informe original: '+timestampLabel(f.originalRecovery.observed_at):'',
    latest:f.latestReport?f.latestReport.form+' · '+dateLabel(f.latestReport.filing_date):'Sin documento registrado',
    status:f.reason+(f.originalEps?' · BPA usa XBRL del informe original':f.originalRecovery?' · Recuperación del informe original sin BPA reconciliado':'')+(f.refreshStatus==='retained_after_failure'?' · Se conservó la captura previa por fallo de actualización':''),
    sourceUrl:url(f.latestReport?.url||a.financials?.source_url||'https://www.sec.gov/edgar/search/')
   })).join('')
 });
}

export function priceMonitorView(data,positions=[],filter='all',open=false){
 const m=priceMonitor(data,positions,filter);
 return template('price-monitor',{
  total:m.total,available:m.available,priceOnly:m.priceOnly,asOf:dateLabel(m.asOf),open:open?'open':'',
  allSelected:filter==='all'?'selected':'',priceSelected:filter==='price_only'?'selected':'',
  heldSelected:filter==='held'?'selected':'',eventsSelected:filter==='events'?'selected':'',
  rows:m.rows.map(r=>template('price-monitor-row',{
   symbol:r.symbol,held:r.held?'En cartera':'',price:money(r.price),date:dateLabel(r.priceDate),
   observed:r.observedAt?'Captura '+timestampLabel(r.observedAt):'Captura no registrada',
   coverage:r.coverage,trend:r.available?r.trend:r.reason,event:r.available?r.event:'Sin evaluación',
   momentum:pct(r.momentum126,1,true),distance:pct(r.distance200,1,true),
   drawdown:pct(r.drawdown252,1),volatility:pct(r.volatility63,1),
   ratio:finite(r.volatilityRatio)?fmt(r.volatilityRatio,2)+'×':'—'
  })).join('')||template('price-monitor-empty')
 });
}

export function robustnessView(report,{busy=false,error=null,progress='',fresh=true}={}){
 if(busy)return template('robustness-running',{progress:progress||'Preparando escenarios'});
 if(error)return template('composition-notice',{message:'Comparación robusta: '+error});
 if(!report)return '';
 if(!fresh)return template('composition-notice',{message:'Comparación robusta desactualizada: cambió la cartera, el corte o algún supuesto. Pulsa Comparar robustez.'});
 const labels={original:'Supuestos de sesión',no_rerating:'Sin expansión de múltiplos',margin_stress:'Estrés de margen operativo',combined:'Margen y múltiplos',low_conviction:'Menor confianza y prima de mercado'};
 const c=report.candidate,good=report.decision==='candidate_survives_assumed_models';
 return template('robustness-report',{
  decision:good?'VENTAJA CONDICIONAL EN LOS CINCO MODELOS':'SIN EVIDENCIA SUFICIENTE PARA REBALANCEAR',
  source:report.account_source,asOf:dateLabel(report.as_of),months:fmt(report.horizon*12,0),
  candidates:report.candidate_count,finalists:report.verified_candidates,
  incumbentNotice:report.current?.structuralFeasible?'La referencia cumple los límites de construcción.':'La referencia excede algún límite de construcción; eso no demuestra por sí solo que rebalancear mejore el resultado.',
  weights:(c?.positions||[]).map(p=>template('robustness-weight',{symbol:p.symbol,weight:pct(p.weight,1)})).join(''),
  scenarios:report.scenarios.map(s=>{
   const m=c?.verification[s.id],base=report.current?.verification[s.id],paired=c?.pairedMonteCarlo[s.id];
   return template('robustness-scenario',{name:labels[s.id]||s.id,
    currentMedian:pct(base?.medianReturn),median:pct(m?.medianReturn),cvar:pct(m?.cvar95),
    probability:pct(m?.lossProbability),gain:money(report.paired_certainty_equivalent_gain_dollars?.[s.id],0),
    lower:money(paired?.lower_ce_gain_dollars,0)});
  }).join(''),
  threshold:money(report.required_gain_dollars,0),cost:money(c?.cost,0),
  transition:robustTransitionView(c?.transition,good),
  missingMargins:report.scenarios.find(s=>s.id==='margin_stress')?.earnings_stresses.filter(r=>!r.available).map(r=>r.symbol).join(', ')||'ninguno',
  copy:c?template('robustness-copy'):''
 });
}

export function robustTransitionView(plan,supported=false){
 if(!plan)return template('composition-notice',{message:'Vuelve a comparar robustez para obtener el detalle de transición y efectivo.'});
 if(!plan.reconciled)return template('composition-notice',{message:'La transición no concilia el efectivo o tiene costos incompletos. Revisa los supuestos antes de simular.'});
 const actions={reserve:'Reserva',hold:'Mantener',exit:'Cerrar',reduce:'Reducir',open:'Abrir',increase:'Aumentar'};
 const signedMoney=v=>(v>1e-7?'+':'')+money(v,2);
 return template('robustness-transition',{
  notice:supported?'Transición de la candidata con ventaja condicional. Revisa precios y condiciones antes de decidir.':
   'Solo comparación hipotética: la evidencia no respalda ejecutar este rebalanceo. Mantener es la referencia.',
  rows:plan.positions.map(r=>template('robustness-transition-row',{
   symbol:r.symbol,action:actions[r.action]||'Revisar',from:pct(r.from,1),to:pct(r.to,1),
   currentValue:money(r.currentValue,2),targetValue:money(r.targetValue,2),change:signedMoney(r.change),
   quantity:r.symbol==='CASH'?'—':fmt(r.quantity,4),price:r.symbol==='CASH'?'—':money(r.price,2),
   cost:money(r.cost,2),note:r.small?'Inferior al mínimo configurado':''
  })).join(''),
  initialCash:money(plan.initialCash,2),sells:money(plan.sells,2),buys:money(plan.buys,2),
  total:money(plan.total,2),endingCash:money(plan.endingCash,2),turnover:pct(plan.turnover,1),
  commission:money(plan.costBreakdown.commission,2),spread:money(plan.costBreakdown.spread,2),
  slippage:money(plan.costBreakdown.slippage,2),tax:money(plan.costBreakdown.tax,2),
  taxRate:pct(plan.assumptions.capitalGainsTax,1)
 });
}

export const NAV = [
  ["portfolio", "Componer cartera", "F1"],
  ["overview", "Seguimiento", "F2"],
  ["forecasts", "Proyecciones", "F3"],
  ["research", "Research", "F4"],
  ["valuation", "Valoración", "F5"],
  ["risk", "Riesgo", "F6"],
  ["macro", "Macro monitor", "F7"],
  ["mandate", "Mandato", "F8"],
];
const icon = (key) => {
  const symbols = {
    arrow: "»",
    download: "↓",
    upload: "↑",
    close: "×",
    refresh: "↻",
    data: "DATOS",
    help: "AYUDA",
    search: "/",
  };
  return symbols[key] ? template("icon", { symbol: symbols[key] }) : "";
};

export function createViews(context) {
  const {
    state,
    data,
    asset,
    override,
    model,
    analyze,
    assetStats,
    monitoring,
    filteredAssets,
  } = context;
  const positionCapital = () =>
    state.proposal?.status === "proposed" && !state.proposal.modified
      ? (state.proposal.trade_plan?.investableCapital ?? state.capital)
      : state.capital;
  const referenceMoney = (value) =>
    (state.mandate?.referenceCurrency || "USD") === "USD"
      ? money(value, 0)
      : finite(value)
        ? fmt(value, 0) + " " + state.mandate.referenceCurrency
        : "—";
  function panel(title, index, body, controls = "", foot = "") {
    return template("panel", {
      index: index,
      title: title,
      controls: controls,
      body: body,
      value5: foot ? template("panel-footnote", { foot: foot }) : "",
    });
  }

  function metric(label, value, sub = "", className = "", unit = "") {
    return template("metric", {
      label: label,
      forecastsIcon: icon("forecasts"),
      className: className,
      value: value,
      value5: unit ? template("metric-unit", { unit: unit }) : "",
      sub: sub,
    });
  }

  function title(eyebrow, heading, subtitle, actions = "") {
    return template("title", {
      eyebrow: eyebrow,
      heading: heading,
      subtitle: subtitle,
      actions: actions,
    });
  }

  function simulationMetrics() {
    const f = state.forecast;
    return template("simulation-metrics", {
      metric: metric(
        "RETORNO MEDIANO · MODELO",
        f ? pct(f.medianReturn) : "—",
        `Horizonte ${state.settings.horizon * 12} meses · percentil 50`,
        f ? color(f.medianReturn) : "",
      ),
      metric2: metric(
        "PROBABILIDAD DE PÉRDIDA",
        f ? pct(f.lossProbability) : "—",
        "Condicional a los supuestos del modelo",
        f && f.lossProbability > 0.5 ? "negative" : "",
      ),
      metric3: metric(
        "VAR 95% · HORIZONTE",
        f ? pct(f.var95) : "—",
        f
          ? `${referenceMoney(f.var95 * state.capital * (f.policy?.fxSpot || 1))} sobre capital inicial`
          : "Monte Carlo correlacionado",
        "negative",
      ),
      metric4: metric(
        "CVAR 95% · HORIZONTE",
        f ? pct(f.cvar95) : "—",
        "Pérdida media en el peor 5%",
        "negative",
      ),
    });
  }

  function allocation(a) {
    const w = a?.weights || [];
    return template("allocation-table", {
      items: w
        .map((p) =>
          template("allocation-row", {
            symbol: p.symbol,
            symbol2: p.symbol,
            weight: pct(p.weight, 1),
            value4: p.weight * 100,
          }),
        )
        .join(""),
      capital: money(positionCapital(), 0),
      effectivePositions: fmt(a?.effectivePositions, 1),
    });
  }

  function forecastPanel(full = false) {
    const f = state.forecast,
      historical = state.chartMode === "history" && !full,
      analysis = historical ? analyze() : null;
    const legend = historical
      ? template("forecast-panel-11")
      : template("forecast-panel-10");
    const resultCards = historical
      ? template("forecast-panel-8", {
          items: [
            ["VOLATILIDAD ANUAL", analysis?.stats.volatility, ""],
            ["DRAWDOWN MÁXIMO", analysis?.stats.maxDrawdown, "negative"],
            ["RETORNO SPY", analysis?.benchmarkStats.total, ""],
          ]
            .map(([l, v, c]) =>
              template("forecast-panel-9", {
                l: l,
                c: c,
                v: pct(v),
                value4: analysis?.stats.n || 0,
              }),
            )
            .join(""),
        })
      : f
        ? template("forecast-panel-6", {
            items: [
              ["P05 · ADVERSO", f.p05, "negative", f.p05TerminalWealth],
              [
                "P50 · MEDIANA",
                f.medianReturn,
                "orange",
                f.medianTerminalWealth,
              ],
              ["P95 · FAVORABLE", f.p95, "positive", f.p95TerminalWealth],
            ]
              .map(([label, r, c, availableWealth]) =>
                template("forecast-panel-7", {
                  label: label,
                  c: c,
                  value3: referenceMoney(availableWealth),
                  r: pct(r, 1, true),
                  value5: state.settings.horizon * 12,
                }),
              )
              .join(""),
          })
        : "";
    return panel(
      historical ? "EVOLUCIÓN HISTÓRICA" : "DISTRIBUCIÓN DE RESULTADOS",
      "01",
      template("forecast-panel-4", {
        value1: state.busy ? template("forecast-panel-5") : "",
        value2: historical
          ? "RETORNO ACUMULADO · CARTERA"
          : "CAPITAL DISPONIBLE AL HORIZONTE · P50",
        value3: historical
          ? pct(analysis?.stats.total, 1, true)
          : f
            ? referenceMoney(f.medianTerminalWealth)
            : "—",
        legend: legend,
        value5: historical
          ? portfolioChart(analysis)
          : forecastCone(f, full ? 310 : 265),
        resultCards: resultCards,
      }),
      full
        ? template("forecast-panel-3", {
            toLocaleString: state.settings.paths.toLocaleString("en-US"),
          })
        : template("forecast-panel-2", {
            value1: state.chartMode === "forecast" ? "active" : "",
            value2: state.chartMode === "history" ? "active" : "",
          }),
      template("forecast-panel", {
        value1: historical
          ? "Pesos constantes · base 100 · sin costos"
          : `${simulatedProcess(f?.settings || state.settings, f?.volatility).label} · buy & hold · base 100`,
        value2: historical
          ? "VENTANA " + state.lookback + "D"
          : "SUPUESTOS EDITABLES",
      }),
    );
  }

  function riskMonitor(a) {
    const s = a?.stats;
    return panel(
      "RIESGO HISTÓRICO",
      "05",
      template("risk-monitor-values", {
        items: [
          ["Volatilidad anual", pct(s?.volatility)],
          ["Caída máxima histórica", pct(s?.maxDrawdown)],
          ["Beta vs SPY", fmt(s?.beta)],
          ["VaR histórico · 1 día", pct(s?.var95)],
          ["Sharpe histórico", fmt(s?.sharpe)],
        ]
          .map(([l, v]) => template("risk-monitor-row", { l: l, v: v }))
          .join(""),
      }),
      template("risk-monitor-action", { arrowIcon: icon("arrow") }),
    );
  }

  function overview() {
    const review = monitoring();
    const actions = template("overview-18", { refreshIcon: icon("refresh") });
    if (!review)
      return (
        title(
          "SEGUIMIENTO / SIN COMPOSICIÓN REGISTRADA",
          "Seguimiento de cartera",
          "Primero registra una composición con sus precios y fundamentos de referencia.",
          actions,
        ) + panel("ESTADO", "01", template("overview-17"))
      );
    const pending = review.alerts.filter(
      (a) => !state.acknowledged.includes(a.id),
    );
    return (
      title(
        "SEGUIMIENTO / CARTERA REGISTRADA",
        "Seguimiento de cartera",
        `Base ${dateLabel(review.baselineAsOf)} · último corte ${dateLabel(review.currentAsOf)}.`,
        actions,
      ) +
      `${review.missing.length ? template("overview-16", { items: review.missing.map(esc).join(", ") }) : ""}` +
      template("overview-15", {
        metric: metric(
          "VALOR AJUSTADO TEÓRICO",
          money(review.currentCapital, 0),
          "Base " + money(state.baseline.capital, 0),
        ),
        metric2: metric(
          "RETORNO DESDE REGISTRO",
          pct(review.totalReturn, 2),
          "Precios ajustados del proveedor",
          color(review.totalReturn),
        ),
        metric3: metric(
          "REVISIONES PENDIENTES",
          String(pending.length),
          "Criterios configurados; no órdenes automáticas",
          pending.length ? "orange" : "",
        ),
        metric4: metric(
          "CARTERA REGISTRADA",
          String(state.baseline.positions.length) + " activos",
          dateLabel(state.baseline.as_of),
        ),
      }) +
      panel(
        "REVISIONES POR INFORMACIÓN DISPONIBLE",
        "01",
        review.alerts.length
          ? template("overview-10", {
              items: review.alerts
                .map((a) =>
                  template("overview-11", {
                    value1:
                      a.priority === "alta"
                        ? "negative"
                        : a.priority === "media"
                          ? "orange"
                          : "muted",
                    toUpperCase: a.priority.toUpperCase(),
                    value3: asset(a.symbol) ? `data-detail="${a.symbol}"` : "",
                    symbol: a.symbol,
                    title: a.title,
                    reason: a.reason,
                    value7: a.url
                      ? template("overview-12", { url: url(a.url) })
                      : "",
                    review: a.review,
                    value9: state.acknowledged.includes(a.id)
                      ? template("overview-14")
                      : template("overview-13", { id: a.id }),
                  }),
                )
                .join(""),
            })
          : template("overview-9"),
        template("overview-8"),
        template("overview-7"),
      ) +
      template("overview-3", {
        panel: panel(
          "COMPOSICIÓN REGISTRADA / EVOLUCIÓN",
          "02",
          template("overview-5", {
            items: review.positions
              .map((p) =>
                template("overview-6", {
                  symbol: p.symbol,
                  symbol2: p.symbol,
                  weight: pct(p.weight),
                  currentWeight: pct(p.currentWeight),
                  returnTone: color(p.return),
                  return: pct(p.return, 2, true),
                  price: money(p.price),
                  price8: money(p.asset.price),
                  fairValue: money(p.currentModel?.fairValue),
                }),
              )
              .join(""),
          }),
          "",
          template("overview-4"),
        ),
      }) +
      template("overview", {
        riskMonitor: riskMonitor(review.analysis),
        panel: panel(
          "REGISTRO Y AVISOS",
          "03",
          template("overview-2", {
            registered_at: dateLabel(state.baseline.registered_at),
            as_of: dateLabel(state.baseline.as_of),
          }),
        ),
      })
    );
  }

  function tableSort(key, label) {
    return template("table-sort", {
      key: key,
      label: label,
      value3:
        state.sort.key === key ? (state.sort.ascending ? " ↑" : " ↓") : "",
    });
  }

  function renderTable(assets, compactTable = false) {
    if (!assets.length) return template("render-table-5");
    return template("render-table", {
      value1: compactTable ? "" : "full-table",
      tableSort: tableSort("symbol", "ACTIVO"),
      tableSort3: tableSort("price", "PRECIO"),
      tableSort4: tableSort("change", "1D %"),
      tableSort5: tableSort("pe", "P/E"),
      value6: compactTable
        ? ""
        : template("render-table-2", {
            tableSort: tableSort("fcfYield", "FCF YIELD"),
            tableSort2: tableSort("volatility", "VOL. ANUAL"),
          }),
      tableSort7: tableSort("upside", "VS MODELO"),
      items: assets
        .map((a) => {
          const m = metrics(a),
            v = model(a),
            added = state.positions.some((p) => p.symbol === a.symbol);
          return template("render-table-3", {
            symbol: a.symbol,
            slice: a.symbol.slice(0, 2),
            symbol3: a.symbol,
            name: a.name,
            price: money(a.price),
            changeTone: color(a.change),
            change: pct(a.change, 2, true),
            value8: finite(m.pe) ? fmt(m.pe, 1) + "x" : "—",
            value9: compactTable
              ? ""
              : template("render-table-4", {
                  fcfYieldTone: color(m.fcfYield),
                  fcfYield: pct(m.fcfYield),
                  volatility: pct(assetStats(a)?.volatility),
                }),
            upsideTone: color(v?.upside),
            upside: pct(v?.upside, 1, true),
            sparkline: sparkline(
              a.history.slice(-63).map((r) => r.adj_close),
              a.history.at(-1).adj_close >= a.history.at(-63)?.adj_close
                ? "var(--chart-positive)"
                : "var(--chart-negative)",
            ),
            value13: added ? "added" : "",
            symbol14: a.symbol,
            value15: added ? "Quitar" : "Agregar",
            symbol16: a.symbol,
            value17: added ? "del" : "al",
            value18: added ? "✓" : "+",
          });
        })
        .join(""),
    });
  }

  function research() {
    const sectors = [...new Set(data.assets.map((a) => a.sector))];
    return (
      title(
        "ACTIVOS / FUNDAMENTOS",
        "Research de activos",
        "Precios, múltiplos, generación de caja y comparación con tu valoración.",
        template("research-5", { downloadIcon: icon("download") }),
      ) +
      panel(
        "EQUITY & ETF SCREENER",
        "01",
        template("research-3", {
          searchIcon: icon("search"),
          text: state.filters.text,
          items: sectors
            .map((s) =>
              template("research-4", {
                value1: state.filters.sector === s ? "selected" : "",
                s: s,
              }),
            )
            .join(""),
          value4: state.filters.type === "stock" ? "selected" : "",
          value5: state.filters.type === "etf" ? "selected" : "",
          value6: state.filters.discount ? "checked" : "",
          renderTable: renderTable(filteredAssets()),
        }),
        template("research-2", { length: data.assets.length }),
        template("research"),
      )
    );
  }

  function validationPanel() {
    const v = state.validation;
    return panel(
      "COMPROBACIÓN FUERA DE MUESTRA",
      "04",
      template("validation-panel-2", {
        value1: v && v.coverage < 0.8 ? "negative" : "positive",
        coverage: pct(v?.coverage, 0),
        value3: v?.count || 0,
        value4:
          v?.results
            .map((r) =>
              template("validation-panel-3", {
                value1: r.covered ? "" : "miss",
                date: r.date,
                realized: pct(r.realized),
                low: pct(r.low),
                high: pct(r.high),
              }),
            )
            .join("") || "",
      }),
      template("validation-panel"),
    );
  }

  function forecastControls() {
    const s = state.settings;
    return panel(
      "PARÁMETROS",
      "02",
      template("forecast-controls", {
        value3: s.horizon === 0.25 ? "selected" : "",
        value4: s.horizon === 0.5 ? "selected" : "",
        value5: s.horizon === 1 ? "selected" : "",
        value6: s.horizon === 3 ? "selected" : "",
        horizonOptions: [...new Set([0.25, 0.5, 1, 2, 3, 5, s.horizon])]
          .sort((a, b) => a - b)
          .map((value) =>
            template("composition-horizon-option", {
              value,
              label: value < 1 ? `${value * 12} meses` : `${value} años`,
              selected: s.horizon === value ? "selected" : "",
            }),
          )
          .join(""),
        value7: s.driftMode === "fundamental" ? "selected" : "",
        value8: s.driftMode === "manual" ? "selected" : "",
        value9: fmt(s.manualReturn * 100, 0),
        items: [1000, 3000, 5000]
          .map((n) =>
            template("forecast-controls-2", {
              n: n,
              value2: s.paths === n ? "selected" : "",
              toLocaleString: n.toLocaleString("en-US"),
            }),
          )
          .join(""),
        items11: [0.94, 0.97, 0.99]
          .map((n) =>
            template("forecast-controls-3", {
              value1: s.lambda === n ? "selected" : "",
              n: n,
            }),
          )
          .join(""),
        processField: simulatedProcess(s).legacy
          ? template("forecast-process-select", {
              value1: s.model === "merton" ? "selected" : "",
              value2: s.model === "gbm" ? "selected" : "",
            })
          : template("forecast-process-fixed", {
              label: simulatedProcess(s, state.forecast?.volatility).label,
            }),
        value12:
          simulatedProcess(s).jumps
            ? template("forecast-controls-4", {
                jumpIntensity: s.jumpIntensity,
                value2: fmt(s.jumpMean * 100, 0),
                jumpVol: pct(s.jumpVol, 0),
              })
            : "",
        value13: state.forecast ? pct(state.forecast.coverage, 0) : "—",
        refreshIcon: icon("refresh"),
        value15: state.busy ? "Calculando…" : "Recalcular simulación",
        resimulateBusy: state.busy ? 'aria-busy="true"' : "",
        seed: s.seed,
      }),
    );
  }

  function forecastsView() {
    const f = state.forecast;
    return (
      title(
        "PROYECCIONES / MONTE CARLO",
        "Simulación de cartera",
        simulatedProcess(f?.settings || state.settings, f?.volatility).subtitle,
        template("forecasts-view-8", { downloadIcon: icon("download") }),
      ) +
      simulationMetrics() +
      template("forecasts-view", {
        forecastPanel: forecastPanel(true),
        panel: panel(
          "RETORNOS TERMINALES",
          "03",
          histogram(f),
          template("forecasts-view-3", { value1: state.settings.horizon * 12 }),
          template("forecasts-view-2"),
        ),
        validationPanel: validationPanel(),
        forecastControls: forecastControls(),
        panel5: panel(
          "SUPUESTOS DE RETORNO POR ACTIVO",
          "05",
          template("forecasts-view-5", {
            value1:
              f?.drifts
                .map((d) =>
                  template("forecasts-view-7", {
                    symbol: d.symbol,
                    symbol2: d.symbol,
                    annualTone: color(d.annual),
                    annual: pct(d.annual, 1, true),
                    source: d.source,
                    symbol6: d.symbol,
                    arrowIcon: icon("arrow"),
                  }),
                )
                .join("") || template("forecasts-view-6"),
          }),
          "",
          template("forecasts-view-4"),
        ),
      })
    );
  }

  function portfolio() {
    const a = analyze(),
      w = normalizeWeights(state.positions),
      total = sum(state.positions.map((p) => p.weight));
    return (
      title(
        "CARTERA / POSICIONES",
        "Composición de cartera",
        "Pesos por activo y capital de simulación.",
        template("portfolio-actions", {
          composeDisabled: state.compositionBusy || state.robustnessBusy ? "disabled" : "",
          referenceDisabled: state.compositionBusy || state.robustnessBusy ? "disabled" : "",
          robustLabel: state.robustnessBusy ? "Comparando…" : "Comparar robustez",
          robustBusy: state.robustnessBusy ? 'aria-busy="true"' : "",
          composeBusy: state.compositionBusy ? 'aria-busy="true"' : "",
          applyDisabled: state.proposal?.status === "proposed" &&
            state.proposal.model_version === MODEL_VERSION &&
            state.proposal.as_of === data.price_as_of &&
            state.proposal.snapshot_generated_at === data.generated_at &&
            !state.proposal.modified && (context.proposalFresh?.()??true) ? "" : "disabled",
          composeLabel: state.compositionBusy
            ? "Evaluando…"
            : "Proponer cartera",
          value1:
            !state.positions.some((p) => p.weight > 0) ||
            Math.abs(total - 1) > 0.0001
              ? "disabled"
              : "",
        }),
      ) +
      compositionControls() +
      financialCoverageView(data) +
      priceMonitorView(data,state.account?.enabled?state.account.positions:state.positions,
        state.priceMonitorFilter||'all',state.priceMonitorOpen||false) +
      compositionReport() +
      robustnessView(state.robustness,{
        busy:state.robustnessBusy,error:state.robustnessError,progress:state.robustnessProgress,
        fresh:state.robustness?.model_version===MODEL_VERSION&&state.robustness?.as_of===data.price_as_of&&
          state.robustness?.snapshot_generated_at===data.generated_at&&(context.robustnessFresh?.()??true),
      }) +
      template("portfolio-layout", {
        value1:
          state.positions.length && Math.abs(total - 1) > 0.0001
            ? template("portfolio-weight-notice", { total: pct(total, 2) })
            : "",
        panel: panel(
          "POSICIONES",
          "01",
          state.positions.length
            ? template("portfolio-positions", {
                items: state.positions
                  .map((p) => {
                    const x = asset(p.symbol);
                    return template("portfolio-position-row", {
                      symbol: p.symbol,
                      slice: p.symbol.slice(0, 2),
                      symbol3: p.symbol,
                      name: x.name,
                      price: money(x.price),
                      value6: fmt(p.weight * 100, 2),
                      symbol7: p.symbol,
                      symbol8: p.symbol,
                      value9: money(
                        (w.find((v) => v.symbol === p.symbol)?.weight || 0) *
                          positionCapital(),
                        0,
                      ),
                      fraction: pct(
                        a?.contributions.find((c) => c.symbol === p.symbol)
                          ?.fraction,
                      ),
                      symbol11: p.symbol,
                      symbol12: p.symbol,
                      closeIcon: icon("close"),
                    });
                  })
                  .join(""),
                value2: Math.abs(total - 1) < 0.0001 ? "positive" : "orange",
                total: pct(total, 2),
              })
            : template("portfolio-empty", {
                price_as_of: dateLabel(data.price_as_of),
                items: data.assets
                  .map((x) =>
                    template("portfolio-asset-option", {
                      symbol: x.symbol,
                      symbol2: x.symbol,
                    }),
                  )
                  .join(""),
              }),
          template("portfolio-add-action"),
        ),
        panel3: panel("DISTRIBUCIÓN", "02", allocation(a)),
        panel4: panel(
          "CAPITAL & ARCHIVO",
          "03",
          template("portfolio-archive", {
            capital: state.capital,
            price_as_of: dateLabel(data.price_as_of),
            downloadIcon: icon("download"),
            uploadIcon: icon("upload"),
          }),
        ),
        panel5: panel(
          "EXPOSICIÓN SECTORIAL",
          "04",
          bars(Object.entries(a?.sectors || {}).sort((a, b) => b[1] - a[1])),
        ),
        riskMonitor: riskMonitor(a),
      })
    );
  }

  function compositionControls() {
    const rules = { ...DEFAULT_COMPOSITION_RULES, ...state.compositionRules };
    const fields = [
      ["maxPosition", "MÁX. EMISOR · ACCIÓN + ETF", 5, 50, 5, 100, "%"],
      ["maxFund", "MÁX. ETF · LÍMITE ESPECÍFICO", 5, 100, 5, 100, "%"],
      ["maxGlobal", "MÁX. GLOBAL POR ACTIVO", 5, 75, 5, 100, "%"],
      ["maxOpportunity", "TOPE POR OPORTUNIDAD VALIDADA", 5, 75, 5, 100, "%"],
      ["maxTreasury", "MÁX. TREASURIES COMBINADOS", 5, 100, 5, 100, "%"],
      ["maxEquity", "MÁX. ACCIONES COMBINADAS", 5, 100, 5, 100, "%"],
      ["maxSector", "MÁX. SECTOR · ACCIÓN + ETF", 10, 100, 5, 100, "%"],
      ["reserveCap", "MÁX. RESERVA SHY", 5, 100, 5, 100, "%"],
      ["maxPositions", "MÁX. POSICIONES", 2, 12, 1, 1, ""],
      ["maxCorrelation", "CORRELACIÓN MÁXIMA", 0.1, 1, 0.05, 1, "ρ"],
      ["cvarBudget", "CVAR 95% MÁX. · HORIZONTE", 1, 80, 1, 100, "%"],
      ["maxLossProbability", "PROB. PÉRDIDA MÁX.", 1, 100, 1, 100, "%"],
    ];
    return template("composition-controls", {
      months: state.settings.horizon * 12,
      universeOptions:[20,40,60,80].map(value=>template('composition-horizon-option',{
        value,label:value+' activos'+(value===40?' · predeterminado':''),
        selected:value===(state.settings.compositionUniverseLimit??state.settings.researchUniverseLimit??40)?'selected':''
      })).join(''),
      budget: pct(rules.cvarBudget, 0),
      volatilityHybridSelected: !["ewma", "legacy"].includes(state.settings.volatilityMode) ? "selected" : "",
      volatilityEWMASelected: state.settings.volatilityMode === "ewma" ? "selected" : "",
      volatilityLegacySelected: state.settings.volatilityMode === "legacy" ? "selected" : "",
      dividendsCashSelected:(state.mandate?.dividendPolicy??"cash") === "cash" ? "selected" : "",
      dividendsReinvestSelected:state.mandate?.dividendPolicy === "reinvest" ? "selected" : "",
      dividendWithholdingValue:fmt(100*(state.mandate?.dividendWithholding||0),0),
      cashYieldValue:fmt(100*(state.mandate?.cashYield||0),2),
      fields: fields
        .map(([key, label, min, max, step, scale, unit]) =>
          template("composition-field", {
            key,
            label,
            min,
            max,
            step,
            scale,
            unit,
            value: fmt(rules[key] * scale, key === "maxCorrelation" ? 2 : 0),
          }),
        )
        .join(""),
      horizons: [
        [0.25, "3 meses"],
        [0.5, "6 meses"],
        [1, "1 año"],
        [2, "2 años"],
        [3, "3 años"],
        [5, "5 años"],
        ...(![0.25, 0.5, 1, 2, 3, 5].includes(state.settings.horizon)
          ? [[state.settings.horizon, `${state.settings.horizon * 12} meses`]]
          : []),
      ]
        .map(([value, label]) =>
          template("composition-horizon-option", {
            value,
            label,
            selected: state.settings.horizon === value ? "selected" : "",
          }),
        )
        .join(""),
    });
  }

  function compositionReport() {
    if (state.compositionError)
      return template("composition-notice", {
        message: state.compositionError,
      });
    const p = state.proposal;
    if (!p) return "";
    if (p.model_version !== MODEL_VERSION ||
        p.as_of !== data.price_as_of ||
        p.snapshot_generated_at !== data.generated_at || (context.proposalFresh && !context.proposalFresh()))
      return template("composition-notice", {
        message: "Propuesta desactualizada: versión del motor o corte de datos distinto. Pulsa Proponer cartera.",
      });
    if (p.status !== "proposed")
      return template("composition-notice", { message: p.reason });
    const metrics = [
      [
        "RETORNO MEDIANO",
        pct(p.metrics.medianReturn, 1, true),
        color(p.metrics.medianReturn),
        `P05 ${pct(p.metrics.p05)} · P95 ${pct(p.metrics.p95)}`,
      ],
      [
        "PROB. DE PÉRDIDA",
        pct(p.metrics.lossProbability),
        "",
        `Error Monte Carlo ±${pct(1.96 * p.metrics.lossProbabilitySE)}`,
      ],
      [
        "CVAR 95% · SIMULADO",
        pct(p.metrics.cvar95),
        "negative",
        `Límite ${pct(p.rules.cvarBudget, 0)}`,
      ],
      [
        "ANÁLISIS EX ANTE",
        `${p.settings.horizon * 12} meses`,
        "orange",
        `Precios ${dateLabel(p.as_of)} · información ${dateLabel(p.information_as_of || p.as_of)}`,
      ],
    ];
    return template("composition-report", {
      asOf: dateLabel(p.as_of),
      sourceNotice: p.reference_id
        ? "CONFIGURACIÓN BASE · Capital USD 100.000 · cuenta vacía"
        : "TU SESIÓN · " + p.account_source + " · USD " + fmt(p.capital,0),
      notice: p.modified
        ? template("composition-notice", {
            message:
              "Pesos, límites o supuestos modificados. Las cifras de esta sección corresponden a la propuesta original.",
          })
        : "",
      metrics: metrics
        .map(([label, value, tone, detail]) =>
          template("composition-metric", { label, value, tone, detail }),
        )
        .join(""),
      rows: p.signals
        .map((s) =>
          template("composition-signal", {
            symbol: s.symbol,
            weight: pct(s.weight, 1),
            low: pct(s.adverseAnchor),
            anchor: pct(s.anchor),
            high: pct(s.favorableAnchor),
            role: compositionRole(s,p),
          }),
        )
        .join(""),
      valuationRows:p.signals.map(s=>template('composition-signal-detail',{
            symbol:s.symbol,
            valuationEvidence: compositionValuationEvidence(s),
            returnSplit: compositionReturnSplit(s),
            source: s.filed
              ? `BPA publicado ${money(s.eps)} · ${s.financialMethod||'método no registrado'} hasta ${dateLabel(s.financialPeriod)} · presentado ${dateLabel(s.filed)} · captura XBRL ${s.financialObservedAt?timestampLabel(s.financialObservedAt):'no registrada'}`
              : s.source+(s.bondDate?' · perfil al '+dateLabel(s.bondDate):''),
          })).join(''),
      allocationSummary:(()=>{
        const s=p.diagnostics?.economicExposure?.sleeves;
        const rows=s?[["Treasuries",s.treasury],["Crédito",s.credit],["Bonos mixtos",s.mixedBonds],
          ["Acciones",s.usEquity+s.globalEquity],["Oro",s.gold],["Plata",s.silver]]:[];
        rows.push(['Efectivo',p.positions.find(r=>r.symbol==='CASH')?.weight||0]);
        return rows.filter(([,w])=>w>1e-8).map(([label,w])=>`${label} ${pct(w,1)}`).join(' · ');
      })(),
      selectionSummary:`Objetivo: ${{growth:'crecimiento logarítmico',preservation:'preservación',target:'capital objetivo'}[p.mandate?.objective]||'según mandato'}. `+
        (p.diagnostics?.selected?.nearLimits?.length
          ? 'Topes próximos: '+p.diagnostics.selected.nearLimits.slice(0,3)
              .map(r=>`${r.name} ${pct(r.observed,0)} / ${pct(r.limit,0)}`).join(' · ')
          : `Comparación local entre ${p.selection?.simulated??'—'} activos simulados.`)+
        ` · máximo ${p.rules.maxPositions} posiciones · correlación ${fmt(p.rules.maxCorrelation,2)}`,
      cashExplanation:compositionCashExplanation(p),
      cashAuditSummary:(()=>{
        const a=p.diagnostics?.cashAllocation;
        return a?`${a.evaluated} reasignaciones evaluadas; ${a.structurallyBlocked} bloqueadas por los topes. `+
          `Efectivo antes de la revisión ${pct(a.initialCashWeight,1)}; después ${pct(a.cashWeight,1)}. `+
          `Mejora equivalente simulada USD ${fmt(a.improvements.reduce((n,r)=>n+r.certaintyEquivalentGain,0),0)}. `+
          'Tramos de 5 y 10 puntos en los mismos escenarios finales: no es una validación independiente ni un óptimo global.'
          : 'Sin comprobación de reasignación del efectivo en esta propuesta.';
      })(),
      cashAuditRows:(p.diagnostics?.cashAllocation?.comparisons||[]).slice(0,10).map(r=>
        template('composition-cash-comparison',{
          target:`${r.symbol} +${pct(r.transfer,0)}`,cash:pct(r.toCash,1),
          median:pct(r.medianReturn,1),cvar:pct(r.cvar95,1),
          gain:fmt(r.certaintyEquivalent-p.metrics.certaintyEquivalent,0),
          result:r.feasible?(Math.abs(r.score-p.metrics.score)<1e-12?'Objetivo equivalente':
            r.score>p.metrics.score?'Mejora candidata':'Menor objetivo'):r.failures.join(', '),
        })).join(''),
      evaluated: p.search.evaluated,
      feasible: p.search.feasible,
      searchPaths: p.search.paths,
      published: p.selection?.published ?? data.assets.length,
      eligible: p.selection?.eligible ?? "—",
      simulated: p.selection?.simulated ?? "—",
      exposureSummary: (() => {
        const d=p.diagnostics?.economicExposure;
        if(!d)return "Sin desglose económico";
        const s=d.sleeves;
        return `Treasuries ${pct(s.treasury,1)} · Crédito ${pct(s.credit,1)} · Bonos mixtos ${pct(s.mixedBonds,1)} · Acciones USA ${pct(s.usEquity,1)} · Acciones globales / internacionales ${pct(s.globalEquity,1)} · Oro ${pct(s.gold,1)}`;
      })(),
      overlapSummary: (() => {
        const r=p.diagnostics?.etfCorrelations||[];
        return r.length
          ? r.slice(0,5).map(x =>
              x.pair+" corr. total "+fmt(x.totalCorrelation,2)+
              (x.residualCorrelation===null?"":", residual "+fmt(x.residualCorrelation,2))+
              (x.knownHoldingsOverlap==null?", holdings compartidas sin verificar":
                ", solapamiento conocido "+pct(x.knownHoldingsOverlap,1)+
                ", exposición compartida "+pct(x.knownSharedPortfolioWeight,1)+" de cartera"))
            .join(" · ")
          : "No hay parejas relevantes con ETF en la propuesta.";
      })(),
      etfHoldingsRows:(p.diagnostics?.economicExposure?.funds||[]).map(f=>
        template("composition-etf-holding",{
          symbol:f.symbol,weight:pct(f.weight),
          group:f.economicGroup,
          date:f.holdingsAsOf ? dateLabel(f.holdingsAsOf):"No observado",
          observed:f.firstObservedAt ? dateLabel(f.firstObservedAt):"—",
          coverage:f.coveredWeight===null?"—":pct(f.coveredWeight,1),
          positions:f.topHoldings.map(h=>h.symbol+" "+pct(h.weight,2)).join(" · ")||
            "Sin datos válidos de composición al corte",
          sourceCell:f.sourceUrl
            ? '<a href="'+esc(url(f.sourceUrl))+'" target="_blank" rel="noopener noreferrer">'+
                esc(f.sourceLayer||"Fuente")+'</a>'
            : "Sin fuente verificable"
        })
      ).join(""),
      lookthroughSummary: (()=>{
        const d=p.diagnostics?.economicExposure;
        if(!d)return "Sin desglose por emisor";
        const top=Object.entries(d.issuers).sort((a,b)=>b[1]-a[1]).slice(0,6)
          .map(([s,w])=>s+" "+pct(w,1)).join(" · ")||"sin acciones";
        return `Emisores conocidos (directo + ETF): ${top}. Parte sin identificar por emisor ${pct(d.unclassifiedIssuerWeight||0,1)} y por sector ${pct(d.unclassifiedSectorWeight||0,1)} de la cartera. Los topes usan cotas conservadoras para esa parte; no representan pesos observados.`;
      })(),
      exposureWarning: (() => {
        const d=p.diagnostics?.economicExposure;
        return d?.unknownHoldings?.length
          ? "Holdings incompletas o no utilizables al corte: " + d.unknownHoldings.join(", ") + ". Composiciones de más de 120 días se excluyen del desglose; su parte desconocida limita las compras."
          : "No hay exposición accionaria con holdings desconocidas entre las posiciones seleccionadas.";
      })(),
      incomeSummary: (p.metrics?.dividendPolicy==="cash"
        ? `Dividendos netos estimados disponibles en efectivo USD ${fmt(p.metrics.expectedNetDividendCash,0)}; brutos cobrados USD ${fmt(p.metrics.expectedGrossDividendCash,0)}; pendientes de pago al final USD ${fmt(p.metrics.expectedDividendReceivable||0,0)}. Retención supuesta ${pct(p.metrics.dividendWithholding,0)}. Importes futuros no declarados estimados desde los últimos 12 meses.`
        : `Distribuciones netas estimadas reinvertidas USD ${fmt(p.metrics.expectedNetReinvestedDividends||0,0)}; retención estimada USD ${fmt(p.metrics.expectedDividendWithholding||0,0)} (${pct(p.metrics.dividendWithholding||0,0)}). La reinversión no deja efectivo disponible para retiros.`)+
          (p.metrics?.cashYield>0?` Intereses de caja modelados USD ${fmt(p.metrics.expectedCashInterest||0,0)} al ${pct(p.metrics.cashYield)} neto declarado; devengo desde cada cobro y hasta cada retiro.`:''),
      dividendCalendarSummary:(()=>{
        const rows=p.metrics?.dividendTiming||[],dated=rows.filter(r=>r.mode==="issuer-calendar");
        const capped=rows.reduce((n,r)=>n+(r.cappedEvents||0),0);
        return `Fechas previstas del emisor: ${dated.map(r=>r.symbol).join(", ")||"sin calendario completo al corte"}. Los demás flujos conservan la aproximación uniforme. La fecha prevista no confirma el importe ni el abono del broker.`+
          (capped?` ${capped} eventos de distribución se limitaron al valor simulado disponible; revisar impago.`:"");
      })(),
      dividendCalendarRows:(p.metrics?.dividendTiming||[]).filter(r=>r.mode==="issuer-calendar")
        .flatMap(r=>r.events.slice(0,6).map(e=>template("composition-dividend-row",{
          symbol:r.symbol,exDate:dateLabel(e.ex_date),payDate:dateLabel(e.pay_date),
          amount:e.amount_per_share===null?"Importe supuesto":money(e.amount_per_share),
          sourceUrl:url(r.source_url),
        }))).join(""),
      globalLimitNote: `Límite global ${pct(p.rules.maxGlobal,0)} por instrumento; tope de excepción ${pct(p.rules.maxOpportunity,0)} únicamente con validación prospectiva independiente. Treasuries combinados ${pct(p.rules.maxTreasury,0)}. Acciones combinadas ${pct(p.rules.maxEquity,0)}. Excepciones aprobadas: ${(p.diagnostics?.concentrationPolicy?.qualified||[]).join(", ")||"ninguna"}.`,
      concentration: p.diagnostics?.selected?.largestPosition
        ? `${p.diagnostics.selected.largestPosition.symbol} ${pct(p.diagnostics.selected.largestPosition.weight, 1)}`
        : "No determinada",
      attributionRows: p.diagnostics?.attribution?.available
        ? p.diagnostics.attribution.contributions.map(c =>
          template("composition-contribution", {
            symbol:c.symbol,weight:pct(c.weight,1),
            returnContribution:pct(c.expectedReturnContribution,2),
            leftTailContribution:pct(c.leftTailLossContribution,2),
            varianceContribution:pct(p.signals.find(s=>s.symbol===c.symbol)?.risk?.fraction,1),
          })).join("")
        : "",
      attributionNotice: p.diagnostics?.attribution?.available
        ? "Aportes condicionados a los mismos escenarios de verificación. Los costes se contabilizan aparte: " +
          pct(p.diagnostics.attribution.costLoss,2) +
          ". Un aporte negativo en la cola puede representar cobertura, no riesgo nulo. La porción de varianza usa la covarianza lineal inicial inducida, aproximada después de transformar las marginales."
        : (p.diagnostics?.attribution?.reason || "No se calculó una atribución compatible."),
      attributionShort:p.diagnostics?.attribution?.available
        ? `Aportes sobre los mismos escenarios; costes ${pct(p.diagnostics.attribution.costLoss,2)} contabilizados aparte.`
        : 'Sin atribución disponible.',
      nearLimits: p.diagnostics?.selected?.nearLimits?.length
        ? p.diagnostics.selected.nearLimits.map((r) =>
            `${r.name} ${pct(r.observed, 1)} / ${pct(r.limit, 1)}`
          ).join("; ")
        : "ninguna al 90% del límite",
      referenceSummary: [["cash", "Efectivo"], ["reserve", "SHY/efectivo"],
        ["equity20", "Índice 20%"]].map(([id, label]) => {
          const r = p.diagnostics?.references?.[id];
          return r ? `${label}${r.researchOnly ? " (hipótesis, no comprable)" : ""}: ${r.feasible ? "factible" : "no factible"} · rendimiento medio ${pct(r.meanReturn, 1)} · CVaR ${pct(r.cvar95, 1)}${r.assumption ? " · " + r.assumption : ""}`
            : `${label}: no comparable (falta historia o no satisface restricciones)`;
        }).join(" | "),
      shyExplanation: (() => {
        const a=p.diagnostics?.concentrationAudit;
        return a?.shyAnnualAnchor==null ? "Sin diagnóstico" :
          `SHY: retorno supuesto ${pct(a.shyAnnualAnchor,1)} (${a.shyAnchorSource}); volatilidad condicional anual ${pct(a.shyAnnualVolatility,1)}. Tope SHY ${pct(a.shyMaxAllowed,0)} (sujeto al tope global ${pct(p.rules.maxGlobal,0)}); peso elegido ${pct(a.actualShyWeight,0)}. Una tasa relativamente elevada y bajo riesgo pueden dominar al no existir primas accionarias suficientemente respaldadas.`;
      })(),
      shyCapAlternatives: (p.diagnostics?.concentrationAudit?.comparedCaps||[])
        .map(r => r.feasible
          ? `SHY ≤${pct(r.cap,0)}: retorno medio ${pct(r.meanReturn,1)}, CVaR ${pct(r.cvar95,1)}, brecha de equivalente cierto vs propuesta USD ${fmt(r.certaintyGapVsSelected,0)} (de ${r.compared} candidatas comparadas)`
          : `SHY ≤${pct(r.cap,0)}: ninguna candidata verificada de las exploradas`)
        .join(" | "),
      shortlistNote: p.selection?.preselectionMethod || "selección no identificada",
      omittedTop: (p.selection?.outsideWithHigherPriority||[])
        .map(r=>r.symbol).join(", ") || "ninguno",
      assumedETFCount: p.diagnostics?.selected?.uncalibratedEtfs?.length ?? "—",
      engineVersion: p.model_version || "—",
      seed: p.settings.seed,
      maxCorr: fmt(p.rules.maxCorrelation, 2),
      dependenceMethod: p.diagnostics?.dependence?.available
        ? "correlación total en pares con ETF; residual SPY bull/bear + sector entre acciones"
        : "total (historia insuficiente)",
      dependenceObservations: p.diagnostics?.dependence?.observations ?? 0,
      volatilityUsed: p.diagnostics?.volatility?.mode || "EWMA",
      volatilityAccepted: p.diagnostics?.volatility?.accepted ?? 0,
      volatilityFallback: p.diagnostics?.volatility?.fallback ?? 0,
      volatilityNote: (p.diagnostics?.volatility?.reason || "Sin calibración disponible") +
        " · Factorización latente: " + (p.diagnostics?.volatility?.factorMethod || "total")+
        (p.diagnostics?.volatility?.accepted>0?` · Cambio máximo de correlación lineal inicial tras las marginales: ${fmt(p.diagnostics.volatility.maxLinearCorrelationShift||0,3)}. La matriz latente y la inducida se registran por separado.`:''),
      stochasticTail: p.diagnostics?.volatility?.accepted > 0
        ? "Marginales Student-t en GJR aceptados, gaussianas en los demás; dependencia por cópula gaussiana sin cola conjunta validada"
        : p.diagnostics?.volatility?.additionalMertonJumps
          ? "Saltos genéricos de Merton (comparador)"
          : "Innovaciones gaussianas EWMA",
      verificationPaths: p.verification.paths,
      months: p.settings.horizon * 12,
      model: p.diagnostics?.volatility?.additionalMertonJumps
        ? "con saltos genéricos de Merton"
        : p.diagnostics?.volatility?.accepted > 0
          ? "con volatilidad condicional GJR-t; saltos Merton desactivados"
          : "GBM/EWMA sin saltos",
    });
  }

  function bars(entries, signed = false) {
    return template("bars", {
      value1:
        entries
          .map(([label, value], i) =>
            template("bar-item", {
              label: label,
              value2: signed ? color(value) : "",
              value: pct(value),
              min: Math.min(100, Math.abs(value) * 100),
              value5: signed && value < 0 ? "negative" : "positive",
            }),
          )
          .join("") || template("bars-empty"),
    });
  }

  function riskView() {
    const a = analyze(),
      s = a?.stats;
    const factor = a?.weights?.length
      ? factorModel(data.assets, a.weights, data.price_as_of,
          state.lookback, state.settings.lambda, data.assets)
      : null;
    const residual = factor?.available
      ? { ...a, matrix: factor.residualCorrelation } : null;
    const validPairs = residual
      ? factor.residualCorrelation.flatMap((row, i) =>
          row.filter((v, j) => i !== j && finite(v))) : [];
    const residualAverage = validPairs.length
      ? validPairs.reduce((total, v) => total + v, 0) / validPairs.length
      : null;
    const points =
      a?.selected.map((x) => {
        const s = assetStats(x);
        return { symbol: x.symbol, x: s?.volatility, y: s?.annualized };
      }) || [];
    const biggest = a?.weights.reduce((x, y) => (x.weight > y.weight ? x : y), {
      weight: 0,
    });
    return (
      title(
        "RIESGO / EXPOSICIONES",
        "Riesgo de cartera",
        "Volatilidad, correlaciones, drawdown y pérdidas de cola.",
        template("risk-view-7", {
          value1: state.lookback === 252 ? "active" : "",
          value2: state.lookback === 500 ? "active" : "",
        }),
      ) +
      template("risk-view", {
        metric: metric(
          "VOLATILIDAD ANUAL",
          pct(s?.volatility),
          "Desv. estándar diaria × √252",
        ),
        metric2: metric(
          "CVAR 95% · 1 DÍA",
          pct(s?.expectedShortfall),
          "Histórico · media del peor 5%",
          "negative",
        ),
        metric3: metric(
          "MÁXIMO DRAWDOWN",
          pct(s?.maxDrawdown),
          "Desde máximos · ventana seleccionada",
          "negative",
        ),
        metric4: metric(
          "CORRELACIÓN MEDIA",
          fmt(a?.averageCorrelation, 2),
          `${a?.stats.n || 0} retornos comunes · Pearson`,
        ),
        panel: panel(
          "MATRIZ DE CORRELACIÓN TOTAL",
          "01",
          template("risk-view-2", { heatmap: heatmap(a) }),
        ),
        panel6: panel(
          "RIESGO / RETORNO HISTÓRICO",
          "02",
          scatter(points, s ? { x: s.volatility, y: s.annualized } : null),
          template("risk-view-3"),
        ),
        panel7: panel(
          "CONTRIBUCIÓN A LA VARIANZA",
          "03",
          bars(
            (a?.contributions || []).map((c) => [c.symbol, c.fraction]),
            true,
          ),
          "",
          template("risk-view-4"),
        ),
        panel8: panel(
          "CAÍDAS DESDE MÁXIMOS",
          "04",
          portfolioChart(a, { height: 230, drawdown: true }),
        ),
        panel9: panel(
          "ESCENARIOS DE ESTRÉS",
          "05",
          template("risk-view-6", {
            value1: pct(finite(s?.beta) ? -0.2 * s.beta : null),
            value2: pct(biggest ? -0.3 * biggest.weight : null),
            value3: biggest?.symbol || "—",
            drawdownProbability: pct(state.forecast?.drawdownProbability),
            value5: state.settings.horizon * 12,
          }),
          "",
          template("risk-view-5"),
        ),
      }) +
      panel(
        "MATRIZ RESIDUAL · SPY BULL/BEAR + SECTOR",
        "06",
        residual ? template("risk-view-2", { heatmap: heatmap(residual) })
          : template("composition-notice", {
              message: factor?.note || "Sin observaciones suficientes.",
            }),
        "",
        residual
          ? `Media residual ${fmt(residualAverage, 2)} · ${factor.observations} sesiones equiponderadas, la misma ventana que la matriz total. EWMA reciente (vida media ${fmt(factor.recentHalfLife, 0)} sesiones) solo como diagnóstico: desvío máximo ${fmt(factor.recentDivergence, 2)}. Betas SPY por régimen determinado con 63 retornos anteriores, más proxy sectorial. La matriz total anterior sigue alimentando Monte Carlo y CVaR. No implica independencia causal.`
          : "Con datos insuficientes, se conserva explícitamente la correlación total."
      ) +
      panel(
        "VOLATILIDAD CONDICIONAL · GJR / EWMA",
        "07",
        template("composition-notice", {
          message: data.volatility
            ? `Corte ${data.volatility.as_of}. Aceptados ${data.volatility.summary?.eligible ?? 0} de ${data.volatility.summary?.evaluated ?? 0} activos.${(a?.weights || []).length ? " " + a.weights.map((p) =>
                `${p.symbol}: ${data.volatility.instruments?.[p.symbol]?.status === "accepted" ? "GJR verificado" : "EWMA / investigación"}`).join(" · ") + "." : ""} Los errores no se descartan por coincidir con noticias.`
            : "No existe un corte de volatilidad compatible. Simulación con EWMA y los supuestos previos, sin atribución automática de noticias.",
        }),
        "",
        "QLIKE walk-forward frente a EWMA; Student-t solo para calibraciones aceptadas. La elección de la distribución y la cobertura del CVaR requieren validación continua. " +
          riskCalibrationNote(data.riskCalibration)
      ) +
      panel(
        "SHOCKS EXTREMOS · SIN ATRIBUCIÓN A NOTICIAS",
        "08",
        template("composition-notice", {
          message: (() => {
            if (!data.volatility) return "Sin registro de anomalías calibrado para este corte.";
            const covered = (a?.weights || []).some((p) =>
              Array.isArray(data.volatility.instruments?.[p.symbol]?.unattributed_shocks));
            if (!covered) return "El corte aún no incluye evaluación de shocks. No se puede concluir que no hayan ocurrido.";
            const shocks = (a?.weights || []).flatMap((p) =>
              (data.volatility.instruments?.[p.symbol]?.unattributed_shocks || []).map((event) =>
                ({...event,symbol:p.symbol})))
              .sort((x,y)=>y.date.localeCompare(x.date)).slice(0,10);
            return shocks.length
              ? shocks.map((event) =>
                  `${event.date} ${event.symbol}: ${pct(event.return_pct/100,1,true)}, innovación ${fmt(event.standardized_surprise,1)}σ · noticia no verificada`).join(" | ")
              : "No se detectaron shocks ≥3σ en los últimos 63 pronósticos fuera de muestra de la cartera. No significa ausencia de noticias.";
          })(),
        }),
        "",
        "Detectar una anomalía no identifica su causa. No se eliminan errores predictivos. Un evento requiere fuente y hora verificables y análisis causal separado."
      )
    );
  }

  function valuationView() {
    const a = asset(state.selected) || data.assets[0],
      m = metrics(a),
      useContinuing = a.type === 'stock' && state.method === 'pe' && state.research?.[a.symbol]?.earningsBasis === 'continuing',
      forecast = useContinuing ? fundamentalForecast(a,override(a.symbol),state.research[a.symbol],
        {asOf:informationDate(data),priceAsOf:data.price_as_of}) : null,
      valuationAsset = useContinuing && forecast.valid ? {...a,financials:{...a.financials,
        eps:{...a.financials.eps,value:forecast.effectiveBaseEPS}}} : a,
      v = useContinuing ? (forecast.valid ? valuation(valuationAsset,override(a.symbol),state.method) : null) : model(a, state.method),
      ass = { ...a.assumptions, ...override(a.symbol) },
      expected = resolveAssumptions(valuationAsset, override(a.symbol), state.method),
      expectedModel = v && valuation(valuationAsset, expected, state.method),
      sc = useContinuing && !forecast.valid ? [] : scenarios(valuationAsset, override(a.symbol), state.method);
    return (
      title(
        "VALORACIÓN / SUPUESTOS",
        "Valoración por múltiplos",
        "Valor presente según crecimiento, múltiplo de salida y tasa de descuento.",
        template("valuation-view-10"),
      ) +
      template("valuation-view", {
        items: data.assets
          .map((x) =>
            template("valuation-view-2", {
              symbol: x.symbol,
              value2: a.symbol === x.symbol ? "selected" : "",
              symbol3: x.symbol,
              name: x.name,
            }),
          )
          .join(""),
        price: money(a.price),
        price_date: dateLabel(a.price_date),
        value4: ass.horizon || 3,
        panel: panel(
          "SUPUESTOS",
          "01",
          template("valuation-view-3", {
            value1: state.method === "pe" ? "active" : "",
            value2: state.method === "fcf" ? "active" : "",
            items: [
              ["growth", "CRECIMIENTO ANUAL", -30, 60, 1, 100, "%"],
              ["multiple", "MÚLTIPLO DE SALIDA", 5, 60, 1, 1, "x"],
              ["discount", "RENTABILIDAD EXIGIDA", 1, 30, 0.5, 100, "%"],
              ["horizon", "HORIZONTE · AÑOS", 1, 5, 1, 1, "a"],
            ]
              .map(([key, label, min, max, step, scale, unit]) =>
                template("valuation-view-4", {
                  key: key,
                  label: label,
                  key3: key,
                  value4: finite(ass[key])
                    ? fmt(
                        ass[key] * scale,
                        key === "multiple" || key === "horizon" ? 0 : 1,
                      )
                    : "—",
                  unit: unit,
                  key6: key,
                  min: min,
                  max: max,
                  step: step,
                  value10:
                    (ass[key] ??
                      (key === "multiple"
                        ? 20
                        : key === "growth"
                          ? 0.06
                          : key === "horizon"
                            ? 3
                            : 0.1)) * scale,
                  key11: key,
                  scale: scale,
                }),
              )
              .join(""),
            splitHorizon: fmt(expected.horizon, 0),
            splitRows: returnSplitRows(expectedModel && returnDecomposition(expectedModel, expectedModel.base, a.price))
              .map((row) => template("return-split-row", row)).join(""),
            reratingNote: `${reratingText(expected.rerating, expected)}. El valor justo usa el múltiplo de referencia; editarlo lo fija tal cual.`,
          }),
        ),
        panel6: panel(
          useContinuing ? "VALOR PRESENTE · BPA CONTINUADO" : "VALOR PRESENTE DEL MODELO",
          "02",
          v
            ? template("valuation-view-6", {
                fairValue: money(v.fairValue),
                price: money(a.price),
                upsideTone: color(v.upside),
                upside: pct(v.upside, 1, true),
                value5:
                  v.upside > 0
                    ? "Descuento bajo estos supuestos"
                    : "Prima bajo estos supuestos",
                ...rulerMarkers(a.price, v.fairValue),
                items: sc
                  .map((s) =>
                    template("valuation-view-7", {
                      label: s.label,
                      growth: pct(s.result?.assumptions.growth, 0),
                      multiple: fmt(s.result?.assumptions.multiple, 1),
                      exitPrice: money(s.result?.exitPrice),
                      annualReturnTone: color(s.result?.annualReturn),
                      annualReturn: pct(s.result?.annualReturn, 1, true),
                    }),
                  )
                  .join(""),
                value9: state.method === "pe" ? (useContinuing ? "BPA continuado" : "BPA total reportado") : "FCF/acción",
                base: money(v.base),
                growth: pct(ass.growth, 0),
                horizon: ass.horizon,
                multiple: fmt(ass.multiple, 1),
                exitPrice: money(v.exitPrice),
                discount: pct(ass.discount, 0),
                fairValue16: money(v.fairValue),
              })
            : useContinuing ? template('composition-notice',{message:forecast.error}) : template("valuation-view-5"),
        ),
        panel7: panel(
          "BASE FINANCIERA",
          "03",
          financialTable(a),
          template("valuation-view-9", {
            value1: url(a.financials?.source_url || a.source_url),
          }),
          template("valuation-view-8", {
            value1: m.periodType || "—",
            period: dateLabel(m.period),
            filed: dateLabel(m.filed),
          }),
        ),
      })
    );
  }

  function financialTable(a) {
    const m = metrics(a),
      f = a.financials || {};
    return template("financial-table", {
      items: [
        ["Ingresos", compact(m.revenue), f.revenue],
        ["BPA diluido", money(m.eps), f.eps],
        ["Flujo de operación", compact(m.cfo), f.cfo],
        ["Inversión en activos · capex", compact(m.capex), f.capex],
        ["FCF simple", compact(m.fcf), f.cfo],
        ["Efectivo", compact(m.cash), f.cash],
        ["Patrimonio", compact(m.equity), f.equity],
        [
          "Acciones en circulación",
          finite(m.shares) ? fmt(m.shares / 1e9, 3) + " B" : "—",
          f.shares,
        ],
      ]
        .map(([label, value, record]) =>
          template("financial-table-2", {
            label: label,
            value: value,
            period_end: dateLabel(record?.period_end),
            value4: record?.method || "",
          }),
        )
        .join(""),
    });
  }

  function macroView() {
    const ten = data.macro.find((s) => s.id === "DGS10"),
      two = data.macro.find((s) => s.id === "DGS2");
    return (
      title(
        "MACRO / ESTADOS UNIDOS",
        "Tasas y datos macro",
        "Tasas, inflación, empleo y actividad. Cobertura y fechas por serie.",
      ) +
      `${ten && two ? template("macro-view-4", { value1: fmt((ten.value - two.value) * 100, 0), date: dateLabel(ten.date) }) : ""}` +
      panel(
        "SERIES DISPONIBLES",
        "01",
        template("macro-view-2", {
          items: data.macro
            .map((s) => {
              const showAnnualChange = s.id === "CPI" && finite(s.yoy);
              const previous = s.history.at(-2);
              const priorYear =
                previous &&
                s.history.find(
                  (row) =>
                    row.date ===
                    `${Number(previous.date.slice(0, 4)) - 1}${previous.date.slice(4)}`,
                );
              const previousAnnualChange =
                priorYear?.value > 0
                  ? previous.value / priorYear.value - 1
                  : null;
              return template("macro-view-3", {
                label: s.label,
                value2: showAnnualChange ? " · interanual" : "",
                value3: showAnnualChange
                  ? pct(s.yoy)
                  : fmt(s.value, 2) +
                    (s.unit === "%" ? "%" : s.unit ? " " + s.unit : ""),
                value4: showAnnualChange
                  ? pct(previousAnnualChange)
                  : fmt(s.previous, 2) +
                    (s.unit === "%" ? "%" : s.unit ? " " + s.unit : ""),
                date: dateLabel(s.date),
                sparkline: sparkline(
                  s.history.map((r) => r.value),
                  "var(--chart-accent)",
                  140,
                  30,
                ),
                source_url: url(s.source_url),
                value8:
                  s.provider ||
                  (s.id === "CPI" || s.id === "UNRATE" ? "BLS" : "Treasury"),
              });
            })
            .join(""),
        }),
        "",
        template("macro-view"),
      )
    );
  }

  function sourcesView() {
    const errors = data.errors || [];
    return template("sources-view", {
      price_as_of: dateLabel(data.price_as_of),
      length: data.assets.length,
      length3: data.assets.filter((a) => metrics(a).eps > 0).length,
      items: (data.sources || [])
        .map((s) =>
          template("sources-view-2", {
            name: s.name,
            kind: s.kind,
            data: s.data,
            url: url(s.url),
          }),
        )
        .join(""),
      generated_at: dateLabel(data.generated_at),
      value6: errors.length
        ? template("sources-view-3", {
            items: errors.map(esc).join(template("sources-view-4")),
          })
        : "",
      refreshIcon: icon("refresh"),
      uploadIcon: icon("upload"),
      panel:
        panel(
          "ESTADO DE FUENTES",
          "",
          template("provider-status", {
            items: (data.providers || [])
              .map((provider) =>
                template("provider-status-row", {
                  name: provider.name,
                  status:
                    {
                      ok: "ACTUALIZADA",
                      partial: "PARCIAL",
                      error: "ERROR",
                      not_configured: "CLAVE PENDIENTE",
                      historical_request: "CORTE HISTÓRICO",
                      private_required: "ENTORNO PRIVADO PENDIENTE",
                    }[provider.status] || "SIN ESTADO",
                  tone:
                    provider.status === "ok"
                      ? "positive"
                      : provider.status === "error" ||
                          provider.status === "partial"
                        ? "negative"
                        : "muted",
                  detail: provider.detail,
                  checked: dateLabel(provider.checked_at),
                }),
              )
              .join(""),
          }),
        ) +
        panel(
          "COBERTURA Y FECHAS",
          "",
          template("sources-view-5", {
            items: data.assets
              .map((a) => {
                const m = metrics(a);
                return template("sources-view-6", {
                  symbol: a.symbol,
                  price_date: dateLabel(a.price_date),
                  period: dateLabel(m.period),
                  filed: dateLabel(m.filed),
                  value5: m.pe ? "DISPONIBLE" : "—",
                  value6: finite(m.fcfYield) ? "DISPONIBLE" : "—",
                });
              })
              .join(""),
          }),
        ),
    });
  }

  function methodologyView() {
    return template("methodology-view");
  }

  function rulesView() {
    return template("rules-view", {
      items: [
        ["weightDrift", "DESVÍO DE PESO · PUNTOS PORCENTUALES"],
        ["valuationPremium", "PRIMA DEL PRECIO SOBRE VALOR MODELO · %"],
        ["earningsDrop", "CAÍDA DEL BPA VS REFERENCIA · %"],
        ["volatilityIncrease", "AUMENTO RELATIVO DE VOLATILIDAD · %"],
        ["drawdown", "PÉRDIDA DESDE REGISTRO · %"],
      ]
        .map(([key, label]) =>
          template("rules-view-2", {
            key: key,
            label: label,
            key3: key,
            key4: key,
            value5: fmt(state.rules[key] * 100, 0),
          }),
        )
        .join(""),
    });
  }
  function shell(page) {
    const nav = NAV.find((n) => n[0] === state.view) || NAV[0];
    return template("shell", {
      modelVersion: MODEL_VERSION,
      price_as_of: dateLabel(data.price_as_of),
      dataIcon: icon("data"),
      helpIcon: icon("help"),
      items: ["SPY", "QQQ", "IWM", "TLT", "GLD", "SHY"]
        .map((s) => {
          const a = asset(s);
          return a
            ? template("shell-2", {
                s: s,
                s2: s,
                price: fmt(a.price),
                changeTone: color(a.change),
                value5: a.change >= 0 ? "▴" : "▾",
                abs: pct(Math.abs(a.change), 2),
              })
            : "";
        })
        .join(""),
      toUpperCase: nav[1].toUpperCase(),
      busy:
        state.busy || state.compositionBusy || state.robustnessBusy
          ? 'aria-busy="true"'
          : "",
      value6: state.busy
        ? "CALCULANDO…"
        : "MOTOR " + MODEL_VERSION + " · CORTE " + dateLabel(data.price_as_of),
      value7: nav[2],
      items8: NAV.map(([id, label, key]) =>
        template("shell-3", {
          value1: state.view === id ? "active" : "",
          id: id,
          value3: state.view === id ? 'aria-current="page"' : "",
          key: key,
          label: label,
        }),
      ).join(""),
      value9: state.forecastError
        ? template("shell-4", { forecastError: state.forecastError })
        : data.errors?.length
          ? template("source-health", { count: data.errors.length })
          : "",
      page: page,
    });
  }
  function modal(heading, content, wide) {
    return template("modal", {
      value1: wide ? "modal-wide" : "",
      heading: heading,
      heading3: heading,
      closeIcon: icon("close"),
      content: content,
    });
  }
  function detail(symbol) {
    const a = asset(symbol);
    if (!a) return "";
    const m = metrics(a),
      s = assetStats(a),
      v = model(a);
    return (
      template("detail", {
        name: a.name,
        sector: a.sector,
        value3: a.type === "stock" ? "ACCIÓN" : "ETF",
        price: money(a.price),
        changeTone: color(a.change),
        change: pct(a.change, 2, true),
        items: [
          ["P/E " + (m.periodType || ""), m.pe ? fmt(m.pe, 1) + "x" : "—"],
          ["FCF YIELD", pct(m.fcfYield)],
          ["VOLATILIDAD ANUAL", pct(s?.volatility)],
          ["VS MODELO", pct(v?.upside, 1, true)],
        ]
          .map(([l, v]) => template("detail-2", { l: l, v: v }))
          .join(""),
        lineChart: lineChart(
          [
            {
              name: symbol,
              color: "var(--chart-primary)",
              values: a.history.slice(-252).map((r) => r.close),
            },
          ],
          a.history.slice(-252).map((r) => r.date),
          { height: 220, label: "Precio de " + symbol },
        ),
        price_date: dateLabel(a.price_date),
        value10: m.periodType || "—",
        period: dateLabel(m.period),
        filed: dateLabel(m.filed),
        value13: url(a.financials?.source_url || a.source_url),
        symbol: symbol,
        value15: state.positions.some((p) => p.symbol === symbol)
          ? "Quitar de cartera"
          : "+ Agregar a cartera",
        symbol16: symbol,
        arrowIcon: icon("arrow"),
      }) + analystConsensus(a)
    );
  }
  function analystConsensus(a) {
    const consensus = a.analyst_estimates;
    if (!consensus?.periods?.length) return "";
    return panel(
      "CONSENSO ANUAL · FMP",
      "",
      template("analyst-consensus", {
        observed: dateLabel(consensus.observed_at),
        source: url(consensus.source_url),
        items: consensus.periods
          .map((row) =>
            template("analyst-consensus-row", {
              period: dateLabel(row.period_end),
              eps: fmt(row.eps_mean, 2),
              epsRange: `${fmt(row.eps_low, 2)} / ${fmt(row.eps_high, 2)}`,
              revenue: finite(row.revenue_mean)
                ? fmt(row.revenue_mean / 1e9, 2) + " B"
                : "—",
              currency: row.currency || "sin moneda declarada",
              analysts: `${fmt(row.eps_analysts, 0)} / ${fmt(row.revenue_analysts, 0)}`,
              revision: pct(row.eps_revision_pct, 1, true),
              comparison: dateLabel(row.comparison_observed_at),
            }),
          )
          .join(""),
      }),
    );
  }
  function commandResults(matches, sections) {
    return (
      matches
        .map((a) =>
          template("command-results-3", {
            symbol: a.symbol,
            symbol2: a.symbol,
            name: a.name,
            price: money(a.price),
          }),
        )
        .join("") +
        sections
          .map((n) =>
            template("command-results-2", {
              value1: n[0],
              value2: n[1],
              value3: n[2],
            }),
          )
          .join("") || template("command-results")
    );
  }
  function shortcutsView() {
    return template("shortcuts-view", {
      items: NAV.map((n) =>
        template("shortcuts-view-2", { value1: n[2], value2: n[1] }),
      ).join(""),
    });
  }
  const extra = createDecisionViews(context);
  return {
    mandate: extra.mandate,
    portfolio: () => portfolio() + extra.decisionReport(),
    overview: () => overview() + extra.decisionReport() + extra.journalPanel(),
    forecasts: forecastsView,
    research,
    valuation: () => valuationView() + extra.researchPanel(),
    risk: () => riskView() + extra.factorPanel(),
    macro: macroView,
    renderTable,
    sourcesView,
    methodologyView,
    rulesView,
    shell,
    modal,
    detail,
    commandResults,
    shortcutsView,
  };
}
