// Diagnostic audit of prospectively scored forecasts. Non-overlap reduces reuse
// of the same returns; it does not prove independence or predictive validity.
export function calibrationAudit(rows, minimum=20){
 if(!Number.isInteger(minimum)||minimum<2)throw Error('Mínimo de ventanas no válido');
 const groups=new Map();
 const day=x=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x)&&Number.isFinite(Date.parse(x+'T00:00:00Z'));
 for(const r of rows||[]){
  const p=r.prediction||{},o=r.origin||{},end=r.maturity||r.target_date;
  if(r.status!=='scored'||o.prospective!==true||!o.model_version||!day(o.price_as_of)||!day(end)||end<=o.price_as_of||
   ![r.realized,p.mean,p.p05,p.p95,p.lossProbability,p.horizon].every(Number.isFinite)||p.horizon<=0||p.p05>p.p95||p.lossProbability<0||p.lossProbability>1)continue;
  const currency=o.settings?.mandate?.referenceCurrency||'USD';
  const key=JSON.stringify([o.model_version,p.model||o.settings?.model||'unknown',p.horizon,currency,o.settings?.driftMode||'unknown',o.settings?.volatilityMode||'unknown']);
  if(!groups.has(key))groups.set(key,{version:o.model_version,model:p.model||o.settings?.model||'unknown',horizon:p.horizon,currency,rows:[]});
  groups.get(key).rows.push({...r,end});
 }
 const result=[];
 for(const g of groups.values()){
  const sorted=g.rows.sort((a,b)=>a.end.localeCompare(b.end)||a.origin.price_as_of.localeCompare(b.origin.price_as_of)||String(a.id).localeCompare(String(b.id)));
  let last='',selected=[];
  for(const r of sorted)if(r.origin.price_as_of>=last){selected.push(r);last=r.end;}
  const n=selected.length,avg=fn=>selected.reduce((s,r)=>s+fn(r),0)/n;
  const coverage=avg(r=>Number(r.realized>=r.prediction.p05&&r.realized<=r.prediction.p95));
  const z=1.959963984540054,den=1+z*z/n,center=(coverage+z*z/(2*n))/den;
  const radius=z*Math.sqrt(coverage*(1-coverage)/n+z*z/(4*n*n))/den;
  result.push({version:g.version,model:g.model,horizon:g.horizon,currency:g.currency,
   scored:g.rows.length,nonoverlapping:n,overlapExcluded:g.rows.length-n,
   selectedIds:selected.map(r=>r.id),bias:avg(r=>r.realized-r.prediction.mean),
   mae:avg(r=>Math.abs(r.realized-r.prediction.mean)),rmse:Math.sqrt(avg(r=>(r.realized-r.prediction.mean)**2)),
   brier:avg(r=>(r.prediction.lossProbability-Number(r.realized<0))**2),
   coverage,coverageLower:Math.max(0,center-radius),coverageUpper:Math.min(1,center+radius),nominalCoverage:.9,
   averageLossProbability:avg(r=>r.prediction.lossProbability),observedLossRate:avg(r=>Number(r.realized<0)),
   status:n<minimum?'insufficient_nonoverlapping_windows':'diagnostic_sample_available',minimum,
   parameterPromotionAllowed:false});
 }
 return {groups:result,minimum,note:'Agrupación por versión, modelo, horizonte, moneda y métodos de retorno/volatilidad. Selección por vencimiento más temprano, sin usar aciertos. Ventanas sin solape no garantizan independencia. IC Wilson 95% descriptivo; mínimo de '+minimum+' ventanas es una regla operativa, no un cálculo de potencia. No recalibra parámetros ni valida el modelo automáticamente.'};
}
