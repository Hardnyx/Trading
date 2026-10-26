/**
 * Immutable daily prospective origin, using the first archived market cut.
 * This never calls an order API and does not report real forecasting skill.
 */
import { readFileSync, existsSync, mkdirSync, writeFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, join, dirname } from "node:path";
import { composePortfolio } from "../dist/assets/js/composer.mjs?v=0.8.0";
import { referenceRequest } from "../dist/assets/js/reference-preset.mjs?v=0.8.0";
import { adjustedReturn } from "../dist/assets/js/factors.mjs?v=0.8.0";

export function nextSessionStart(cutDate){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(cutDate))throw Error("Invalid market cut");
  let day=new Date(cutDate+"T12:00:00Z");
  do day.setUTCDate(day.getUTCDate()+1);
  while([0,6].includes(day.getUTCDay()));
  return day.toISOString().slice(0,10);
}
function newYorkParts(value) {
  const x=Object.fromEntries(new Intl.DateTimeFormat("en-US",{
    timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit",
    hour:"2-digit",minute:"2-digit",hourCycle:"h23"
  }).formatToParts(new Date(value)).map(p=>[p.type,p.value]));
  return {date:x.year+"-"+x.month+"-"+x.day,
          minutes:Number(x.hour)*60+Number(x.minute)};
}
export function prospectiveEligibility(snapshot, issuedAt){
  const now=new Date(issuedAt), collected=new Date(snapshot.generated_at);
  if(!Number.isFinite(now.getTime()) || !Number.isFinite(collected.getTime()) ||
     collected>now || !snapshot.price_as_of)
    return {eligible:false,reason:"Snapshot not captured before issuance"};
  const date=newYorkParts(issuedAt), next=nextSessionStart(snapshot.price_as_of);
  // An original close must be observed before sealing it; do not accept
  // replayed October prices as if known before the next market session.
  if(date.date<snapshot.price_as_of ||
     (date.date===snapshot.price_as_of && date.minutes<16*60) ||
     date.date>next ||
     (date.date===next && date.minutes>=9*60+30))
    return {eligible:false,reason:"Issuer is outside first subsequent NYSE opening"};
  return {eligible:true,reason:"Original-close-to-next-session-window",
          next_session_start_estimate:next+"T09:30 America/New_York",
          warning:"Weekday calendar is conservative and does not certify exchange holidays."};
}
function hash(bytes){return createHash("sha256").update(bytes).digest("hex")}
export function buildSealedOrigin(snapshot, volatility, marketBytes, volatilityBytes,
                                  now,search={candidates:300,paths:600,finalPaths:3000}){
  const state=prospectiveEligibility(snapshot,now);
  if(!state.eligible)throw Error("Nonprospective origin: "+state.reason);
  if(volatility.as_of!==snapshot.price_as_of ||
     volatility.source_market_generated_at!==snapshot.generated_at)
    throw Error("Market snapshot and GJR calibration are not same original cut");
  const preset=referenceRequest({...snapshot,volatility});
  const model=composePortfolio(snapshot,preset.settings,preset.overrides,
                               preset.rules,search);
  const issueDate=newYorkParts(now).date;
  const maturity=new Date(snapshot.price_as_of+"T12:00:00Z");
  maturity.setUTCFullYear(maturity.getUTCFullYear()+1);
  return {
    schema_version:1,
    origin_type:"first-capture-forward-shadow-no-trading",
    research_only:true,
    issued_at:now,
    issue_ny_date:issueDate,
    original_price_as_of:snapshot.price_as_of,
    market_collected_at:snapshot.generated_at,
    maturity_date:maturity.toISOString().slice(0,10),
    eligibility:state,
    market_sha256:hash(marketBytes),
    volatility_sha256:hash(volatilityBytes),
    engine_version:model.model_version,
    model_settings:{horizon:1,seed:preset.settings.seed,
                    volatility_mode:preset.settings.volatilityMode},
    model_status:model.status,
    positions:model.positions||[],
    forecast:model.metrics ? {
      expected_return:model.metrics.meanReturn,
      median_return:model.metrics.medianReturn,
      p05:model.metrics.p05,p95:model.metrics.p95,
      probability_loss:model.metrics.lossProbability,
      simulated_cvar95:model.metrics.cvar95,
    }:null,
    note:"This is a sealed prior forecast, not proven predictive skill. It may never be silently altered by newer API data.",
  };
}
export function maturityCheck(origin,market){
  if(market.price_as_of<origin.maturity_date)return {status:"immature"};
  const relevant=(origin.positions||[]).filter(p=>p.weight>0&&p.symbol!=="CASH");
  if(!relevant.length)return {status:"mature_without_risky_positions",realized:0};
  const assets=new Map(market.assets.map(a=>[a.symbol,a]));
  let sum=0;
  for(const row of relevant){
    const asset=assets.get(row.symbol);
    if(!asset)return {status:"missing_delisted_or_unavailable_asset",symbol:row.symbol};
    const ret=adjustedReturn(asset,origin.original_price_as_of,
                             origin.maturity_date);
    if(!Number.isFinite(ret))return {status:"missing_historical_price",symbol:row.symbol};
    sum+=row.weight*ret;
  }
  return {
    status:"eligible_outcome_approximation",
    realized_buy_and_hold_gross:sum,
    // Ignore transaction costs here until an exact historic execution
    // archive is available; never call this net portfolio utility.
    brier_loss_probability:origin.forecast
      ? (origin.forecast.probability_loss-Number(sum<0))**2:null,
    covered_90_percent_interval:origin.forecast
      ? sum>=origin.forecast.p05&&sum<=origin.forecast.p95:null,
    warning:"Ex-post adjusted close and cash flows approximated; this does not establish net trading skill, delisted membership or original vintages.",
  };
}
function main(){
  const args=new Set(process.argv.slice(2));
  const base=resolve("data/forecasts");
  const marketFile=readFileSync("dist/data/market.json");
  const volatilityFile=readFileSync("dist/data/volatility.json");
  const market=JSON.parse(marketFile.toString("utf8"));
  const volatility=JSON.parse(volatilityFile.toString("utf8"));
  const location=join(base,market.price_as_of+".json");
  mkdirSync(base,{recursive:true});
  if(!args.has("--score") && existsSync(location)){
    console.log("Existing immutable origin retained:",location);
    return;
  }
  if(args.has("--score")){
    const outcomeDirectory=join(base,"outcomes");
    mkdirSync(outcomeDirectory,{recursive:true});
    for(const name of readdirSync(base).filter(p=>/^\d{4}-\d\d-\d\d\.json$/.test(p))){
      const path=join(outcomeDirectory,name);
      if(existsSync(path))continue;
      const record=JSON.parse(readFileSync(join(base,name),"utf8"));
      const result=maturityCheck(record,market);
      if(result.status==="immature")continue;
      writeFileSync(path,JSON.stringify({
        scored_at:new Date().toISOString(),
        origin_file:name,
        origin_sha256:hash(readFileSync(join(base,name))),
        ...result},null,2)+"\n",{flag:"wx"});
      console.log("New outcome",name,result.status);
    }
    return;
  }
  const now=new Date().toISOString();
  const gate=prospectiveEligibility(market,now);
  if(!gate.eligible && args.has("--skip-ineligible")){
    console.log("No prospective seal:",gate.reason);
    return;
  }
  const origin=buildSealedOrigin(market,volatility,marketFile,volatilityFile,now);
  if(origin.model_status==="no_feasible")
    throw Error("Cannot seal a probability forecast without feasible model");
  writeFileSync(location,JSON.stringify(origin,null,2)+"\n",{flag:"wx"});
  console.log("Sealed original forward forecast",location,
              "matures",origin.maturity_date,"status",origin.model_status);
}
if(process.argv[1] && import.meta.url===new URL("file://"+resolve(process.argv[1])).href)
  main();
