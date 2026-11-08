/** First-capture monthly full-engine evidence. No broker orders or validation claims.
 *
 * Called with the exact proposal already computed by the daily reference sealer.
 * Public market/volatility bytes are archived, not fetched again or reconstructed.
 */
import {readFileSync,writeFileSync,existsSync,mkdirSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative,join} from 'node:path';
import {gzipSync,gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {MODEL_VERSION} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {PRICE_KERNEL_VERSION} from '../dist/assets/js/path-model.mjs?v=0.35.0';
import {REFERENCE_ID} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const BASE='data/confirmatory/full-engine-v2';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const check=(ok,why)=>{if(!ok)throw Error(why);};
const json=x=>JSON.stringify(x);
const nyParts=instant=>Object.fromEntries(new Intl.DateTimeFormat('en-US',{
  timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',hourCycle:'h23',
}).formatToParts(new Date(instant)).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
function parseTime(value,label){
  const t=Date.parse(value);
  check(typeof value==='string'&&/([zZ]|[+-]\d\d:\d\d)$/.test(value)&&Number.isFinite(t),
    'Missing timezone-aware '+label);
  return t;
}
export function lastWeekdayCandidate(cut) {
  check(/^\d{4}-\d\d-\d\d$/.test(cut),'Invalid origin cut');
  const day=new Date(cut+'T12:00:00Z');
  check(!Number.isNaN(day.getTime())&&day.toISOString().slice(0,10)===cut,
    'Invalid calendar date');
  if([0,6].includes(day.getUTCDay()))return false;
  let next=new Date(day);
  do next.setUTCDate(next.getUTCDate()+1);
  while([0,6].includes(next.getUTCDay()));
  // Conservative: a final trading session followed by an exchange holiday
  // may be missed. Never use a weekday approximation as an exchange certificate.
  return next.toISOString().slice(0,7)!==cut.slice(0,7);
}
export function sourceHashMap(root=ROOT) {
  const tracked=['scripts/seal_forecast.mjs','scripts/capture_full_engine_origin.mjs'];
  const walk=dir=>{
    for(const entry of readdirSync(resolve(root,dir),{withFileTypes:true})){
      const child=dir+'/'+entry.name;
      if(entry.isDirectory())walk(child);
      else if(entry.isFile()&&child.endsWith('.mjs'))tracked.push(child);
    }
  };
  walk('dist/assets/js');
  return Object.fromEntries(tracked.sort().map(path=>[path,sha(readFileSync(resolve(root,path)))]));
}
function requireNoFuture(source,issued,depth=0){
  check(depth<=30,'Nested source metadata exceeded audit limit');
  if(!source||typeof source!=='object')return;
  for(const [key,value] of Object.entries(source)){
    if(['observed_at','price_observed_at','first_seen_at'].includes(key)&&value!==null){
      check(parseTime(value,key)<=issued,'Source was observed after original issue');
    }else if(value&&typeof value==='object')requireNoFuture(value,issued,depth+1);
  }
}
export function buildFullEngineCapture({market,volatility,marketBytes,volatilityBytes,
  proposal,request,issuedAt,sourceHashes,registration}) {
  const cut=market.price_as_of,month=cut?.slice(0,7);
  check(lastWeekdayCandidate(cut),'Not the conservative month-end closing session');
  const t=parseTime(issuedAt,'issuance'),capture=parseTime(market.generated_at,'market capture'),
    issueNY=nyParts(issuedAt),captureNY=nyParts(market.generated_at);
  check(issueNY.year+'-'+issueNY.month+'-'+issueNY.day===cut&&
    captureNY.year+'-'+captureNY.month+'-'+captureNY.day===cut&&
    Number(issueNY.hour)>=16&&Number(captureNY.hour)>=16&&capture<=t,
    'Monthly issue or market capture is outside the original post-close window');
  requireNoFuture(market,t);
  check(registration.schema==='full-engine-prospective-registration-v2'&&
    registration.status==='registered-methodology-inactive-confirmatory-inference'&&
    cut>=registration.sampling.first_possible_cut&&
    registration.sampling.first_month<=month&&
    registration.sampling.horizons_sessions.join(',')==='21,63,252',
    'Origin is outside the registered future monthly study');
  check(registration.fixed_cohort.engine_version===MODEL_VERSION&&
    registration.fixed_cohort.price_kernel_version===PRICE_KERNEL_VERSION&&
    registration.fixed_cohort.reference_id===REFERENCE_ID,
    'Current engine/kernel/reference does not match registered cohort');
  check(volatility.as_of===cut&&
    volatility.source_market_generated_at===market.generated_at,
    'Original volatility and market clocks disagree');
  check(market.assets?.some(a=>a.symbol==='SPY'&&a.price_date===cut&&
    a.history?.at(-1)?.date===cut),
    'SPY has no original exact-cut session');
  check(market.assets.every(a=>(a.history||[]).every(r=>r.date<=cut)),
    'A future price entered the original snapshot');
  check(request?.settings?.asOf===cut&&
    request.settings.informationAsOf===cut&&
    request.settings.seed===20261024&&
    request.settings.account?.enabled===false,
    'Reference request uses future information or an unregistered account');
  check(proposal?.as_of===cut&&proposal.information_as_of===cut&&
    proposal.calibration_end===cut&&
    proposal.model_version===MODEL_VERSION&&
    Array.isArray(proposal.positions)&&proposal.trade_plan&&
    typeof proposal.trade_plan==='object'&&
    typeof proposal.status==='string'&&proposal.status!=='no_feasible'&&
    proposal.settings?.informationAsOf===cut,
    'Unsealed or incompletely calibrated full-engine decision');
  check(Buffer.isBuffer(marketBytes)&&Buffer.isBuffer(volatilityBytes)&&
    json(JSON.parse(marketBytes.toString('utf8')) )===json(market) &&
    json(JSON.parse(volatilityBytes.toString('utf8')))===json(volatility),
    'The supplied original bytes do not reproduce the decision inputs');
  check(sourceHashes&&typeof sourceHashes==='object'&&
    Object.keys(sourceHashes).length>=30&&
    Object.entries(sourceHashes).every(([path,digest])=>
      /^(scripts\/(?:capture_full_engine_origin|seal_forecast)\.mjs|dist\/assets\/js\/[\w/.-]+\.mjs)$/.test(path) &&
      /^[a-f0-9]{64}$/.test(digest)),
    'Missing original source-file hashes');
  const rawMarketSha=sha(marketBytes),rawVolatilitySha=sha(volatilityBytes),
    marketArchive='inputs/'+cut+'.market.json.gz',
    volatilityArchive='inputs/'+cut+'.volatility.json.gz',
    inputsManifest=json({cut,market_archive:marketArchive,
      volatility_archive:volatilityArchive,market_sha256:rawMarketSha,
      volatility_sha256:rawVolatilitySha,
      market_collected_at:market.generated_at,original_capture_only:true}),
    policyJson=json(request),proposalJson=json(proposal),
    sourceHashesJson=json(sourceHashes);
  const candidate={
    schema:'full-engine-first-capture-v2',
    study:registration.schema,
    role:'new-full-engine-only',
    cut,month,
    issued_at:issuedAt,market_collected_at:market.generated_at,
    engine_version:proposal.model_version,
    price_kernel_version:PRICE_KERNEL_VERSION,
    reference_id:REFERENCE_ID,
    horizons_sessions:[21,63,252],
    calibration_end:proposal.calibration_end,
    optimizer_executed:true,
    orders_recorded:true,
    forecast_scope:'full-engine optimization result and captured proposal; full-instrument distribution and account outcomes not certified',
    initial_account_scope:'canonical hypothetical account without broker connectivity',
    status:proposal.status,
    input_market_archive:marketArchive,
    input_volatility_archive:volatilityArchive,
    input_manifest_json:inputsManifest,
    policy_json:policyJson,
    proposal_json:proposalJson,
    source_hashes_json:sourceHashesJson,
    evidence:{
      market_sha256:rawMarketSha,
      inputs_sha256:sha(Buffer.from(inputsManifest)),
      model_sha256:sha(Buffer.from(sourceHashesJson)),
      policy_sha256:sha(Buffer.from(policyJson)),
      risk_calibration_sha256:rawVolatilitySha,
      forecast_sha256:sha(Buffer.from(proposalJson)),
    },
    original_price_vintages_certified:false,
    source_publication_certified:false,
    account_cashflows_certified:false,
    full_engine_confirmatory_eligible:false,
    predictive_validation:'not-established',
    production_eligible:false,
    realized_returns:null,scoring:null,future_outcomes:null,
  };
  return {candidate,marketArchiveBytes:gzipSync(marketBytes),
    volatilityArchiveBytes:gzipSync(volatilityBytes)};
}
function writeOnce(path,bytes){
  mkdirSync(dirname(path),{recursive:true});
  try {writeFileSync(path,bytes,{flag:'wx'});return true;}
  catch(error){
    if(error.code!=='EEXIST')throw error;
    check(sha(readFileSync(path))===sha(bytes),'Immutable full-engine archive differs: '+path);
    return false;
  }
}
export function preserveFullEngineCapture(root,bundle) {
  const cut=bundle.candidate.cut,base=resolve(root,BASE),
    record=resolve(base,'origins',cut+'.json.gz'),
    market=resolve(base,bundle.candidate.input_market_archive),
    volatility=resolve(base,bundle.candidate.input_volatility_archive);
  const listed=existsSync(resolve(base,'origins'))?
    readdirSync(resolve(base,'origins')).filter(x=>x.endsWith('.json.gz')):[];
  check(!listed.some(name=>name.slice(0,7)===cut.slice(0,7)&&name!==cut+'.json.gz'),
    'A first capture for this monthly cohort already exists');
  // Preserve raw bytes before publishing the receipt. If the job fails, the
  // already-written inputs can be retried only when byte-identical.
  writeOnce(market,bundle.marketArchiveBytes);
  writeOnce(volatility,bundle.volatilityArchiveBytes);
  const original=JSON.parse(gunzipSync(bundle.marketArchiveBytes));
  check(original.price_as_of===cut,'Original market archive cut differs');
  return {created:writeOnce(record,gzipSync(json(bundle.candidate))),
    origin:relative(root,record).replaceAll('\\','/'),
    cut,month:bundle.candidate.month};
}
export function captureMonthlyProposal({market,volatility,marketBytes,volatilityBytes,
  proposal,request,issuedAt,root=ROOT}) {
  const cut=market.price_as_of;
  if(!lastWeekdayCandidate(cut))return {status:'not-month-end',cut};
  const registration=JSON.parse(readFileSync(resolve(root,
    'docs/protocolo-confirmacion-integral-v2.json')));
  const data=buildFullEngineCapture({market,volatility,marketBytes,volatilityBytes,
    proposal,request,issuedAt,sourceHashes:sourceHashMap(root),registration});
  const stored=preserveFullEngineCapture(root,data);
  return {status:stored.created?'first-capture':'already-captured',...stored,
    confirmatory_eligible:false};
}
