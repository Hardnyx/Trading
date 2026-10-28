import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { composeMultiStart } from "../dist/assets/js/composer.mjs?v=0.34.1";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.34.1";
import { exposureReport } from "../dist/assets/js/economic-exposure.mjs?v=0.34.1";
import { MODEL_VERSION } from "../dist/assets/js/policy.mjs?v=0.34.1";

const market=JSON.parse(readFileSync("dist/data/market.json","utf8"));
const volatility=JSON.parse(readFileSync("dist/data/volatility.json","utf8"));
const snapshot={...market,volatility};
const {settings,overrides,rules}=referenceRequest(snapshot);
const expected=composeMultiStart(snapshot,settings,overrides,rules,
  {candidates:300,paths:600,finalPaths:3000});
if(!['proposed','hold'].includes(expected.status))throw Error("La referencia no produjo una decisión");
if(expected.status==='proposed'&&expected.diagnostics?.robustDecision?.status!=='passed')
  throw Error('The canonical proposal bypassed the ordinary model-uncertainty decision');
if(expected.diagnostics?.robustDecision&&expected.diagnostics.robustDecision.models.length!==5)
  throw Error('The canonical model comparison is incomplete');
const economicWeights=new Map(expected.positions.map(p=>[p.symbol,p.weight]));
const economic=exposureReport(expected.model_inputs.assets,
  expected.model_inputs.assets.map(a=>economicWeights.get(a.symbol)||0),expected.as_of,
  expected.information_as_of,expected.model_inputs.securitySectors);
if(economic.sleeves.usEquity+economic.sleeves.globalEquity > expected.rules.maxEquity+1e-8)
  throw Error("Equity sleeve exceeded the global risk budget");
if(economic.sleeves.treasury>expected.rules.maxTreasury+1e-8)
  throw Error("Treasury ETF sleeves were not aggregated");
if(expected.positions.some(p=>p.symbol==="SHY"&&p.weight>expected.rules.maxGlobal+1e-8))
  throw Error("SHY bypassed the global position cap");
if(Object.values(economic.issuerUpperBounds).some(w=>
  w>Math.min(expected.rules.maxPosition,expected.rules.maxGlobal)+1e-8) ||
  economic.unclassifiedIssuerWeight>expected.rules.maxPosition+1e-8 ||
  Object.values(economic.sectorUpperBounds).some(w=>w>expected.rules.maxSector+1e-8))
  throw Error("Look-through bounds exceeded issuer or sector limits");
const expectedWeights=Object.fromEntries(expected.positions.map(p=>
  [p.symbol,Math.round(p.weight*1000)/10]));

const server=spawn("python3",["-m","http.server","8813","--directory","dist"],
  {stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let browser;
try {
  for(let i=0;i<50;i++){
    try {const r=await fetch("http://127.0.0.1:8813/");
      if(r.ok)break;}catch{}
    await sleep(100);
  }
  browser=await chromium.launch({headless:true,
    ...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const context=await browser.newContext({viewport:{width:1460,height:1080},locale:"es-PE"});
  const page=await context.newPage();
  const issues=[];
  page.on("pageerror",e=>issues.push(e.message));
  page.on("console",e=>{if(e.type()==="error")issues.push(e.text())});
  await page.goto(`http://127.0.0.1:8813/?build=${MODEL_VERSION}#portfolio`,
    {waitUntil:"networkidle",timeout:60000});
  const button=page.locator('[data-action="compose-reference"]');
  await button.waitFor({state:"visible",timeout:45000});
  const universeChoices=await page.locator('#composition-universe-limit option').allTextContents();
  if(!universeChoices.some(t=>t.includes('80 activos'))||!universeChoices.some(t=>t.includes('60 activos')))
    throw Error('Expanded search budgets are missing from composition controls');
  await page.locator('.price-monitor > summary').click();
  const monitorCount=await page.locator('.price-monitor tbody tr').count();
  if(monitorCount!==snapshot.assets.filter(a=>a.type!=='cash').length)
    throw Error('Price monitor does not cover the complete catalog');
  await page.locator('#price-monitor-filter').selectOption('price_only');
  const monitorText=await page.locator('.price-monitor').innerText();
  if(!monitorText.includes('BPA no conciliado o ausente')||!monitorText.includes('no suministra retornos esperados'))
    throw Error('Price-only observation is conflated with a fundamental signal');
  const monitorLayout=await page.locator('.price-monitor').evaluate(p=>p.scrollWidth<=p.clientWidth+3);
  if(!monitorLayout)throw Error('Price monitor overflows the workspace');
  await page.locator('#price-monitor-filter').selectOption('all');
  await page.locator('.price-monitor > summary').click();
  await page.locator('.financial-coverage > summary').click();
  const coverage=await page.locator('.financial-coverage').innerText();
  if(!coverage.includes('CAPTURA XBRL')||!coverage.includes('PERÍODO BPA'))
    throw Error('Missing financial reporting provenance');
  const coverageCount=await page.locator('.financial-coverage tbody tr').count();
  if(coverageCount!==snapshot.assets.filter(a=>a.type==='stock').length)
    throw Error('Financial coverage does not include the stock universe');
  await page.locator('.financial-coverage > summary').click();
  const actualFooter=await page.locator(".footer-right").innerText();
  if(!actualFooter.includes('v'+MODEL_VERSION) || actualFooter.includes("v0.6.0"))
    throw Error("La etiqueta de versión del pie de página no corresponde al motor: "+
      actualFooter);

  // Simulate a genuine long-lived user workspace: previously selected stock,
  // different seed, tighter reserve cap, custom macro weights and broker holdings.
  await page.evaluate(modelVersion=>{
    const key="trading-workspace-v1";
    const stored=JSON.parse(localStorage.getItem(key)||"{}");
    stored.workspaceVersion=modelVersion;
    stored.positions=[{symbol:"NVDA",weight:1}];
    stored.settings={...stored.settings,seed:20261025,volatilityMode:"ewma"};
    stored.compositionRules={...stored.compositionRules,reserveCap:0.1,
      maxPosition:0.1};
    stored.account={enabled:true,cash:95000,positions:[
      {symbol:"NVDA",quantity:3,costBasis:100}
    ]};
    localStorage.setItem(key,JSON.stringify(stored));
  },MODEL_VERSION);
  await page.reload({waitUntil:"networkidle"});
  await button.waitFor({state:"visible",timeout:45000});
  const baselineStorage=await page.evaluate(()=>{
    const raw=localStorage.getItem("trading-workspace-v1");
    const state=raw?JSON.parse(raw):{};
    return {positions:state.positions||[],baseline:state.baseline||null,
      account:state.account||null,settings:state.settings||null,
      compositionRules:state.compositionRules||null,
      macroRegimes:state.macroRegimes||null,
      mandate:state.mandate||null};
  });
  await button.click();
  const decision=page.locator('.decision-section').filter({has:
    page.getByRole('heading',{name:'DECISIÓN DESDE LA CARTERA ACTUAL',exact:true})});
  await decision.waitFor({state:'visible',timeout:480000});
  const observed=await page.evaluate(()=>{
    const p=JSON.parse(localStorage.getItem('trading-workspace-v1')).proposal;
    return {status:p.status,positions:p.positions,reason:p.reason,cost:p.trade_plan?.total,
      gate:p.diagnostics?.robustDecision?.status};
  });
  if(observed.status!==expected.status||observed.gate!==expected.diagnostics?.robustDecision?.status)
    throw Error('The browser decision differs from the canonical model gate');
  let result,source,report,calendarRows=0;
  const expectedDividendRows=expected.status==='proposed'?(expected.metrics?.dividendTiming||[])
    .filter(r=>r.mode==='issuer-calendar').reduce((n,r)=>n+Math.min(6,r.events.length),0):0;
  if(expected.status==='proposed') {
    await page.locator('.composition-report').waitFor({state:'visible'});
    const rendered=await page.locator(".composition-positions tbody tr").evaluateAll(rows=>
      rows.map(row=>({
        symbol:row.querySelector("td")?.textContent?.trim(),
        weight:row.querySelectorAll("td")[1]?.textContent?.trim(),
      })));
    result=Object.fromEntries(rendered.map(row=>[
      row.symbol, Number(row.weight.replace("%","").replace(",",".").trim())]));
    source=await page.locator(".composition-source").innerText();
    report=await page.locator(".composition-report").innerText();
    const riskCards=await page.locator('.composition-metrics').innerText();
    if(!riskCards.includes('CVAR 95% · COTA MC')||!riskCards.includes('sin calibración predictiva'))
      throw Error('Primary risk metrics hide sampling uncertainty or predictive limits');
    if(!(await page.locator('body').innerText()).includes('MEJORA MÍNIMA · CINCO MODELOS'))
      throw Error('The ordinary decision omits model-uncertainty evidence');
    const roles=await page.locator('.composition-positions .composition-role').allTextContents();
    if(roles.length!==expected.positions.length||roles.some(t=>t.length>95||t.includes('captura XBRL')||t.includes('Supuestos:')))
      throw Error('The primary allocation table is no longer concise');
    if(!(await page.locator('.composition-cash-explanation').innerText()).includes('reserva exigida'))
      throw Error('The report does not explain the cash allocation');
    const layout=await page.locator(".composition-report").evaluate(panel=>{
      const source=panel.querySelector(":scope > .composition-source");
      const contributions=panel.querySelector(".composition-contributions");
      const brief=panel.querySelector(".composition-brief");
      const methods=panel.querySelector("details.composition-method");
      const style=e=>e?getComputedStyle(e):null;
      return {
        sourcePadding:Number.parseFloat(style(source)?.paddingLeft||"0"),
        // Tables run edge to edge; what must keep its inset is the content:
        // container padding plus the heading's and first cell's own padding.
        contributionsPadding:Number.parseFloat(style(contributions)?.paddingLeft||"0")+
          Math.min(...[contributions?.querySelector("h3"),contributions?.querySelector("th, td")]
            .map(e=>Number.parseFloat(style(e)?.paddingLeft||"0"))),
        briefPadding:Number.parseFloat(style(brief)?.paddingLeft||"0"),
        technicalOpen:methods?.open,
        hasGlobalCap:panel.textContent?.includes("Límite global"),
        cashDividendSummary:panel.textContent?.includes("Dividendos netos"),
        issuerSummary:panel.textContent?.includes("Emisores conocidos (directo + ETF)"),
      };
    });
    if(layout.sourcePadding<8 || layout.contributionsPadding<8 ||
       layout.briefPadding<8 || layout.technicalOpen===true ||
       !layout.hasGlobalCap || !layout.cashDividendSummary || !layout.issuerSummary)
      throw Error("La composición perdió espacios o faltan controles de concentración/ingresos: "+JSON.stringify(layout));

    // The ETF look-through table must remain tucked inside the technical panel,
    // with a horizontal scroll container rather than overflowing the workspace.
    await page.locator(".composition-report details.composition-method > summary").click();
    if(expected.diagnostics?.stability?.method==='robust-finite-pool'&&expected.diagnostics.stability.unresolved>0){
      const ranges=await page.locator('.composition-weight-ranges tbody tr').allTextContents();
      if(ranges.length!==expected.diagnostics.stability.ranges.length||
         !report.includes('Identificación de pesos')||!report.includes('capacidad predictiva'))
        throw Error('The rendered proposal hides unresolved allocation weights');
    }
    const lookthrough=await page.locator(".composition-etf-holdings").evaluate(table=>{
      const wrapper=table.closest(".table-wrap"),panel=table.closest(".composition-report");
      return {rows:table.querySelectorAll("tbody tr").length,
        inset:parseFloat(getComputedStyle(wrapper).paddingLeft)||0,
        width:table.scrollWidth,wrapperWidth:wrapper.clientWidth,
        parentOverflows:panel.scrollWidth>panel.clientWidth+3,
        sourceLinks:[...table.querySelectorAll("a")].every(a=>
          a.href.startsWith("https://")&&a.target==="_blank"),
      };
    });
    const expectedFunds=expected.diagnostics?.economicExposure?.funds?.length||0;
    const stockAssumptions=await page.locator('.composition-valuation-details .composition-valuation-evidence')
      .allTextContents();
    if(stockAssumptions.filter(t=>t.includes('Supuestos:')).length!==
        expected.signals.filter(s=>s.filed&&s.valuationEvidence).length ||
       stockAssumptions.some(t=>t.includes('Supuestos:')&&
         (!/P\/E (de salida|actual [\d.,]+ → salida)/.test(t)||!t.includes('Sin calibración predictiva'))))
      throw Error('La composición oculta los supuestos de valoración');
    if(lookthrough.rows!==expectedFunds || lookthrough.parentOverflows ||
       !lookthrough.sourceLinks)
      throw Error("ETF holdings report geometry or provenance failed: "+
        JSON.stringify({lookthrough,expectedFunds}));
    calendarRows=await page.locator('.composition-dividend-calendar tbody tr').count();
    if(calendarRows!==expectedDividendRows)
      throw Error("Calendario de dividendos distinto entre motor y pantalla");
  } else {
    result=Object.fromEntries(observed.positions.map(p=>[p.symbol,Math.round(p.weight*1000)/10]));
    source=await page.locator('.notice').filter({hasText:expected.reason}).innerText();
    report=await decision.innerText();
    if(observed.cost!==0||!report.includes('Mantener')||!report.includes(expected.reason)||
       !await page.locator('[data-action="apply-proposal"]').isDisabled()||
       await page.locator('.composition-report').count())
      throw Error('Holding must preserve positions, zero operations and a visible reason');
    const audit=expected.diagnostics?.robustDecision;
    if(audit) {
      if(!report.includes('MEJORA MÍNIMA · CINCO MODELOS'))throw Error('Holding hides its model comparison');
      for(const row of audit.models)for(const failure of row.failures)
        if(!report.includes(`No · ${row.failures.join(', ')}`))throw Error('Holding hides a model risk rejection: '+failure);
    }
  }
  mkdirSync("out",{recursive:true});
  await page.screenshot({path:"out/browser-parity.png",fullPage:true});
  if(!source.includes("CONFIGURACIÓN BASE"))
    throw Error("La vista no identifica el origen de la referencia: "+source);
  for(const [symbol,weight] of Object.entries(expectedWeights)){
    if(Math.abs((result[symbol]??NaN)-weight)>.11)
      throw Error(`Desajuste en ${symbol}: vista=${result[symbol]}, motor=${weight}`);
  }
  if(Object.keys(result).length!==Object.keys(expectedWeights).length)
    throw Error("Número de posiciones diferente: "+JSON.stringify(result));
  const afterStorage=await page.evaluate(()=>{
    const state=JSON.parse(localStorage.getItem("trading-workspace-v1")||"{}");
    return {positions:state.positions||[],baseline:state.baseline||null,
      account:state.account||null,settings:state.settings||null,
      compositionRules:state.compositionRules||null,
      macroRegimes:state.macroRegimes||null,
      mandate:state.mandate||null};
  });
  if(JSON.stringify(baselineStorage)!==JSON.stringify(afterStorage))
    throw Error("La comparación base alteró las posiciones o preferencias");
  if(baselineStorage.settings.seed!==20261025 ||
     baselineStorage.compositionRules.reserveCap!==0.1 ||
     baselineStorage.account.positions[0].symbol!=="NVDA")
    throw Error("La prueba no restauró realmente la sesión personalizada");
  const detailedReport=await page.locator('body').innerText();
  if(!detailedReport.includes('MOTOR '+MODEL_VERSION) && !detailedReport.includes('Motor '+MODEL_VERSION))
    throw Error('El informe no identifica el motor '+MODEL_VERSION);
  // The real worker must compare the preserved session and keep all account
  // quantities, settings and working weights unchanged.
  await page.locator('[data-action="compare-robustness"]').click();
  await page.locator('.robustness-scenarios').waitFor({state:'visible',timeout:240000});
  const robust=await page.evaluate(()=>JSON.parse(localStorage.getItem('trading-workspace-v1')).robustness);
  if(robust.scenarios.length!==5||robust.snapshot_generated_at!==
      snapshot.generated_at)
    throw Error('Robustness report lost its scenario set or input vintage');
  const robustText=await page.locator('.robustness-report').innerText();
  if(!robustText.includes('EXPERIMENTAL')||!robustText.includes('MEDIANA · MANTENER')||
     !robustText.includes('LÍMITE INFERIOR MC'))throw Error('Missing robust comparison evidence');
  if(!robust.candidate?.transition?.reconciled ||
     Math.abs(robust.candidate.transition.total-robust.candidate.cost)>1e-6)
    throw Error('Transition costs or cash do not reconcile with the evaluated candidate');
  await page.locator('.robustness-transition > summary').click();
  const transition=await page.locator('.robustness-transition').innerText();
  if(!transition.includes('Conciliación verificada') || !transition.includes('CANTIDAD EST.'))
    throw Error('The transition hides quantities or cash reconciliation');
  const transitionLayout=await page.locator('.robustness-report').evaluate(panel=>
    ({overflows:panel.scrollWidth>panel.clientWidth+3,
      rows:panel.querySelectorAll('.robustness-transition tbody tr').length}));
  if(transitionLayout.overflows || transitionLayout.rows!==robust.candidate.transition.positions.length)
    throw Error('Transition layout or positions are incomplete');
  const retained=await page.evaluate(()=>{
    const s=JSON.parse(localStorage.getItem('trading-workspace-v1'));
    return {positions:s.positions||[],baseline:s.baseline||null,account:s.account||null,
      settings:s.settings||null,compositionRules:s.compositionRules||null,
      macroRegimes:s.macroRegimes||null,mandate:s.mandate||null};
  });
  if(JSON.stringify(retained)!==JSON.stringify(baselineStorage))throw Error('Robustness comparison altered the session');
  await page.screenshot({path:'out/browser-robustness.png',fullPage:true});
  await page.locator('#capital-input').fill('120000');
  await page.locator('#capital-input').dispatchEvent('change');
  await page.getByText('Comparación robusta desactualizada:',{exact:false}).waitFor({state:'visible',timeout:15000});
  if(await page.locator('[data-action="use-robust-weights"]').count())throw Error('Stale robust weights remain applicable');
  await page.locator('[data-view="valuation"]').click();
  await page.locator('#valuation-asset').selectOption('AAPL');
  const growthPanel=page.locator('.decision-section').filter({has:
    page.getByRole('heading',{name:'EVIDENCIA DEL CRECIMIENTO',exact:true})});
  await growthPanel.waitFor({state:'visible'});
  const growthText=await growthPanel.innerText();
  const history=snapshot.assets.find(a=>a.symbol==='AAPL').financials?.earnings_history;
  const periods=new Set((history?.records||[]).map(r=>r.period_end)).size;
  if(!growthText.includes(`${periods} ejercicios`)||
     !growthText.includes('Sin vintage predictivo verificado')||
     !growthText.includes('sin ajuste automático del ancla'))
    throw Error('Annual EPS evidence lost coverage, provenance or research status');
  if(await growthPanel.evaluate(panel=>panel.scrollWidth>panel.clientWidth+3))
    throw Error('Growth evidence overflows its panel');
  await growthPanel.screenshot({path:'out/browser-growth-evidence.png'});
  if(issues.length)throw Error("Errores del navegador: "+issues.join("; "));
  console.log(JSON.stringify({
    browserParity:"PASS",
    decision:observed.status,gate:observed.gate,
    browserVersion:browser.version(),
    browserChannel:process.env.PLAYWRIGHT_CHANNEL||"bundled-chromium",
    calendarRows,expectedDividendRows,
    expected:expectedWeights,
    rendered:result,
    model:expected.model_version,
    equity_exposure:economic.sleeves.usEquity+economic.sleeves.globalEquity,
    treasury_exposure:economic.sleeves.treasury,
    source,retainedUserSettings:true,
    reportExcerpt:report.slice(0,220),
  }));
} finally {
  await browser?.close();
  server.kill();
}
