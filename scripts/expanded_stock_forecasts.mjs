/** Reconstruct and archive marginals for every registered eligible origin. No outcomes or orders. */
import {readFileSync,writeFileSync,mkdirSync,existsSync,readdirSync} from 'node:fs';
import {gunzipSync,gzipSync} from 'node:zlib';
import {resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest,pilotRequest} from './scoped_engine_pilot.mjs';
import {assertEquivalent,verifySources} from './attribute_scoped_pilot.mjs';
import {flatBaseline} from './scoped_pilot_distributions.mjs';
import {distributionSummary} from './simulator_validation.mjs';
import {prepareComposition} from '../dist/assets/js/composer.mjs';
import {generatePaths,PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const check=(ok,message)=>{if(!ok)throw Error(message);};
const read=p=>readFileSync(resolve(ROOT,p));
export function selectedCuts(bundle) {
  const expected=bundle.schedule.filter(r=>r.research_history_weight>=bundle.protocol.selection.minimum_weight)
    .map(r=>r.cut).sort().slice(0,bundle.protocol.selection.maximum_origins);
  check(expected.length===bundle.origins.length&&bundle.origins.every((o,i)=>o.cut===expected[i]),
    'Expanded origin selection mismatch');
  check(bundle.schedule.filter(r=>r.selected).map(r=>r.cut).sort().join('|')===expected.join('|'),
    'Expanded schedule flags mismatch');
  return expected;
}
function sourceManifest(directory) {
  return readdirSync(directory,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name)).flatMap(e=>{
    const path=resolve(directory,e.name);
    return e.isDirectory()?sourceManifest(path):e.name.endsWith('.mjs')?
      [{path:relative(ROOT,path).replaceAll('\\','/'),sha256:digest(readFileSync(path))}]:[];
  });
}
function immutable(path,value) {
  if(existsSync(path))assertEquivalent(value,JSON.parse(gunzipSync(readFileSync(path))));
  else writeFileSync(path,gzipSync(JSON.stringify(value)),{flag:'wx'});
  return digest(readFileSync(path));
}
export function forecastOrigin(origin,protocol) {
  const request=pilotRequest(origin,protocol),x=prepareComposition(origin.snapshot,request.settings,request.overrides,request.rules),
    stocks=new Set(origin.snapshot.assets.filter(a=>a.type==='stock').map(a=>a.symbol)),records=[];
  for(const id of protocol.models) {
    check(['pilot_kernel','flat_ewma_zero_mean'].includes(id),'Unknown registered model');
    const sample=generatePaths(id==='pilot_kernel'?x:flatBaseline(x),protocol.paths,
      protocol.distribution_seed,protocol.steps_per_year);
    for(let i=0;i<x.assets.length;i++) {
      const symbol=x.assets[i].symbol;
      if(!stocks.has(symbol)&&symbol!=='SPY')continue;
      for(const horizon of protocol.horizons_sessions) {
        const values=Array.from({length:protocol.paths},(_,p)=>sample.gross[i][p*(sample.steps+1)+horizon]-1);
        records.push({symbol,role:stocks.has(symbol)?'stock':'benchmark',model:id,horizon_sessions:horizon,
          distribution:{...distributionSummary(values),loss_probability:values.filter(v=>v<0).length/values.length}});
      }
    }
    console.log(JSON.stringify({cut:origin.cut,model:id,records:records.length}));
  }
  return {cut:origin.cut,usable_stocks:origin.usable_stocks,eps_exclusions:origin.eps_exclusions,
    snapshot_sha256:digest(JSON.stringify(origin.snapshot)),request_sha256:digest(JSON.stringify(request)),
    prepared:{symbols:x.assets.map(a=>a.symbol),anchors:x.anchors,covariance:x.covariance,
      calibration_end:x.calibrationEnd,observations:x.observations},records};
}
export function main() {
  const inputRaw=gunzipSync(read('out/expanded-validation-inputs-v1.json.gz')),bundle=JSON.parse(inputRaw),
    protocolRaw=read('docs/protocolo-validacion-ampliada-v1.json'),protocol=JSON.parse(protocolRaw),
    original=JSON.parse(gunzipSync(read('data/historical/scoped-engine-pilot-v1/results.json.gz')));
  assertEquivalent(protocol,bundle.protocol,'protocol');
  check(digest(protocolRaw)===bundle.protocol_sha256,'Expanded protocol hash mismatch');
  check(digest(read('scripts/expanded_validation_inputs.py'))===bundle.compiler_sha256&&
    digest(read('scripts/scoped_engine_inputs.py'))===bundle.builder_sha256,'Input compiler mismatch');
  selectedCuts(bundle);verifySources(original.production_sources);
  const sources=sourceManifest(resolve(ROOT,'dist/assets/js')),
    directory=resolve(ROOT,protocol.forecast_directory);mkdirSync(directory,{recursive:true});
  const files=bundle.origins.map(origin=>{
    const result=forecastOrigin(origin,protocol),filename=origin.cut+'.json.gz',
      sha256=immutable(resolve(directory,filename),result);
    return {cut:origin.cut,file:filename,sha256,usable_stocks:result.usable_stocks,
      forecast_stocks:new Set(result.records.filter(r=>r.role==='stock').map(r=>r.symbol)).size,
      records:result.records.length,snapshot_sha256:result.snapshot_sha256};
  });
  const manifest={protocol,price_kernel_version:PRICE_KERNEL_VERSION,production_eligible:false,prospective:false,
    independent_holdout:false,predictive_validation:'not-established',certified_full_engine_cuts:0,
    optimization_executed:false,schedule:bundle.schedule,origins:files,production_sources:sources,
    evidence:{inputs_uncompressed_sha256:digest(inputRaw),protocol_sha256:digest(protocolRaw),
      eps_archive_sha256:bundle.eps_archive_sha256,price_audit_sha256:bundle.price_audit_sha256,
      canonical_market_sha256:bundle.canonical_market_sha256,
      production_sources_sha256:digest(JSON.stringify(sources)),
      input_compiler_sha256:bundle.compiler_sha256,stock_compiler_sha256:bundle.builder_sha256,
      runner_sha256:digest(read('scripts/expanded_stock_forecasts.mjs'))}};
  const target=resolve(directory,'manifest.json');
  if(existsSync(target))assertEquivalent(manifest,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(manifest,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({origins:files.length,forecasts:files.reduce((n,r)=>n+r.records,0),certified_full_engine_cuts:0}));
  return manifest;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main();
