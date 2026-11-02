/** Reproduce selection-stage failures for fixed archived finalists. No new search or confirmation. */
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {isDeepStrictEqual} from 'node:util';
import {digest, pilotRequest} from './scoped_engine_pilot.mjs';
import {prepareComposition, validWeights} from '../dist/assets/js/composer.mjs';
import {generatePaths, evaluatePaths, utilityCertaintyEquivalent} from '../dist/assets/js/path-model.mjs';
import {MODEL_VARIANTS, variantInputs} from '../dist/assets/js/robust-core.mjs';
import {pairedDecisionEvidence, tailStressInputs, DECISION_EXPERIMENT_SEEDS} from '../dist/assets/js/robust-decision.mjs';
import {riskSamplingEvidence} from '../dist/assets/js/simulation-evidence.mjs';
import {tradePlan} from '../dist/assets/js/policy.mjs';

const ROOT=fileURLToPath(new URL('../',import.meta.url));
const check=(ok,message)=>{if(!ok)throw Error(message);};
export function verifySources(manifest, root=ROOT) {
  check(manifest.length>0,'Missing archived production manifest');
  for(const source of manifest)
    check(digest(readFileSync(resolve(root,source.path)))===source.sha256,
      `Archived production source mismatch: ${source.path}`);
}
export function riskAttribution(risk) {
  return risk.rows.map(row=>({...row,
    failed:!Number.isFinite(row.upper)||row.upper>row.limit+1e-12,
    point_exceeds_limit:!Number.isFinite(row.value)||row.value>row.limit+1e-12,
    sampling_margin_only:Number.isFinite(row.value)&&row.value<=row.limit+1e-12&&
      (!Number.isFinite(row.upper)||row.upper>row.limit+1e-12)}));
}
export function gainFailures(evidence,hurdle,hold) {
  return hold?[]:[...(evidence.meanUtilityGain<=0?['nonpositive_utility_gain']:[]),
    ...(evidence.lowerGain<hurdle?['gain_below_hurdle']:[])];
}
function close(actual,expected,label) {
  check(Number.isFinite(actual)&&Number.isFinite(expected)&&
    Math.abs(actual-expected)<=1e-8*Math.max(1,Math.abs(expected)),`Archived metric mismatch: ${label}`);
}
export function verifyCandidate(actual,archived) {
  for(const key of ['feasible','selected'])check(actual[key]===archived[key],`Archived ${key} mismatch`);
  for(const key of ['worstCertaintyEquivalent','minimumLowerGain','maximumRisk','turnover'])
    close(actual[key],archived[key],key);
}

export function attributeOrigin(origin,result,protocol) {
  check(origin.cut===result.cut&&origin.snapshot_sha256===result.stored_snapshot_sha256,'Origin identity mismatch');
  check(digest(JSON.stringify(origin.snapshot))===result.engine_snapshot_json_sha256,'Snapshot hash mismatch');
  const request=pilotRequest(origin,protocol),{settings,overrides,rules}=request;
  check(digest(JSON.stringify(request))===result.request_sha256,'Archived request mismatch');
  const x=prepareComposition(origin.snapshot,settings,overrides,rules),capital=x.current.capital;
  check(isDeepStrictEqual(x.assets.map(a=>a.symbol),result.prepared.symbols),'Prepared universe mismatch');
  for(const key of ['anchors','covariance','innovationCovariance','buyAllowed']) {
    const archivedKey={innovationCovariance:'innovation_covariance',buyAllowed:'buy_allowed'}[key]||key;
    check(isDeepStrictEqual(JSON.parse(JSON.stringify(x[key])),result.prepared[archivedKey]),`Prepared ${key} mismatch`);
  }
  const selection=result.proposal.diagnostics.reliableSelection,
    paths=result.proposal.diagnostics.stability.commonPaths,
    current=x.assets.map(a=>x.current.positions.find(p=>p.symbol===a.symbol)?.weight||0);
  check(isDeepStrictEqual(selection.seeds,DECISION_EXPERIMENT_SEEDS),'Selection seeds mismatch');
  check(selection.finalists===selection.candidates.length&&paths>0,'Invalid finalist archive');
  const rows=selection.candidates.map(archived=>{
    const weights=x.assets.map(a=>archived.positions.find(p=>p.symbol===a.symbol)?.weight||0);
    check(Math.abs(weights.reduce((a,b)=>a+b,0)-1)<1e-8,'Unknown or incomplete archived weights');
    const hold=isDeepStrictEqual(weights,current),plan=tradePlan(x.assets,archived.positions,x.current.positions,capital,x.costs);
    // These rows already passed structural and execution filtering before selection.
    check(hold||validWeights(weights,x),'Archived finalist fails structural filter');
    check(hold||(plan.complete&&!plan.smallTrades&&
      (x.current.source==='Capital inicial en efectivo'||plan.turnover<=x.costs.maxTurnover+1e-8)),
      'Archived finalist fails execution filter');
    return {archived,weights,plan,hold,models:[],worstScore:Infinity,minimumLowerGain:Infinity,maximumRisk:0};
  });
  for(const model of MODEL_VARIANTS) {
    const sample=generatePaths(variantInputs(x,model),paths,selection.seeds.selection,52),
      held=evaluatePaths(current,sample,{capital,cost:0,pathUtilities:true});
    for(const row of rows) {
      const m=evaluatePaths(row.weights,sample,{capital,cost:row.plan.total,pathUtilities:true}),
        evidence=pairedDecisionEvidence(m.pathUtilities,held.pathUtilities,x.policy,capital),
        risk=riskSamplingEvidence(m,x.rules,x.policy),hurdle=Math.max(x.costs.minBenefit,row.plan.total*x.costs.benefitCostRatio),
        failures=[...risk.failures,...gainFailures(evidence,hurdle,row.hold)];
      row.worstScore=Math.min(row.worstScore,m.score);
      row.minimumLowerGain=Math.min(row.minimumLowerGain,evidence.lowerGain);
      row.maximumRisk=Math.max(row.maximumRisk,risk.rows[0].upper);
      row.models.push({id:model.id,role:'economic-and-risk',hurdle,evidence,
        risk:riskAttribution(risk),failures,passes:failures.length===0});
    }
  }
  const sample=generatePaths(tailStressInputs(x),paths,selection.seeds.selection,52);
  for(const row of rows) {
    const risk=riskSamplingEvidence(evaluatePaths(row.weights,sample,
      {capital,cost:row.plan.total,riskOnly:true}),x.rules,x.policy);
    row.maximumRisk=Math.max(row.maximumRisk,risk.rows[0].upper);
    row.tail_stress={id:'tail_student',role:'risk-only',risk:riskAttribution(risk),
      failures:risk.failures,passes:risk.failures.length===0};
  }
  const candidates=rows.map(row=>{
    const candidate={positions:row.archived.positions,hold:row.hold,selected:row.archived.selected,
      feasible:row.models.every(m=>m.passes)&&row.tail_stress.passes,
      worstCertaintyEquivalent:utilityCertaintyEquivalent(row.worstScore,x.policy,capital),
      minimumLowerGain:row.minimumLowerGain,maximumRisk:row.maximumRisk,turnover:row.plan.turnover,
      models:row.models,tail_stress:row.tail_stress};
    verifyCandidate(candidate,row.archived);
    return candidate;
  });
  check(candidates.filter(c=>!c.hold&&c.feasible).length===selection.admissible,'Admissible count mismatch');
  const model_rejections=[...MODEL_VARIANTS.map(m=>m.id),'tail_student'].map(id=>{
    const checks=candidates.filter(c=>!c.hold).map(c=>id==='tail_student'?c.tail_stress:c.models.find(m=>m.id===id));
    const ids=[...new Set(checks.flatMap(m=>m.failures))];
    return {id,rejected:checks.filter(m=>!m.passes).length,
      reasons:ids.map(reason=>({reason,candidates:checks.filter(m=>m.failures.includes(reason)).length}))};
  });
  return {cut:origin.cut,paths,seed:selection.seeds.selection,finalists:candidates.length,
    admissible_transitions:selection.admissible,archived_metrics_reproduced:true,
    model_rejections,candidates};
}

export function main(output='data/historical/scoped-pilot-attribution-v1/report.json') {
  const base=resolve(ROOT,'data/historical/scoped-engine-pilot-v1'),
    inputs=readFileSync(resolve(base,'inputs.json.gz')),results=readFileSync(resolve(base,'results.json.gz')),
    bundle=JSON.parse(gunzipSync(inputs)),full=JSON.parse(gunzipSync(results)),
    published=JSON.parse(readFileSync(resolve(base,'report.json')));
  check(digest(inputs)===full.input_file_sha256&&digest(inputs)===published.input_file_sha256&&
    digest(results)===published.full_results_sha256,'Published archive hash mismatch');
  check(full.production_eligible===false&&full.certified_full_engine_cuts===0,'Unexpected pilot scope');
  check(isDeepStrictEqual(bundle.protocol,full.protocol),'Protocol mismatch');
  check(bundle.origins.length===full.results.length,'Origin count mismatch');
  verifySources(full.production_sources);
  const report={method:'fixed-archived-finalists-selection-attribution-v1',
    production_eligible:false,prospective:false,certified_full_engine_cuts:0,predictive_validation:'not-established',
    new_search:false,new_confirmation:false,changed_decisions:false,
    scope:'Exact replay of selection paths for all archived finalists; no evidence on predictive validity or justification of risk limits',
    evidence:{pilot_inputs_sha256:digest(inputs),pilot_results_sha256:digest(results),
      production_sources_sha256:full.production_sources_sha256,
      runner_sha256:digest(readFileSync(fileURLToPath(import.meta.url)))},
    origins:bundle.origins.map((origin,i)=>{
      console.log(`Attributing fixed finalists: ${origin.cut}`);
      return attributeOrigin(origin,full.results[i],bundle.protocol);
    })};
  const target=resolve(ROOT,output);mkdirSync(dirname(target),{recursive:true});
  writeFileSync(target,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report.origins.map(o=>({cut:o.cut,finalists:o.finalists,model_rejections:o.model_rejections})),null,2));
  return report;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main(...process.argv.slice(2));
