import { readFileSync } from "node:fs";
import { preparePaths, generatePaths } from "../dist/assets/js/path-model.mjs?v=0.5.0";
import { BASE_REGIME } from "../dist/assets/js/path-model.mjs?v=0.5.0";

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
if(hybrid.conditional.active<1 || !hybrid.conditional.enabled)
  throw Error("El modelo no aceptó un activo que validó la calibración");
if(hybrid.conditional.active+hybrid.conditional.fallback!==assets.length)
  throw Error("Pérdida de activos en selección de riesgo");
const ewma=preparePaths(assets,{...baseOptions,volatilityMode:"ewma"}, {}, market.assets);
if(ewma.conditional.enabled)throw Error("El control EWMA quedó alterado");
const generated=generatePaths(hybrid,100,20261025,52);
for(const series of generated.gross)
  if(!Array.from(series).every(v=>Number.isFinite(v)&&v>0))
    throw Error("Se generaron precios inválidos");
const legacy=generatePaths(ewma,100,20261025,52);
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
