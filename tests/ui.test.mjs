import {timestampLabel} from '../dist/assets/js/ui/format.mjs?v=0.33.1';
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createTemplateRenderer,
  loadTemplates,
} from "../dist/assets/js/ui/templates.mjs?v=0.33.1";
import { createViews, NAV } from "../dist/assets/js/ui/views.mjs?v=0.33.1";
import {
  valuation,
  portfolioAnalysis,
  metrics,
} from "../dist/assets/js/analytics.mjs?v=0.33.1";
import {
  simulateForecast,
  validateRiskBands,
} from "../dist/assets/js/forecast.mjs?v=0.33.1";
import {
  registerPortfolio,
  reviewPortfolio,
  DEFAULT_RULES,
} from "../dist/assets/js/monitor.mjs?v=0.33.1";

test("external templates escape untrusted text and attributes without interpreting inserted placeholders", () => {
  const render = createTemplateRenderer([
    '<template id="sample">\n<button title="{{text}}">{{text}}{{{fragment}}}</button>\n</template>',
  ]);
  const html = render("sample", {
    text: '\"><img src=x onerror=alert(1)>{{text}}',
    fragment: "<b>Contenido controlado</b>",
  });
  assert.ok(html.includes("&lt;img"));
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("<b>Contenido controlado</b>"));
  assert.ok(html.includes("{{text}}"));
});

test("template configuration rejects missing bindings and duplicate template names", () => {
  const source = '<template id="sample">\n{{text}}\n</template>';
  assert.throws(() => createTemplateRenderer([source, source]), /duplicada/);
  const render = createTemplateRenderer([source]);
  assert.throws(() => render("sample"), /Falta/);
  assert.throws(() => render("missing"), /no disponible/);
});

import { MODEL_VERSION } from "../dist/assets/js/policy.mjs?v=0.33.1";

await loadTemplates(async (url) => ({
  ok: true,
  text: () => readFile(url, "utf8"),
}));
const data = JSON.parse(
  await readFile(new URL("../dist/data/market.json", import.meta.url), "utf8"),
);

test("an incomplete incumbent comparison renders unavailable metrics without certifying safety", async () => {
  const { createDecisionViews } = await import("../dist/assets/js/ui/decision-views.mjs?v=0.33.1");
  const views = createDecisionViews({ data, asset: () => null, state: {
    proposal: { status: "hold", reason: "Mantener: faltan anclas para GLD.", metrics: null,
      alternatives: { hold: { metrics: null, feasible: null } },
      diagnostics: { robustDecision: { status: "incomplete", models: [],
        minimumLowerGain: null, hurdle: null } },
      trade_plan: { total: 0, turnover: 0, rows: [] } },
  } });
  const html = views.decisionReport();
  assert.match(html, /Mantener: faltan anclas para GLD/);
  assert.match(html, /Sin evaluar/);
  assert.doesNotMatch(html, /NaN|undefined/);
});

test("footer version is rendered from the actual engine, never hardcoded", () => {
  const views = createViews({
    state: { view: "portfolio", busy: false, forecastError: null },
    data,
    asset: () => null,
  });
  const html = views.shell("<h1>Revisión</h1>");
  assert.ok(html.includes("v" + MODEL_VERSION + " &nbsp;"), "Footer must show actual model version");
  assert.ok(html.includes("MULTIACTIVO"));
  assert.ok(!html.includes("v0.6.0"));
  assert.ok(!html.includes("{{modelVersion}}"));
});

test("a positive economic gain does not hide a rejected portfolio risk limit", async () => {
  const { createDecisionViews } = await import("../dist/assets/js/ui/decision-views.mjs?v=0.33.1");
  const views = createDecisionViews({ data, asset: () => null, state: {
    proposal: { status: "hold", reason: "Mantener: transición descartada en Combinado (CVaR).",
      metrics: {}, diagnostics: { robustDecision: { minimumLowerGain: 1265, hurdle: 100,
        models: [{ id: "combined", evidence: { gain: 3587, lowerGain: 2251 },
          candidate: { cvar95: .2042 }, passes: false, failures: ["CVaR"] }] } },
      trade_plan: { total: 0, turnover: 0, rows: [] } },
  } });
  const html = views.decisionReport();
  assert.match(html, /No · CVaR/);
  assert.match(html, /20[.,]4%/);
  assert.doesNotMatch(html, /mejora insuficiente/);
});

test("partial refreshes remain visible with a direct link to source dates", () => {
  const views = createViews({
    state: { view: "portfolio" },
    data: { ...data, errors: ["SEC: HTTP 403", "BLS: HTTP 403"] },
    asset: () => null,
  });
  const html = views.shell("<h1>Cartera</h1>");
  assert.ok(html.includes("Actualización parcial: 2 incidencias."));
  assert.ok(
    html.replace(/\s+/g, " ").includes("Se conservaron los últimos datos"),
  );
  assert.ok(html.includes('data-action="sources"'));
  assert.ok(!html.includes("{{count}}"));
});

test("provider configuration and imported consensus show dates, coverage and revisions", () => {
  const stock = {
    ...data.assets.find((a) => a.symbol === "MSFT"),
    analyst_estimates: {
      observed_at: "2026-10-24T18:00:00Z",
      source_url: "https://example.test/estimates",
      periods: [
        {
          period_end: "2027-06-30",
          eps_mean: 12.5,
          eps_low: 11,
          eps_high: 14,
          revenue_mean: 1250000000,
          currency: null,
          eps_analysts: 10,
          revenue_analysts: 12,
          eps_revision_pct: 0.05,
          comparison_observed_at: "2026-10-23T18:00:00Z",
        },
      ],
    },
  };
  const views = createViews({
    state: { positions: [] },
    data: {
      ...data,
      assets: [stock],
      providers: [
        {
          name: "FRED",
          status: "not_configured",
          detail: "FRED_API_KEY pendiente",
          checked_at: data.generated_at,
        },
      ],
    },
    asset: () => stock,
    assetStats: () => ({ volatility: 0.2 }),
    model: () => valuation(stock),
  });
  const detail = views.detail("MSFT");
  assert.ok(detail.includes("CONSENSO ANUAL · FMP"));
  assert.ok(detail.includes("30 JUN 2027"));
  assert.ok(detail.includes("+5.0%"));
  assert.ok(detail.includes("10 / 12"));
  assert.ok(detail.includes("1.25 B"));
  assert.ok(detail.includes("sin moneda declarada"));
  assert.ok(views.sourcesView().includes("CLAVE PENDIENTE"));
});

test("macro comparisons use matching inflation units and label employment in thousands", () => {
  const views = createViews({
    data: {
      macro: [
        {
          id: "CPI",
          label: "IPC",
          unit: "índice",
          provider: "FRED",
          value: 130,
          previous: 120,
          yoy: 0.3,
          date: "2026-09-01",
          source_url: "https://example.test/cpi",
          history: [
            { date: "2025-08-01", value: 100 },
            { date: "2025-09-01", value: 100 },
            { date: "2026-08-01", value: 120 },
            { date: "2026-09-01", value: 130 },
          ],
        },
        {
          id: "PAYEMS",
          label: "Nóminas",
          unit: "miles de personas",
          provider: "FRED",
          value: 159044,
          previous: 159015,
          date: "2026-09-01",
          source_url: "https://example.test/jobs",
          history: [
            { date: "2026-08-01", value: 159015 },
            { date: "2026-09-01", value: 159044 },
          ],
        },
      ],
    },
  });
  const html = views.macro();
  assert.match(html, /<td>30\.0%<\/td>/);
  assert.match(html, /<td>20\.0%<\/td>/);
  assert.ok(html.includes("159,044.00 miles de personas"));
});

for (const populated of [false, true])
  test(`all views render valid fragments with ${populated ? "a registered" : "an empty"} portfolio`, () => {
    const positions = populated
      ? ["MSFT", "AMZN", "GOOGL", "JNJ", "SHY"].map((symbol) => ({
          symbol,
          weight: 0.2,
        }))
      : [];
    const state = {
      view: "portfolio",
      positions,
      capital: 100000,
      lookback: 252,
      selected: "MSFT",
      method: "pe",
      overrides: {},
      acknowledged: [],
      rules: DEFAULT_RULES,
      settings: {
        model: "merton",
        horizon: 1,
        paths: 100,
        seed: 1,
        driftMode: "fundamental",
        manualReturn: 0.06,
        lambda: 0.94,
        jumpIntensity: 0.35,
        jumpMean: -0.12,
        jumpVol: 0.08,
      },
      filters: { text: "", sector: "all", type: "all", discount: false },
      sort: { key: "symbol", ascending: true },
    };
    if (populated) {
      state.forecast = simulateForecast(data.assets, positions, state.settings);
      state.validation = validateRiskBands(data.assets, positions);
      state.baseline = registerPortfolio(data, positions, state.capital, {});
    }
    const asset = (symbol) => data.assets.find((a) => a.symbol === symbol);
    const views = createViews({
      state,
      data,
      asset,
      override: () => ({}),
      model: (a, method) => valuation(a, {}, method),
      analyze: () => portfolioAnalysis(data.assets, positions, 252, 0.04),
      assetStats: () => ({ volatility: 0.2, annualized: 0.1 }),
      monitoring: () =>
        populated ? reviewPortfolio(data, state.baseline, DEFAULT_RULES) : null,
      filteredAssets: () => data.assets,
    });
    for (const [id] of NAV) {
      state.view = id;
      const html = views.shell(views[id]());
      assert.ok(html.includes("<main"), id);
      assert.ok(html.includes("<h1>"), id);
      assert.ok(!/\{\{\w+/.test(html), id);
      assert.ok(
        !/&lt;(?:button|section|svg|path|div|span|table)\b/.test(html),
        `Escaped markup in ${id}`,
      );
      assert.ok(
        !/\s(?:style|onclick|onchange)=/.test(html),
        `Inline presentation or handlers in ${id}`,
      );
    }
    for (const html of [
      views.detail("MSFT"),
      views.sourcesView(),
      views.rulesView(),
      views.methodologyView(),
      views.shortcutsView(),
      views.commandResults([asset("MSFT")], NAV),
    ]) {
      assert.ok(!/&lt;(?:button|section|svg|path|div|span)\b/.test(html));
    }
    assert.ok(metrics(asset("MSFT")).eps > 0);
  });

test("composition distinguishes published EPS from the effective valuation assumptions", async () => {
  const { compositionValuationEvidence } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  const text = compositionValuationEvidence({filed:"2026-10-22",valuationEvidence:{
    source:"BPA y múltiplo propios",assumptions:{growth:.04,multiple:16,horizon:3},
    confidence:.514285714,prior:.06,
  }});
  assert.match(text,/Supuestos:/);
  assert.match(text,/16[,.]0/);
  assert.match(text,/valoración a 3 años/);
  assert.match(text,/confianza asignada/);
  assert.match(text,/Sin calibración predictiva/);
  assert.match(compositionValuationEvidence({filed:"2026-10-22"}),/vuelve a proponer/);
  assert.equal(compositionValuationEvidence({symbol:"SHY"}),"");
});

test('the compact allocation keeps financial evidence in details and explains actual cash constraints',async()=>{
 const {compositionCashExplanation,compositionRole}=await import('../dist/assets/js/ui/views.mjs?v=0.33.1');
 const p={positions:[{symbol:'CASH',weight:.15}],mandate:{cashYield:0},diagnostics:{cashAllocation:{
  cashWeight:.15,requiredCash:.05,status:'no_local_improvement'}}};
 assert.match(compositionCashExplanation(p),/15[,.]0%/);
 assert.match(compositionCashExplanation(p),/reserva exigida 5[,.]0%/);
 assert.match(compositionCashExplanation(p),/local probada/);
 p.diagnostics.cashAllocation.status='risk_or_execution_limits';
 assert.match(compositionCashExplanation(p),/incumplen/);
 delete p.diagnostics.cashAllocation;
 assert.match(compositionCashExplanation(p),/Falta comprobar/);
 const signal={symbol:'AAA',filed:'2026-08-01',valuationEvidence:{assumptions:{growth:.12}}};
 const role=compositionRole(signal,p);
 assert.ok(role.length<95);assert.doesNotMatch(role,/captura|calibración|Supuestos:/);
 assert.match(compositionRole({symbol:'CASH'},p),/sin remuneración/);
 const html=await readFile(new URL('../dist/templates/composition.html',import.meta.url),'utf8');
 const detailStart=html.indexOf('<details class="composition-method">');
 assert.ok(detailStart>0);
 assert.ok(html.indexOf('composition-valuation-details')>detailStart);
 const primary=html.slice(html.indexOf('id="composition-signal"'),html.indexOf('id="composition-signal-detail"'));
 assert.doesNotMatch(primary,/valuationEvidence|returnSplit/);
 assert.match(html,/FUENTES, SUPUESTOS Y COMPARACIONES/);
});

test('robustness panel exposes conditional results, current comparison and stale-input protection', async()=>{
 const {robustnessView}=await import('../dist/assets/js/ui/views.mjs?v=0.33.1');
 const metric={medianReturn:.03,cvar95:.1,lossProbability:.3};
 const report={as_of:'2026-10-23',horizon:1,account_source:'Cuenta <propia>',candidate_count:500,
  verified_candidates:12,decision:'no_robust_rebalance_evidence',current:{structuralFeasible:false,verification:{original:metric}},
  candidate:{positions:[{symbol:'AAA',weight:.2},{symbol:'CASH',weight:.8}],cost:10,
   verification:{original:metric},pairedMonteCarlo:{original:{lower_ce_gain_dollars:-54}}},
  scenarios:[{id:'original'}],paired_certainty_equivalent_gain_dollars:{original:383},required_gain_dollars:100};
 const html=robustnessView(report);
 assert.match(html,/SIN EVIDENCIA SUFICIENTE/);
 assert.match(html,/MEDIANA · MANTENER/);
 assert.match(html,/Usar pesos para simular/);
 assert.ok(html.includes('Cuenta &lt;propia&gt;'));
 const stale=robustnessView(report,{fresh:false});
 assert.match(stale,/desactualizada/);assert.ok(!stale.includes('use-robust-weights'));
 const running=robustnessView(report,{busy:true,progress:'Verificando'});
 assert.match(running,/cancel-robustness/);assert.ok(!running.includes('use-robust-weights'));
});

test('robust transition explains hypothetical trades, reconciles cash and blocks incomplete tax evidence',async()=>{
 const {robustTransitionView}=await import('../dist/assets/js/ui/views.mjs?v=0.33.1');
 const {robustTransition}=await import('../dist/assets/js/robust-transition.mjs?v=0.33.1');
 const plan=robustTransition([{symbol:'A<',price:100},{symbol:'CASH',price:1}],
  [{symbol:'CASH',weight:1}],[{symbol:'A<',weight:.5},{symbol:'CASH',weight:.5}],10000,{commissionFixed:5});
 const html=robustTransitionView(plan,false);
 assert.match(html,/Solo comparación hipotética/);
 assert.match(html,/Abrir/);assert.match(html,/A&lt;/);
 assert.match(html,/Conciliación verificada/);
 assert.match(html,/CANTIDAD EST\./);
 assert.ok(!html.includes('undefined'));
 assert.match(robustTransitionView(plan,true),/ventaja condicional/);
 const incomplete=robustTransitionView({...plan,reconciled:false},true);
 assert.match(incomplete,/costos incompletos/);assert.ok(!incomplete.includes('<table'));
});

test('financial coverage distinguishes report, accounting period and source capture',async()=>{
 const {financialCoverageView}=await import('../dist/assets/js/ui/views.mjs?v=0.33.1');
 const html=financialCoverageView({price_as_of:'2026-10-26',assets:[{symbol:'A<',type:'stock',
  financials:{eps:{value:5,period_end:'2026-06-30',filed:'2026-07-30',method:'TTM'},
   observed_at:'2026-10-26T21:00:00Z',refresh_status:'retained_after_failure'},
  filings:[{form:'10-Q',filing_date:'2026-10-23',report_date:'2026-09-30',url:'https://www.sec.gov/'}]}]});
 assert.match(html,/1 CON INFORME POSTERIOR/);assert.match(html,/CAPTURA XBRL/);
 assert.match(html,/A&lt;/);assert.ok(html.includes(timestampLabel('2026-10-26T21:00:00Z')));
 assert.match(html,/captura previa por fallo/);assert.ok(!html.includes('undefined'));
});

test('price monitor renders empty filters and keeps descriptive price data separate from anchors',async()=>{
 const {priceMonitorView}=await import('../dist/assets/js/ui/views.mjs?v=0.33.1');
 const snapshot={price_as_of:'2026-10-26',assets:[{symbol:'A<',type:'stock',price:10,price_date:'2026-10-26',history:[]}]};
 const html=priceMonitorView(snapshot,[],'all');
 assert.match(html,/A&lt;/);assert.match(html,/252 cierres/);
 assert.match(html,/no suministra retornos esperados/);
 assert.match(priceMonitorView(snapshot,[],'held'),/Sin activos para este filtro/);
});

test('the primary valuation and scenarios follow the reconciled continuing EPS selection',()=>{
 const row=value=>({value,period_end:'2026-06-30',filed:'2026-08-01',method:'TTM',components:[
  {start:'2025-07-01',end:'2026-06-30',filed:'2026-08-01',val:value,accn:'one'}]});
 const a={symbol:'AAA',name:'Example',type:'stock',sector:'Industrial',price:100,price_date:'2026-10-26',history:[],
  assumptions:{growth:.05,multiple:15,discount:.1,horizon:3},financials:{eps:row(10),continuing_eps:row(4),discontinued_eps:row(6)}};
 const state={selected:'AAA',method:'pe',research:{AAA:{earningsBasis:'continuing'}},overrides:{}};
 const views=createViews({state,data:{price_as_of:a.price_date,generated_at:'2026-10-26T23:00:00Z',assets:[a]},
  asset:()=>a,override:()=>({}),model:()=>valuation(a)});
 const html=views.valuation();
 assert.ok(html.includes('VALOR PRESENTE · BPA CONTINUADO'));
 assert.ok(html.includes('$4.00'));
 const expected=valuation({...a,financials:{...a.financials,eps:row(4)}});
 assert.ok(html.includes('$'+expected.fairValue.toFixed(2)), 'present value must use the displayed reference multiple');
 assert.ok(html.includes('$'+expected.exitPrice.toFixed(2)), 'formula and base scenario must share the same exit price');
 state.research.AAA.earningsBasis='reported';
 assert.ok(!views.valuation().includes('$4.00'));
 state.research.AAA.earningsBasis='continuing';a.financials.discontinued_eps=null;
 const blocked=views.valuation();
 assert.ok(blocked.includes('sin conciliar'));
 assert.ok(!blocked.includes('$4.00'));
});

test("F3 names the process that is actually simulated", async () => {
  const { simulatedProcess } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  const hybrid = simulatedProcess({ volatilityMode: "hybrid", model: "merton" }, { accepted: 2 });
  assert.equal(hybrid.jumps, false);
  assert.equal(hybrid.legacy, false);
  assert.match(hybrid.label, /GJR-t validado \(2\)/);
  assert.match(hybrid.subtitle, /sin saltos/);
  const fallback = simulatedProcess({ volatilityMode: "hybrid", model: "merton" }, { accepted: 0 });
  assert.equal(fallback.label, "EWMA con reversión");
  assert.equal(simulatedProcess({ volatilityMode: "ewma", model: "merton" }).jumps, false);
  const legacy = simulatedProcess({ volatilityMode: "legacy", model: "merton" });
  assert.equal(legacy.jumps, true);
  assert.match(legacy.subtitle, /no estimados/);
  assert.equal(simulatedProcess({ volatilityMode: "legacy", model: "gbm" }).jumps, false);
});

test("F6 summarizes the sealed one-session risk ledger without overstating it", async () => {
  const { riskCalibrationNote } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  assert.match(riskCalibrationNote(null), /todavía sin sesiones/);
  const summary = {
    current_risk_model_version: "1.0.0", minimum_sessions: 20, minimum_observations: 500,
    versions: { "1.0.0": {
      status: "accumulating", sealed_sessions: 3, scored_sessions: 2, pending: ["2026-10-28"],
      models: { production: { observations: 520, var95_exception_rate: .0615,
        kupiec: { p_value: .21 }, christoffersen: { p_value: .48 } } },
      paired_qlike_ewma_minus_gjr: { observations: 38, mean: .04 },
    } },
  };
  const text = riskCalibrationNote(summary);
  assert.match(text, /2 de 3 sesiones puntuadas, 520 activo-días/);
  assert.match(text, /6[.,]2%/);
  assert.match(text, /Kupiec p=0[.,]21/);
  assert.match(text, /Acumulando: se interpreta desde 20 sesiones/);
  summary.versions["1.0.0"].status = "evaluable";
  assert.match(riskCalibrationNote(summary), /no promueve parámetros/);
});

test("composition explains the exit multiple and splits the model return", async () => {
  const { compositionValuationEvidence } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  const text = compositionValuationEvidence({filed:"2026-10-22",valuationEvidence:{
    source:"BPA y múltiplo propios",assumptions:{growth:.04,multiple:8.2,horizon:3},
    confidence:.5,prior:.06,
    rerating:{applied:true,explicit:false,current:7,reference:16,effective:8.2,share:.188,halfLife:10},
    decomposition:{growth:.04,rerating:.055,dividends:.048,total:.143},
  }});
  assert.match(text,/P\/E actual 7[,.]0 → salida 8[,.]2/);
  assert.match(text,/sectorial 16[,.]0; vida media 10 años/);
  assert.doesNotMatch(text,/dividendos/);
  const { compositionReturnSplit, compositionAnchorRefinement, rulerMarkers } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  assert.match(compositionAnchorRefinement({valuationEvidence:{refinement:{anchor:.086,equilibrium:.067,beta:1.18,
    benchmark:"SPY",alpha:.019,ic:.0467,omega:.255,score:2.2,buildingBlock:.109}}}),
    /Ancla 8[,.]6% = equilibrio 6[,.]7% \(β 1[,.]18 frente a SPY\) \+ alfa \+1[,.]9%.*Bloques sin ajustar 10[,.]9%/);
  assert.equal(compositionAnchorRefinement({}),"");
  const { shortfallDetail, compositionSubstitutionSummary } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  assert.match(shortfallDetail({lossProbabilitySE:.008,shortfallProbabilitySE:.009,shortfallProbability:.451,shortfallRate:.0422,shortfallBasis:"bill"}),
    /^45[,.]1% bajo letra 3M \(4[,.]2% anual\) · error MC ±1[,.]8%$/);
  assert.match(shortfallDetail({lossProbabilitySE:.008,shortfallProbability:null}),/^Error Monte Carlo ±1[,.]6%$/);
  assert.match(compositionSubstitutionSummary({screened:200,verified:8,structurallyBlocked:541,threshold:1.645,
    accepted:[{from:"SHV",to:"IEI",transfer:.1,full:true,certaintyEquivalentGain:52.4,z:5.29}],
    closestRejected:{from:"TGT",to:"NFLX",transfer:.05,full:false,certaintyEquivalentGain:49.6,z:1.38}}),
    /200 probados.*8 verificados.*SHV → IEI \(10% completo\).*z 5[,.]3.*TGT → NFLX 5%.*z 1[,.]4/);
  assert.match(compositionSubstitutionSummary(null),/Sin revisión/);
  const { compositionStabilityNote } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  assert.match(compositionStabilityNote({starts:3,equivalent:1,worse:1,minimumOverlap:.55,level:"low",
    winners:[{chosen:true,equivalent:true,overlap:1,certaintyEquivalent:106084,positions:[]},
      {chosen:false,equivalent:true,overlap:.55,certaintyEquivalent:105915,positions:[{symbol:"CASH",weight:.05},{symbol:"LQD",weight:.2},{symbol:"NVDA",weight:.2},{symbol:"AGG",weight:.1}]},
      {chosen:false,equivalent:false,overlap:.4,certaintyEquivalent:105365,positions:[]}]}),
    /^Estabilidad baja entre 3 búsquedas independientes, comparadas en escenarios comunes\. 1 ganadora alternativa no es significativamente peor; la más distinta comparte 55% de los pesos \(LQD 20%, NVDA 20%, AGG 10%\)\. Entre equivalentes se elige la de menor rotación\. 1 queda descartada por ser significativamente peor \(hasta USD 719 menos\)\. Selección experimental/);
  assert.match(compositionStabilityNote({starts:3,equivalent:0,worse:2,minimumOverlap:1,level:"high",
    winners:[{chosen:true,equivalent:true,overlap:1,certaintyEquivalent:1,positions:[]},{chosen:false,equivalent:false,overlap:.3,certaintyEquivalent:0,positions:[]},{chosen:false,equivalent:false,overlap:.3,certaintyEquivalent:0,positions:[]}]}),
    /Ninguna otra ganadora iguala a esta mezcla\. 2 quedan descartadas/);
  assert.match(compositionStabilityNote(null),/^Selección experimental/);
  const { regimeProbabilityNote } = await import("../dist/assets/js/ui/decision-views.mjs?v=0.33.1");
  assert.match(regimeProbabilityNote({source:"curve",curve:{probability:.1304,spread:.9338,observations:21,to:"2026-10-27"}},1),
    /^Recesión 13% según la curva al corte: modelo probit de la Fed de Nueva York con el diferencial 10A − 3M medio de 0[.,]93 pp \(21 sesiones/);
  assert.match(regimeProbabilityNote({source:"manual",curve:null},.95),/^Probabilidades fijadas a mano: suma 95%/);
  assert.match(compositionReturnSplit({valuationEvidence:{decomposition:{growth:.04,rerating:.055,dividends:.048,total:.143}}}),
    /Modelo \+14[,.]3%\/año = BPA \+4[,.]0% · múltiplo \+5[,.]5% · dividendos \+4[,.]8%/);
  assert.equal(compositionReturnSplit({}),"");
  // Nearly equal price and fair value: labels open outward instead of overlapping.
  const near=rulerMarkers(532.6,529.6);
  assert.equal(near.priceLabelSide,"label-end");
  assert.equal(near.modelLabelSide,"label-start");
  const far=rulerMarkers(100,50);
  assert.equal(far.priceLabelSide,"");
  assert.ok(far.max>far.max7);
  const explicit = compositionValuationEvidence({filed:"2026-10-22",valuationEvidence:{
    source:"BPA y múltiplo propios",assumptions:{growth:.04,multiple:12,horizon:3},
    confidence:.5,rerating:{explicit:true,applied:false},
  }});
  assert.match(explicit,/P\/E de salida 12[,.]0 fijado por ti/);
});

test("a holdings-anchored ETF is described as a diversified fund, not an explicit assumption", async () => {
  const { compositionRole } = await import("../dist/assets/js/ui/views.mjs?v=0.33.1");
  assert.match(compositionRole({symbol:"SPY",holdingsCoverage:.72}), /Fondo de acciones · 72% del peso con ancla de sus constituyentes/);
  assert.equal(compositionRole({symbol:"GLD"}), "Supuesto de retorno explícito");
});
