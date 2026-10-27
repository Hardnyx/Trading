// Every EPS component must be published on the current share basis. This
// guard also applies when net income is missing or no original filing was read.
export function earningsShareBasis(asset, asOf=asset.price_date, record=asset.financials?.eps){
 const splits=(asset.splits||[]).filter(s=>s.date&&s.date<=asOf&&Number.isFinite(s.ratio)&&s.ratio>0&&s.ratio!==1);
 if(!record || !splits.length)return {blocked:false};
 const latest=splits.map(s=>s.date).sort().at(-1),components=record.components;
 const blocked=!Array.isArray(components)||!components.length||components.some(c=>!c.filed||c.filed<latest);
 return {blocked,splitDate:latest,reason:blocked?
  'BPA sin base por acción conciliada tras el split: faltan componentes reexpresados en informes posteriores':null};
}

// Filing presence is a coverage check, not a claim that a newer EPS was parsed.
export function financialFreshness(asset,asOf){
 const eps=asset.financials?.eps;
 const reports=(asset.filings||[]).filter(f=>
  ['10-Q','10-K','20-F'].includes(f.form)&&f.filing_date&&f.filing_date<=asOf&&
  (!f.report_date||f.report_date<=asOf));
 const latest=reports.sort((a,b)=>b.filing_date.localeCompare(a.filing_date))[0];
 const usable=eps&&eps.filed&&eps.filed<=asOf&&eps.period_end&&eps.period_end<=asOf;
 const gap=!!(usable&&latest&&(latest.report_date
  ?latest.report_date>eps.period_end:latest.filing_date>eps.filed));
 const basis=earningsShareBasis(asset,asOf);
 const status=!usable?'missing':basis.blocked?'split_basis_unverified':gap?'newer_report':'no_newer_report_detected';
 return {status,blocked:!usable||gap||basis.blocked,shareBasis:basis,period:usable?eps.period_end:null,
  filed:usable?eps.filed:null,method:usable?eps.method:null,
  observedAt:asset.financials?.observed_at||null,
  originalRecovery:asset.financials?.original_filing_recovery||null,
  originalEps:!!eps?.components?.some(r=>r.source_kind==='original_inline_xbrl'),
  refreshStatus:asset.financials?.refresh_status||'unknown',latestReport:latest||null,
  reason:!usable?'Sin BPA utilizable al corte':basis.blocked?basis.reason:gap?
   'Informe contable más reciente que el BPA: verificar cobertura XBRL antes de nuevas compras':
   'Sin informe contable posterior detectado; no acredita cobertura completa'};
}
