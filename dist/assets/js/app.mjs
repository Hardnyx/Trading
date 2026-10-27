import {
  finite,
  sum,
  normalizeWeights,
  metrics,
  valuation,
  scenarios,
  portfolioAnalysis,
  alignReturns,
  returnStats,
  validateSnapshot,
} from "./analytics.mjs?v=0.25.0";
import {
  registerPortfolio,
  reviewPortfolio,
  DEFAULT_RULES,
} from "./monitor.mjs?v=0.25.0";

import { fmt, pct, money, dateLabel } from "./ui/format.mjs?v=0.25.0";
import { createViews, NAV } from "./ui/views.mjs?v=0.25.0";
import { loadTemplates } from "./ui/templates.mjs?v=0.25.0";
import { applyVisualValues, showStartupError } from "./ui/dom.mjs?v=0.25.0";
import { createTickerRotation } from "./ui/ticker-rotation.mjs?v=0.25.0";
import { DEFAULT_COMPOSITION_RULES } from "./composer.mjs?v=0.25.0";

import {
  DEFAULT_MANDATE,
  DEFAULT_EXECUTION,
  DEFAULT_REGIMES,
  mandate,
  execution,
  regimes,
  withCashAsset,
  currentAccount,
  informationDate,
  MODEL_VERSION,
} from "./policy.mjs?v=0.25.0";
import { validateResearch } from "./research-model.mjs?v=0.25.0";
import {
  journalOrigin,
  appendForecast,
  freezeMaturedOutcomes,
} from "./journal.mjs?v=0.25.0";

import { openJournal, saveJournal } from "./journal-store.mjs?v=0.25.0";

let journalDBReady = false,
  storageErrorShown = false;

const $ = (s, root = document) => root.querySelector(s);

import { referenceRequest, REFERENCE_ID } from "./reference-preset.mjs?v=0.25.0";

let saved = {};
try {
  saved = JSON.parse(localStorage.getItem("trading-workspace-v1") || "{}");
} catch {}
const state = {
  view: "portfolio",
  positions: [],
  capital: 100000,
  lookback: 252,
  chartMode: "forecast",
  selected: "MSFT",
  method: "pe",
  overrides: {},
  baseline: null,
  acknowledged: [],
  rules: { ...DEFAULT_RULES },
  filters: { text: "", sector: "all", discount: false, type: "all" },
  sort: { key: "symbol", ascending: true },
  forecast: null,
  validation: null,
  busy: false,
  forecastError: null,
  robustness: null,
  robustSimulation: null,
  robustnessBusy: false,
  robustnessError: null,
  robustnessProgress: null,
  compositionBusy: false,
  compositionError: null,
  compositionRules: { ...DEFAULT_COMPOSITION_RULES },
  proposal: null,
  mandate: { ...DEFAULT_MANDATE },
  execution: { ...DEFAULT_EXECUTION },
  account: { enabled: false, cash: 0, positions: [] },
  research: {},
  assetAssumptions: {},
  macroRegimes: structuredClone(DEFAULT_REGIMES),
  journal: [],
  settings: {
    model: "merton",
    horizon: 1,
    paths: 3000,
    seed: 20261024,
    driftMode: "fundamental",
    manualReturn: 0.06,
    lambda: 0.94,
    jumpIntensity: 0.35,
    jumpMean: -0.12,
    jumpVol: 0.08,
    uncertainFundamentals: true,
    volatilityMode: "hybrid",
  },
  ...saved,
};
state.view = NAV.some((n) => n[0] === state.view) ? state.view : "portfolio";
state.forecast = null;
state.validation = null;
state.busy = false;
state.forecastError = null;
state.robustnessBusy = false;
state.robustnessError = null;
state.robustnessProgress = null;
if(state.robustness?.model_version!==MODEL_VERSION)state.robustness=null;
state.compositionBusy = false;
state.compositionError = null;
state.compositionRules = {
  ...DEFAULT_COMPOSITION_RULES,
  ...state.compositionRules,
};
if (state.proposal && state.proposal.model_version !== MODEL_VERSION) {
  state.proposal = null;
  state.compositionError =
    `Propuesta guardada con un motor anterior al ${MODEL_VERSION}. Conservamos posiciones y supuestos. Pulsa Proponer cartera para recalcular.`;
}
if (
  !saved.workspaceVersion &&
  saved.compositionRules?.reserveCap === 0.5 &&
  saved.compositionRules?.maxPosition === 0.2 &&
  saved.compositionRules?.maxSector === 0.35 &&
  saved.compositionRules?.maxPositions === 6 &&
  saved.compositionRules?.maxCorrelation === 0.85
)
  state.compositionRules.reserveCap = 1;
state.rules = { ...DEFAULT_RULES, ...state.rules };
state.mandate = { ...DEFAULT_MANDATE, ...state.mandate };
state.execution = { ...DEFAULT_EXECUTION, ...state.execution };
state.account ||= { enabled: false, cash: 0, positions: [] };
state.research ||= {};
state.assetAssumptions ||= {};
state.macroRegimes ||= structuredClone(DEFAULT_REGIMES);
// Older sessions predate the credit spread scenario: show its default.
state.macroRegimes = state.macroRegimes.map((row) => ({
  spreadShift: DEFAULT_REGIMES.find((d) => d.id === row.id)?.spreadShift ?? 0, ...row }));
state.journal = Array.isArray(state.journal) ? state.journal : [];
state.acknowledged = Array.isArray(state.acknowledged)
  ? state.acknowledged
  : [];
state.filters = { text: "", sector: "all", discount: false, type: "all" };
state.sort = { key: "symbol", ascending: true };
let data,
  worker,
  compositionWorker,
  compositionJob = 0,
  job = 0,
  toastTimer,
  weightTimer,
  lastFocus,
  statsCache = new Map();

function views() {
  return createViews({
    state,
    data,
    asset,
    override,
    model,
    analyze,
    assetStats,
    monitoring,
    filteredAssets,
    proposalFresh: () => state.proposal?.signature === proposalSignature(),
    robustnessFresh: () => state.robustness?.signature === proposalSignature(),
  });
}
function renderTable(assets) {
  return views().renderTable(assets);
}

function persist() {
  if (data) state.journal = freezeMaturedOutcomes(state.journal, data);
  if (journalDBReady)
    saveJournal(state.journal).catch((error) => {
      journalDBReady = false;
      if (!storageErrorShown) {
        storageErrorShown = true;
        toast(
          "No se pudo guardar el registro. Exporta una copia: " + error.message,
        );
      }
    });
  try {
    localStorage.setItem(
      "trading-workspace-v1",
      JSON.stringify({
        workspaceVersion: MODEL_VERSION,
        positions: state.positions,
        capital: state.capital,
        lookback: state.lookback,
        selected: state.selected,
        overrides: state.overrides,
        settings: state.settings,
        view: state.view,
        baseline: state.baseline,
        acknowledged: state.acknowledged,
        rules: state.rules,
        proposal: state.proposal,
        robustness: state.robustness,
        robustSimulation: state.robustSimulation,
        compositionRules: state.compositionRules,
        mandate: state.mandate,
        execution: state.execution,
        account: state.account,
        research: state.research,
        assetAssumptions: state.assetAssumptions,
        macroRegimes: state.macroRegimes,
        ...(journalDBReady ? {} : { journal: state.journal }),
      }),
    );
  } catch {
    if (!storageErrorShown) {
      storageErrorShown = true;
      toast(
        "El almacenamiento está lleno. Exporta la cartera para conservar los cambios.",
      );
    }
  }
}
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("visible"), 4500);
}
function asset(symbol) {
  return data.assets.find((a) => a.symbol === symbol);
}
function override(symbol) {
  return state.overrides?.[symbol] || {};
}
function model(a, method = "pe") {
  return valuation(a, override(a.symbol), method);
}
function riskFree() {
  return (data.macro.find((s) => s.id === "DGS3MO")?.value ?? 4) / 100;
}
function analyze(positions = state.positions, lookback = state.lookback) {
  return portfolioAnalysis(data.assets, positions, lookback, riskFree());
}
function assetStats(a) {
  const key = a.symbol + ":" + state.lookback;
  if (!statsCache.has(key)) {
    const alignment = alignReturns([a, asset("SPY") || a], state.lookback);
    statsCache.set(
      key,
      returnStats(alignment.columns[0], riskFree(), alignment.columns[1]),
    );
  }
  return statsCache.get(key);
}

function monitoring() {
  return state.baseline
    ? reviewPortfolio(data, state.baseline, state.rules, state.research)
    : null;
}

function filteredAssets() {
  const f = state.filters;
  return data.assets
    .filter(
      (a) =>
        (!f.text ||
          `${a.symbol} ${a.name}`
            .toLowerCase()
            .includes(f.text.toLowerCase())) &&
        (f.sector === "all" || a.sector === f.sector) &&
        (f.type === "all" || a.type === f.type) &&
        (!f.discount || (model(a)?.upside || 0) > 0),
    )
    .sort((a, b) => {
      const k = state.sort.key;
      let av =
        k === "symbol"
          ? a.symbol
          : ["price", "change"].includes(k)
            ? a[k]
            : k === "upside"
              ? model(a)?.upside
              : k === "volatility"
                ? assetStats(a)?.volatility
                : metrics(a)[k];
      let bv =
        k === "symbol"
          ? b.symbol
          : ["price", "change"].includes(k)
            ? b[k]
            : k === "upside"
              ? model(b)?.upside
              : k === "volatility"
                ? assetStats(b)?.volatility
                : metrics(b)[k];
      if (av == null) return 1;
      if (bv == null) return -1;
      return (
        (typeof av === "string" ? av.localeCompare(bv) : av - bv) *
        (state.sort.ascending ? 1 : -1)
      );
    });
}

const tickers = createTickerRotation();
function render() {
  if (!data) return;
  const editing = document.activeElement;
  const preserve =
    editing?.tagName === "INPUT" && editing.closest("#app")
      ? {
          id: editing.id,
          weight: editing.dataset.weight,
          value: editing.value,
          start: editing.selectionStart,
          end: editing.selectionEnd,
        }
      : null;
  const nav = NAV.find((n) => n[0] === state.view) || NAV[0];
  const ui = views();
  const page = (ui[state.view] || ui.overview)();
  $("#app").innerHTML = ui.shell(page);
  applyVisualValues($("#app"));
  tickers.attach($("#app"));
  if (preserve) {
    const input = preserve.id
      ? document.getElementById(preserve.id)
      : preserve.weight
        ? document.querySelector(`[data-weight="${preserve.weight}"]`)
        : null;
    if (input) {
      input.value = preserve.value;
      input.focus({ preventScroll: true });
      if (input.type === "text" && preserve.start != null)
        input.setSelectionRange(preserve.start, preserve.end);
      if (input.id === "command-input" && input.value)
        input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }
  persist();
}
function navigate(view) {
  if (!NAV.some((n) => n[0] === view)) return;
  state.view = view;
  history.replaceState(null, "", "#" + view);
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
}
function calculationOptions(forComposition = false) {
  const policy = mandate({ ...state.mandate, horizon: state.settings.horizon });
  return {
    ...state.settings,
    asOf: data.price_as_of,
    informationAsOf: informationDate(data),
    mandate: policy,
    execution: execution(state.execution),
    macroRegimes: regimes(state.macroRegimes),
    capital: state.capital,
    research: state.research,
    assetAssumptions: state.assetAssumptions,
    yieldCurve: Object.fromEntries(data.macro.map((r) => [r.id, r.value])),
    volatilityData: data.volatility ?? null,
    ...(forComposition
      ? { account: state.account, baseline: state.baseline }
      : {
          initialCost:
            state.robustSimulation?.key===robustPreviewKey()
              ? state.robustSimulation.cost
              : state.proposal?.status === "proposed" && !state.proposal.modified
              ? state.proposal.trade_plan?.total || 0
              : 0,
        }),
  };
}
function runForecast() {
  if (!data) return;
  state.settings.reserveReturn = riskFree();
  if (
    state.proposal?.status === "proposed" &&
    state.proposal.signature !== proposalSignature()
  )
    state.proposal.modified = true;
  const current = ++job;
  state.busy = true;
  state.forecastError = null;
  if (!state.positions.some((p) => p.weight > 0)) {
    state.busy = false;
    state.forecast = null;
    state.validation = null;
    render();
    return;
  }
  try {
    const options = calculationOptions();
    const origin = journalOrigin(
      data,
      state.positions,
      options,
      state.overrides,
      state.research,
    );
    worker ||= new Worker(
      new URL("./forecast-worker.mjs?v=0.25.0", import.meta.url),
      {
        type: "module",
      },
    );
    worker.onmessage = (event) => {
      const r = event.data;
      if (r.id !== job) return;
      state.busy = false;
      if (r.error) {
        state.forecast = null;
        state.validation = null;
        state.forecastError = r.error;
      } else {
        state.forecast = r.forecast;
        state.validation = r.validation;
        state.journal = appendForecast(state.journal, origin, r.forecast);
      }
      render();
    };
    worker.onerror = () => {
      state.busy = false;
      state.forecastError =
        "No se pudo ejecutar el motor de simulación. Recarga la página para reintentar.";
      render();
    };
    worker.postMessage({
      id: current,
      assets: data.assets,
      positions: state.positions,
      options,
      overrides: state.overrides,
    });
  } catch (error) {
    state.busy = false;
    state.forecastError = error.message;
  }
  render();
}
function proposalSignature() {
  return JSON.stringify({
    modelVersion: MODEL_VERSION,
    asOf: data?.price_as_of,
    snapshot: data?.generated_at,
    capital: state.capital,
    baseline: state.baseline,
    positions: [...state.positions].sort((a, b) =>
      a.symbol.localeCompare(b.symbol),
    ),
    settings: state.settings,
    overrides: state.overrides,
    rules: state.compositionRules,
    mandate: state.mandate,
    execution: state.execution,
    account: state.account,
    research: state.research,
    assetAssumptions: state.assetAssumptions,
    macroRegimes: state.macroRegimes,
  });
}

function runComposition(reference = false) {
  if (!data || state.compositionBusy || state.robustnessBusy) return;
  const id = ++compositionJob,
    signature = proposalSignature();
  const request = reference
    ? referenceRequest(data)
    : {
        settings: calculationOptions(true),
        overrides: state.overrides,
        rules: state.compositionRules,
      };
  state.compositionBusy = true;
  state.compositionError = null;
  try {
    compositionWorker ||= new Worker(
      new URL("./composer-worker.mjs?v=0.25.0", import.meta.url),
      { type: "module" },
    );
    compositionWorker.onmessage = (event) => {
      if (event.data.id !== compositionJob) return;
      state.compositionBusy = false;
      if (proposalSignature() !== signature) {
        render();
        toast(
          "La entrada cambió durante el cálculo. Vuelve a proponer con los valores actuales.",
        );
        return;
      }
      if (event.data.error) {
        state.compositionError = event.data.error;
        render();
        return;
      }
      state.proposal = event.data.proposal;
      if (reference) state.proposal.reference_id = REFERENCE_ID;
      state.proposal.signature = proposalSignature();
      state.proposal.modified = false;
      // A recommendation never mutates actual or working positions.
      // It must be deliberately applied by the user.
      persist();
      render();
      toast(reference
        ? "Referencia base calculada con entradas independientes de tu sesión."
        : "Propuesta calculada. Tus posiciones no se han modificado.");
    };
    compositionWorker.onerror = () => {
      state.compositionBusy = false;
      state.compositionError =
        "No se pudo ejecutar la composición. Recarga la página para reintentar.";
      render();
    };
    compositionWorker.postMessage({
      id,
      snapshot: data,
      settings: request.settings,
      overrides: request.overrides,
      rules: request.rules,
    });
  } catch (error) {
    state.compositionBusy = false;
    state.compositionError = error.message;
  }
  render();
}

let robustWorker=null,robustJob=0;
function robustPreviewKey(){
 return JSON.stringify({model:MODEL_VERSION,snapshot:data?.generated_at,positions:state.positions,capital:state.capital,execution:state.execution,
  account:state.account,baseline:state.baseline});
}
function runRobustness(){
 if(!data||state.robustnessBusy||state.compositionBusy)return;
 const signature=proposalSignature(),id=++robustJob;
 const settings=calculationOptions(true);
 let comparisonLabel=null;
 if(!settings.account?.enabled&&!settings.baseline?.positions?.length&&state.positions.some(p=>p.weight>0)){
  if(Math.abs(sum(state.positions.map(p=>p.weight))-1)>1e-7){
   state.robustnessError='Los pesos de la cartera de trabajo deben sumar 100% para comparar.';render();return;
  }
  settings.account={enabled:true,cash:0,positions:[]};
  for(const p of state.positions){
   if(p.symbol==='CASH')settings.account.cash=state.capital*p.weight;
   else settings.account.positions.push({symbol:p.symbol,quantity:state.capital*p.weight/asset(p.symbol).price});
  }
  comparisonLabel='Cartera de trabajo a precios del corte; sin conciliación con broker';
 }
 state.robustnessBusy=true;state.robustnessError=null;state.robustnessProgress='Preparando comparación';render();
 try{
  robustWorker??=new Worker(new URL('./robust-worker.mjs?v=0.25.0',import.meta.url),{type:'module'});
  robustWorker.onmessage=({data:message})=>{
   if(message.id!==robustJob)return;
   if(proposalSignature()!==signature){
    robustWorker.terminate();robustWorker=null;state.robustnessBusy=false;
    state.robustnessError='La sesión cambió durante el cálculo. Vuelve a comparar con los valores actuales.';render();return;
   }
   if(message.progress){state.robustnessProgress=message.progress.phase+' · '+message.progress.detail;render();return;}
   state.robustnessBusy=false;state.robustnessProgress=null;
   if(message.error)state.robustnessError=message.error;
   else {state.robustness={...message.report,signature};persist();}
   render();
  };
  robustWorker.onerror=()=>{state.robustnessBusy=false;state.robustnessError='No se pudo terminar la comparación. Puedes volver a intentarlo.';
   robustWorker?.terminate();robustWorker=null;render();};
  robustWorker.postMessage({id,snapshot:data,settings,overrides:state.overrides,rules:state.compositionRules,
   comparisonLabel,proposal:state.proposal?.snapshot_generated_at===data.generated_at?state.proposal:null});
 }catch(error){state.robustnessBusy=false;state.robustnessError=error.message;render();}
}

function changePositions() {
  state.forecast = null;
  state.validation = null;
  persist();
  runForecast();
}
function toggleAsset(symbol) {
  if (state.positions.some((p) => p.symbol === symbol)) {
    state.positions = state.positions.filter((p) => p.symbol !== symbol);
    toast(`${symbol} retirado de la cartera.`);
  } else {
    state.positions = normalizeWeights([
      ...state.positions,
      { symbol, weight: state.positions.length ? 0.05 : 1 },
    ]);
    toast(`${symbol} agregado. Pesos ajustados a 100%.`);
  }
  changePositions();
}
function showModal(heading, content, wide = false) {
  lastFocus = document.activeElement;
  $("#modal-root").innerHTML = views().modal(heading, content, wide);
  document.body.classList.add("modal-open");
  applyVisualValues($("#modal-root"));
  $('.modal [data-action="close-modal"]').focus();
}
function closeModal() {
  $("#modal-root").innerHTML = "";
  document.body.classList.remove("modal-open");
  lastFocus?.isConnected && lastFocus.focus();
}
function showDetail(symbol) {
  if (asset(symbol)) showModal(`${symbol} US EQUITY`, views().detail(symbol));
}
function download(name, body, type = "application/json") {
  const blob = new Blob([body], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function portfolioExport() {
  download(
    "trading-cartera.json",
    JSON.stringify(
      {
        version: 1,
        price_as_of: data.price_as_of,
        positions: state.positions,
        capital: state.capital,
        settings: state.settings,
        overrides: state.overrides,
        baseline: state.baseline,
        rules: state.rules,
        acknowledged: state.acknowledged,
        proposal: state.proposal,
        compositionRules: state.compositionRules,
        mandate: state.mandate,
        execution: state.execution,
        account: state.account,
        research: state.research,
        assetAssumptions: state.assetAssumptions,
        macroRegimes: state.macroRegimes,
        journal: state.journal,
      },
      null,
      2,
    ),
  );
  toast("Cartera y supuestos exportados.");
}

function notifyReview(previousIds = []) {
  if (!state.baseline) return;
  const r = monitoring();
  const fresh = r.alerts.filter(
    (a) => !previousIds.includes(a.id) && !state.acknowledged.includes(a.id),
  );
  if (
    fresh.length &&
    typeof Notification !== "undefined" &&
    Notification.permission === "granted"
  )
    new Notification(`Trading: ${fresh.length} revisiones de cartera`, {
      body: fresh
        .slice(0, 3)
        .map((a) => `${a.symbol}: ${a.title}`)
        .join("\n"),
      tag: "trading-review",
    });
}
function exportResearch() {
  const rows = [
    [
      "Ticker",
      "Empresa",
      "Fecha precio",
      "Precio USD",
      "Variacion 1D",
      "PE",
      "FCF yield",
      "Volatilidad anual",
      "Valor modelo",
      "Descuento modelo",
    ],
  ];
  for (const a of filteredAssets()) {
    const m = metrics(a),
      v = model(a);
    rows.push([
      a.symbol,
      a.name,
      a.price_date,
      a.price,
      a.change,
      m.pe,
      m.fcfYield,
      assetStats(a)?.volatility,
      v?.fairValue,
      v?.upside,
    ]);
  }
  download(
    "trading-research.csv",
    "\ufeff" +
      rows
        .map((row) =>
          row
            .map((v) => `"${String(v ?? "").replaceAll('"', '""')}"`)
            .join(","),
        )
        .join("\r\n"),
    "text/csv;charset=utf-8",
  );
}
let importKind = "portfolio";
function importFile(kind) {
  importKind = kind;
  $("#import-file").value = "";
  $("#import-file").click();
}
async function matchingVolatility(snapshot) {
  try {
    const url=new URL("../../data/volatility.json",import.meta.url);
    const response=await fetch(url,{cache:"no-cache"});
    if(!response.ok)return null;
    const source=await response.json();
    return source.schema_version===1 &&
      source.as_of===snapshot.price_as_of &&
      source.source_market_generated_at===snapshot.generated_at
      ? source : null;
  } catch {
    return null; // A missing or malformed research file must not break the site.
  }
}
// Prospective one-session risk ledger summary; independent of the cut loaded.
async function riskCalibration() {
  try {
    const url=new URL("../../data/risk-calibration.json",import.meta.url);
    const response=await fetch(url,{cache:"no-cache"});
    if(!response.ok)return null;
    const source=await response.json();
    return source.schema_version===1 && source.versions &&
      typeof source.versions==="object" ? source : null;
  } catch {
    return null; // Missing evidence must not break the site.
  }
}
let marketETag = null;
let marketURL = null;

// Prefer the compressed public artifact; the JSON fallback works on browsers
// without DecompressionStream and local servers without the gzip file.
async function fetchMarketCut() {
  if (typeof DecompressionStream === "function") {
    try {
      const url = new URL("../../data/market.json.gz", import.meta.url);
      const response = await fetch(url, { cache: "no-cache" });
      if (response.ok && response.body) {
        const body = response.body.pipeThrough(new DecompressionStream("gzip"));
        const snapshot = await new Response(body).json();
        return { snapshot, etag: response.headers.get("ETag"), url };
      }
    } catch {
      // A stale or unsupported compressed response must not prevent loading.
    }
  }
  const url = new URL("../../data/market.json", import.meta.url);
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error("No se pudo cargar el corte de mercado.");
  return { snapshot: await response.json(), etag: response.headers.get("ETag"), url };
}
async function loadData() {
  const result = await fetchMarketCut();
  marketETag = result.etag;
  marketURL = result.url;
  const checked=validateSnapshot(result.snapshot);
  checked.volatility=await matchingVolatility(checked);
  checked.riskCalibration=await riskCalibration();
  data = withCashAsset(checked);
  if (state.proposal &&
      (state.proposal.model_version !== MODEL_VERSION ||
       state.proposal.as_of !== data.price_as_of ||
       state.proposal.snapshot_generated_at !== data.generated_at)) {
    const oldVersion = state.proposal.model_version || "desconocida";
    state.proposal = null;
    state.compositionError =
      `La propuesta anterior (${oldVersion}) no corresponde al motor ${MODEL_VERSION} o al corte publicado. Recalcula con Proponer cartera.`;
  }
  statsCache.clear();
  state.positions = Array.isArray(state.positions)
    ? state.positions.filter(
        (p) =>
          asset(p.symbol) && finite(p.weight) && p.weight >= 0 && p.weight <= 1,
      )
    : [];
  state.capital =
    finite(state.capital) && state.capital > 0 ? state.capital : 100000;
  state.overrides =
    state.overrides && typeof state.overrides === "object"
      ? state.overrides
      : {};
  state.settings = {
    model: "merton",
    horizon: 1,
    paths: 3000,
    seed: 20261024,
    driftMode: "fundamental",
    manualReturn: 0.06,
    lambda: 0.94,
    jumpIntensity: 0.35,
    jumpMean: -0.12,
    jumpVol: 0.08,
    volatilityMode: "hybrid",
    ...state.settings,
  };
  if (!asset(state.selected)) state.selected = data.assets[0].symbol;
}

// Only checks the published snapshot while the application is open.
setInterval(async () => {
  if (!data || !state.baseline || document.visibilityState !== "visible")
    return;
  try {
    // HEAD against the same compressed or ordinary resource we last loaded.
    if (marketETag && marketURL) {
      const head = await fetch(marketURL, { method: "HEAD", cache: "no-cache" });
      if (!head.ok) return;
      if (head.headers.get("ETag") === marketETag) return;
    }
    const result = await fetchMarketCut();
    const next = validateSnapshot(result.snapshot);
    marketETag = result.etag;
    marketURL = result.url;
    if (next.generated_at === data.generated_at) return;
    const previous = monitoring()?.alerts.map((a) => a.id) || [];
    next.volatility=await matchingVolatility(next);
    next.riskCalibration=await riskCalibration();
    data = withCashAsset(next);
    if (state.proposal &&
        (state.proposal.model_version !== MODEL_VERSION ||
         state.proposal.as_of !== data.price_as_of ||
         state.proposal.snapshot_generated_at !== data.generated_at)) {
      state.proposal = null;
      state.compositionError =
        "El corte de mercado cambió. Recalcula la propuesta con los datos nuevos.";
    }
    statsCache.clear();
    notifyReview(previous);
    state.forecast = null;
    runForecast();
  } catch {
    /* Keep the last valid cut; a failed poll never changes reference data. */
  }
}, 300000);

document.addEventListener("click", async (event) => {
  const element = event.target.closest("button,[data-view]");
  if (event.target.classList.contains("modal-backdrop")) {
    closeModal();
    return;
  }
  if (!element) {
    if (!event.target.closest(".command-wrap"))
      $("#command-results")?.setAttribute("hidden", "");
    return;
  }
  if (element.dataset.view) {
    navigate(element.dataset.view);
    return;
  }
  if (element.dataset.detail) {
    showDetail(element.dataset.detail);
    return;
  }
  if (element.dataset.add) {
    const inModal = !!element.closest(".modal");
    toggleAsset(element.dataset.add);
    if (inModal) showDetail(element.dataset.add);
    return;
  }
  if (element.dataset.remove) {
    state.positions = state.positions.filter(
      (p) => p.symbol !== element.dataset.remove,
    );
    changePositions();
    return;
  }
  if (element.dataset.ack) {
    state.acknowledged.push(element.dataset.ack);
    render();
    return;
  }
  if (element.dataset.value) {
    state.selected = element.dataset.value;
    state.method = "pe";
    closeModal();
    navigate("valuation");
    return;
  }
  if (element.dataset.chart) {
    state.chartMode = element.dataset.chart;
    render();
    return;
  }
  if (element.dataset.lookback) {
    state.lookback = Number(element.dataset.lookback);
    statsCache.clear();
    render();
    return;
  }
  if (element.dataset.method) {
    state.method = element.dataset.method;
    render();
    return;
  }
  if (element.dataset.sort) {
    const key = element.dataset.sort;
    state.sort = {
      key,
      ascending: state.sort.key === key ? !state.sort.ascending : true,
    };
    if (state.view === "research")
      $("#screener-table").innerHTML = renderTable(filteredAssets());
    else navigate("research");
    return;
  }
  if (element.dataset.accountRemove) {
    state.account.positions = state.account.positions.filter(
      (p) => p.symbol !== element.dataset.accountRemove,
    );
    persist();
    render();
    return;
  }
  const action = element.dataset.action;
  if (action === "account-add") {
    const symbol = $("#account-symbol")?.value;
    if (symbol && !state.account.positions.some((p) => p.symbol === symbol)) {
      state.account.positions.push({ symbol, quantity: 0, costBasis: null });
      persist();
      render();
    }
    return;
  }
  if (action === "reload-app") {
    location.reload();
    return;
  }
  if (action === "close-modal") closeModal();
  if (action === "compose") {
    runComposition();
    return;
  }
  if(action==='compare-robustness'){runRobustness();return;}
  if(action==='cancel-robustness'){
   robustWorker?.terminate();robustWorker=null;++robustJob;state.robustnessBusy=false;state.robustnessProgress=null;render();return;
  }
  if(action==='use-robust-weights'){
   const r=state.robustness;
   if(!r?.candidate||r.signature!==proposalSignature()||r.snapshot_generated_at!==data.generated_at){
    toast('La comparación cambió o está desactualizada. Vuelve a calcularla.');return;
   }
   state.positions=r.candidate.positions.map(p=>({...p}));
   state.capital=r.capital;
   state.robustSimulation={key:robustPreviewKey(),cost:r.candidate.cost};
   if(state.proposal)state.proposal.modified=true;
   changePositions();toast('Pesos candidatos copiados para simular. No se registraron operaciones.');return;
  }
  if (action === "compose-reference") {
    runComposition(true);
    return;
  }
  if (action === "apply-proposal") {
    if (!state.proposal || state.proposal.status !== "proposed" ||
        state.proposal.model_version !== MODEL_VERSION ||
        state.proposal.as_of !== data.price_as_of ||
        state.proposal.snapshot_generated_at !== data.generated_at ||
        state.proposal.modified || state.proposal.signature !== proposalSignature()) {
      toast("Esta propuesta ya no está vigente. Vuelve a calcularla.");
      return;
    }
    state.positions = state.proposal.positions.map(p => ({...p}));
    state.capital = state.proposal.capital;
    if (state.proposal.reference_id) {
      // Preserve the user's own mandate, settings, and registered holdings:
      // applying a reference changes working weights only.
      toast("Pesos de referencia aplicados a la cartera de trabajo.");
    }
    state.proposal.signature = proposalSignature();
    changePositions();
    return;
  }
  if (action === "sources")
    showModal("DATOS & FUENTES", views().sourcesView(), true);
  if (action === "rules")
    showModal("CRITERIOS DE SEGUIMIENTO", views().rulesView());
  if (action === "register") {
    const total = sum(state.positions.map((p) => p.weight));
    if (!state.positions.some((p) => p.weight > 0)) {
      toast("Agrega al menos un activo.");
      return;
    }
    if (Math.abs(total - 1) > 0.0001) {
      toast("Ajusta los pesos a 100% antes de registrar.");
      return;
    }
    state.baseline = registerPortfolio(
      data,
      state.positions,
      state.capital,
      state.overrides,
    );
    state.baseline.research = structuredClone(state.research);
    state.baseline.mandate = structuredClone(state.mandate);
    state.baseline.execution = structuredClone(state.execution);
    if (state.proposal?.status === "proposed" && !state.proposal.modified)
      state.baseline.capital = state.proposal.trade_plan.investableCapital;
    state.acknowledged = [];
    state.baseline.proposal = state.proposal
      ? JSON.parse(JSON.stringify(state.proposal))
      : null;
    state.baseline.projection_settings = { ...state.settings };
    persist();
    navigate("overview");
    toast("Composición registrada con precios y fundamentos de referencia.");
  }
  if (action === "notifications") {
    if (typeof Notification === "undefined" || !isSecureContext) {
      toast("Este navegador no permite avisos en esta página.");
      return;
    }
    const permission = await Notification.requestPermission();
    toast(
      permission === "granted"
        ? "Avisos activados mientras esta página permanezca abierta."
        : "Los avisos no se activaron. Las revisiones siguen visibles en Seguimiento.",
    );
  }
  if (action === "methodology")
    showModal("METODOLOGÍA", views().methodologyView());
  if (action === "help")
    showModal("ATAJOS DE TECLADO", views().shortcutsView());
  if (action === "export") portfolioExport();
  if (action === "export-research") exportResearch();
  if (action === "export-forecast") {
    if (!state.forecast) {
      toast("Espera a que termine la simulación.");
      return;
    }
    download(
      "trading-proyeccion.json",
      JSON.stringify(
        {
          price_as_of: data.price_as_of,
          capital: state.capital,
          positions: state.positions,
          forecast: state.forecast,
          validation: state.validation,
        },
        null,
        2,
      ),
    );
  }
  if (action === "resimulate") {
    runForecast();
    toast("Simulación recalculada con semilla reproducible.");
  }
  if (action === "equal") {
    state.positions = state.positions.map((p) => ({
      ...p,
      weight: 1 / state.positions.length,
    }));
    changePositions();
  }
  if (action === "normalize") {
    state.positions = normalizeWeights(state.positions);
    changePositions();
  }
  if (action === "import-portfolio") importFile("portfolio");
  if (action === "import-snapshot") importFile("snapshot");
  if (action === "reset-valuation") {
    delete state.overrides[state.selected];
    state.method = "pe";
    runForecast();
  }
  if (action === "clear-filters") {
    state.filters = { text: "", sector: "all", discount: false, type: "all" };
    render();
  }
  if (action === "reload") {
    try {
      const previous = monitoring()?.alerts.map((a) => a.id) || [];
      await loadData();
      notifyReview(previous);
      state.forecast = null;
      closeModal();
      runForecast();
      toast("Corte publicado cargado: " + dateLabel(data.price_as_of));
    } catch (e) {
      toast(e.message);
    }
  }
});
document.addEventListener("input", (event) => {
  const el = event.target;
  if (el.dataset.weight) {
    const value = Number(el.value);
    if (el.value !== "" && finite(value) && value >= 0 && value <= 100) {
      state.positions = state.positions.map((p) =>
        p.symbol === el.dataset.weight ? { ...p, weight: value / 100 } : p,
      );
      job++;
      state.busy = false;
      state.forecast = null;
      state.validation = null;
      clearTimeout(weightTimer);
      weightTimer = setTimeout(() => {
        persist();
        runForecast();
      }, 350);
    }
  }
  if (el.id === "research-search") {
    state.filters.text = el.value;
    $("#screener-table").innerHTML = renderTable(filteredAssets());
  }
  if (el.dataset.assumption) {
    const key = el.dataset.assumption;
    $("#output-" + key).textContent =
      fmt(Number(el.value), key === "multiple" || key === "horizon" ? 0 : 1) +
      (key === "multiple" ? "x" : key === "horizon" ? "a" : "%");
  }
  if (el.id === "command-input") {
    const query = el.value.trim().toLowerCase(),
      r = $("#command-results");
    if (!query) {
      r.hidden = true;
      return;
    }
    const matches = data.assets
      .filter((a) => `${a.symbol} ${a.name}`.toLowerCase().includes(query))
      .slice(0, 5);
    const sections = NAV.filter((n) => n[1].toLowerCase().includes(query));
    r.innerHTML = views().commandResults(matches, sections);
    r.hidden = false;
  }
});
document.addEventListener('toggle',event=>{
  if(event.target.matches?.('.price-monitor'))state.priceMonitorOpen=event.target.open;
},true);
document.addEventListener("change", async (event) => {
  if(event.target.id==='price-monitor-filter'){
    const value=event.target.value;
    if(['all','price_only','held','events'].includes(value)){
      state.priceMonitorFilter=value;state.priceMonitorOpen=true;render();
    }
    return;
  }
  const el = event.target;
  if (el.dataset.scope) {
    try {
      const scope = el.dataset.scope,
        key = el.dataset.key,
        symbol = el.dataset.symbol;
      if (el.type === "number" && !el.checkValidity())
        throw new Error("Revisa el rango del campo.");
      const value =
        el.type === "checkbox"
          ? el.checked
          : el.type === "number"
            ? el.value === ""
              ? null
              : Number(el.value) / Number(el.dataset.scale || 1)
            : el.value;
      if (scope === "holding")
        state.account.positions = state.account.positions.map((p) =>
          p.symbol === symbol ? { ...p, [key]: value } : p,
        );
      else if (scope === "research")
        state.research[symbol] = validateResearch({
          ...state.research[symbol],
          [key]: value,
        });
      else if (scope === "assetAssumptions")
        state.assetAssumptions[symbol] = {
          ...state.assetAssumptions[symbol],
          [key]: value,
        };
      else if (scope === "regime")
        state.macroRegimes = state.macroRegimes.map((r) =>
          r.id === symbol ? { ...r, [key]: value } : r,
        );
      else if (scope === "setting") state.settings[key] = value;
      else if (scope === "mandate" && key === "withdrawalsText") {
        const withdrawals = String(value)
          .split(/\n/)
          .map((row) => row.trim())
          .filter(Boolean)
          .map((row) => {
            const [date, amount] = row.split(",").map((x) => x.trim());
            return { date, amount: Number(amount) };
          });
        const next = { ...state.mandate, withdrawals };
        mandate(next);
        state.mandate = next;
      } else if (
        scope === "mandate" ||
        scope === "execution" ||
        scope === "account"
      ) {
        state[scope] = { ...state[scope], [key]: value };
        if (scope === "mandate" && key === "horizon")
          state.settings.horizon = value;
      }
      state.forecast = null;
      if (state.proposal) state.proposal.modified = true;
      job++;
      state.busy = false;
      persist();
      render();
    } catch (error) {
      toast(error.message);
      render();
    }
    return;
  }
  if (el.dataset.compositionRule) {
    const value = Number(el.value) / Number(el.dataset.scale);
    if (!el.checkValidity() || !finite(value)) {
      toast("Revisa el rango permitido del límite.");
      render();
      return;
    }
    state.compositionRules[el.dataset.compositionRule] = value;
    if (state.proposal) state.proposal.modified = true;
    persist();
    render();
    return;
  }
  if (el.dataset.rule) {
    const value = Number(el.value);
    if (value >= 1 && value <= 100) {
      state.rules[el.dataset.rule] = value / 100;
      persist();
      render();
    } else toast("El umbral debe estar entre 1 y 100.");
  }
  if (el.dataset.weight) {
    clearTimeout(weightTimer);
    const value = Number(el.value);
    if (!finite(value) || value < 0 || value > 100) {
      toast("El peso debe estar entre 0% y 100%.");
      render();
      return;
    }
    state.positions = state.positions.map((p) =>
      p.symbol === el.dataset.weight ? { ...p, weight: value / 100 } : p,
    );
    changePositions();
  }
  if (el.id === "capital-input") {
    const value = Number(el.value);
    if (value > 0 && value <= 1e9) {
      state.capital = value;
      render();
    } else {
      toast("Ingresa un capital positivo, hasta USD 1,000 millones.");
      render();
    }
  }
  if (el.id === "sector-filter") {
    state.filters.sector = el.value;
    $("#screener-table").innerHTML = renderTable(filteredAssets());
  }
  if (el.id === "type-filter") {
    state.filters.type = el.value;
    $("#screener-table").innerHTML = renderTable(filteredAssets());
  }
  if (el.id === "discount-filter") {
    state.filters.discount = el.checked;
    $("#screener-table").innerHTML = renderTable(filteredAssets());
  }
  if (el.id === "valuation-asset") {
    state.selected = el.value;
    state.method = "pe";
    render();
  }
  if (el.dataset.assumption) {
    const key = el.dataset.assumption;
    state.overrides[state.selected] = {
      ...override(state.selected),
      [key]: Number(el.value) / Number(el.dataset.scale),
    };
    state.forecast = null;
    runForecast();
  }
  if (el.dataset.setting) {
    const key = el.dataset.setting;
    const value = el.dataset.scale
      ? Number(el.value) / Number(el.dataset.scale)
      : el.hasAttribute("data-numeric")
        ? Number(el.value)
        : el.value;
    if (el.type === "number" && !el.checkValidity()) {
      toast("Revisa el rango permitido del parámetro.");
      render();
      return;
    }
    state.settings[key] = value;
    if (key === "horizon") state.mandate.horizon = value;
    if(["dividendPolicy","dividendWithholding","cashYield"].includes(key)){
      const next={...state.mandate,[key]:value};
      try { mandate(next); }
      catch(error){ toast(error.message); render(); return; }
      state.mandate=next;
    }
    if(state.proposal)state.proposal.modified=true;
    persist();
    state.forecast = null;
    runForecast();
  }
  if (el.id === "import-file" && el.files[0]) {
    try {
      if (el.files[0].size > 100e6)
        throw new Error("El archivo supera 100 MB.");
      const input = JSON.parse(await el.files[0].text());
      if (importKind === "snapshot") {
        data = withCashAsset(validateSnapshot(input));
        state.proposal = null;
        state.compositionError =
          "Corte importado. Debes recalcular la propuesta con los datos de este archivo.";
        statsCache.clear();
        state.positions = state.positions.filter((p) => asset(p.symbol));
        toast("Corte importado para esta sesión.");
      } else {
        if (
          input.version !== 1 ||
          !Array.isArray(input.positions) ||
          input.positions.length > 100 ||
          input.positions.some(
            (p) =>
              !asset(p.symbol) ||
              !finite(p.weight) ||
              p.weight < 0 ||
              p.weight > 1,
          ) ||
          new Set(input.positions.map((p) => p.symbol)).size !==
            input.positions.length
        )
          throw new Error(
            "La cartera contiene posiciones inválidas o fuera del universo.",
          );
        state.positions = input.positions.map(({ symbol, weight }) => ({
          symbol,
          weight,
        }));
        if (input.mandate) state.mandate = mandate(input.mandate);
        if (input.execution) state.execution = execution(input.execution);
        if (input.macroRegimes)
          state.macroRegimes = regimes(input.macroRegimes);
        if (input.research) {
          for (const value of Object.values(input.research))
            validateResearch(value);
          state.research = input.research;
        }
        if (
          input.assetAssumptions &&
          typeof input.assetAssumptions === "object"
        )
          state.assetAssumptions = input.assetAssumptions;
        if (input.account) {
          currentAccount(
            data,
            input.account,
            null,
            input.capital || state.capital,
          );
          state.account = input.account;
        }
        if (input.journal) {
          if (
            !Array.isArray(input.journal) ||
            input.journal.length > 10000 ||
            input.journal.some(
              (r) =>
                !r.origin?.positions ||
                !r.prediction ||
                !/^\d{4}-\d{2}-\d{2}$/.test(r.target_date),
            )
          )
            throw new Error("Registro de previsiones no válido.");
          state.journal = input.journal;
        }
        if (input.capital > 0 && input.capital <= 1e9)
          state.capital = input.capital;
        if (input.overrides && typeof input.overrides === "object") {
          for (const [symbol, assumptions] of Object.entries(input.overrides)) {
            if (
              asset(symbol) &&
              assumptions &&
              finite(assumptions.growth) &&
              assumptions.growth > -0.9 &&
              assumptions.growth <= 2 &&
              assumptions.multiple > 0 &&
              assumptions.multiple <= 100 &&
              assumptions.discount > 0 &&
              assumptions.discount < 1 &&
              assumptions.horizon >= 1 &&
              assumptions.horizon <= 5
            )
              state.overrides[symbol] = {
                growth: assumptions.growth,
                multiple: assumptions.multiple,
                discount: assumptions.discount,
                horizon: assumptions.horizon,
              };
          }
        }
        if (input.settings) {
          const allowed = ["gbm", "merton"];
          if (["hybrid","ewma"].includes(input.settings.volatilityMode))
            state.settings.volatilityMode = input.settings.volatilityMode;
          if (allowed.includes(input.settings.model))
            state.settings.model = input.settings.model;
          if (
            finite(input.settings.horizon) &&
            input.settings.horizon >= 0.25 &&
            input.settings.horizon <= 5
          )
            state.settings.horizon = input.settings.horizon;
          if (["fundamental", "manual"].includes(input.settings.driftMode))
            state.settings.driftMode = input.settings.driftMode;
          if (
            finite(input.settings.manualReturn) &&
            input.settings.manualReturn > -0.8 &&
            input.settings.manualReturn <= 1
          )
            state.settings.manualReturn = input.settings.manualReturn;
          for (const [key, min, max] of [
            ["jumpIntensity", 0, 5],
            ["jumpMean", -0.8, 0.5],
            ["jumpVol", 0, 1],
          ]) {
            if (
              finite(input.settings[key]) &&
              input.settings[key] >= min &&
              input.settings[key] <= max
            )
              state.settings[key] = input.settings[key];
          }
          if ([1000, 3000, 5000].includes(input.settings.paths))
            state.settings.paths = input.settings.paths;
          if ([0.94, 0.97, 0.99].includes(input.settings.lambda))
            state.settings.lambda = input.settings.lambda;
          if (
            Number.isInteger(input.settings.seed) &&
            input.settings.seed >= 0 &&
            input.settings.seed <= 4294967295
          )
            state.settings.seed = input.settings.seed;
          for (const key of [
            "fundamentalMarketShare",
            "fundamentalSectorShare",
          ])
            if (
              finite(input.settings[key]) &&
              input.settings[key] >= 0 &&
              input.settings[key] <= 1
            )
              state.settings[key] = input.settings[key];
          if (
            (state.settings.fundamentalMarketShare ?? 0.35) +
              (state.settings.fundamentalSectorShare ?? 0.3) >
            1
          )
            throw new Error("Participaciones de incertidumbre no válidas.");
          if (typeof input.settings.uncertainFundamentals === "boolean")
            state.settings.uncertainFundamentals =
              input.settings.uncertainFundamentals;
        }
        state.proposal = null;
        const proposal = input.proposal;
        if (
          [1, 2].includes(proposal?.version) &&
          proposal.method === "ex-ante-fundamental-monte-carlo" &&
          proposal.model_version === MODEL_VERSION &&
          proposal.status === "proposed" &&
          Array.isArray(proposal.signals) &&
          proposal.signals.length <= 100 &&
          Array.isArray(proposal.positions) &&
          proposal.positions.length <= 100 &&
          proposal.settings &&
          proposal.metrics &&
          proposal.rules &&
          proposal.search &&
          proposal.verification
        )
          state.proposal = proposal;
        for (const key of Object.keys(DEFAULT_COMPOSITION_RULES)) {
          const v = input.compositionRules?.[key];
          if (finite(v) && v > 0 && v <= (key === "maxPositions" ? 12 : 1))
            state.compositionRules[key] = v;
        }
        toast("Cartera importada.");
      }
      if (importKind === "portfolio" && input.baseline) {
        const b = input.baseline;
        if (
          b.version !== 1 ||
          !Array.isArray(b.positions) ||
          !b.positions.length ||
          b.positions.length > 200 ||
          !(b.capital > 0) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(b.as_of) ||
          !Number.isFinite(Date.parse(b.registered_at)) ||
          b.positions.some(
            (p) =>
              !/^[A-Z0-9.^-]{1,12}$/.test(p.symbol) ||
              !finite(p.weight) ||
              p.weight <= 0 ||
              p.weight > 1 ||
              !(p.adj_close > 0) ||
              !(p.price > 0),
          )
        )
          throw new Error("La referencia registrada no es válida.");
        state.baseline = b;
        state.acknowledged = Array.isArray(input.acknowledged)
          ? input.acknowledged
              .filter((x) => typeof x === "string")
              .slice(0, 1000)
          : [];
        if (input.rules)
          for (const key of Object.keys(DEFAULT_RULES))
            if (
              finite(input.rules[key]) &&
              input.rules[key] >= 0.01 &&
              input.rules[key] <= 1
            )
              state.rules[key] = input.rules[key];
      }
      closeModal();
      changePositions();
    } catch (error) {
      toast(error.message || "No se pudo importar el archivo.");
    }
  }
});
document.addEventListener("keydown", (event) => {
  const modal = $(".modal");
  if (event.key === "Escape") {
    closeModal();
    $("#command-results")?.setAttribute("hidden", "");
    return;
  }
  if (modal && event.key === "Tab") {
    const f = [...modal.querySelectorAll("button,a[href],input,select")].filter(
      (el) => !el.disabled,
    );
    if (event.shiftKey && document.activeElement === f[0]) {
      event.preventDefault();
      f.at(-1).focus();
    } else if (!event.shiftKey && document.activeElement === f.at(-1)) {
      event.preventDefault();
      f[0].focus();
    }
    return;
  }
  if (event.key === "Enter" && event.target.id === "command-input") {
    const button = $("#command-results button");
    if (button) {
      event.preventDefault();
      button.click();
    }
    return;
  }
  if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
  if (event.key === "/") {
    event.preventDefault();
    $("#command-input")?.focus();
  }
  const match = NAV.find((n) => n[2] === event.key);
  if (match) {
    event.preventDefault();
    closeModal();
    navigate(match[0]);
  }
});
window.addEventListener("hashchange", () => {
  const view = location.hash.slice(1);
  if (NAV.some((n) => n[0] === view)) {
    state.view = view;
    render();
  }
});
try {
  await Promise.all([loadTemplates(), loadData()]);
  try {
    const stored = await openJournal();
    state.journal = [
      ...new Map(
        [...state.journal, ...stored].map((row) => [row.id, row]),
      ).values(),
    ].sort((a, b) => a.origin.created_at.localeCompare(b.origin.created_at));
    await saveJournal(state.journal);
    journalDBReady = true;
  } catch {
    journalDBReady = false;
  }
  const view = location.hash.slice(1);
  if (NAV.some((n) => n[0] === view)) state.view = view;
  render();
  runForecast();
} catch (error) {
  showStartupError(error);
}
