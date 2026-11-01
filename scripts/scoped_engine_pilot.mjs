// Restricted retrospective integration experiment. Never an executable portfolio feed.
import { readFileSync, readdirSync, mkdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { gunzipSync, gzipSync } from 'node:zlib';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { referenceRequest } from '../dist/assets/js/reference-preset.mjs';
import { prepareComposition, composeMultiStart } from '../dist/assets/js/composer.mjs';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
export const digest = bytes => createHash('sha256').update(bytes).digest('hex');
function requireThat(condition, message) { if (!condition) throw new Error(message); }

export function validateOrigin(origin) {
  const {cut, snapshot:s} = origin;
  requireThat(/^\d{4}-\d{2}-\d{2}$/.test(cut) && s.price_as_of === cut && s.requested_as_of === cut, 'Origin mismatch');
  requireThat(s.generated_at?.slice(0,10) > cut, 'Compilation time must retain actual later retrieval');
  requireThat(!s.volatility && !s.validated_opportunities && !s.default_portfolio && !s.positions?.length, 'Current models or account injected');
  requireThat(new Set(s.assets.map(a=>a.symbol)).size === s.assets.length, 'Duplicate symbols');
  requireThat(s.assets.filter(a=>a.symbol==='SPY').length === 1, 'Missing benchmark');
  for (const a of s.assets) {
    requireThat(a.type==='stock' || (a.symbol==='SPY' && a.type==='etf'), 'Outside registered universe');
    const allowed = new Set(['symbol','name','type','sector','currency','cik','assumptions','history','price','price_date','splits','dividend_per_share','financials','filings','historical_reconstruction','holdings']);
    requireThat(Object.keys(a).every(k=>allowed.has(k)), `Unregistered field: ${a.symbol}`);
    requireThat(a.price_date===cut && a.history.at(-1)?.date===cut && a.price===a.history.at(-1).close, 'Origin price mismatch');
    let previous='';
    for (const r of a.history) {
      requireThat(r.date<=cut && r.date>previous && r.close>0 && r.adj_close>0 && Number.isFinite(r.close+r.adj_close), 'Invalid historical price');
      previous=r.date;
    }
    requireThat((a.splits||[]).every(r=>r.date<=cut), 'Future split exposed');
    if(a.type==='stock') {
      requireThat(Object.keys(a.financials).every(k=>['eps','observed_at','refresh_status','history'].includes(k)), 'Unverified financial quality injected');
      const e=a.financials.eps;
      requireThat(e?.value>0 && e.filed<cut && e.period_end<cut && e.components?.length>0 &&
        e.components.every(c=>c.filed<cut && c.end<cut), 'Future or missing EPS');
      requireThat(!a.financials.history.length && a.filings.every(f=>f.filing_date<cut && f.report_date<cut), 'Future financial history');
      requireThat(Number.isFinite(a.dividend_per_share) && a.dividend_per_share>=0, 'Invalid dividend');
    } else {
      requireThat(a.holdings?.observed_at_semantics==='virtual-public-availability-clock-for-research-not-capture' &&
        a.holdings.original_capture_verified===false && a.holdings.observed_at.slice(0,10)<=cut &&
        a.holdings.retrieved_at?.slice(0,10)>cut && a.holdings.as_of<=cut, 'Holdings clock contract');
    }
  }
  for(const r of s.macro) requireThat(r.date<cut && r.vintage_date<cut && r.known_by_day<cut &&
    r.history.every(h=>h.date<cut), 'Future macro value');
}

export function pilotRequest(origin, protocol) {
  validateOrigin(origin);
  requireThat(protocol.risk_mode==='ewma' && protocol.seed===20261024 && protocol.horizon_years===1 &&
    protocol.outcome_scoring===false && protocol.production_eligible===false, 'Unregistered pilot policy');
  const request=referenceRequest(origin.snapshot);
  request.settings.volatilityMode=protocol.risk_mode;
  request.settings.volatilityData=null;
  requireThat(request.settings.informationAsOf===origin.cut, 'Engine information clock mismatch');
  return request;
}

function sourceManifest(directory) {
  return readdirSync(directory,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name)).flatMap(e=>{
    const path=resolve(directory,e.name);
    return e.isDirectory()?sourceManifest(path):e.name.endsWith('.mjs')?
      [{path:relative(ROOT,path),sha256:digest(readFileSync(path))}]:[];
  });
}

export function runOrigin(origin, protocol) {
  const {settings,overrides,rules}=pilotRequest(origin,protocol);
  const x=prepareComposition(origin.snapshot,settings,overrides,rules);
  const proposal=composeMultiStart(origin.snapshot,settings,overrides,rules,protocol.search,protocol.search.starts);
  requireThat(proposal && proposal.as_of===origin.cut && proposal.information_as_of===origin.cut &&
    proposal.calibration_end<=origin.cut, 'Engine result clock mismatch');
  requireThat(proposal.current_account.positions.length===1 && proposal.current_account.positions[0].symbol==='CASH' &&
    proposal.current_account.positions[0].weight===1, 'Independent cash account changed');
  requireThat(proposal.diagnostics?.robustDecision, 'Robust decision gate not executed');
  return {cut:origin.cut, usable_stocks:origin.usable_stocks, eps_exclusions:origin.eps_exclusions,
    stored_snapshot_sha256:origin.snapshot_sha256,
    engine_snapshot_json_sha256:digest(JSON.stringify(origin.snapshot)),
    request_sha256:digest(JSON.stringify({settings,overrides,rules})),
    prepared:{symbols:x.assets.map(a=>a.symbol), buy_allowed:x.buyAllowed,
      anchors:x.anchors, covariance:x.covariance, innovation_covariance:x.innovationCovariance,
      annual_volatility:x.assets.map((a,i)=>({symbol:a.symbol,value:Math.sqrt(x.covariance[i][i])})),
      factor_covariance:x.factorCovariance, dependence:x.dependence,
      conditional_risk:{dynamic:x.conditional.dynamic,reason:x.conditional.reason,asOf:x.conditional.asOf},
      calibration_end:x.calibrationEnd, observations:x.observations,
      regime_probabilities:x.regimeProbabilities}, proposal};
}

export function main(input='out/scoped-engine-inputs-v1.json.gz', output='data/historical/scoped-engine-pilot-v1/report.json') {
  const raw=readFileSync(resolve(ROOT,input)), bundle=JSON.parse(gunzipSync(raw));
  const protocolRaw=readFileSync(resolve(ROOT,'docs/protocolo-piloto-integrado-v1.json'));
  requireThat(digest(protocolRaw)===bundle.pilot_protocol_sha256 &&
    isDeepStrictEqual(JSON.parse(protocolRaw),bundle.protocol), 'Protocol hash mismatch');
  requireThat(digest(readFileSync(resolve(ROOT,bundle.protocol.eps_archive)))===bundle.eps_archive_sha256 &&
    digest(readFileSync(resolve(ROOT,'scripts/scoped_engine_inputs.py')))===bundle.builder_sha256, 'Builder or EPS archive mismatch');
  const selected=bundle.schedule.filter(r=>r.selected).map(r=>r.cut).sort();
  const expected=bundle.schedule.filter(r=>r.research_history_weight>=bundle.protocol.selection.minimum_weight)
    .map(r=>r.cut).sort().slice(0,bundle.protocol.selection.maximum_origins);
  requireThat(selected.length===expected.length && selected.every((d,i)=>d===expected[i]) &&
    bundle.origins.length===selected.length && bundle.origins.every((o,i)=>o.cut===selected[i]), 'Registered selection changed');
  const sources=sourceManifest(resolve(ROOT,'dist/assets/js'));
  const results=[];
  for(const origin of bundle.origins) {
    console.log(`Executing unchanged composer and robust gate: ${origin.cut}`);
    results.push(runOrigin(origin,bundle.protocol));
    console.log(JSON.stringify({cut:origin.cut,status:results.at(-1).proposal.status}));
  }
  const full={protocol:bundle.protocol,generated_at:new Date().toISOString(),
    input_file_sha256:digest(raw),runner_sha256:digest(readFileSync(fileURLToPath(import.meta.url))),
    production_sources:sources,production_sources_sha256:digest(JSON.stringify(sources)),
    production_eligible:false,prospective:false,certified_full_engine_cuts:0,
    predictive_validation:'not-established',results};
  const artifact='out/scoped-engine-results-v1.json.gz';
  mkdirSync(resolve(ROOT,'out'),{recursive:true});
  const compressed=gzipSync(JSON.stringify(full));
  writeFileSync(resolve(ROOT,artifact),compressed);
  const report={...full,protocol:bundle.protocol,full_results_artifact:artifact,full_results_sha256:digest(compressed),
    schedule:bundle.schedule,
    results:results.map(r=>({cut:r.cut,usable_stocks:r.usable_stocks,eps_exclusions:r.eps_exclusions,
      stored_snapshot_sha256:r.stored_snapshot_sha256,engine_snapshot_json_sha256:r.engine_snapshot_json_sha256,
      request_sha256:r.request_sha256,prepared:r.prepared,
      decision:{status:r.proposal.status,reason:r.proposal.reason,positions:r.proposal.positions,
        trade_plan:r.proposal.trade_plan,metrics:r.proposal.metrics,selection:r.proposal.selection,
        model_version:r.proposal.model_version,verification:r.proposal.verification,
        robust_status:r.proposal.diagnostics.robustDecision.status,
        candidate_review_positions:r.proposal.candidate_review?.positions??null,
        stability:r.proposal.diagnostics.stability,
        reliable_selection:r.proposal.diagnostics.reliableSelection}}))};
  const target=resolve(ROOT,output);mkdirSync(dirname(target),{recursive:true});
  writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({executed_development_cuts:results.length,certified_full_engine_cuts:0,predictive_validation:'not-established'}));
  return report;
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) main(...process.argv.slice(2));
