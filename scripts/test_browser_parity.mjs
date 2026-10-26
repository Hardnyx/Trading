import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.8.2";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.8.2";
import { exposureReport } from "../dist/assets/js/economic-exposure.mjs?v=0.8.2";

const market=JSON.parse(readFileSync("dist/data/market.json","utf8"));
const volatility=JSON.parse(readFileSync("dist/data/volatility.json","utf8"));
const snapshot={...market,volatility};
const {settings,overrides,rules}=referenceRequest(snapshot);
const expected=composePortfolio(snapshot,settings,overrides,rules,
  {candidates:300,paths:600,finalPaths:3000});
if(expected.status!=="proposed")throw Error("La referencia no produjo una cartera");
const economicWeights=new Map(expected.positions.map(p=>[p.symbol,p.weight]));
const economic=exposureReport(expected.model_inputs.assets,
  expected.model_inputs.assets.map(a=>economicWeights.get(a.symbol)||0),expected.as_of);
if(economic.sleeves.usEquity+economic.sleeves.globalEquity > expected.rules.maxEquity+1e-8)
  throw Error("Equity sleeve exceeded the global risk budget");
if(economic.sleeves.treasury>expected.rules.maxTreasury+1e-8)
  throw Error("Treasury ETF sleeves were not aggregated");
if(expected.positions.some(p=>p.symbol==="SHY"&&p.weight>expected.rules.maxGlobal+1e-8))
  throw Error("SHY bypassed the global position cap");
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
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1460,height:1080},locale:"es-PE"});
  const page=await context.newPage();
  const issues=[];
  page.on("pageerror",e=>issues.push(e.message));
  page.on("console",e=>{if(e.type()==="error")issues.push(e.text())});
  await page.goto("http://127.0.0.1:8813/?build=0.8.2#portfolio",
    {waitUntil:"networkidle",timeout:60000});
  const button=page.locator('[data-action="compose-reference"]');
  await button.waitFor({state:"visible",timeout:45000});
  const actualFooter=await page.locator(".footer-right").innerText();
  if(!actualFooter.includes("v0.8.2") || actualFooter.includes("v0.6.0"))
    throw Error("La etiqueta de versión del pie de página no corresponde al motor: "+
      actualFooter);

  // Simulate a genuine long-lived user workspace: previously selected stock,
  // different seed, tighter reserve cap, custom macro weights and broker holdings.
  await page.evaluate(()=>{
    const key="trading-workspace-v1";
    const stored=JSON.parse(localStorage.getItem(key)||"{}");
    stored.workspaceVersion="0.8.2";
    stored.positions=[{symbol:"NVDA",weight:1}];
    stored.settings={...stored.settings,seed:20261025,volatilityMode:"ewma"};
    stored.compositionRules={...stored.compositionRules,reserveCap:0.1,
      maxPosition:0.1};
    stored.account={enabled:true,cash:95000,positions:[
      {symbol:"NVDA",quantity:3,costBasis:100}
    ]};
    localStorage.setItem(key,JSON.stringify(stored));
  });
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
  await page.locator(".composition-report").waitFor({state:"visible",timeout:180000});
  const rendered=await page.locator(".composition-report tbody tr").evaluateAll(rows=>
    rows.map(row=>({
      symbol:row.querySelector("td")?.textContent?.trim(),
      weight:row.querySelectorAll("td")[1]?.textContent?.trim(),
    })));
  const result=Object.fromEntries(rendered.map(row=>[
    row.symbol, Number(row.weight.replace("%","").replace(",",".").trim())]));
  const source=await page.locator(".composition-source").innerText();
  const report=await page.locator(".composition-report").innerText();
  const layout=await page.locator(".composition-report").evaluate(panel=>{
    const source=panel.querySelector(":scope > .composition-source");
    const contributions=panel.querySelector(".composition-contributions");
    const brief=panel.querySelector(".composition-brief");
    const methods=panel.querySelector("details.composition-method");
    const style=e=>e?getComputedStyle(e):null;
    return {
      sourcePadding:Number.parseFloat(style(source)?.paddingLeft||"0"),
      contributionsPadding:Number.parseFloat(style(contributions)?.paddingLeft||"0"),
      briefPadding:Number.parseFloat(style(brief)?.paddingLeft||"0"),
      technicalOpen:methods?.open,
      hasGlobalCap:panel.textContent?.includes("Límite global"),
      cashDividendSummary:panel.textContent?.includes("Dividendos netos"),
    };
  });
  if(layout.sourcePadding<8 || layout.contributionsPadding<8 ||
     layout.briefPadding<8 || layout.technicalOpen===true ||
     !layout.hasGlobalCap || !layout.cashDividendSummary)
    throw Error("La composición perdió espacios o faltan controles de concentración/ingresos: "+JSON.stringify(layout));

  // The ETF look-through table must remain tucked inside the technical panel,
  // with a horizontal scroll container rather than overflowing the workspace.
  await page.locator(".composition-report details.composition-method > summary").click();
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
  if(lookthrough.rows!==expectedFunds || lookthrough.parentOverflows ||
     !lookthrough.sourceLinks)
    throw Error("ETF holdings report geometry or provenance failed: "+
      JSON.stringify({lookthrough,expectedFunds}));
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
  if(!report.includes("MOTOR 0.8.2") && !report.includes("Motor 0.8.2"))
    throw Error("El informe no identifica el motor 0.8.2");
  if(issues.length)throw Error("Errores del navegador: "+issues.join("; "));
  console.log(JSON.stringify({
    browserParity:"PASS",
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
