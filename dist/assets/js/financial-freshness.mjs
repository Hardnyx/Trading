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
 const status=!usable?'missing':gap?'newer_report':'no_newer_report_detected';
 return {status,blocked:!usable||gap,period:usable?eps.period_end:null,
  filed:usable?eps.filed:null,method:usable?eps.method:null,
  observedAt:asset.financials?.observed_at||null,
  refreshStatus:asset.financials?.refresh_status||'unknown',latestReport:latest||null,
  reason:!usable?'Sin BPA utilizable al corte':gap?
   'Informe contable más reciente que el BPA: verificar cobertura XBRL antes de nuevas compras':
   'Sin informe contable posterior detectado; no acredita cobertura completa'};
}
