import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createTemplateRenderer,
  loadTemplates,
} from "../dist/assets/js/ui/templates.mjs?v=0.5.2";
import { createViews, NAV } from "../dist/assets/js/ui/views.mjs?v=0.5.2";
import {
  valuation,
  portfolioAnalysis,
  metrics,
} from "../dist/assets/js/analytics.mjs?v=0.5.2";
import {
  simulateForecast,
  validateRiskBands,
} from "../dist/assets/js/forecast.mjs?v=0.5.2";
import {
  registerPortfolio,
  reviewPortfolio,
  DEFAULT_RULES,
} from "../dist/assets/js/monitor.mjs?v=0.5.2";

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

await loadTemplates(async (url) => ({
  ok: true,
  text: () => readFile(url, "utf8"),
}));
const data = JSON.parse(
  await readFile(new URL("../dist/data/market.json", import.meta.url), "utf8"),
);

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
