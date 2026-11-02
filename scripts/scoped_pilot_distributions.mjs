/** Freeze reconstructed total-return marginals before examining their scores. */
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {gunzipSync,gzipSync} from 'node:zlib';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest,pilotRequest} from './scoped_engine_pilot.mjs';
import {verifySources,assertEquivalent} from './attribute_scoped_pilot.mjs';
import {prepareComposition} from '../dist/assets/js/composer.mjs';
import {generatePaths,BASE_REGIME,PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs';
import {distributionSummary} from './simulator_validation.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const check=(ok,message)=>{if(!ok)throw Error(message);};
export function flatBaseline(x) {
  return {...x,conditional:{...x.conditional,dynamic:false},factorization:null,horizonVariance:null,
    regimes:[BASE_REGIME],options:{...x.options,model:'gbm',uncertainFundamentals:false},
    anchors:x.anchors.map(a=>({...a,annual:0,low:0,high:0,mu:0,distributionMean:0}))};
}
export function freezeDistributions(bundle,full,protocol,onProgress=()=>{}) {
  check(bundle.origins.length===full.results.length,'Origin count mismatch');
  return bundle.origins.map((origin,k)=>{
    const archived=full.results[k],request=pilotRequest(origin,bundle.protocol);
    check(origin.cut===archived.cut&&digest(JSON.stringify(origin.snapshot))===archived.engine_snapshot_json_sha256&&
      digest(JSON.stringify(request))===archived.request_sha256,'Archived origin or request mismatch');
    const x=prepareComposition(origin.snapshot,request.settings,request.overrides,request.rules);
    assertEquivalent(JSON.parse(JSON.stringify(x.anchors)),archived.prepared.anchors,'anchors');
    assertEquivalent(x.covariance,archived.prepared.covariance,'covariance');
    assertEquivalent(x.assets.map(a=>a.symbol),archived.prepared.symbols,'symbols');
    const stocks=new Set(origin.snapshot.assets.filter(a=>a.type==='stock').map(a=>a.symbol)),records=[];
    for(const id of protocol.models) {
      const input=id==='pilot_kernel'?x:flatBaseline(x),
        sample=generatePaths(input,protocol.paths,protocol.seed,protocol.steps_per_year);
      for(let i=0;i<x.assets.length;i++) {
        const symbol=x.assets[i].symbol;
        if(!stocks.has(symbol)&&symbol!=='SPY')continue;
        for(const horizon of protocol.horizons_sessions) {
          const values=Array.from({length:protocol.paths},(_,p)=>sample.gross[i][p*(sample.steps+1)+horizon]-1);
          records.push({symbol,role:stocks.has(symbol)?'stock':'benchmark',model:id,horizon_sessions:horizon,
            distribution:{...distributionSummary(values),loss_probability:values.filter(v=>v<0).length/values.length}});
        }
      }
      onProgress({cut:origin.cut,model:id,records:records.length});
    }
    return {cut:origin.cut,request_sha256:archived.request_sha256,
      snapshot_sha256:archived.engine_snapshot_json_sha256,records};
  });
}
export function main() {
  const protocolRaw=readFileSync(resolve(ROOT,'docs/protocolo-distribuciones-piloto-v1.json')),
    protocol=JSON.parse(protocolRaw),base=resolve(ROOT,protocol.pilot_directory),
    inputRaw=readFileSync(resolve(base,'inputs.json.gz')),resultRaw=readFileSync(resolve(base,'results.json.gz')),
    bundle=JSON.parse(gunzipSync(inputRaw)),full=JSON.parse(gunzipSync(resultRaw)),
    published=JSON.parse(readFileSync(resolve(base,'report.json')));
  check(full.production_eligible===false&&full.certified_full_engine_cuts===0,'Unexpected pilot scope');
  check(digest(inputRaw)===published.input_file_sha256&&digest(resultRaw)===published.full_results_sha256&&
    digest(inputRaw)===full.input_file_sha256,'Published archive hash mismatch');
  verifySources(full.production_sources);
  const report={protocol,price_kernel_version:PRICE_KERNEL_VERSION,
    prospective:false,independent_holdout:false,production_eligible:false,
    predictive_validation:'not-established',certified_full_engine_cuts:0,
    evidence:{protocol_sha256:digest(protocolRaw),pilot_inputs_sha256:digest(inputRaw),
      pilot_results_sha256:digest(resultRaw),production_sources_sha256:full.production_sources_sha256,
      runner_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))},
    origins:freezeDistributions(bundle,full,protocol,p=>console.log(JSON.stringify(p)))};
  const dir=resolve(ROOT,protocol.forecast_directory);mkdirSync(dir,{recursive:true});
  const target=resolve(dir,'forecasts.json.gz'),raw=gzipSync(JSON.stringify(report));
  if(existsSync(target))assertEquivalent(report,JSON.parse(gunzipSync(readFileSync(target))));
  else writeFileSync(target,raw,{flag:'wx'});
  console.log(JSON.stringify({origins:report.origins.length,sha256:digest(readFileSync(target))}));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main();
