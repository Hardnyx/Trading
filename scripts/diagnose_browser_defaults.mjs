import { readFileSync } from "node:fs";
import { composePortfolio, DEFAULT_COMPOSITION_RULES } from "../dist/assets/js/composer.mjs?v=0.24.0";
import { informationDate, DEFAULT_MANDATE, DEFAULT_EXECUTION,
  DEFAULT_REGIMES } from "../dist/assets/js/policy.mjs?v=0.24.0";
import { BASE_REGIME } from "../dist/assets/js/path-model.mjs?v=0.24.0";
import { referenceRequest, REFERENCE_ID, resultFingerprint } from "../dist/assets/js/reference-preset.mjs?v=0.24.0";

const snapshot=JSON.parse(readFileSync(new URL("../dist/data/market.json",import.meta.url)));
const volatility=JSON.parse(readFileSync(new URL("../dist/data/volatility.json",import.meta.url)));
if (volatility.as_of!==snapshot.price_as_of ||
    volatility.source_market_generated_at!==snapshot.generated_at)
  throw Error("El motor de riesgo no comparte el corte de datos");

const common={
  asOf:snapshot.price_as_of,informationAsOf:informationDate(snapshot),
  model:"merton",horizon:1,paths:3000,
  driftMode:"fundamental",manualReturn:.06,lambda:.94,
  jumpIntensity:.35,jumpMean:-.12,jumpVol:.08,
  uncertainFundamentals:true,volatilityMode:"hybrid",
  volatilityData:volatility,
  mandate: structuredClone(DEFAULT_MANDATE),
  execution: structuredClone(DEFAULT_EXECUTION),
  capital:100000,
  research:{},assetAssumptions:{},account:{enabled:false,cash:0,positions:[]},
  baseline:null,
  yieldCurve:Object.fromEntries(snapshot.macro.map(r=>[r.id,r.value])),
};
const tests=[
  {id:"web_defaults_20261024",seed:20261024,macroRegimes:DEFAULT_REGIMES},
  {id:"web_defaults_20261025",seed:20261025,macroRegimes:DEFAULT_REGIMES},
  {id:"previous_single_regime",seed:20261025,macroRegimes:[BASE_REGIME]},
];
const referenceInput = referenceRequest({...snapshot,volatility});
const canonical = composePortfolio(snapshot, referenceInput.settings,
  referenceInput.overrides, referenceInput.rules,
  {candidates:300,paths:600,finalPaths:3000});
console.log(JSON.stringify({
  check:"SHY-concentration-attribution",
  selection:canonical.selection,
  audit:canonical.diagnostics?.concentrationAudit,
  interpretation:"SHY caps are independently searched, not filtered from an unrestricted candidate list",
  GJRaccepted:canonical.diagnostics?.volatility?.accepted,
}));
console.log(JSON.stringify({
  check:"canonical-reference",id:REFERENCE_ID,
  positions:canonical.positions,median:canonical.metrics?.medianReturn,
  cvar95:canonical.metrics?.cvar95,
  fingerprint:resultFingerprint(canonical),
}));
for(const test of tests){
  const options={...common,seed:test.seed,macroRegimes:structuredClone(test.macroRegimes)};
  const started=Date.now();
  const result=composePortfolio(snapshot,options,{},DEFAULT_COMPOSITION_RULES,{
    candidates:300,paths:600,finalPaths:3000,
  });
  if(test.id==="web_defaults_20261024" &&
    resultFingerprint(result)!==resultFingerprint(canonical))
    throw Error("El preset utilizado por la web difiere del baseline CI.");
  console.log(JSON.stringify({
    check:"configuration-parity",
    id:test.id,model_version:result.model_version,
    snapshot:result.snapshot_generated_at,
    price_as_of:result.as_of,
    information_as_of:result.information_as_of,
    seed:test.seed,regimes:test.macroRegimes.map(r=>({id:r.id,probability:r.probability})),
    limits:DEFAULT_COMPOSITION_RULES,
    result:result.status,
    proposed:result.positions,
    median:result.metrics?.medianReturn,
    cvar95:result.metrics?.cvar95,
    selection:result.selection,
    current_source:result.account_source,
    elapsed_s:Math.round((Date.now()-started)/1000),
  }));
}
