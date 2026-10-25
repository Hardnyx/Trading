import { readFileSync } from "node:fs";
import { preparePaths, generatePaths } from "../dist/assets/js/path-model.mjs?v=0.5.0";
import { BASE_REGIME } from "../dist/assets/js/path-model.mjs?v=0.5.0";
import { composePortfolio, prepareComposition } from "../dist/assets/js/composer.mjs?v=0.5.0";

const market=JSON.parse(readFileSync(new URL("../dist/data/market.json",import.meta.url)));
const vol=JSON.parse(readFileSync(new URL("../dist/data/volatility.json",import.meta.url)));
if(vol.schema_version!==1 || vol.as_of!==market.price_as_of ||
   vol.source_market_generated_at!==market.generated_at)
  throw Error("La calibración no corresponde al corte de mercado");

const ids=["SPY","QQQ","TLT","SHY","GLD","NVDA","NFLX"];
const assets=ids.map(id=>market.assets.find(a=>a.symbol===id));
if(assets.some(a=>!a)) throw Error("Activos de diagnóstico ausentes");
const baseOptions={
  asOf:market.price_as_of,
  informationAsOf:market.requested_as_of || market.price_as_of,
  model:"merton",volatilityMode:"hybrid",
  volatilityData:vol,horizon:.25,paths:100,seed:20261025,
  macroRegimes:[BASE_REGIME],
};
const hybrid=preparePaths(assets,baseOptions,{},market.assets);
const expectedAccepted=ids.filter(id=>vol.instruments[id]?.status==="accepted").length;
if(hybrid.conditional.active!==expectedAccepted)
  throw Error("El número de calibraciones GJR activas no concuerda con la publicación");
if(!hybrid.conditional.dynamic)
  throw Error("El modo híbrido debe utilizar EWMA diario incluso sin GJR aceptado");
if(hybrid.conditional.active+hybrid.conditional.fallback!==assets.length)
  throw Error("Pérdida de activos en selección de riesgo");
const ewma=preparePaths(assets,{...baseOptions,volatilityMode:"ewma"}, {}, market.assets);
if(ewma.conditional.enabled)throw Error("El control EWMA quedó alterado");
const generated=generatePaths(hybrid,100,20261025,52);
for(const series of generated.gross)
  if(!Array.from(series).every(v=>Number.isFinite(v)&&v>0))
    throw Error("Se generaron precios inválidos");
const legacy=generatePaths(ewma,100,20261025,52);
const full=process.env.TRADING_FULL_DIAGNOSTIC==="1";
const budget=full?{candidates:300,paths:600,finalPaths:3000}
  :{candidates:45,paths:100,finalPaths:200};
const compositionInputs=prepareComposition(market,{
  ...baseOptions,horizon:1,capital:100000,
}, {}, {});
if(!compositionInputs.conditional.dynamic ||
    compositionInputs.selection.simulated>40)
  throw Error("El compositor abandonó el riesgo condicional o superó el límite de muestra");
const blockedGold=compositionInputs.excluded.find(x=>x.symbol==="GLD");
if(!blockedGold || !blockedGold.reason.includes("retorno esperado fundamentado"))
  throw Error("El optimizador sigue aceptando GLD con el retorno genérico del 6%");

const began=Date.now();
const decision=composePortfolio(market,{
  ...baseOptions,horizon:1,capital:100000,
}, {}, {}, budget);
if(decision.positions?.some(p=>p.symbol==="GLD"))
  throw Error("Se propone GLD sin una expectativa económica verificada");
if(!["proposed","hold","no_feasible"].includes(decision.status))
  throw Error("Estado inválido del compositor");
const benchmarkDecision=composePortfolio(market,{
  ...baseOptions,volatilityMode:"ewma",horizon:1,capital:100000,
}, {}, {}, budget);
console.log(JSON.stringify({
  comparison:"same-cut-same-seed-different-risk-engine",
  GJR:{status:decision.status,positions:decision.positions,
    cvar:decision.metrics?.cvar95,median:decision.metrics?.medianReturn},
  EWMA:{status:benchmarkDecision.status,positions:benchmarkDecision.positions,
    cvar:benchmarkDecision.metrics?.cvar95,median:benchmarkDecision.metrics?.medianReturn},
}));
console.log(JSON.stringify({
  integration:"complete-portfolio-composition",
  model:compositionInputs.conditional.mode,
  validated:compositionInputs.conditional.active,
  fallback:compositionInputs.conditional.fallback,
  status:decision.status,
  simulated:compositionInputs.selection.simulated,
  scenarios:decision.search?.evaluated,
  elapsedSeconds:Math.round((Date.now()-began)/1000),
}));
console.log(JSON.stringify({
  cut:vol.as_of,reportedCount:vol.summary,
  instruments:ids.map((symbol,i)=>({
    symbol,
    model:hybrid.conditional.fits[i]?"GJR-t":"EWMA",
    nextAnnualizedVol:Math.sqrt(hybrid.covariance[i][i]),
  })),
  simulation:{paths:100,steps:generated.steps,correlated:true,
    GJRvsEWMA:generated.gross[0][generated.steps]-
      legacy.gross[0][legacy.steps]},
  newsAttribution:"No automatic attribution; shocks remain forecast errors",
}));
