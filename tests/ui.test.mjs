import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createTemplateRenderer,
  loadTemplates,
} from "../dist/assets/js/ui/templates.mjs";
import { createViews, NAV } from "../dist/assets/js/ui/views.mjs";
import {
  valuation,
  portfolioAnalysis,
  metrics,
} from "../dist/assets/js/analytics.mjs";
import {
  simulateForecast,
  validateRiskBands,
} from "../dist/assets/js/forecast.mjs";
import {
  registerPortfolio,
  reviewPortfolio,
  DEFAULT_RULES,
} from "../dist/assets/js/monitor.mjs";

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
