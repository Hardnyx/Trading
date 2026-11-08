/** Classify observed snapshot archives without rewriting their original bytes.
 * Exposes source-readiness diagnostics, NOT first Git-publication or vendor
 * certification. Historical and weekend repeated closes never count as fresh.
 */
import {readFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve,join,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {classifyDailySnapshot} from './forward_account_bridge.mjs';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const fail=why=>{throw Error(why)};
const stamp=x=>typeof x==='string'&&Number.isFinite(Date.parse(x));
export function inspectDailyArchives(rows){
 if(!Array.isArray(rows))fail('Expected original daily archive collection');
 const classifications={},byDay=new Map();
 let total=0,eligible=0;
 for(const row of rows){
  const snapshot=row?.snapshot;
  const classification=classifyDailySnapshot(snapshot);
  const reason=classification.reason;
  classifications[reason]=(classifications[reason]||0)+1;
  total++;
  if(!classification.eligible)continue;
  if(!stamp(snapshot.collected_at))fail('Missing source collection timestamp');
  eligible++;
  const day=snapshot.price_as_of;
  const item={path:row.path||null,collected_at:snapshot.collected_at,
   market_date:day};
  const existing=byDay.get(day);
  // This selects an observed first-collection *candidate*, not a first Git
  // publication: Git append-only verification is done in the account bridge.
  if(!existing||Date.parse(item.collected_at)<Date.parse(existing.collected_at))
   byDay.set(day,item);
 }
 const dates=[...byDay.keys()].sort();
 return {schema:'daily-snapshot-archive-readiness-v1',
  status:'research-source-readiness-not-confirmatory',
  archive_count:total,
  original_post_close_candidate_archives:eligible,
  distinct_candidate_market_dates:dates.length,
  first_collection_candidates:dates.map(day=>byDay.get(day)),
  excluded_count:total-eligible,
  classification_counts:Object.fromEntries(Object.entries(classifications).sort()),
  first_git_publication_verified_here:false,
  independently_verified_exchange_calendar:false,
  issuer_cashflow_settlement_complete:false,
  full_engine_confirmatory_origins_certified:0,
  predictive_validation:'not-established'};
}
export function auditDailyArchives(root=ROOT){
 const base=resolve(root,'data/snapshots');
 if(!existsSync(base))return inspectDailyArchives([]);
 const rows=[];
 for(const month of readdirSync(base,{withFileTypes:true})){
  if(!month.isDirectory()||!/^20\d\d-\d\d$/.test(month.name))continue;
  const folder=join(base,month.name);
  for(const name of readdirSync(folder).filter(n=>n.endsWith('.json')).sort()){
   const path=join(folder,name);
   const bytes=readFileSync(path);
   let snapshot;
   try{snapshot=JSON.parse(bytes.toString('utf8'))}
   catch{fail('Malformed original snapshot archive: '+relative(root,path))}
   rows.push({path:relative(root,path).replaceAll('\\','/'),snapshot});
  }
 }
 return inspectDailyArchives(rows);
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const report=auditDailyArchives();
 console.log(JSON.stringify(report,null,2));
}
