/** Account-aware research origin: never a revision to frozen full-engine v2. */
import {createHash} from 'node:crypto';
import {referenceRequest,REFERENCE_ID} from '../dist/assets/js/reference-preset.mjs?v=0.35.0';
import {MODEL_VERSION,currentAccount} from '../dist/assets/js/policy.mjs?v=0.35.0';
import {composeMultiStart} from '../dist/assets/js/composer.mjs?v=0.35.0';

export const ACCOUNT_RESEARCH_COHORT='continuous-account-research-v1';
export const SEGREGATED_RESEARCH_COHORT='continuous-account-research-v2';
export const FIXED_SEARCH=Object.freeze({candidates:300,paths:600,finalPaths:3000});
const hash=b=>createHash('sha256').update(b).digest('hex');
const guard=(ok,why)=>{if(!ok)throw Error(why)};
const number=x=>typeof x==='number'&&Number.isFinite(x);
const positive=x=>number(x)&&x>0;
const tolerance=x=>Math.max(1e-7,Math.abs(x)*1e-8);
const day=x=>typeof x==='string'&&/^\d{4}-\d\d-\d\d$/.test(x)&&
  !Number.isNaN(Date.parse(x+'T12:00:00Z'))&&
  new Date(x+'T12:00:00Z').toISOString().slice(0,10)===x;
const timed=x=>typeof x==='string'&&/(?:Z|[+-]\d\d:\d\d)$/.test(x)&&
  Number.isFinite(Date.parse(x));
function newYork(t){
 return Object.fromEntries(new Intl.DateTimeFormat('en-US',{
  timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',hourCycle:'h23'
 }).formatToParts(new Date(t)).map(x=>[x.type,x.value]));
}
function postClose(value,cut){
 if(!timed(value))return false;
 const p=newYork(value);
 return p.year+'-'+p.month+'-'+p.day===cut&&Number(p.hour)>=16;
}
function nextWeekday(cut){
 const d=new Date(cut+'T12:00:00Z');
 do d.setUTCDate(d.getUTCDate()+1);
 while([0,6].includes(d.getUTCDay()));
 return d.toISOString().slice(0,10);
}
function nextOpen(cut){
 let t=Date.parse(nextWeekday(cut)+'T14:30:00Z');
 for(let k=0;k<3;k++){
  const p=newYork(t);
  t+=((9*60+30)-(Number(p.hour)*60+Number(p.minute)))*60000;
 }
 return t;
}
/** Convert a cut-matched ledger close into the existing supported account API. */
function prepareAccountRequest({snapshot,ledger,ledgerBytes,issuedAt},{segregateReceivables=false}={}){
 const cut=snapshot?.price_as_of;
 guard(day(cut)&&postClose(snapshot?.generated_at,cut),
  'Original market snapshot must be collected after New York close');
 guard(postClose(issuedAt,cut)&&Date.parse(issuedAt)>=Date.parse(snapshot.generated_at)&&
  Date.parse(issuedAt)<nextOpen(cut),
  'Account-aware issue must occur after close and before next opening');
 guard(snapshot.requested_as_of===cut&&Array.isArray(snapshot.assets)&&
  snapshot.assets.every(a=>(a.history||[]).every(p=>p.date<=cut)),
  'Future market observations or backfilled historical request');
 guard(Buffer.isBuffer(ledgerBytes)&&
  JSON.stringify(JSON.parse(ledgerBytes.toString('utf8')))===JSON.stringify(ledger),
  'Reconciled account differs from its supplied original bytes');
 guard(ledger?.schema==='full-engine-cash-account-research-v1'&&
  ledger.status==='complete'&&ledger.observed_through===cut&&
  Array.isArray(ledger.nav)&&ledger.nav.length>0&&
  ledger.nav.at(-1).date===cut&&ledger.accounted_sessions===ledger.nav.length&&
  Array.isArray(ledger.journal)&&Array.isArray(ledger.decisions)&&
  Array.isArray(ledger.pending_receivables),
  'Missing complete account ledger ending at the decision close');
 guard(ledger.nav.every((r,i)=>day(r.date)&&r.date<=cut&&
  (!i||ledger.nav[i-1].date<r.date)&&number(r.identity_residual)&&
  Math.abs(r.identity_residual)<=tolerance(r.nav))&&
  ledger.journal.every(p=>day(p.date)&&p.date<=cut)&&
  ledger.decisions.every(d=>day(d.cut)&&day(d.execute)&&d.cut<d.execute&&d.execute<=cut),
  'Account contains future postings, out-of-order dates or a NAV residual');
 const last=ledger.nav.at(-1);
 guard(positive(last.nav)&&number(last.cash)&&last.cash>=0&&
  Array.isArray(last.holdings)&&number(last.receivables)&&last.receivables>=0&&
  Math.abs(last.cash-ledger.final_cash)<=tolerance(last.nav),
  'Account NAV or final settled cash is invalid');
 let segregated=0;
 if(!segregateReceivables){
  guard(last.receivables<=tolerance(last.nav)&&ledger.pending_receivables.length===0,
   'Unsettled dividends cannot enter an optimizer without receivables');
 }else{
  const claims=ledger.pending_receivables;
  const used=new Set();
  for(const claim of claims){
   guard(claim&&typeof claim.symbol==='string'&&day(claim.ex_date)&&
    day(claim.pay_date)&&claim.ex_date<=cut&&claim.pay_date>cut&&
    positive(claim.gross)&&positive(claim.quantity)&&
    number(claim.per_share)&&claim.per_share>0&&
    Math.abs(claim.quantity*claim.per_share-claim.gross)<=tolerance(claim.gross),
    'Unsettled dividend is missing a valid previously declared entitlement');
   const key=[claim.symbol,claim.ex_date,claim.pay_date,claim.gross].join('|');
   guard(!used.has(key),'Duplicate unsettled entitlement');
   used.add(key);
   const original=ledger.journal.filter(p=>p.type==='dividend-receivable'&&
    p.symbol===claim.symbol&&p.ex_date===claim.ex_date&&
    p.pay_date===claim.pay_date&&number(p.gross)&&
    Math.abs(p.gross-claim.gross)<=tolerance(claim.gross));
   const alreadyPaid=ledger.journal.some(p=>p.type==='dividend-payment'&&
    p.symbol===claim.symbol&&p.ex_date===claim.ex_date);
   guard(original.length===1&&!alreadyPaid,
    'Unsettled dividend has no unique original unpaid entitlement');
   segregated+=claim.gross;
  }
  guard(Math.abs(segregated-last.receivables)<=tolerance(last.nav),
   'Unsettled entitlements do not reconcile to receivables in total NAV');
 }
 const investable=last.nav-segregated;
 guard(positive(investable),'No positive investable NAV after segregating claims');
 const market=new Map(snapshot.assets.map(x=>[x.symbol,x]));
 guard(market.size===snapshot.assets.length,'Duplicate symbols in original snapshot');
 const holdings=[],seen=new Set();let invested=0;
 for(const row of last.holdings){
  guard(typeof row.symbol==='string'&&row.symbol!=='CASH'&&!seen.has(row.symbol)&&
   positive(row.quantity)&&positive(row.raw_close)&&positive(row.market_value),
   'Invalid or duplicate held position');
  seen.add(row.symbol);
  const asset=market.get(row.symbol);
  guard(asset?.currency==='USD'&&asset.price_date===cut&&positive(asset.price)&&
   asset.history?.at(-1)?.date===cut&&positive(asset.history.at(-1).close)&&
   Math.abs(asset.price-row.raw_close)<=tolerance(asset.price)&&
   Math.abs(asset.history.at(-1).close-row.raw_close)<=tolerance(asset.price),
   'Held asset has no matching unadjusted original cut close');
  guard(Math.abs(row.quantity*row.raw_close-row.market_value)<=tolerance(row.market_value)&&
   ledger.final_units?.[row.symbol]===row.quantity,
   'Original holdings disagree with shares, price or final account units');
  invested+=row.market_value;
  holdings.push({symbol:row.symbol,quantity:row.quantity,costBasis:null});
 }
 guard(ledger.final_units&&Object.keys(ledger.final_units).length===seen.size&&
  Object.keys(ledger.final_units).every(k=>seen.has(k)),
  'Hidden final units were omitted from the current account');
 guard(Math.abs(invested+last.cash-investable)<=tolerance(last.nav),
  'NAV contains unrepresented assets or liabilities');
 const preset=referenceRequest(snapshot);
 guard(preset.settings.account?.enabled===false&&preset.settings.baseline===null&&
  preset.settings.mandate.referenceCurrency==='USD'&&
  preset.settings.mandate.dividendPolicy==='cash'&&
  preset.settings.mandate.cashYield===0&&
  (preset.settings.execution.capitalGainsTax??0)===0,
  'Reference economics cannot value this cash-only account');
 const request={...preset,settings:{...preset.settings,
  capital:investable,baseline:null,account:{enabled:true,cash:last.cash,positions:holdings}}};
 const valued=currentAccount(snapshot,request.settings.account,null,investable);
 guard(Math.abs(valued.capital-investable)<=tolerance(last.nav)&&
  Math.abs(valued.positions.reduce((s,p)=>s+p.weight,0)-1)<1e-8,
  'Existing optimizer values carried state differently from the cash ledger');
 return {schema:segregateReceivables?
   'account-aware-research-request-v2':'account-aware-research-request-v1',
  cohort_id:segregateReceivables?SEGREGATED_RESEARCH_COHORT:ACCOUNT_RESEARCH_COHORT,
  account_basis:segregateReceivables?'settled-investable-only':'total-nav-no-receivables',
  total_account_nav:last.nav,investable_account_nav:investable,
  segregated_receivables:segregated,
  unsettled_claims:segregateReceivables?ledger.pending_receivables.map(c=>({...c})):[],
  reference_id:REFERENCE_ID,engine_version:MODEL_VERSION,
  cut,issued_at:issuedAt,request,search:{...FIXED_SEARCH},
  state_sha256:hash(ledgerBytes),
  market_snapshot_sha256:hash(Buffer.from(JSON.stringify(snapshot))),
  request_sha256:hash(Buffer.from(JSON.stringify(request))),
  initial_account_nav:last.nav,
  original_v2_cohort_reused:false,source_lineage_certified:false,
  confirmatory_eligible:false,predictive_validation:'not-established'};
}
/** Retain the original no-receivable research cohort unchanged. */
export function prepareContinuousAccountRequest(input){
 return prepareAccountRequest(input,{segregateReceivables:false});
}
/** Explicit separate cohort: do not allow dividend claims to finance trades. */
export function prepareSegregatedAccountRequest(input){
 return prepareAccountRequest(input,{segregateReceivables:true});
}
/** Strict handoff; deliberately not connected to captureMonthlyProposal(v2). */
function accountHandoff(prepared,segregated){
 const cohort=segregated?SEGREGATED_RESEARCH_COHORT:ACCOUNT_RESEARCH_COHORT;
 const schema=segregated?'account-aware-research-request-v2':'account-aware-research-request-v1';
 guard(prepared?.schema===schema&&
  prepared.cohort_id===cohort&&
  prepared.account_basis===(segregated?'settled-investable-only':'total-nav-no-receivables')&&
  number(prepared.total_account_nav)&&positive(prepared.investable_account_nav)&&
  number(prepared.segregated_receivables)&&prepared.segregated_receivables>=0&&
  Math.abs(prepared.total_account_nav-prepared.investable_account_nav-
   prepared.segregated_receivables)<=tolerance(prepared.total_account_nav)&&
  (!segregated?prepared.segregated_receivables===0:
   Array.isArray(prepared.unsettled_claims))&&
  prepared.confirmatory_eligible===false&&
  JSON.stringify(prepared.search)===JSON.stringify(FIXED_SEARCH)&&
  prepared.request.settings.account?.enabled===true&&
  prepared.request.settings.asOf===prepared.cut&&
  prepared.request.settings.informationAsOf===prepared.cut&&
  prepared.request.settings.seed===20261024&&
  hash(Buffer.from(JSON.stringify(prepared.request)))===prepared.request_sha256,
  'Invalid research cohort, altered search or unregistered account');
 return {schema:segregated?'account-aware-research-handoff-v2':
   'account-aware-research-handoff-v1',
  cohort_id:cohort,account_basis:prepared.account_basis,
  total_account_nav:prepared.total_account_nav,
  investable_account_nav:prepared.investable_account_nav,
  segregated_receivables:prepared.segregated_receivables,cut:prepared.cut,
  account_state_sha256:prepared.state_sha256,
  request:prepared.request,search:{...FIXED_SEARCH},
  original_v2_cohort_reused:false,confirmatory_eligible:false,
  predictive_validation:'not-established'};
}
export function continuousAccountHandoff(prepared){
 return accountHandoff(prepared,false);
}
export function segregatedAccountHandoff(prepared){
 return accountHandoff(prepared,true);
}
/** Explicit research-only composer; without publication, no causal confirmation. */
function runResearchComposer(snapshot,prepared,segregated){
 const handoff=accountHandoff(prepared,segregated);
 guard(snapshot?.price_as_of===handoff.cut&&
  snapshot.generated_at&&handoff.request.settings.account.enabled===true&&
  hash(Buffer.from(JSON.stringify(snapshot)))===prepared.market_snapshot_sha256,
  'Research composer market or account origin changed');
 const proposal=composeMultiStart(snapshot,handoff.request.settings,
  handoff.request.overrides,handoff.request.rules,handoff.search);
 guard(proposal?.as_of===handoff.cut&&proposal.current_account?.capital>0&&
  proposal.account_source==='Cantidades y efectivo ingresados',
  'Composer rejected carried account state');
 return {schema:segregated?'continuous-account-research-proposal-v2':
   'continuous-account-research-proposal-v1',
  cohort_id:handoff.cohort_id,
  account_basis:handoff.account_basis,
  total_account_nav:handoff.total_account_nav,
  investable_account_nav:handoff.investable_account_nav,
  segregated_receivables:handoff.segregated_receivables,
  cut:handoff.cut,
  account_state_sha256:handoff.account_state_sha256,proposal,
  original_v2_cohort_reused:false,first_git_publication_certified:false,
  confirmatory_eligible:false,predictive_validation:'not-established'};
}

export function composeContinuousAccountResearch(snapshot,prepared){
 return runResearchComposer(snapshot,prepared,false);
}
export function composeSegregatedAccountResearch(snapshot,prepared){
 return runResearchComposer(snapshot,prepared,true);
}
