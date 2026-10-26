import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.7.1";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.7.1";

const market=JSON.parse(readFileSync("dist/data/market.json","utf8"));
const volatility=JSON.parse(readFileSync("dist/data/volatility.json","utf8"));
const snapshot={...market,volatility};
const {settings,overrides,rules}=referenceRequest(snapshot);
const expected=composePortfolio(snapshot,settings,overrides,rules,
  {candidates:300,paths:600,finalPaths:3000});
if(expected.status!=="proposed")throw Error("La referencia no produjo una cartera");
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
  await page.goto("http://127.0.0.1:8813/?build=0.7.1#portfolio",
    {waitUntil:"networkidle",timeout:60000});
  const button=page.locator('[data-action="compose-reference"]');
  await button.waitFor({state:"visible",timeout:45000});
  const actualFooter=await page.locator(".footer-right").innerText();
  if(!actualFooter.includes("v0.7.1") || actualFooter.includes("v0.6.0"))
    throw Error("La etiqueta de versión del pie de página no corresponde al motor: "+
      actualFooter);

  // Simulate a genuine long-lived user workspace: previously selected stock,
  // different seed, tighter reserve cap, custom macro weights and broker holdings.
  await page.evaluate(()=>{
    const key="trading-workspace-v1";
    const stored=JSON.parse(localStorage.getItem(key)||"{}");
    stored.workspaceVersion="0.7.1";
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
  if(!report.includes("MOTOR 0.7.1") && !report.includes("Motor 0.7.1"))
    throw Error("El informe no identifica el motor 0.7.1");
  if(issues.length)throw Error("Errores del navegador: "+issues.join("; "));
  console.log(JSON.stringify({
    browserParity:"PASS",
    expected:expectedWeights,
    rendered:result,
    model:expected.model_version,
    source,retainedUserSettings:true,
    reportExcerpt:report.slice(0,220),
  }));
} finally {
  await browser?.close();
  server.kill();
}
