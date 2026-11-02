/** Score the expanded frozen cohort, retaining every unavailable horizon. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest} from './scoped_engine_pilot.mjs';
import {assertEquivalent} from './attribute_scoped_pilot.mjs';
import {scoreFrozenDistributions} from './score_scoped_distributions.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
export const FORECAST_COMMIT='c323b8187c3bf0a52129333e5a7236304629f2f3';
const ORIGINAL_CUTS=new Set(['2024-12-31','2025-04-30']);
const check=(ok,message)=>{if(!ok)throw Error(message);};

export function summarizeExpanded(report,horizons) {
  return Object.fromEntries(horizons.map(h=>{
    const rows=report.origins.map(o=>({cut:o.cut,...o.horizons.find(r=>r.horizon_sessions===h)})),
      mature=rows.filter(r=>r.maturity!==null),nonoverlapping=[];
    let previousEnd='';
    for(const row of [...mature].sort((a,b)=>a.cut.localeCompare(b.cut)))
      if(row.cut>=previousEnd){nonoverlapping.push(row.cut);previousEnd=row.maturity;}
    const comparable=mature.filter(r=>r.scored_stocks>0),
      better=metric=>comparable.filter(r=>r.stock_metrics.pilot_kernel[metric]<r.stock_metrics.flat_ewma_zero_mean[metric]).length;
    return [h,{forecast_origins:rows.length,mature_origins:mature.length,
      additional_mature_origins:mature.filter(r=>!ORIGINAL_CUTS.has(r.cut)).length,
      pending_cuts:rows.filter(r=>!r.maturity).map(r=>r.cut),
      stock_comparisons:mature.reduce((n,r)=>n+r.scored_stocks,0),
      nonoverlapping_cut_schedule:nonoverlapping,nonoverlapping_origins:nonoverlapping.length,
      stock_exclusions:mature.reduce((n,r)=>n+r.exclusions.filter(e=>e.role==='stock').length,0),
      descriptive_better_crps_origins:better('crps'),descriptive_better_brier_origins:better('brier_loss'),
      descriptive_better_rmse_origins:better('rmse'),comparable_origins:comparable.length,
      inference:'Counts describe paired per-origin averages; neither independent wins nor predictive confidence'}];
  }));
}
export function main(output='data/historical/expanded-stock-validation-scores-v1/report.json',verify=false) {
  const show=path=>execFileSync('git',['show',`${FORECAST_COMMIT}:${path}`],{cwd:ROOT,maxBuffer:128*1024*1024}),
    directory='data/historical/expanded-stock-validation-v1',manifestRaw=show(directory+'/manifest.json'),
    manifest=JSON.parse(manifestRaw),protocolRaw=show('docs/protocolo-validacion-ampliada-v1.json');
  check(digest(protocolRaw)===manifest.evidence.protocol_sha256,'Frozen expanded protocol mismatch');
  assertEquivalent(JSON.parse(protocolRaw),manifest.protocol,'protocol');
  const origins=manifest.origins.map(entry=>{
    const raw=show(directory+'/'+entry.file);
    check(digest(raw)===entry.sha256,'Frozen origin file hash mismatch');
    const origin=JSON.parse(gunzipSync(raw));
    check(origin.cut===entry.cut&&origin.snapshot_sha256===entry.snapshot_sha256,'Frozen origin identity mismatch');
    return origin;
  });
  const marketRaw=execFileSync('git',['show',`${manifest.protocol.market_commit}:${manifest.protocol.market_path}`],
    {cwd:ROOT,maxBuffer:128*1024*1024});
  const report=scoreFrozenDistributions({...manifest,origins},JSON.parse(marketRaw));
  Object.assign(report,{optimization_executed:false,certified_full_engine_cuts:0,
    repeated_original_cuts:origins.filter(o=>ORIGINAL_CUTS.has(o.cut)).map(o=>o.cut),
    additional_origins:origins.filter(o=>!ORIGINAL_CUTS.has(o.cut)).length,
    horizon_summary:summarizeExpanded(report,manifest.protocol.horizons_sessions),
    evidence:{forecast_commit:FORECAST_COMMIT,forecast_manifest_sha256:digest(manifestRaw),
      protocol_sha256:digest(protocolRaw),market_commit:manifest.protocol.market_commit,
      market_sha256:digest(marketRaw),scorer_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))}});
  const target=resolve(ROOT,output);mkdirSync(dirname(target),{recursive:true});
  if(verify)assertEquivalent(report,JSON.parse(readFileSync(target)));
  else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.horizon_summary,null,2));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main(process.argv.slice(2).find(a=>a!=='--verify'),process.argv.includes('--verify'));
