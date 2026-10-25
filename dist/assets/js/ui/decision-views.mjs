import { template as t } from "./templates.mjs?v=0.6.0";
import { pct, fmt, money, dateLabel } from "./format.mjs?v=0.6.0";
import { finite, sum, normalizeWeights } from "../analytics.mjs?v=0.6.0";
import {
  DEFAULT_MANDATE,
  DEFAULT_EXECUTION,
  DEFAULT_RESEARCH,
  DEFAULT_REGIMES,
  currentAccount,
  informationDate,
} from "../policy.mjs?v=0.6.0";
import {
  fundamentalForecast,
  businessQuality,
  evaluateThesis,
  bondAssumptions,
} from "../research-model.mjs?v=0.6.0";
import { factorModel, factorAttribution } from "../factors.mjs?v=0.6.0";
import { evaluateJournal } from "../journal.mjs?v=0.6.0";
const objectives = {
  growth: "Crecimiento logarítmico",
  preservation: "Preservación · utilidad CRRA",
  target: "Capital objetivo · minimizar faltante",
};
const section = (title, body, note = "", meta = "") =>
  t("decision-section", { title, body, note, meta });
const grid = (fields) => t("decision-grid", { fields: fields.join("") });
const table = (headers, rows) =>
  t("decision-table", {
    headers: headers.map((value) => t("decision-th", { value })).join(""),
    rows: rows
      .map((row) =>
        t("decision-row", {
          cells: row.map((value) => t("decision-td", { value })).join(""),
        }),
      )
      .join(""),
  });
const stats = (items) =>
  t("decision-summary", {
    items: items
      .map(([label, value, detail = ""]) =>
        t("decision-stat", { label, value, detail }),
      )
      .join(""),
  });
const message = (message) => t("decision-message", { message });
function field(
  scope,
  key,
  label,
  value,
  {
    type = "number",
    scale = 1,
    min = "",
    max = "",
    step = "any",
    unit = "",
    symbol = "",
  } = {},
) {
  return t("decision-field", {
    id: `${scope}-${symbol}-${key}`,
    scope,
    key,
    label,
    value:
      value == null
        ? ""
        : type === "number"
          ? Number((value * scale).toFixed(6))
          : value,
    type,
    scale,
    min,
    max,
    step,
    unit,
    symbol,
    checked: type === "checkbox" && value ? "checked" : "",
  });
}
function select(scope, key, label, value, choices, symbol = "") {
  return t("decision-select", {
    id: `${scope}-${symbol}-${key}`,
    scope,
    key,
    label,
    symbol,
    options: choices
      .map(([v, l]) =>
        t("decision-option", {
          value: v,
          label: l,
          selected: value === v ? "selected" : "",
        }),
      )
      .join(""),
  });
}
function text(scope, key, label, value, symbol = "", rows = 3) {
  return t("decision-text", {
    id: `${scope}-${symbol}-${key}`,
    scope,
    key,
    label,
    value: value || "",
    symbol,
    rows,
  });
}
export function createDecisionViews({ state = {}, data, asset }) {
  const policy = { ...DEFAULT_MANDATE, ...state.mandate },
    costs = { ...DEFAULT_EXECUTION, ...state.execution };
  function mandateView() {
    const fields = [
      select(
        "mandate",
        "objective",
        "OBJETIVO",
        policy.objective,
        Object.entries(objectives),
      ),
      select(
        "mandate",
        "referenceCurrency",
        "MONEDA DE REFERENCIA",
        policy.referenceCurrency,
        [
          ["USD", "USD"],
          ["PEN", "PEN"],
          ["EUR", "EUR"],
        ],
      ),
      field(
        "mandate",
        "horizon",
        "HORIZONTE DE INVERSIÓN",
        state.settings?.horizon || policy.horizon,
        { min: 0.25, max: 5, step: 0.25, unit: "años" },
      ),
      field(
        "mandate",
        "riskAversion",
        "AVERSIÓN AL RIESGO · CRRA",
        policy.riskAversion,
        { min: 1, max: 20 },
      ),
      field(
        "mandate",
        "terminalTarget",
        "CAPITAL OBJETIVO FINAL",
        policy.terminalTarget,
        { min: 0, unit: policy.referenceCurrency },
      ),
      field(
        "mandate",
        "capitalFloor",
        "PISO DE CAPITAL EN EL CAMINO",
        policy.capitalFloor,
        { min: 0, unit: policy.referenceCurrency },
      ),
      field(
        "mandate",
        "maxDrawdown",
        "CAÍDA TOLERABLE DESDE MÁXIMOS",
        policy.maxDrawdown,
        { scale: 100, min: 1, max: 100, unit: "%" },
      ),
      field(
        "mandate",
        "maxDrawdownProbability",
        "PROB. MÁX. DE EXCEDER ESA CAÍDA",
        policy.maxDrawdownProbability,
        { scale: 100, min: 0, max: 100, unit: "%" },
      ),
      field("mandate", "minimumCash", "EFECTIVO MÍNIMO", policy.minimumCash, {
        scale: 100,
        min: 0,
        max: 100,
        unit: "%",
      }),
      field(
        "mandate",
        "monthlyWithdrawal",
        "RETIRO MENSUAL",
        policy.monthlyWithdrawal,
        { min: 0, unit: policy.referenceCurrency },
      ),
      field(
        "mandate",
        "maxLiquidityFailure",
        "PROB. MÁX. DE FALTA DE LIQUIDEZ / PISO",
        policy.maxLiquidityFailure,
        { scale: 100, min: 0, max: 100, unit: "%" },
      ),
      select("mandate", "benchmark", "ETF DE REFERENCIA", policy.benchmark, [
        ["SPY", "SPY · S&P 500"],
        ["QQQ", "QQQ · Nasdaq 100"],
        ["IWM", "IWM · Russell 2000"],
      ]),
    ];
    if (policy.referenceCurrency !== "USD")
      fields.push(
        field(
          "mandate",
          "fxSpot",
          "TIPO DE CAMBIO · MONEDA / USD",
          policy.fxSpot,
          { min: 0.00001 },
        ),
        field(
          "mandate",
          "fxAnnualChange",
          "CAMBIO ANUAL ESPERADO DEL TIPO DE CAMBIO",
          policy.fxAnnualChange,
          { scale: 100, min: -80, max: 100, unit: "%" },
        ),
        field(
          "mandate",
          "fxVolatility",
          "VOLATILIDAD CAMBIARIA ANUAL",
          policy.fxVolatility,
          { scale: 100, min: 0, max: 100, unit: "%" },
        ),
        field(
          "mandate",
          "fxMarketCorrelation",
          "CORRELACIÓN FX / MERCADO",
          policy.fxMarketCorrelation,
          { min: -1, max: 1 },
        ),
        field(
          "mandate",
          "fxConfirmed",
          "CONFIRMO LOS SUPUESTOS CAMBIARIOS",
          policy.fxConfirmed,
          { type: "checkbox" },
        ),
      );
    const costFields = [
      ["commissionFixed", "COMISIÓN POR ORDEN", 1, "USD"],
      ["commissionBps", "COMISIÓN VARIABLE", 1, "pb"],
      ["spreadBps", "SPREAD COMPLETO", 1, "pb"],
      ["slippageBps", "DESLIZAMIENTO POR ORDEN", 1, "pb"],
      [
        "capitalGainsTax",
        "IMPUESTO SUPUESTO SOBRE GANANCIA REALIZADA",
        100,
        "%",
      ],
      ["maxTurnover", "ROTACIÓN MÁXIMA AL REBALANCEAR", 100, "%"],
      ["minTrade", "ORDEN MÍNIMA", 1, "USD"],
      ["minBenefit", "MEJORA EQUIVALENTE MÍNIMA PARA OPERAR", 1, "USD"],
      ["benefitCostRatio", "MEJORA MÍNIMA / COSTO", 1, "veces"],
    ].map(([key, label, scale, unit]) =>
      field("execution", key, label, costs[key], { min: 0, scale, unit }),
    );
    const account = state.account || { enabled: false, cash: 0, positions: [] };
    const accountBody = t("decision-account", {
      fields: [
        field(
          "account",
          "enabled",
          "USAR CANTIDADES REALES INGRESADAS",
          account.enabled,
          { type: "checkbox" },
        ),
        field("account", "cash", "EFECTIVO ACTUAL EN USD", account.cash, {
          min: 0,
        }),
      ].join(""),
      options: data.assets
        .filter(
          (a) =>
            a.symbol !== "CASH" &&
            !account.positions.some((p) => p.symbol === a.symbol),
        )
        .map((a) =>
          t("decision-option", {
            value: a.symbol,
            label: a.symbol,
            selected: "",
          }),
        )
        .join(""),
      table: t("decision-table", {
        headers: ["ACTIVO", "CANTIDAD", "COSTO POR UNIDAD · USD", ""]
          .map((value) => t("decision-th", { value }))
          .join(""),
        rows: account.positions
          .map((p) =>
            t("decision-holding", {
              symbol: p.symbol,
              quantity: field("holding", "quantity", "CANTIDAD", p.quantity, {
                min: 0,
                symbol: p.symbol,
              }),
              basis: field(
                "holding",
                "costBasis",
                "COSTO POR UNIDAD",
                p.costBasis,
                { min: 0, symbol: p.symbol },
              ),
            }),
          )
          .join(""),
      }),
    });
    const scenarioFields = (state.macroRegimes || DEFAULT_REGIMES)
      .map((row) =>
        section(
          row.label,
          grid(
            [
              ["probability", "PROBABILIDAD", 100, "%"],
              [
                "earningsShift",
                "CAMBIO DE CRECIMIENTO DE BENEFICIOS / AÑO",
                100,
                "pp",
              ],
              ["multipleShift", "CAMBIO DEL MÚLTIPLO AL HORIZONTE", 100, "%"],
              ["rateShift", "CAMBIO DE TASA AL HORIZONTE", 100, "pp"],
              ["rateJumpBps", "SHOCK DE TASA EN UN EVENTO SISTÉMICO", 1, "pb"],
            ].map(([key, label, scale, unit]) =>
              field("regime", key, label, row[key], {
                scale,
                unit,
                symbol: row.id,
              }),
            ),
          ),
        ),
      )
      .join("");
    return (
      t("decision-heading") +
      section(
        "OBJETIVO Y RESTRICCIONES",
        grid(fields) +
          text(
            "mandate",
            "withdrawalsText",
            "RETIROS ADICIONALES · UNA LÍNEA POR FECHA: AAAA-MM-DD, IMPORTE",
            policy.withdrawals.map((r) => `${r.date}, ${r.amount}`).join("\n"),
          ),
        "El piso se evalúa sobre capital disponible después de los retiros; el drawdown se mide sobre un índice ajustado por flujos. Los retiros se prefundan en efectivo.",
      ) +
      section(
        "CUENTA ACTUAL",
        accountBody,
        "La cuenta ingresada sirve como punto de partida para calcular órdenes. Si está desactivada se usa la referencia registrada; sin registro, el capital inicial queda en efectivo. Registrar una propuesta no confirma una operación en el broker.",
      ) +
      section(
        "COSTOS Y ZONA DE MANTENIMIENTO",
        grid(costFields),
        "Se aplica medio spread por lado. Impuesto 0 significa exclusión asumida, no una determinación tributaria. Ventas gravadas sin costo de compra impiden una propuesta completa. La búsqueda no incluye lotes fiscales.",
      ) +
      section(
        "INCERTIDUMBRE FUNDAMENTAL",
        grid([
          field(
            "setting",
            "fundamentalMarketShare",
            "VARIANZA DE INCERTIDUMBRE: MERCADO",
            state.settings?.fundamentalMarketShare ?? 0.35,
            { scale: 100, min: 0, max: 100, unit: "%" },
          ),
          field(
            "setting",
            "fundamentalSectorShare",
            "VARIANZA DE INCERTIDUMBRE: SECTOR",
            state.settings?.fundamentalSectorShare ?? 0.3,
            { scale: 100, min: 0, max: 100, unit: "%" },
          ),
        ]),
        "El resto corresponde a empresa. Son participaciones de una cópula normal; no una calibración estadística de los retornos esperados.",
      ) +
      section(
        "ESCENARIOS MACRO CONDICIONALES",
        scenarioFields,
        `Probabilidades supuestas, editables: suma ${pct(sum((state.macroRegimes || DEFAULT_REGIMES).map((r) => r.probability)), 0)}. Deben sumar 100%. Beneficios y múltiplos afectan renta variable; tasas y duración afectan bonos. La covarianza histórica y estos escenarios se superponen como incertidumbre del modelo.`,
      ) +
      t("decision-actions")
    );
  }
  function researchPanel() {
    const a = asset(state.selected) || data.assets[0],
      r = { ...DEFAULT_RESEARCH, ...state.research?.[a.symbol] },
      asOf = informationDate(data);
    if (a.type !== "stock") {
      const own = state.assetAssumptions?.[a.symbol] || {},
        bond = bondAssumptions(a, {
          assetAssumptions: state.assetAssumptions,
          informationAsOf: asOf,
        });
      const fields = bond
        ? [
            field(
              "assetAssumptions",
              "yieldToMaturity",
              "TIR BRUTA ANUAL",
              own.yieldToMaturity ?? bond.yieldToMaturity,
              { scale: 100, min: -5, max: 100, unit: "%", symbol: a.symbol },
            ),
            field(
              "assetAssumptions",
              "duration",
              "DURACIÓN EFECTIVA",
              own.duration ?? bond.duration,
              { min: 0, max: 40, unit: "años", symbol: a.symbol },
            ),
            field(
              "assetAssumptions",
              "expenseRatio",
              "GASTOS ANUALES",
              own.expenseRatio ?? bond.expenseRatio,
              { scale: 100, min: 0, max: 10, unit: "%", symbol: a.symbol },
            ),
          ]
        : [
            field(
              "assetAssumptions",
              "expectedReturn",
              "RETORNO ANUAL ASUMIDO",
              own.expectedReturn ?? 0.06,
              { scale: 100, min: -80, max: 200, unit: "%", symbol: a.symbol },
            ),
            field(
              "assetAssumptions",
              "uncertainty",
              "SEMIRANGO DE INCERTIDUMBRE",
              own.uncertainty ?? 0.06,
              { scale: 100, min: 0, max: 100, unit: "pp", symbol: a.symbol },
            ),
          ];
      return section(
        "SUPUESTOS DEL ACTIVO",
        grid(fields),
        bond
          ? `${bond.source} · perfil ${dateLabel(bond.date)}. Carry aproximado = TIR bruta menos gastos; efecto local de tasas = −duración × cambio de tasa. No utiliza Treasury 3M como retorno de SHY.`
          : "ETF: retorno futuro asumido, no extrapolado de su rentabilidad histórica. Efectivo CASH: 0% de remuneración.",
      );
    }
    const f = fundamentalForecast(a, state.overrides?.[a.symbol] || {}, r, {
        asOf,
        priceAsOf: data.price_as_of,
      }),
      q = businessQuality(a, asOf),
      thesis = evaluateThesis(a, r, asOf);
    const fields = [
      select(
        "research",
        "basis",
        "BASE DE LA PREVISIÓN",
        r.basis,
        [
          ["own", "BPA propio"],
          ["drivers", "Ventas / margen / dilución"],
          ["consensus", "Consenso comparable"],
          ["blend", "50% propia / 50% consenso"],
        ],
        a.symbol,
      ),
      field(
        "research",
        "confidence",
        "CONFIANZA SUBJETIVA ANTES DE COBERTURA",
        r.confidence,
        { scale: 100, min: 0, max: 100, unit: "%", symbol: a.symbol },
      ),
      field(
        "research",
        "priorReturn",
        "RETORNO PREVIO AL QUE SE CONTRAE",
        r.priorReturn,
        { scale: 100, min: -80, max: 200, unit: "%", symbol: a.symbol },
      ),
      field(
        "research",
        "revenueGrowth",
        "CRECIMIENTO ANUAL DE VENTAS",
        r.revenueGrowth,
        { scale: 100, min: -80, max: 200, unit: "%", symbol: a.symbol },
      ),
      field(
        "research",
        "targetMargin",
        "MARGEN NETO AL HORIZONTE",
        r.targetMargin,
        { scale: 100, min: 0.01, max: 100, unit: "%", symbol: a.symbol },
      ),
      field(
        "research",
        "annualDilution",
        "DILUCIÓN ANUAL ASUMIDA",
        r.annualDilution,
        { scale: 100, min: -50, max: 100, unit: "%", symbol: a.symbol },
      ),
      field(
        "research",
        "consensusComparable",
        "CONFIRMO BASE CONTABLE COMPARABLE",
        r.consensusComparable,
        { type: "checkbox", symbol: a.symbol },
      ),
      field(
        "research",
        "comparableEPS",
        "BPA ACTUAL EN LA BASE DEL CONSENSO",
        r.comparableEPS,
        { min: 0.00001, symbol: a.symbol },
      ),
      select(
        "research",
        "consensusBasis",
        "BASE DEL CONSENSO CONFIRMADA",
        r.consensusBasis || "",
        [
          ["", "Sin confirmar"],
          ["non_gaap", "No GAAP"],
          ["gaap", "GAAP"],
        ],
        a.symbol,
      ),
      select(
        "research",
        "consensusCurrency",
        "MONEDA DE REPORTE CONFIRMADA",
        r.consensusCurrency || "",
        [
          ["", "Sin confirmar"],
          ["USD", "USD"],
        ],
        a.symbol,
      ),
    ];
    const comparison = stats([
      ["BPA PROPIO AL HORIZONTE", fmt(f.ownEPS), dateLabel(f.targetDate)],
      [
        "BPA DE CONSENSO",
        fmt(f.consensus?.eps_mean),
        f.consensus?.error || f.consensus?.basis || "",
      ],
      [
        "CRECIMIENTO IMPLÍCITO EN PRECIO",
        pct(f.impliedGrowth),
        "Condicional al múltiplo y descuento elegidos",
      ],
      [
        "RETORNO PROPIO ANTES DEL AJUSTE",
        pct(f.ownAnnualReturn),
        "Modelo de valoración",
      ],
      [
        "MODO AJUSTADO / AÑO",
        pct(f.central),
        `Peso efectivo de la previsión: ${pct(f.confidence)}`,
      ],
    ]);
    const quality = table(
      ["OBSERVACIÓN", "VALOR"],
      [
        ["Margen neto comparable", pct(q.netMargin)],
        ["Margen operativo", pct(q.operatingMargin)],
        [
          "Mediana de margen operativo TTM disponible",
          pct(q.normalizedOperatingMargin),
        ],
        [
          "CFO / beneficio neto",
          finite(q.cashConversion) ? fmt(q.cashConversion) + "x" : "—",
        ],
        ["Capex / CFO", pct(q.reinvestment)],
        [
          "Deuda neta / FCF",
          finite(q.netDebtToFCF) ? fmt(q.netDebtToFCF) + "x" : "—",
        ],
        ["Dilución anual ajustada por splits", pct(q.dilution)],
        ["SBC / ventas", pct(q.sbcRevenue)],
        ["Cobertura de evidencia", pct(q.coverage)],
        [
          "Antigüedad desde presentación",
          finite(q.ageDays) ? fmt(q.ageDays, 0) + " días" : "—",
        ],
      ],
    );
    const thresholds = [
      ["marginFloor", "MARGEN OPERATIVO MÍNIMO", 100, "%"],
      ["leverageCeiling", "DEUDA NETA / FCF MÁXIMA", 1, "x"],
      ["epsFloor", "BPA MÍNIMO", 1, "USD"],
      ["cashConversionFloor", "CFO / BENEFICIO MÍNIMO", 1, "x"],
      ["maxDilution", "DILUCIÓN ANUAL MÁXIMA", 100, "%"],
    ].map(([key, label, scale, unit]) =>
      field("research", key, label, r[key], { scale, unit, symbol: a.symbol }),
    );
    return (
      section(
        "PREVISIÓN Y EXPECTATIVAS DEL PRECIO",
        grid(fields) +
          comparison +
          message(f.error || (f.warnings || []).join(" · ")),
        "La confianza se ajusta por cobertura, antigüedad y contradicciones de tesis; no equivale a precisión observada. El consenso es anual, puede interpolarse entre ejercicios y requiere base contable comparable.",
      ) +
      section(
        "CALIDAD Y SOSTENIBILIDAD",
        quality +
          table(
            [
              "VENCIMIENTO REPORTADO",
              "IMPORTE USD",
              "FECHA DE BALANCE / PRESENTACIÓN",
            ],
            Object.entries(a.financials || {})
              .filter(
                ([key, row]) =>
                  key.startsWith("debt_due_") && row?.filed <= asOf,
              )
              .map(([key, row]) => [
                key === "debt_due_6"
                  ? "Después del año 5"
                  : key === "debt_due_1"
                    ? "Próximos 12 meses"
                    : key.replace("debt_due_", "Año "),
                money(row.value),
                `${dateLabel(row.period_end)} / ${dateLabel(row.filed)}`,
              ]),
          ),
        "Deuda: sólo saldos disponibles, sin calendario completo de vencimientos. Dilución sólo si las acciones históricas tienen ajuste de splits documentado. Márgenes normalizados son supuestos propios.",
      ) +
      section(
        "TESIS Y CONDICIONES DE REVISIÓN",
        text(
          "research",
          "thesis",
          "RAZÓN PARA TENER LA POSICIÓN",
          r.thesis,
          a.symbol,
        ) +
          text(
            "research",
            "invalidation",
            "EVIDENCIA QUE INVALIDARÍA LA TESIS",
            r.invalidation,
            a.symbol,
          ) +
          text(
            "research",
            "catalyst",
            "CATALIZADORES / PRÓXIMA EVIDENCIA",
            r.catalyst,
            a.symbol,
          ) +
          grid([
            ...thresholds,
            field("research", "reviewDate", "PRÓXIMA REVISIÓN", r.reviewDate, {
              type: "date",
              symbol: a.symbol,
            }),
          ]) +
          table(
            ["CONDICIÓN", "OBSERVADO", "UMBRAL", "ESTADO", "PRESENTADO"],
            thesis.observations.map((o) => [
              o.label,
              fmt(o.value, 3),
              fmt(o.threshold, 3),
              o.status === "contradicted"
                ? "Contradice"
                : o.status === "missing"
                  ? "Sin dato"
                  : "Cumple",
              dateLabel(o.filed),
            ]),
          ),
        "Los umbrales estructurados generan revisiones; el texto de la tesis se conserva como investigación propia. Una nueva presentación requiere actualizar las hipótesis.",
      )
    );
  }
  function decisionReport() {
    const p = state.proposal;
    if (!p) return "";
    const alternatives = p.alternatives || {},
      plan = p.trade_plan;
    return section(
      "DECISIÓN DESDE LA CARTERA ACTUAL",
      stats([
        [
          "RESULTADO",
          p.status === "hold"
            ? "Mantener"
            : p.status === "proposed"
              ? "Cambiar"
              : "Sin propuesta viable",
          p.reason || objectives[p.objective],
        ],
        [
          "COSTO INICIAL",
          money(plan?.total),
          `Rotación ${pct(plan?.turnover)}`,
        ],
        [
          "RIESGO DE CAÍDA",
          pct(p.metrics?.drawdownProbability),
          "Prob. de exceder el drawdown del mandato",
        ],
        [
          "FALTA DE LIQUIDEZ",
          pct(p.metrics?.liquidityFailureProbability),
          "Trayectorias sin efectivo para los retiros",
        ],
        [
          "CAPITAL FINAL MEDIANO",
          finite(p.metrics?.medianTerminalWealth)
            ? fmt(p.metrics.medianTerminalWealth, 0) +
              " " +
              p.mandate?.referenceCurrency
            : "—",
          "Después de retiros",
        ],
        ["MEJORA EQUIVALENTE", money(p.benefit), `Umbral ${money(p.hurdle)}`],
        [
          "TIEMPO MÁXIMO BAJO MÁXIMOS · MEDIANA",
          finite(p.metrics?.medianUnderwaterYears)
            ? fmt(p.metrics.medianUnderwaterYears * 12, 1) + " meses"
            : "—",
          "Medido semanalmente; puede quedar abierto al final",
        ],
        [
          "SIN RECUPERAR MÁXIMOS AL FINAL",
          pct(p.metrics?.underwaterAtHorizonProbability),
          "Proporción de trayectorias",
        ],
        [
          "PROBABILIDAD DE CUMPLIR LA META",
          p.mandate?.terminalTarget > 0
            ? pct(p.metrics?.goalProbability)
            : "Sin meta",
          "Capital final después de retiros",
        ],
      ]) +
        table(
          [
            "ALTERNATIVA",
            "RETORNO MEDIANO",
            "CVAR 95%",
            "PROB. CAÍDA",
            "VIABLE",
          ],
          [
            [
              "Mantener",
              pct(alternatives.hold?.metrics.medianReturn),
              pct(alternatives.hold?.metrics.cvar95),
              pct(alternatives.hold?.metrics.drawdownProbability),
              alternatives.hold?.feasible ? "Sí" : "No",
            ],
            [
              "ETF / SHY / efectivo",
              pct(alternatives.passive?.metrics.medianReturn),
              pct(alternatives.passive?.metrics.cvar95),
              pct(alternatives.passive?.metrics.drawdownProbability),
              alternatives.passive
                ? alternatives.passive.feasible
                  ? "Sí"
                  : "No"
                : "Sin candidata",
            ],
          ],
        ) +
        (plan
          ? table(
              ["ACTIVO", "LADO", "IMPORTE USD", "COSTO USD"],
              plan.rows.map((r) => [
                r.symbol,
                r.side === "buy" ? "Comprar" : "Vender",
                fmt(r.notional),
                fmt(r.cost),
              ]),
            )
          : "") +
        (p.signals
          ? table(
              [
                "ACTIVO",
                "PESO",
                "CONFIANZA EFECTIVA",
                "APORTE AL RIESGO",
                "RIESGO MARGINAL",
              ],
              p.signals.map((s) => [
                s.symbol,
                pct(s.weight),
                pct(s.confidence),
                pct(s.risk?.fraction),
                pct(s.risk?.marginal),
              ]),
            )
          : "") +
        (p.sensitivity
          ? table(
              [
                "SENSIBILIDAD",
                "CAMBIO TOTAL DE PESOS",
                "MAYOR CAMBIO",
                "VIABLE",
              ],
              p.sensitivity.map((s) => [
                s.label,
                pct(s.turnover),
                s.largestChange || "—",
                s.feasible ? "Sí" : "No",
              ]),
            )
          : "") +
        t("decision-actions"),
      `Cuenta: ${p.account_source || "capital inicial"}. Alternativas con los mismos escenarios, objetivos, costos y límites; sectores sólo de acciones directas. La segunda simulación semanal comprueba la propuesta. ${(p.notes || []).join(" ")}`,
    );
  }
  function journalPanel() {
    const result = evaluateJournal(state.journal || [], data),
      status = {
        immature: "Pendiente de vencimiento",
        retrospective: "Retrospectivo · excluido",
        missing: "Sin datos comparables",
        missing_fx: "Falta historia FX",
        unreconciled_flows: "Retiros sin realización conciliada",
        scored: "Evaluado",
      };
    return section(
      "VALIDACIÓN PROSPECTIVA",
      stats([
        ["ORÍGENES REGISTRADOS", String(result.rows.length)],
        ["PRONÓSTICOS VENCIDOS EVALUADOS", String(result.count)],
        [
          "BRIER · PROBABILIDAD DE PÉRDIDA",
          fmt(result.brier, 3),
          "Menor es mejor",
        ],
        [
          "COBERTURA P05–P95",
          pct(result.coverage),
          "Objetivo nominal 90%; sin calibración demostrada",
        ],
        ["ERROR ABSOLUTO MEDIO", pct(result.mae)],
      ]) +
        table(
          [
            "ORIGEN",
            "VENCIMIENTO",
            "PÉRDIDA PREVISTA",
            "RETORNO OBSERVADO",
            "ESTADO",
          ],
          result.rows
            .slice(-12)
            .reverse()
            .map((row) => [
              dateLabel(row.origin.price_as_of),
              dateLabel(row.target_date),
              pct(row.prediction.lossProbability),
              pct(row.realized),
              status[row.status],
            ]),
        ),
      result.note +
        " Registro persistente en este navegador; se exporta con la cartera. No se descartan orígenes por la llegada de otro corte. Las proyecciones se registran al calcular con la página abierta. Los casos con retiros o sin historia FX quedan sin puntuar.",
    );
  }
  function factorPanel() {
    const factors = factorModel(
        data.assets,
        state.positions || [],
        data.price_as_of,
      ),
      attribution = state.baseline
        ? factorAttribution(data, state.baseline)
        : null;
    return (
      section(
        "EXPOSICIONES A MERCADO Y SECTOR",
        table(
          [
            "ACTIVO",
            "BETA MERCADO",
            "BETA SECTOR RESIDUAL",
            "R²",
            "VOL. RESIDUAL",
          ],
          factors.rows.map((r) => [
            r.symbol,
            fmt(r.betaMarket),
            r.sector ? fmt(r.betaSector) : "Sin proxy",
            pct(r.rSquared),
            pct(r.residualVolatility),
          ]),
        ) +
          table(
            ["CORRELACIÓN RESIDUAL", ...factors.rows.map((r) => r.symbol)],
            factors.rows.map((r, i) => [
              r.symbol,
              ...factors.residualCorrelation[i].map((v) => fmt(v, 2)),
            ]),
          ),
        factors.note,
      ) +
      (attribution
        ? section(
            "ATRIBUCIÓN DESDE EL REGISTRO",
            stats([
              ["MERCADO", pct(attribution.market)],
              ["SECTOR", pct(attribution.sector)],
              ["NO EXPLICADO", pct(attribution.unexplained)],
              ["TOTAL", pct(attribution.total)],
            ]),
            attribution.note,
          )
        : "")
    );
  }
  return {
    mandate: mandateView,
    researchPanel,
    decisionReport,
    journalPanel,
    factorPanel,
  };
}
