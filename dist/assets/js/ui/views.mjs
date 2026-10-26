import {
  finite,
  sum,
  normalizeWeights,
  metrics,
  scenarios,
} from "../analytics.mjs?v=0.8.0";
import {
  sparkline,
  portfolioChart,
  lineChart,
  heatmap,
  scatter,
  forecastCone,
  histogram,
} from "../charts.mjs?v=0.8.0";
import {
  esc,
  url,
  fmt,
  pct,
  money,
  compact,
  color,
  dateLabel,
} from "./format.mjs?v=0.8.0";
import { template } from "./templates.mjs?v=0.8.0";
import { DEFAULT_COMPOSITION_RULES } from "../composer.mjs?v=0.8.0";
import { factorModel } from "../factors.mjs?v=0.8.0";
import { MODEL_VERSION } from "../policy.mjs?v=0.8.0";

import { createDecisionViews } from "./decision-views.mjs?v=0.8.0";

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
          : `${f?.volatility?.accepted > 0
              ? "Volatilidad condicional GJR-t"
              : state.settings.model === "merton"
                ? "Difusión con saltos genéricos"
                : "Difusión GBM/EWMA"} · buy & hold · base 100`,
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
        value1: s.model === "merton" ? "selected" : "",
        value2: s.model === "gbm" ? "selected" : "",
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
        value12:
          s.model === "merton"
            ? template("forecast-controls-4", {
                jumpIntensity: s.jumpIntensity,
                value2: fmt(s.jumpMean * 100, 0),
                jumpVol: pct(s.jumpVol, 0),
              })
            : "",
        value13: state.forecast ? pct(state.forecast.coverage, 0) : "—",
        refreshIcon: icon("refresh"),
        value15: state.busy ? "Calculando…" : "Recalcular simulación",
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
        "GBM y difusión con saltos. Supuestos de retorno y covarianza EWMA.",
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
          composeDisabled: state.compositionBusy ? "disabled" : "",
          referenceDisabled: state.compositionBusy ? "disabled" : "",
          applyDisabled: state.proposal?.status === "proposed" &&
            state.proposal.model_version === MODEL_VERSION &&
            state.proposal.as_of === data.price_as_of &&
            state.proposal.snapshot_generated_at === data.generated_at &&
            !state.proposal.modified ? "" : "disabled",
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
      compositionReport() +
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
      ["maxPosition", "MÁX. POR ACCIÓN", 5, 50, 5, 100, "%"],
      ["maxFund", "MÁX. POR ETF DIVERSIFICADO", 5, 100, 5, 100, "%"],
      ["maxSector", "MÁX. SECTOR DIRECTO", 10, 100, 5, 100, "%"],
      ["reserveCap", "MÁX. RESERVA SHY", 5, 100, 5, 100, "%"],
      ["maxPositions", "MÁX. POSICIONES", 2, 12, 1, 1, ""],
      ["maxCorrelation", "CORRELACIÓN MÁXIMA", 0.1, 1, 0.05, 1, "ρ"],
      ["cvarBudget", "CVAR 95% MÁX. · HORIZONTE", 1, 80, 1, 100, "%"],
      ["maxLossProbability", "PROB. PÉRDIDA MÁX.", 1, 100, 1, 100, "%"],
    ];
    return template("composition-controls", {
      months: state.settings.horizon * 12,
      budget: pct(rules.cvarBudget, 0),
      volatilityHybridSelected: !["ewma", "legacy"].includes(state.settings.volatilityMode) ? "selected" : "",
      volatilityEWMASelected: state.settings.volatilityMode === "ewma" ? "selected" : "",
      volatilityLegacySelected: state.settings.volatilityMode === "legacy" ? "selected" : "",
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
        p.snapshot_generated_at !== data.generated_at)
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
        `Límite ${pct(p.rules.cvarBudget, 0)} · Colas conjuntas gaussianas sin validación externa`,
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
        ? "CONFIGURACIÓN BASE · Capital USD 100.000 · cuenta vacía · 4 escenarios originales · semilla " + p.settings.seed + ". No se modificaron tus posiciones ni supuestos."
        : "CONFIGURACIÓN DE TU SESIÓN · " + p.account_source +
          " · semilla " + p.settings.seed + ". Esta propuesta no se aplica automáticamente.",
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
            source: s.filed
              ? `BPA ${money(s.eps)} · publicado ${dateLabel(s.filed)}`
              : s.source,
          }),
        )
        .join(""),
      evaluated: p.search.evaluated,
      feasible: p.search.feasible,
      searchPaths: p.search.paths,
      published: p.selection?.published ?? data.assets.length,
      eligible: p.selection?.eligible ?? "—",
      simulated: p.selection?.simulated ?? "—",
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
          ". Un aporte negativo en la cola puede representar cobertura, no riesgo nulo."
        : (p.diagnostics?.attribution?.reason || "No se calculó una atribución compatible."),
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
          `SHY: retorno supuesto ${pct(a.shyAnnualAnchor,1)} (${a.shyAnchorSource}); volatilidad condicional anual ${pct(a.shyAnnualVolatility,1)}. Tope editable ${pct(a.shyMaxAllowed,0)}; peso elegido ${pct(a.actualShyWeight,0)}. Una tasa relativamente elevada y bajo riesgo pueden dominar al no existir primas accionarias suficientemente respaldadas.`;
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
        ? "residual SPY bull/bear + sector"
        : "total (historia insuficiente)",
      dependenceObservations: p.diagnostics?.dependence?.observations ?? 0,
      volatilityUsed: p.diagnostics?.volatility?.mode || "EWMA",
      volatilityAccepted: p.diagnostics?.volatility?.accepted ?? 0,
      volatilityFallback: p.diagnostics?.volatility?.fallback ?? 0,
      volatilityNote: (p.diagnostics?.volatility?.reason || "Sin calibración disponible") +
        " · Covarianza: " + (p.diagnostics?.volatility?.factorMethod || "total"),
      stochasticTail: p.diagnostics?.volatility?.accepted > 0
        ? "Innovaciones gaussianas en riesgo conjunto; GJR-t solo estimación"
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
          ? `Media residual ${fmt(residualAverage, 2)} · ${factor.observations} sesiones. Betas SPY por régimen determinado con 63 retornos anteriores, más proxy sectorial. La matriz total anterior sigue alimentando Monte Carlo y CVaR. No implica independencia causal.`
          : "Con datos insuficientes, se conserva explícitamente la correlación total."
      ) +
      panel(
        "VOLATILIDAD CONDICIONAL · GJR / EWMA",
        "07",
        template("composition-notice", {
          message: data.volatility
            ? `Corte ${data.volatility.as_of}. Aceptados ${data.volatility.summary?.eligible ?? 0} de ${data.volatility.summary?.evaluated ?? 0} activos. ${(a?.weights || []).map((p) =>
                `${p.symbol}: ${data.volatility.instruments?.[p.symbol]?.status === "accepted" ? "GJR verificado" : "EWMA / investigación"}`).join(" · ")}. Los errores no se descartan por coincidir con noticias.`
            : "No existe un corte de volatilidad compatible. Simulación con EWMA y los supuestos previos, sin atribución automática de noticias.",
        }),
        "",
        "QLIKE walk-forward frente a EWMA; Student-t solo para calibraciones aceptadas. La elección de la distribución y la cobertura del CVaR requieren validación continua."
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
      v = model(a, state.method),
      ass = { ...a.assumptions, ...override(a.symbol) },
      sc = scenarios(a, override(a.symbol), state.method);
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
          }),
        ),
        panel6: panel(
          "VALOR PRESENTE DEL MODELO",
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
                max: Math.max(
                  8,
                  Math.min(92, (a.price / Math.max(a.price, v.fairValue)) * 75),
                ),
                max7: Math.max(
                  8,
                  Math.min(
                    92,
                    (v.fairValue / Math.max(a.price, v.fairValue)) * 75,
                  ),
                ),
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
                value9: state.method === "pe" ? "BPA" : "FCF/acción",
                base: money(v.base),
                growth: pct(ass.growth, 0),
                horizon: ass.horizon,
                multiple: fmt(ass.multiple, 0),
                exitPrice: money(v.exitPrice),
                discount: pct(ass.discount, 0),
                fairValue16: money(v.fairValue),
              })
            : template("valuation-view-5"),
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
