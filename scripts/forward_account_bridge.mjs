/** Connect immutable monthly decisions to first-published closes and cash accounting.
 * The result remains a shadow research account, never a broker or skill record.
 */
import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve,join,relative,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {gunzipSync} from 'node:zlib';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {replayCashAccount} from './full_engine_cash_ledger.mjs';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const BASE='data/confirmatory/full-engine-v2';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const requireEvidence=(ok,why)=>{if(!ok)throw Error(why);};
const date=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&
  Number.isFinite(Date.parse(d+'T12:00:00Z'))&&
  new Date(d+'T12:00:00Z').toISOString().slice(0,10)===d;
const instant=d=>typeof d==='string'&&/(?:Z|[+-]\d\d:\d\d)$/.test(d)&&
  Number.isFinite(Date.parse(d));
const hex=s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const ny=stamp=>Object.fromEntries(new Intl.DateTimeFormat('en-US',{
  timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',hourCycle:'h23'
}).formatToParts(new Date(stamp)).map(p=>[p.type,p.value]));
function weekdayAfter(day){
  requireEvidence(date(day),'Invalid exchange session date');
  const next=new Date(day+'T12:00:00Z');
  do next.setUTCDate(next.getUTCDate()+1);
  while([0,6].includes(next.getUTCDay()));
  return next.toISOString().slice(0,10);
}
function nyOpen(day){
  let t=Date.parse(day+'T14:30:00Z');
  for(let k=0;k<3;k++){
    const p=ny(t);
    t+=((9*60+30)-(Number(p.hour)*60+Number(p.minute)))*60000;
  }
  return t;
}
function postClose(stamp,day){
  if(!instant(stamp))return false;
  const p=ny(stamp);
  return p.year+'-'+p.month+'-'+p.day===day&&Number(p.hour)>=16;
}
function publication(pub,issue,cut){
  requireEvidence(pub?.verified===true&&
    /^[a-f0-9]{40}$/.test(pub.first_commit||'')&&
    instant(pub.committed_at)&&instant(issue)&&
    Date.parse(pub.committed_at)>=Date.parse(issue)&&
    Date.parse(pub.committed_at)<nyOpen(weekdayAfter(cut)),
    'Original publication is not verified before the conservative next opening');
}
const sameJson=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

/** Archive and first-publication hashes are checked before any price is used. */
export function decodeOriginalDecision({origin,firstPublication,marketBytes}){
 const cut=origin?.cut,root=origin?.evidence;
 requireEvidence(origin?.schema==='full-engine-first-capture-v2'&&
   origin.study==='full-engine-prospective-registration-v2'&&
   origin.role==='new-full-engine-only'&&date(cut)&&cut>='2026-11-09'&&
   origin.month===cut.slice(0,7)&&origin.predictive_validation==='not-established'&&
   origin.full_engine_confirmatory_eligible===false,
   'Unregistered or falsely promoted monthly decision');
 requireEvidence(postClose(origin.issued_at,cut),'Monthly decision was not issued after NY close');
 publication(firstPublication,origin.issued_at,cut);
 for(const [key,field] of [
  ['proposal_json','forecast_sha256'],['policy_json','policy_sha256'],
  ['source_hashes_json','model_sha256'],['input_manifest_json','inputs_sha256']
 ])requireEvidence(typeof origin[key]==='string'&&sha(Buffer.from(origin[key]))===root?.[field],
   'Modified original '+key);
 requireEvidence(Buffer.isBuffer(marketBytes)&&sha(marketBytes)===root?.market_sha256,
   'Original market archive does not match first-capture hash');
 const originalMarket=JSON.parse(marketBytes.toString('utf8'));
 const proposal=JSON.parse(origin.proposal_json),policy=JSON.parse(origin.policy_json);
 requireEvidence(originalMarket.price_as_of===cut&&
  originalMarket.generated_at===origin.market_collected_at&&
  postClose(originalMarket.generated_at,cut)&&
  originalMarket.assets?.some(a=>a.symbol==='SPY'&&a.price_date===cut),
  'Original market was not collected at the decision cut');
 requireEvidence(proposal.as_of===cut&&proposal.information_as_of===cut&&
  proposal.calibration_end===cut&&proposal.model_version===origin.engine_version&&
  proposal.status===origin.status&&['hold','proposed'].includes(proposal.status)&&
  Array.isArray(proposal.positions)&&proposal.trade_plan&&
  policy.settings?.asOf===cut&&policy.settings?.informationAsOf===cut&&
  policy.settings.account?.enabled===false,
  'Original proposal is not the registered reference decision');
 requireEvidence(policy.settings.mandate?.dividendPolicy==='cash'&&
  policy.settings.mandate?.cashYield===0&&
  policy.settings.mandate?.referenceCurrency==='USD'&&
  Number.isFinite(policy.settings.capital)&&policy.settings.capital>0,
  'Reference account needs noncash interest, reinvestment, FX or unknown capital');
 return {decision:{cut,issued_at:origin.issued_at,publication:firstPublication,
  forecast_sha256:root.forecast_sha256,model_status:proposal.status,
  positions:proposal.positions},
  originalMarket,execution:policy.settings.execution,
  mandate:policy.settings.mandate,capital:policy.settings.capital,
  initialAccount:proposal.current_account||null};
}

/** Eligibility is based on original market date, not the capture's label. */
export function classifyDailySnapshot(snapshot){
 const s=snapshot;
 if(s?.schema_version!==1||!date(s.price_as_of)||!date(s.requested_as_of)||
    !instant(s.collected_at))
  return {eligible:false,reason:'invalid-capture-metadata'};
 const local=ny(s.collected_at);
 const observedDay=local.year+'-'+local.month+'-'+local.day;
 if(s.requested_as_of!==observedDay)
  return {eligible:false,reason:'historical-request'};
 if(s.price_as_of!==s.requested_as_of)
  return {eligible:false,reason:'stale-market-close'};
 if(!postClose(s.collected_at,s.price_as_of))
  return {eligible:false,reason:'pre-close-or-different-session'};
 if(s.collection_mode!=='current')
  return {eligible:false,reason:'not-original-current-capture'};
 const spy=s.assets?.find(a=>a.symbol==='SPY');
 if(spy?.price_date!==s.price_as_of||spy.quote?.date!==s.price_as_of||
    !(spy.quote?.close>0))
  return {eligible:false,reason:'benchmark-original-close-missing'};
 return {eligible:true,reason:'post-close-original-candidate'};
}
export function partitionDailyArchives(rows){
 const accepted=[],excluded=[],reasons={};
 for(const row of rows){
  const result=classifyDailySnapshot(row.snapshot);
  if(result.eligible)accepted.push(row);
  else{
   excluded.push({path:row.path||null,
    price_as_of:row.snapshot?.price_as_of||null,
    requested_as_of:row.snapshot?.requested_as_of||null,
    reason:result.reason});
   reasons[result.reason]=(reasons[result.reason]||0)+1;
  }
 }
 return {accepted,excluded,reasons};
}

/** Select the earliest original publication per date; later revisions cannot replace it. */
export function selectFirstPublishedCloses(rows){
 requireEvidence(Array.isArray(rows),'Daily publication evidence is missing');
 const eligible=new Map(),revisions=[];
 for(const row of rows){
  const s=row?.snapshot;
  requireEvidence(s?.schema_version===1&&date(s.price_as_of)&&
    classifyDailySnapshot(s).eligible&&
    Buffer.isBuffer(row.bytes)&&sha(row.bytes)===row.source_sha256&&
    sameJson(JSON.parse(row.bytes.toString('utf8')),s),
    'A daily observation is not its original current-market archive');
  publication(row.publication,s.collected_at,s.price_as_of);
  const key=s.price_as_of;
  const sortKey=[row.publication.committed_at,s.collected_at,row.path||''].join('|');
  const current={...row,sortKey};
  const previous=eligible.get(key);
  if(!previous||sortKey<previous.sortKey){
   if(previous)revisions.push({date:key,path:previous.path||null});
   eligible.set(key,current);
  }else revisions.push({date:key,path:row.path||null});
 }
 return {first:eligible,revisions};
}

/** Prepared calendar must be externally verified; observed SPY records alone do not certify holidays. */
export function buildForwardAccount({capture,daily,sessionEvidence,issuerEvidence}){
 const {decision,originalMarket,execution,mandate,capital,initialAccount}=
  decodeOriginalDecision(capture);
 requireEvidence(sessionEvidence?.schema==='verified-us-exchange-sessions-v1'&&
  sessionEvidence.original_source_verified===true&&hex(sessionEvidence.source_sha256)&&
  Array.isArray(sessionEvidence.sessions)&&sessionEvidence.sessions.length>=2,
  'Missing separately verified exchange-session calendar');
 const calendar=sessionEvidence.sessions;
 requireEvidence(calendar[0]===decision.cut&&
  calendar.every((day,i)=>date(day)&&(!i||calendar[i-1]<day)),
  'Exchange sessions are duplicated, unsorted or omit first decision cut');
 const selected=selectFirstPublishedCloses(daily);
 // The first published source for every session is mandatory; no skipping holidays
 // by inferring a weekday-only calendar from Yahoo prices.
 requireEvidence(calendar.slice(1).every(d=>selected.first.has(d))&&
  [...selected.first.keys()].every(d=>d<=decision.cut||calendar.includes(d)),
  'At least one registered trading session lacks its original first-published close');
 const symbols=new Set(['SPY']);
 if(decision.model_status!=='hold')for(const pos of decision.positions)
  if(pos.weight>0&&pos.symbol!=='CASH')symbols.add(pos.symbol);
 const assets=[];
 for(const symbol of [...symbols].sort()){
  const c=issuerEvidence?.[symbol];
  requireEvidence(c?.schema==='issuer-cash-settlement-v1'&&
    c.symbol===symbol&&c.currency==='USD'&&c.complete===true&&
    c.original_source_verified===true&&hex(c.source_sha256)&&
    date(c.coverage_start)&&date(c.coverage_end)&&
    c.coverage_start<=decision.cut&&c.coverage_end>=calendar.at(-1)&&
    Array.isArray(c.events)&&Array.isArray(c.splits),
    'Missing verified issuer dividend/split settlement coverage for '+symbol);
  const base=originalMarket.assets.find(a=>a.symbol===symbol);
  const originRow=base?.history?.find(x=>x.date===decision.cut);
  requireEvidence(base?.price_date===decision.cut&&
    Number.isFinite(originRow?.close)&&originRow.close>0,
    'Original decision has no unadjusted cut close for '+symbol);
  const history=[{date:decision.cut,close:originRow.close}];
  for(const day of calendar.slice(1)){
   const s=selected.first.get(day).snapshot;
   const a=s.assets?.find(a=>a.symbol===symbol),q=a?.quote;
   requireEvidence(a?.currency==='USD'&&a.price_date===day&&
    q?.date===day&&Number.isFinite(q?.close)&&q.close>0,
    'Original first-published close is missing for '+symbol+' on '+day);
   history.push({date:day,close:q.close});
  }
  assets.push({symbol,currency:'USD',history,
    distributions:{complete:true,currency:'USD',coverage_start:c.coverage_start,
      coverage_end:c.coverage_end,events:c.events},
    splits:c.splits});
 }
 // A second monthly decision from the canonical empty account cannot correctly
 // rebalance an already invested account. Never splice reset accounts together.
 requireEvidence(initialAccount===null||initialAccount.capital===capital,
   'Original optimizer account capital disagrees with sealed reference');
 const prepared={id:'original-full-engine-shadow-cash-account',
  calendar,assets,decisions:[{...decision,execute:calendar[1]}],
  initialCapital:capital,costs:execution,mandate};
 return {prepared,sourceManifest:{origin_cut:decision.cut,
   original_forecast_sha256:decision.forecast_sha256,
   first_publication:decision.publication.first_commit,
   calendar_source_sha256:sessionEvidence.source_sha256,
   daily_first_publications:calendar.slice(1).map(day=>({
    date:day,commit:selected.first.get(day).publication.first_commit,
    archive_sha256:selected.first.get(day).source_sha256})),
   ignored_later_revisions:selected.revisions,
   issuer_source_sha256:Object.fromEntries([...symbols].sort().map(symbol=>
    [symbol,issuerEvidence[symbol].source_sha256]))}};
}
export function runForwardAccount(inputs){
 const result=replayCashAccount(inputs.prepared);
 return {...result,source_manifest:inputs.sourceManifest,
  broker_execution_certified:false,
  original_market_vintages_certified:false,
  exchange_calendar_authenticated_by_code:false,
  formal_validation:false,predictive_validation:'not-established'};
}

function gitFirstAdd(root,path,original){
 const rel=relative(root,path).replaceAll('\\','/');
 const command=(args,encoding='utf8')=>execFileSync('git',args,
  {cwd:root,encoding,stdio:['ignore','pipe','ignore']});
 requireEvidence(command(['rev-parse','--is-shallow-repository']).trim()==='false',
  'Full Git history is required for independent first-add verification');
 const shaCommit=command(['log','--reverse','--diff-filter=A','--format=%H','--',rel])
  .trim().split('\n')[0];
 requireEvidence(/^[a-f0-9]{40}$/.test(shaCommit),
  'Missing first Git publication for '+rel);
 requireEvidence(sha(command(['show',shaCommit+':'+rel],null))===sha(original),
  'Archive was overwritten after its first published commit: '+rel);
 return {verified:true,first_commit:shaCommit,
  committed_at:command(['show','-s','--format=%cI',shaCommit]).trim()};
}
function archiveFiles(root,folder,suffix){
 const dir=resolve(root,folder);
 if(!existsSync(dir))return [];
 return readdirSync(dir).filter(x=>x.endsWith(suffix)).sort()
  .map(x=>join(dir,x));
}
export function auditForwardAccount(root=ROOT){
 const answer={schema:'forward-full-engine-account-audit-v1',
  status:'blocked-no-original-full-engine-capture',original_months:0,
  observed_sessions:0,causally_certified_origins:0,
  original_vintages_verified:false,formal_validation:false,
  predictive_validation:'not-established',blockers:[]};
 const origins=archiveFiles(root,BASE+'/origins','.json.gz');
 answer.original_months=origins.length;
 if(!origins.length){
  answer.blockers.push('No first-published monthly full-engine origin since registration');
  return answer;
 }
 // Archive, source-code and first-publication verification is independently
 // enforced by the preregistration auditor before any further reconciliation.
 execFileSync(process.env.PYTHON||'python',
  ['scripts/prospective_study_registry.py','--verify'],
  {cwd:root,stdio:['ignore','pipe','pipe']});
 const captures=origins.map(path=>{
  const bytes=readFileSync(path),origin=JSON.parse(gunzipSync(bytes));
  const input=resolve(root,BASE,origin.input_market_archive);
  requireEvidence(input.startsWith(resolve(root,BASE)+'/'),
    'Monthly source archive path escapes its study folder');
  return {origin,marketBytes:gunzipSync(readFileSync(input)),
   firstPublication:gitFirstAdd(root,path,bytes)};
 });
 // The canonical engine currently resets the account on every monthly run.
 // Even with daily outcomes, only a single-origin account can be safely
 // reconstructed until a continuous-account decision source is implemented.
 if(captures.length>1){
  answer.status='blocked-reset-account-between-months';
  answer.blockers.push('Multiple canonical zero-holdings decisions cannot form a continuous account');
  return answer;
 }
 const sessionFile=resolve(root,BASE,'exchange-sessions.json');
 if(!existsSync(sessionFile)){
  answer.status='blocked-exchange-calendar-source';
  answer.blockers.push('No independently sourced NYSE session calendar has been archived');
  return answer;
 }
 const sessionBytes=readFileSync(sessionFile);
 gitFirstAdd(root,sessionFile,sessionBytes);
 const sessions=JSON.parse(sessionBytes);
 const cashflow={},symbols=new Set(['SPY']);
 const orig=JSON.parse(captures[0].origin.proposal_json);
 if(orig.status!=='hold')for(const p of orig.positions)
  if(p.weight>0&&p.symbol!=='CASH')symbols.add(p.symbol);
 for(const symbol of symbols){
  const path=resolve(root,BASE,'cashflow-evidence',symbol+'.json');
  if(!existsSync(path)){
   answer.status='blocked-issuer-cashflow-source';
   answer.blockers.push('Missing independently verified issuer cashflow settlement index for '+symbol);
   continue;
  }
  const bytes=readFileSync(path);
  gitFirstAdd(root,path,bytes);
  cashflow[symbol]=JSON.parse(bytes);
 }
 if(answer.blockers.length)return answer;
 const month=captures[0].origin.month;
 // Future sessions require explicit month-by-month input archives.
 let cursor=month.slice(0,4)*12+Number(month.slice(5,7));
 const terminal=sessions.sessions.at(-1).slice(0,4)*12+
  Number(sessions.sessions.at(-1).slice(5,7));
 const files=[];
 while(cursor<=terminal){
  const y=Math.floor((cursor-1)/12),m=(cursor-1)%12+1;
  files.push(...archiveFiles(root,'data/snapshots/'+y+'-'+String(m).padStart(2,'0'),'.json'));
  cursor++;
 }
 const candidateSnapshots=files.flatMap(path=>{
  const bytes=readFileSync(path),snapshot=JSON.parse(bytes);
  if(!(snapshot.price_as_of>captures[0].origin.cut&&
       sessions.sessions.includes(snapshot.price_as_of)))return [];
  return [{snapshot,bytes,source_sha256:sha(bytes),
    path:relative(root,path).replaceAll('\\','/')}];
 });
 const selectedArchives=partitionDailyArchives(candidateSnapshots);
 answer.excluded_snapshot_count=selectedArchives.excluded.length;
 answer.excluded_snapshot_reasons=selectedArchives.reasons;
 // Do not admit stale/repeated quotes even if their collection_mode was
 // mislabeled 'current' by an older collector version.
 const daily=selectedArchives.accepted.map(row=>({
  ...row,publication:gitFirstAdd(root,
    resolve(root,row.path),row.bytes)}));
 answer.observed_sessions=daily.length;
 const input=buildForwardAccount({capture:captures[0],daily,
  sessionEvidence:sessions,issuerEvidence:cashflow});
 const result=runForwardAccount(input);
 answer.status=result.status==='complete'?'research-account-unconfirmed':'blocked-account-reconciliation';
 answer.accounted_sessions=result.accounted_sessions;
 answer.identity_max_residual=result.nav.length?
  Math.max(...result.nav.map(n=>Math.abs(n.identity_residual))):null;
 answer.blockers.push(...result.issues.map(i=>i.date+': '+i.reason));
 answer.shadow_trade_count=result.journal.filter(x=>x.type==='shadow-trade').length;
 return answer;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
 console.log(JSON.stringify(auditForwardAccount(),null,2));
