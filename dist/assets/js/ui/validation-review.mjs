/** Evidence presentation only. This module never changes anchors or weights. */
import {template} from './templates.mjs?v=0.35.0';
import {fmt,pct,dateLabel} from './format.mjs?v=0.35.0';
import {lineChart} from '../charts.mjs?v=0.35.0';
import {PRICE_KERNEL_VERSION} from '../path-model.mjs?v=0.35.0';

export function reviewStatus(report,market,now=Date.now()){
 if(!report||report.protocol!=='monthly-validation-review-v1'||!report.kernel?.series||!report.signals||
  !['accumulating','incomplete','review-required','not-rejected-unvalidated'].includes(report.monthly_review?.verdict))return {label:'SEGUIMIENTO NO DISPONIBLE',tone:'orange',
  message:'No se puede comprobar el estado de los registros de validación.',warning:true};
 const age=now-Date.parse(report.updated_at);
 if(report.price_kernel_version!==PRICE_KERNEL_VERSION||report.price_cut!==market.price_as_of||report.source_market_generated_at!==market.generated_at||
  !Number.isFinite(age)||age>96*3600000||age< -300000)return {label:'SEGUIMIENTO DESACTUALIZADO',tone:'orange',
  message:'El seguimiento no corresponde al corte cargado o lleva más de cuatro días sin actualizarse.',warning:true};
 if(report.health!=='complete')return {label:'EVIDENCIA INCOMPLETA',tone:'negative',
  message:'Hay fallos de actualización, publicación o resultados pendientes de conciliar. Revisa el registro antes de interpretar sus pruebas.',warning:true};
 const verdict=report.monthly_review?.verdict;
 if(verdict==='review-required')return {label:'MODELO EN REVISIÓN',tone:'negative',
  message:'La revisión mensual detectó rechazos. Se suspenden nuevas promociones y se requiere una decisión documentada; esta propuesta no acredita operativa validada.',warning:true};
 if(verdict==='incomplete')return {label:'REVISIÓN MENSUAL INCOMPLETA',tone:'orange',
  message:'La revisión fijada para este mes no pudo evaluar toda la evidencia. La reparación posterior no reescribe esa revisión.',warning:true};
 return {label:verdict==='not-rejected-unvalidated'?'SIN RECHAZO · SIN VALIDAR':'ACUMULANDO · SIN VALIDAR',tone:'orange',
  message:verdict==='not-rejected-unvalidated'?'No rechazar no demuestra precisión, buena estimación de cola ni ventaja económica.':'Faltan resultados maduros para contrastar el acierto del modelo.',warning:false};
}
export function reviewDecisionWarning(report,market,now=Date.now()){
 const status=reviewStatus(report,market,now);
 return status.warning?template('validation-review-warning',{message:status.message}):'';
}
export function validationReviewPanel(report,market,now=Date.now()){
 const status=reviewStatus(report,market,now),usable=report&&report.price_cut===market.price_as_of&&
  report.source_market_generated_at===market.generated_at,rows=[],plots=[];
 if(usable)for(const h of [1,5,21]){
  for(const [key,r] of Object.entries(report.kernel?.series||{})){
   if(!key.startsWith(h+'|')||!key.includes('PORTFOLIO:'))continue;
   const name=key.split('PORTFOLIO:')[1]==='reference-decision'?'Propuesta sellada':'Cesta de riesgo';
   rows.push(template('validation-review-row',{horizon:h,name,origins:r.nonoverlapping_origins,
    coverage:r.nonoverlapping_origins?pct(r.exception_rate,1):'Pendiente',
    interval:r.exact_binomial_95?r.exact_binomial_95.map(v=>pct(v,1)).join(' a '):'Sin muestra',
    gain:r.crps_gain===null?'Pendiente':fmt(r.crps_gain,4),missing:r.missing_outcomes}));
   if(name==='Propuesta sellada'&&r.cumulative?.length){
    const a=r.cumulative,dates=a.map(r=>r.maturity_date),q=a.filter(r=>Number.isFinite(r.qlike_gain)),
     coverage=lineChart([{name:'Excepciones acumuladas',color:'#ffab00',values:a.map(r=>r.exceptions/r.observations)},
      {name:'Referencia 5%',color:'#8f9aa3',dashed:true,values:a.map(()=>.05)}],dates,{height:190,percent:true,area:false,label:'Excepciones VaR95 acumuladas'}),
     qlike=q.length?lineChart([{name:'QLIKE EWMA menos núcleo',color:'#4cc9a6',values:q.map(r=>r.qlike_gain)}],q.map(r=>r.maturity_date),
      {height:190,area:false,label:'Ganancia QLIKE acumulada frente a EWMA'}):'Sin QLIKE comparable';
    plots.push(template('validation-review-plots',{horizon:h,coverage,qlike}));
   }
  }
 }
 const current=usable?report.signals?.cohorts?.[report.signals.current_cohort]:null;
 const signalMature=current?Object.entries(current.horizons).map(([h,r])=>`${h}: ${r.mature_origins}`).join(' · '):'Sin emisión de la cohorte actual';
 const rejections=usable?(report.monthly_review?.rejections||[]):[];
 return template('validation-review',{tone:status.tone,label:status.label,message:status.message,
  cut:usable?dateLabel(report.price_cut):'No comprobado',
  kernelSeals:usable?report.kernel?.sealed??'Sin dato':'Sin dato',
  signalSeals:usable?report.signals?.sealed??'Sin dato':'Sin dato',signalMature,
  review:usable?report.monthly_review?.month||'Pendiente':'Pendiente',
  reviewSummary:report?.monthly_review?.tests?.some(t=>t.p_value!==null)
   ?`${rejections.length} RECHAZOS EN ${report.monthly_review.tests.filter(t=>t.p_value!==null).length} PRUEBAS`
   :'SIN PRUEBAS EVALUABLES',rows:rows.join(''),plots:plots.join('')||'Todavía no hay resultados maduros para dibujar curvas.',
  issueText:usable?(report.issues||[]).map(i=>`${i.code}${i.origin?' · '+i.origin:''}${i.symbol?' · '+i.symbol:''}`).join('; '):'Seguimiento no comprobado',
  rejectionText:rejections.map(r=>`${r.series} · ${r.kind} · p ajustado ${fmt(r.holm_p,6)}`).join('; ')||'Ningún rechazo asignado; no equivale a validación.'});
}
